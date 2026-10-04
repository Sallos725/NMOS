"""Google Vertex AI service-account keys for the extraction LLM (ADR 0022).

Vertex's OpenAI-compatible endpoint takes a Bearer OAuth access token that expires after an hour, not
a fixed API key. When the configured LLM key is a service-account JSON key, the sidecar exchanges it
for access tokens itself and refreshes them before they expire.
"""

from __future__ import annotations

import hashlib
import json
import re
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


# Vertex's OpenAI-compatible endpoint, global (`aiplatform…`) or regional (`us-central1-aiplatform…`).
_ENDPOINT = re.compile(r"https://((?:[a-z0-9-]+-)?aiplatform\.googleapis\.com)/v1(?:beta1)?/projects/([^/]+)"
                       r"/locations/[^/]+/endpoints/openapi/?")
# A Model Garden card with deploy actions is a deploy-it-yourself model, not one Vertex serves by name.
_DEPLOY_ACTIONS = ("deploy", "multiDeployVertex", "deployGke")


def catalog_target(url: str) -> tuple[str, str] | None:
    """(host, project) when `url` is a Vertex OpenAI-compatible endpoint, else None."""
    match = _ENDPOINT.fullmatch(url.strip())
    return (match.group(1), match.group(2)) if match else None


def list_models(info: dict[str, Any], url: str, client: httpx.Client | None = None) -> list[str]:
    """The Gemini chat models Vertex serves, named as the OpenAI-compatible endpoint takes them (`google/…`).

    That endpoint has no `/models`; the list comes from the publisher-model catalog on the endpoint's own host
    (ADR 0022 amendment 1). Raises VertexAuthError, or httpx.HTTPError with Google's message on a refusal."""
    target = catalog_target(url)
    if target is None:
        raise VertexAuthError("not a Vertex AI OpenAI-compatible endpoint")
    host, project = target
    headers = {"Authorization": f"Bearer {access_token(info, client)}", "x-goog-user-project": project}
    get = client.get if client is not None else httpx.get
    rows: list[dict[str, Any]] = []
    page: str | None = None
    for _ in range(20):
        params: dict[str, Any] = {"pageSize": 100, **({"pageToken": page} if page else {})}
        res = get(f"https://{host}/v1beta1/publishers/google/models", headers=headers, params=params, timeout=15)
        if res.status_code != 200:
            raise httpx.HTTPStatusError(f"Vertex model catalog: HTTP {res.status_code}: {_google_message(res)}",
                                        request=res.request, response=res)
        body = res.json()
        rows += body.get("publisherModels") or []
        page = body.get("nextPageToken")
        if not page:
            break
    names = set()
    for row in rows:
        name = str(row.get("name", "")).rsplit("/", 1)[-1]
        actions = row.get("supportedActions") or {}
        if (name.startswith("gemini") and "embedding" not in name and row.get("launchStage") != "DEPRECATED"
                and not any(a in actions for a in _DEPLOY_ACTIONS)):
            names.add(f"google/{name}")
    return sorted(names)


def _google_message(res: httpx.Response) -> str:
    try:
        return str(res.json()["error"]["message"])[:300]
    except (ValueError, KeyError, TypeError):
        return res.text[:300]
