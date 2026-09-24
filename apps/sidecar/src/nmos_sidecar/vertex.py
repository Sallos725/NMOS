"""Google Vertex AI service-account keys for the extraction LLM (ADR 0022).

Vertex's OpenAI-compatible endpoint takes a Bearer OAuth access token that expires after an hour, not
a fixed API key. When the configured LLM key is a service-account JSON key, the sidecar exchanges it
for access tokens itself and refreshes them before they expire.
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

import httpx
from google.auth import exceptions as gexc
from google.auth import transport
from google.oauth2 import service_account

SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_REQUIRED = ("client_email", "private_key", "token_uri")


class VertexAuthError(RuntimeError):
    pass


def service_account_info(api_key: str) -> dict[str, Any] | None:
    """The parsed key when `api_key` is a service-account JSON key, None for a plain API key."""
    text = api_key.strip()
    if not text.startswith("{"):
        return None
    try:
        info = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VertexAuthError(f"the key looks like JSON but is not valid JSON ({exc.msg})") from None
    if not isinstance(info, dict) or info.get("type") != "service_account":
        raise VertexAuthError('a JSON key must be a Google service-account key ("type": "service_account")')
    missing = [k for k in _REQUIRED if not info.get(k)]
    if missing:
        raise VertexAuthError(f"service-account key is missing {', '.join(missing)}")
    return info


def check_key(api_key: str) -> None:
    """Raise VertexAuthError when `api_key` is JSON but not a usable service-account key."""
    info = service_account_info(api_key)
    if info is not None:
        _credentials(info)


class _HttpxRequest(transport.Request):
    """google-auth transport over httpx (google-auth's own transports need requests or urllib3)."""

    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        try:
            if self.client is not None:
                res = self.client.request(method, url, content=body, headers=headers, timeout=timeout or 15)
            else:
                res = httpx.request(method, url, content=body, headers=headers, timeout=timeout or 15)
        except httpx.HTTPError as exc:
            raise gexc.TransportError(str(exc)) from exc
        return _Response(res)


class _Response(transport.Response):
    def __init__(self, res: httpx.Response):
        self._res = res

    @property
    def status(self) -> int:
        return self._res.status_code

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._res.headers)

    @property
    def data(self) -> bytes:
        return self._res.content


def _credentials(info: dict[str, Any]) -> service_account.Credentials:
    try:
        return service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])
    except (ValueError, TypeError) as exc:
        raise VertexAuthError(f"service-account key is unusable: {exc}") from None


_lock = threading.Lock()
_cache: dict[str, service_account.Credentials] = {}


def access_token(info: dict[str, Any], client: httpx.Client | None = None) -> str:
    """A valid access token for the key, minted on first use and refreshed shortly before expiry."""
    fp = hashlib.sha256(json.dumps(info, sort_keys=True).encode()).hexdigest()
    with _lock:
        creds = _cache.get(fp)
        if creds is None:
            if len(_cache) >= 8:
                _cache.clear()
            creds = _cache[fp] = _credentials(info)
        if not creds.valid:
            try:
                creds.refresh(_HttpxRequest(client))
            except gexc.GoogleAuthError as exc:
                raise VertexAuthError(f"service-account token exchange failed: {exc}") from None
        return str(creds.token)
