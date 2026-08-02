from __future__ import annotations

from knowagent.common.errors import FeatureDisabledError


class DisabledIdentityProvider:
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def authorization_url(self, redirect_uri: str) -> str:
        del redirect_uri
        raise FeatureDisabledError(f"SSO provider: {self._name}")

    def resolve_callback(self, query: dict[str, str]) -> tuple[str, str]:
        del query
        raise FeatureDisabledError(f"SSO provider: {self._name}")
