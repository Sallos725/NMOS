"""Phase 39 amendment 2: inactive templates and explicit, isolated card application."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import runtime
from nmos_sidecar.parsers import compile_rules
from simchat import SimChat
from test_sidecar_integration import sync


RULE = {"id": "hp", "kind": "regex", "pattern": r"HP: (?P<value>\d+)", "key": "HP"}
PRESETS = [{"name": "HP bar", "rules": [RULE]}]


def apply(client, card, rules=None):
    response = client.put("/v1/parsers/card", json={"card": card, "rules": [RULE] if rules is None else rules})
    assert response.status_code == 200, response.text
    return response.json()


def chat(client, card, hp):
    value = SimChat()
    value.user("Start")
    value.reply(f"HP: {hp}")
    value.user("Continue")
    cid = sync(client, value, character_name=card)["conversation_id"]
    return cid


def rows(url, table):
    with psycopg.connect(url, row_factory=dict_row) as conn:
        return conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()


def test_bound_versions_unchanged_and_legacy_unbound_version_invalidated():
    bound = {"rules": [{**RULE, "card": "A"}]}
    old = hashlib.sha256(json.dumps(bound, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    assert compile_rules(bound).version == old
    legacy = {"rules": [RULE, {**RULE, "id": "bound", "card": "B"}]}
    old = hashlib.sha256(json.dumps(legacy, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    active = compile_rules(legacy)
    assert active.errors and len(active.rules) == 1 and active.version != old
    assert not compile_rules({"rules": [RULE]}).rules


def test_blank_default_presets_inactive_and_validation_atomic(client, migrated):
    cfg = client.get("/v1/config").json()["parsers"]
    assert cfg["spec"] == {"rules": []} and cfg["presets"] == [] and cfg["active_rules"] == 0
    apply(client, "A")
    chat(client, "A", 9)
    before = {t: rows(migrated, t) for t in ("state_observation", "source_revision", "job")}
    active = client.get("/v1/config").json()["parsers"]["spec"]
    saved = client.put("/v1/config", json={"parser_presets": PRESETS})
    assert saved.status_code == 200, saved.text
    assert saved.json()["parsers"]["presets"] == PRESETS
    assert saved.json()["parsers"]["spec"] == active
    assert before == {t: rows(migrated, t) for t in before}
    for bad in [None, {}, PRESETS * 2, [{"name": "", "rules": [RULE]}],
                [{"name": "x", "rules": [{**RULE, "pattern": "("}]}], PRESETS * 51,
                [{"name": "x", "rules": [{**RULE, "prefix": "x" * 300000}]}]]:
        assert client.put("/v1/config", json={"parser_presets": bad}).status_code == 422
        assert client.get("/v1/config").json()["parsers"]["presets"] == PRESETS
    assert client.put("/v1/config", json={"parsers": {"rules": [RULE]}}).status_code == 422
    for body in [{"rules": [RULE]}, {"card": " ", "rules": [RULE]}, {"card": "A", "rules": ""},
                 {"card": " " * 200 + "A", "rules": [RULE]}]:
        assert client.put("/v1/parsers/card", json=body).status_code == 422
    assert before == {t: rows(migrated, t) for t in before}


def test_target_apply_preserves_other_card_and_same_card_chats(client, migrated):
    apply(client, "A")
    apply(client, "B")
    a, a2, b = chat(client, "A", 9), chat(client, "A", 7), chat(client, "B", 4)
    before = rows(migrated, "source_revision")
    state = lambda cid: client.get(f"/v1/conversations/{cid}/state").json()
    assert [state(cid)[0]["value"] for cid in (a, a2, b)] == ["9", "7", "4"]
    old_b = state(b)
    config = apply(client, "A", [])
    assert state(a) == [] and state(a2) == [] and state(b) == old_b
    assert [r["card"] for r in config["parsers"]["spec"]["rules"]] == ["B"]
    assert rows(migrated, "source_revision") == before


def test_concurrent_card_apply_keeps_both_and_ids_are_stable(client):
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda card: apply(client, card), ("A", "B")))
    initial = client.get("/v1/config").json()["parsers"]["spec"]["rules"]
    assert {r["card"] for r in initial} == {"A", "B"}
    assert len({r["id"] for r in initial}) == 2
    before = next(r for r in initial if r["card"] == "A")
    after = apply(client, "A", [before])["parsers"]["spec"]["rules"]
    assert next(r for r in after if r["card"] == "A") == before


@pytest.mark.parametrize("failure", ["rebuild", "save", "construct"])
@pytest.mark.parametrize("route", ["card", "config"])
def test_failed_apply_keeps_runtime_config_and_derived_state(client, migrated, monkeypatch, failure, route):
    import nmos_sidecar.api as api
    apply(client, "A")
    chat(client, "A", 8)
    config = client.get("/v1/config").json()
    before = {t: rows(migrated, t) for t in ("app_config", "state_observation", "source_revision")}
    original_save = runtime.save
    def fail(*args):
        if failure == "save":
            original_save(*args)  # failure after the database write still rolls its transaction back
        raise RuntimeError("simulated apply failure")
    if failure == "rebuild":
        monkeypatch.setattr(api, "rebuild_state", fail)
    else:
        monkeypatch.setattr(runtime, "save" if failure == "save" else "ruleset", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        if route == "card":
            client.put("/v1/parsers/card", json={"card": "A", "rules": []})
        else:
            client.put("/v1/config", json={"parsers": {"rules": []}})
    assert client.get("/v1/config").json() == config
    assert before == {t: rows(migrated, t) for t in before}


def test_file_legacy_visible_and_presets_survive_restart(migrated, tmp_path):
    path = tmp_path / "parsers.json"
    spec = {"rules": [RULE, {**RULE, "id": "bound", "card": "B"}]}
    path.write_text(json.dumps(spec), encoding="utf-8")
    with make_client(migrated, parsers_file=str(path)) as client:
        config = client.get("/v1/config").json()["parsers"]
        assert config["source"] == "file" and config["spec"] == spec
        assert config["active_rules"] == 1 and config["errors"]
        assert client.put("/v1/config", json={"parser_presets": PRESETS}).status_code == 200
        apply(client, "A")
    with make_client(migrated, parsers_file=str(path)) as client:
        config = client.get("/v1/config").json()["parsers"]
        assert config["presets"] == PRESETS
        assert {r.get("card") for r in config["spec"]["rules"]} == {None, "A", "B"}
        assert config["active_rules"] == 2 and config["errors"]
        assert client.put("/v1/config", json={"parser_presets": []}).json()["parsers"]["presets"] == []


def test_presets_and_bound_state_survive_archive_restore(migrated, database_url_factory, tmp_path):
    from nmos_sidecar.archive import restore_file

    with make_client(migrated) as client:
        apply(client, "A")
        cid = chat(client, "A", 6)
        assert client.put("/v1/config", json={"parser_presets": PRESETS}).status_code == 200
        config = client.get("/v1/config").json()["parsers"]
        state = client.get(f"/v1/conversations/{cid}/state").json()
        path = tmp_path / "status.nmos.zip"
        path.write_bytes(client.get("/v1/archive").content)
    target = database_url_factory()
    restore_file(target, str(path))
    with make_client(target) as client:
        assert client.get("/v1/config").json()["parsers"] == config
        assert client.get(f"/v1/conversations/{cid}/state").json() == state


def test_concurrent_separate_apps_merge_latest_saved_document(migrated):
    with make_client(migrated) as first, make_client(migrated) as second:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(apply, first, "A"), pool.submit(apply, second, "B")]
            for future in futures:
                future.result()
    with make_client(migrated) as client:
        rules = client.get("/v1/config").json()["parsers"]["spec"]["rules"]
        assert {rule["card"] for rule in rules} == {"A", "B"}


def test_preset_save_does_not_reload_changed_parser_file(migrated, tmp_path):
    path = tmp_path / "parsers.json"
    path.write_text(json.dumps({"rules": [{**RULE, "card": "A"}]}), encoding="utf-8")
    with make_client(migrated, parsers_file=str(path)) as client:
        path.write_text(json.dumps({"rules": []}), encoding="utf-8")
        response = client.put("/v1/config", json={"parser_presets": PRESETS})
        assert response.status_code == 200 and response.json()["parsers"]["active_rules"] == 1
        cid = chat(client, "A", 3)
        assert client.get(f"/v1/conversations/{cid}/state").json()[0]["value"] == "3"


def test_invalid_existing_file_cannot_be_silently_overwritten(migrated, tmp_path):
    path = tmp_path / "parsers.json"
    path.write_text("{bad JSON", encoding="utf-8")
    with make_client(migrated, parsers_file=str(path)) as client:
        response = client.put("/v1/parsers/card", json={"card": "A", "rules": [RULE]})
        assert response.status_code == 422
        assert rows(migrated, "app_config") == []
        assert path.read_text(encoding="utf-8") == "{bad JSON"


def test_restart_removes_old_global_observations_without_rewriting_sources(migrated):
    from nmos_sidecar.state import rebuild_state

    legacy = {"rules": [RULE, {**RULE, "id": "bound", "card": "B"}]}
    with make_client(migrated) as client:
        a, b = chat(client, "A", 9), chat(client, "B", 4)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        runtime.save(conn, {"parsers": legacy})
        # Simulate the previous compiler's accepted global rules and version, including their derived rows.
        rebuild_state(conn, compile_rules(legacy, template=True))
    sources = rows(migrated, "source_revision")
    assert len(rows(migrated, "state_observation")) == 2  # the last rule wins for one key in each message
    with make_client(migrated) as client:
        assert client.get(f"/v1/conversations/{a}/state").json() == []
        assert client.get(f"/v1/conversations/{b}/state").json()[0]["value"] == "4"
        assert client.get("/v1/config").json()["parsers"]["spec"] == legacy
    assert len(rows(migrated, "state_observation")) == 1
    assert rows(migrated, "source_revision") == sources
