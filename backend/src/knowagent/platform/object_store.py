from __future__ import annotations

from collections.abc import Mapping
from typing import BinaryIO, Protocol, cast

import boto3  # type: ignore[import-untyped]
from boto3.s3.transfer import TransferConfig  # type: ignore[import-untyped]
from botocore.config import Config as BotoCoreConfig  # type: ignore[import-untyped]
from botocore.exceptions import (  # type: ignore[import-untyped]
    BotoCoreError,
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    PartialCredentialsError,
    ReadTimeoutError,
)

from knowagent.platform.settings import ObjectStorageSettings


class ObjectStoreError(Exception):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class _StreamingBody(Protocol):
    def read(self) -> bytes: ...

    def close(self) -> None: ...


class _S3Client(Protocol):
    def upload_fileobj(
        self,
        fileobj: BinaryIO,
        bucket: str,
        key: str,
        *,
        ExtraArgs: Mapping[str, str],
        Config: TransferConfig,
    ) -> None: ...

    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]: ...

    def delete_object(self, *, Bucket: str, Key: str) -> object: ...


class S3ObjectStore:
    def __init__(
        self,
        *,
        client: object,
        bucket: str,
        multipart_threshold: int = 8 * 1024 * 1024,
        multipart_chunk_size: int = 8 * 1024 * 1024,
    ) -> None:
        if not bucket.strip():
            raise ValueError("bucket must not be empty")
        self._client = cast(_S3Client, client)
        self._bucket = bucket
        self._transfer_config = TransferConfig(
            multipart_threshold=multipart_threshold,
            multipart_chunksize=multipart_chunk_size,
            use_threads=True,
        )

    @classmethod
    def from_settings(cls, settings: ObjectStorageSettings) -> S3ObjectStore:
        client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            region_name=settings.region,
            aws_access_key_id=settings.access_key,
            aws_secret_access_key=settings.secret_key,
            verify=settings.verify_value,
            config=BotoCoreConfig(
                signature_version="s3v4",
                connect_timeout=settings.connect_timeout_seconds,
                read_timeout=settings.read_timeout_seconds,
                retries={"max_attempts": settings.sdk_max_attempts, "mode": "standard"},
            ),
        )
        return cls(
            client=client,
            bucket=settings.bucket,
            multipart_threshold=settings.multipart_threshold,
            multipart_chunk_size=settings.multipart_chunk_size,
        )

    def put(
        self,
        *,
        key: str,
        content: BinaryIO,
        content_type: str,
        content_length: int,
    ) -> None:
        del content_length
        try:
            self._client.upload_fileobj(
                content,
                self._bucket,
                key,
                ExtraArgs={"ContentType": content_type},
                Config=self._transfer_config,
            )
        except Exception as error:
            raise self._map_error(error) from error

    def get(self, *, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            body = cast(_StreamingBody, response["Body"])
            try:
                return body.read()
            finally:
                body.close()
        except Exception as error:
            if isinstance(error, ObjectStoreError):
                raise
            raise self._map_error(error) from error

    def delete(self, *, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as error:
            raise self._map_error(error) from error

    @staticmethod
    def _map_error(error: Exception) -> ObjectStoreError:
        if isinstance(
            error,
            (
                EndpointConnectionError,
                ConnectionClosedError,
                ConnectTimeoutError,
                ReadTimeoutError,
            ),
        ):
            return ObjectStoreError("对象存储暂时不可用", retryable=True)
        if isinstance(error, ClientError):
            code = str(error.response.get("Error", {}).get("Code", ""))
            status = int(error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
            retryable = code in {
                "SlowDown",
                "RequestTimeout",
                "InternalError",
                "ServiceUnavailable",
                "Throttling",
            } or status in {429, 500, 502, 503, 504}
            return ObjectStoreError("对象存储请求失败", retryable=retryable)
        if isinstance(error, (NoCredentialsError, PartialCredentialsError)):
            return ObjectStoreError("对象存储凭据不可用", retryable=False)
        if isinstance(error, BotoCoreError):
            return ObjectStoreError("对象存储客户端失败", retryable=False)
        return ObjectStoreError("对象存储操作失败", retryable=False)
