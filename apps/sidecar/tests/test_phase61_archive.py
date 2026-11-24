"""PHASE-61 A5: the extra request body and the temperature switch are archived and restored like any other setting;
the archive's credential scan is unchanged (no key is ever accepted into the body). Synthetic names only."""

from __future__ import annotations

from conftest import make_client
from nmos_sidecar import archive, runtime
from test_archive import read, story
from test_restore import export_to, tables
from test_generations import LLM
from test_sidecar_integration import sync

BODY = {"reasoning": {"effort": "low"}, "provider": {"order": ["a", "b"]}, "max_tokens": 900}


def test_both_are_archived_settings_and_the_secrets_are_the_same_three():
    assert {"llm_extra_body", "llm_no_temperature"} <= set(archive.SETTINGS)
    assert runtime.SECRET == {"llm_api_key", "embed_api_key", "rerank_api_key"}
    assert not {"llm_extra_body", "llm_no_temperature"} & set(archive.URL_SETTINGS)


def test_an_archive_holds_both_and_a_restore_brings_them_back(migrated, database_url_factory, tmp_path):
    with make_client(migrated, **LLM) as c:
        assert c.put("/v1/config", json={"llm_extra_body": BODY, "llm_no_temperature": True,
                                         "llm_api_key": "sk-made-up-0123456789"}).status_code == 200
        sync(c, story())
    source = export_to(tmp_path, migrated, "a")
    _, rows, raw = read(source.read_bytes())
    saved = {r["key"]: r["value"] for r in rows["app_config"]}
    assert saved["llm_extra_body"] == BODY and saved["llm_no_temperature"] is True
    assert "llm_api_key" not in saved and not any(b"sk-made-up" in body for body in raw.values())

    target = database_url_factory()
    archive.restore_file(target, str(source))
    with make_client(target, **LLM) as c:
        view = c.get("/v1/config").json()["llm"]
        assert view["extra_body"] == BODY and view["no_temperature"] is True
    assert tables(export_to(tmp_path, target, "b")) == tables(source)


def test_at_the_defaults_an_archive_holds_neither(migrated, tmp_path):
    with make_client(migrated, **LLM) as c:
        sync(c, story())
    _, rows, _ = read(export_to(tmp_path, migrated, "a").read_bytes())
    assert not {"llm_extra_body", "llm_no_temperature"} & {r["key"] for r in rows["app_config"]}
