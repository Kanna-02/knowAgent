from __future__ import annotations

from io import BytesIO

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from knowagent.platform.object_store import ObjectStoreError, S3ObjectStore
from knowagent.platform.settings import ObjectStorageSettings


class BodyFake:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False

    def read(self) -> bytes:
        return self.content

    def close(self) -> None:
        self.closed = True


class S3ClientFake:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.body: BodyFake | None = None
        self.failure: Exception | None = None

    def upload_fileobj(self, content: BytesIO, bucket: str, key: str, **_: object) -> None:
        if self.failure:
            raise self.failure
        self.objects[(bucket, key)] = content.read()

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, BodyFake]:
        if self.failure:
            raise self.failure
        self.body = BodyFake(self.objects[(Bucket, Key)])
        return {"Body": self.body}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        if self.failure:
            raise self.failure
        self.objects.pop((Bucket, Key), None)


def test_s3_store_put_get_and_delete_use_configured_bucket() -> None:
    client = S3ClientFake()
    store = S3ObjectStore(client=client, bucket="knowagent-test")

    store.put(
        key="documents/source.md",
        content=BytesIO(b"content"),
        content_type="text/markdown",
        content_length=7,
    )
    assert store.get(key="documents/source.md") == b"content"
    assert client.body is not None and client.body.closed is True
    store.delete(key="documents/source.md")

    assert client.objects == {}


def test_s3_store_maps_connectivity_and_server_errors_as_retryable() -> None:
    client = S3ClientFake()
    store = S3ObjectStore(client=client, bucket="knowagent-test")
    client.failure = EndpointConnectionError(endpoint_url="https://storage.test")

    with pytest.raises(ObjectStoreError) as caught:
        store.get(key="missing")
    assert caught.value.retryable is True

    client.failure = ClientError(
        {"Error": {"Code": "SlowDown", "Message": "retry"}, "ResponseMetadata": {}},
        "GetObject",
    )
    with pytest.raises(ObjectStoreError) as server_error:
        store.get(key="missing")
    assert server_error.value.retryable is True


def test_s3_store_maps_permission_errors_as_permanent_without_leaking_details() -> None:
    client = S3ClientFake()
    store = S3ObjectStore(client=client, bucket="knowagent-test")
    client.failure = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "secret detail"}},
        "PutObject",
    )

    with pytest.raises(ObjectStoreError) as caught:
        store.put(
            key="documents/source.md",
            content=BytesIO(b"content"),
            content_type="text/markdown",
            content_length=7,
        )

    assert caught.value.retryable is False
    assert "secret detail" not in str(caught.value)


def test_s3_store_builds_client_with_configured_timeouts_and_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = S3ClientFake()
    captured: dict[str, object] = {}

    def create_client(service: str, **options: object) -> S3ClientFake:
        captured["service"] = service
        captured.update(options)
        return client

    monkeypatch.setattr("knowagent.platform.object_store.boto3.client", create_client)
    settings = ObjectStorageSettings(
        endpoint_url="https://storage.test",
        bucket="documents",
        region="cn-test-1",
        access_key="access",
        secret_key="secret",
        connect_timeout_seconds=4,
        read_timeout_seconds=20,
        sdk_max_attempts=5,
    )

    store = S3ObjectStore.from_settings(settings)
    store.put(
        key="source.md",
        content=BytesIO(b"data"),
        content_type="text/markdown",
        content_length=4,
    )

    config = captured["config"]
    assert captured["service"] == "s3"
    assert captured["endpoint_url"] == "https://storage.test"
    assert config.connect_timeout == 4  # type: ignore[union-attr]
    assert config.read_timeout == 20  # type: ignore[union-attr]
    assert config.retries["max_attempts"] == 5  # type: ignore[union-attr,index]


def test_s3_store_rejects_empty_bucket_and_maps_credentials_or_unknown_errors() -> None:
    with pytest.raises(ValueError, match="bucket"):
        S3ObjectStore(client=S3ClientFake(), bucket="")

    client = S3ClientFake()
    store = S3ObjectStore(client=client, bucket="documents")
    client.failure = NoCredentialsError()
    with pytest.raises(ObjectStoreError) as credentials:
        store.delete(key="source.md")
    assert credentials.value.retryable is False
    assert "凭据" in str(credentials.value)

    client.failure = RuntimeError("unexpected secret")
    with pytest.raises(ObjectStoreError) as unknown:
        store.delete(key="source.md")
    assert unknown.value.retryable is False
    assert "unexpected secret" not in str(unknown.value)
