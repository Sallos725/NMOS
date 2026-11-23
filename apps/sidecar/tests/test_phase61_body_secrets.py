"""PHASE-61 S1 (review F2): a credential of this install pasted as a value of the extra request body is refused.

Values are not inspected by name, but a body holding one of the sidecar's own credentials (a saved key, the
environment's key, the auth token: the list the archive's credential scan uses) would be stored in every generation
spec, shown by `/v1/config`, and would then refuse every later archive. The save, the preview and the settings test
refuse it, naming a key path, never the value; saving a key the stored body already holds is refused too. No model is
called here: the settings test's address answers nothing."""

from __future__ import annotations

import pytest

from conftest import TOKEN, make_client
from nmos_sidecar import config

SAVED = "sk-or-v1-saved0123456789abcdef"  # made-up keys of this install: never echoed anywhere
ENV_KEY = "sk-env-0123456789abcdef"
LOOKALIKE = "sk-or-v1-9f8e7d6c5b4a39281706f5e4d3c2b1a0"  # resembles a key, but is no credential of this install
NOWHERE = "http://127.0.0.1:9/v1"


def save_key(c, key: str = SAVED) -> None:
    assert c.put("/v1/config", json={"llm_url": "http://llm.test/v1", "llm_api_key": key}).status_code == 200


def overridden(c) -> list[str]:
    return c.get("/v1/config").json()["overridden"]


@pytest.mark.parametrize("body", [
    {"note": SAVED},
    {"provider": {"x": f"Bearer {SAVED}"}},
    {"plugins": [{"deeper": [{"y": SAVED + "-tail"}]}]},
    {"provider": {SAVED: 1}},  # as a key name: the path is the object holding it
])
def test_a_saved_key_as_a_value_is_refused_on_save_and_preview(client, body):
    save_key(client)
    before = overridden(client)
    for send, route in ((client.put, "/v1/config"), (client.post, "/v1/config/preview")):
        res = send(route, json={"llm_extra_body": body})
        assert res.status_code == 422, (route, res.text)
        (detail,) = res.json()["detail"]
        assert detail.startswith("llm_extra_body: ") and "credentials" in detail and "key field" in detail
        assert SAVED not in res.text
    assert overridden(client) == before and client.get("/v1/config").json()["llm"]["extra_body"] == {}


def test_the_refusal_names_the_path(client):
    save_key(client)
    res = client.put("/v1/config", json={"llm_extra_body": {"provider": {"x": SAVED}}})
    assert "provider.x" in res.json()["detail"][0]
    res = client.put("/v1/config", json={"llm_extra_body": {"provider": {SAVED: 1}}})
    assert "provider" in res.json()["detail"][0] and SAVED not in res.text


def test_a_key_and_a_body_holding_it_in_one_save_are_refused(client):
    res = client.put("/v1/config", json={"llm_api_key": SAVED, "llm_extra_body": {"note": SAVED}})
    assert res.status_code == 422 and res.json()["detail"][0].startswith("llm_extra_body: ")
    assert SAVED not in res.text and overridden(client) == []


def test_the_environments_key_and_the_auth_token_count_too(migrated):
    with make_client(migrated, llm_api_key=ENV_KEY) as c:
        for value in (ENV_KEY, TOKEN):
            res = c.put("/v1/config", json={"llm_extra_body": {"note": value}})
            assert res.status_code == 422, res.text
            assert ENV_KEY not in res.text
        assert overridden(c) == []


@pytest.mark.parametrize("key", ["llm_api_key", "embed_api_key", "rerank_api_key"])
def test_saving_a_key_the_stored_body_already_holds_is_refused(client, key):
    assert client.put("/v1/config", json={"llm_extra_body": {"note": SAVED}}).status_code == 200  # no key yet
    res = client.put("/v1/config", json={key: SAVED})
    assert res.status_code == 422, res.text
    (detail,) = res.json()["detail"]
    assert detail.startswith(f"{key}: ") and "extra request body holds" in detail and "note" in detail
    assert SAVED not in res.text
    assert overridden(client) == ["llm_extra_body"]


def test_the_settings_test_refuses_it_before_any_call(client):
    save_key(client)
    res = client.post("/v1/config/test", json={"kind": "llm", "url": NOWHERE, "model": "m",
                                                "extra_body": {"provider": {"x": SAVED}}})
    assert res.status_code == 422, res.text
    (detail,) = res.json()["detail"]
    assert detail.startswith("extra_body: ") and "provider.x" in detail and SAVED not in res.text


def test_a_value_that_merely_resembles_a_key_is_accepted_and_an_archive_still_succeeds(client):
    save_key(client)
    body = {"note": LOOKALIKE, "provider": {"order": [LOOKALIKE[:20]]}}
    res = client.post("/v1/config/test", json={"kind": "llm", "url": NOWHERE, "model": "m", "extra_body": body})
    assert res.status_code == 200 and res.json()["ok"] is False  # nothing listens there: the call itself failed
    assert client.post("/v1/config/preview", json={"llm_extra_body": body}).status_code == 200
    res = client.put("/v1/config", json={"llm_extra_body": body})
    assert res.status_code == 200, res.text
    assert config.canonical_body(res.json()["llm"]["extra_body"]) == config.canonical_body(body)
    archived = client.get("/v1/archive")
    assert archived.status_code == 200, archived.text
    assert SAVED.encode() not in archived.content


def test_at_the_defaults_a_key_save_is_unchanged(client):
    save_key(client)
    assert client.put("/v1/config", json={"embed_api_key": "embed-0123456789"}).status_code == 200
