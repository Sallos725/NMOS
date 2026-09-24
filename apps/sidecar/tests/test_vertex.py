"""Vertex AI service-account keys for the extraction LLM (ADR 0022). The token endpoint is mocked; a
real Vertex call needs an owner-supplied key."""

from __future__ import annotations

import datetime as dt
import json
from urllib.parse import parse_qs

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import jwt

from nmos_sidecar import llm, vertex

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PEM = _KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption()).decode()
_PUBLIC = _KEY.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo).decode()
TOKEN_URI = "https://oauth2.googleapis.com/token"


def sa_key(project: str = "my-proj") -> str:
    return json.dumps({
        "type": "service_account", "project_id": project, "private_key_id": "k1", "private_key": _PEM,
        "client_email": f"nmos@{project}.iam.gserviceaccount.com", "client_id": "1", "token_uri": TOKEN_URI,
    }, indent=2)


class TokenServer:
    def __init__(self):
        self.assertions: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == TOKEN_URI
        form = parse_qs(request.content.decode())
        assert form["grant_type"] == ["urn:ietf:params:oauth:grant-type:jwt-bearer"]
        self.assertions.append(form["assertion"][0])
        return httpx.Response(200, json={"access_token": f"ya29.token{len(self.assertions)}", "expires_in": 3600,
                                         "token_type": "Bearer"})


@pytest.fixture(autouse=True)
def fresh_cache():
    vertex._cache.clear()
    yield
    vertex._cache.clear()


def test_plain_api_keys_are_not_service_accounts():
    assert vertex.service_account_info("sk-abc") is None
    assert vertex.service_account_info("") is None


@pytest.mark.parametrize("key, message", [
    ("{not json", "not valid JSON"),
    ('{"type": "authorized_user"}', "service-account key"),
    ('{"type": "service_account", "client_email": "a@b"}', "missing private_key, token_uri"),
])
def test_malformed_json_keys_are_named(key, message):
    with pytest.raises(vertex.VertexAuthError, match=message):
        vertex.check_key(key)


def test_unreadable_private_key_is_rejected():
    bad = json.loads(sa_key())
    bad["private_key"] = "-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n"
    with pytest.raises(vertex.VertexAuthError, match="unusable"):
        vertex.check_key(json.dumps(bad))


def test_token_is_minted_with_a_signed_assertion_cached_and_refreshed():
    server = TokenServer()
    client = httpx.Client(transport=httpx.MockTransport(server))
    info = vertex.service_account_info(sa_key())
    assert vertex.access_token(info, client) == "ya29.token1"
    claims = jwt.decode(server.assertions[0], certs=_PUBLIC, audience=TOKEN_URI)
    assert claims["iss"] == "nmos@my-proj.iam.gserviceaccount.com" and claims["scope"] == vertex.SCOPE

    assert vertex.access_token(info, client) == "ya29.token1" and len(server.assertions) == 1  # cached
    creds = next(iter(vertex._cache.values()))
    creds.expiry = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(minutes=2)
    assert vertex.access_token(info, client) == "ya29.token2"  # refreshed before it expires


def test_token_exchange_failure_is_an_llm_error(monkeypatch):
    client = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(400, json={"error": "invalid_grant", "error_description": "Invalid JWT Signature."})))
    monkeypatch.setattr(vertex, "_HttpxRequest", lambda c=None, _real=vertex._HttpxRequest: _real(client))
    with pytest.raises(llm.LLMError, match="token exchange failed.*invalid_grant"):
        llm.chat_headers(sa_key())


def test_chat_model_sends_the_access_token(monkeypatch):
    monkeypatch.setattr(vertex, "access_token", lambda info, client=None: f"ya29.for-{info['project_id']}")
    seen: dict[str, str] = {}

    def post(url, json, headers, timeout):
        seen.update(url=url, auth=headers["Authorization"])
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(llm.httpx, "post", post)
    base = "https://aiplatform.googleapis.com/v1/projects/p1/locations/global/endpoints/openapi"
    parsed, _ = llm.ChatModel(base, "google/gemini-2.5-flash", sa_key("p1")).complete_json("s", "u")
    assert parsed == {"ok": True}
    assert seen == {"url": f"{base}/chat/completions", "auth": "Bearer ya29.for-p1"}
    assert llm.chat_headers("sk-plain") == {"Authorization": "Bearer sk-plain"}


def test_config_accepts_a_service_account_key_without_echoing_it(client):
    ok = client.put("/v1/config", json={
        "llm_url": "https://aiplatform.googleapis.com/v1/projects/my-proj/locations/global/endpoints/openapi",
        "llm_model": "google/gemini-2.5-flash", "llm_api_key": sa_key()}).json()
    assert ok["llm"]["api_key_set"] is True
    assert "PRIVATE KEY" not in json.dumps(ok) and "PRIVATE KEY" not in client.get("/v1/config").text


def test_config_rejects_bad_json_keys_placeholders_and_embedding_json(client):
    bad = client.put("/v1/config", json={
        "llm_url": "https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/endpoints/openapi",
        "llm_api_key": '{"type": "authorized_user"}', "embed_api_key": sa_key()})
    detail = bad.json()["detail"]
    assert bad.status_code == 422 and len(detail) == 3
    assert any("{project}" in d for d in detail) and any("embed_api_key" in d for d in detail)
    assert client.get("/v1/config").json()["llm"]["api_key_set"] is False  # nothing was saved
