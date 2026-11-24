"""PHASE-60 S6 (ADR 0085): the panel's memory screen and person sheet hand the carried lines over (`d["carry"]`).

Tested through the panel routes: `views.memory` / `views.person` and `inspector.with_participants` are wrapped to
see the data the routes build and the view it was built from. Stub extractor only; synthetic names 세라, 카이토,
하나, 유나, 도현, 유찬."""

from __future__ import annotations

import json
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from conftest import make_client
from nmos_sidecar import inspector, views
from simchat import SimChat
from test_extraction import drain as drain_extract
from test_generations import conv_id
from test_phase60_carry_take import ON, _build_source_chat, _fact, _stub_extract
from test_sidecar_integration import sync

SOURCE_LABELS = {"character_name": "세라", "chat_name": "항구의 밤", "persona_name": "도현"}
TARGET_TURN_0 = "세라와 카이토는 아침 항구 광장에 도착했다."
WHEN = "4월 11일"


def _stub_both(system: str, user: str) -> tuple[dict, str, dict]:
    ans, raw, used = _stub_extract(system, user)
    target = user.split("TARGET turn", 1)[-1]
    if TARGET_TURN_0 in target:
        rows = list(ans.get("assertions") or [])
        rows += [
            _fact("세라", "located_in", None, "항구 광장", "place", evidence="항구 광장에 도착했다"),
            _fact("카이토", "located_in", None, "항구 광장", "place", evidence="항구 광장에 도착했다"),
        ]
        return {"assertions": rows}, raw, used
    return ans, raw, used


def _setup(c, migrated: str) -> tuple[str, str]:
    src_sim = _build_source_chat(4)
    sync(c, src_sim, **SOURCE_LABELS)
    tgt_sim = SimChat("tgt-data-chat")
    tgt_sim.user("새 이야기를 시작한다.")
    tgt_sim.reply(TARGET_TURN_0)
    tgt_sim.user("둘러보자.")
    sync(c, tgt_sim, character_name="세라", chat_name="새 이야기", persona_name="유찬")
    drain_extract(migrated, _stub_both)
    return conv_id(c, src_sim), conv_id(c, tgt_sim)


class Seen:
    """The last data each panel screen was built from, and the last view `with_participants` handed on."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.memory: dict[str, Any] | None = None
        self.person: dict[str, Any] | None = None
        self.view: dict[str, Any] | None = None
        real_memory, real_person, real_with = views.memory, views.person, inspector.with_participants

        def memory(d: dict[str, Any], *args: Any, **kw: Any) -> str:
            self.memory = d
            return real_memory(d, *args, **kw)

        def person(d: dict[str, Any], *args: Any, **kw: Any) -> str:
            self.person = d
            return real_person(d, *args, **kw)

        def with_participants(view: dict[str, Any]) -> dict[str, Any]:
            self.view = real_with(view)
            return self.view

        monkeypatch.setattr(views, "memory", memory)
        monkeypatch.setattr(views, "person", person)
        monkeypatch.setattr(inspector, "with_participants", with_participants)


def _memory(c, seen: Seen, tgt: str) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    res = c.get(f"/v1/views/c/{tgt}/memory")
    assert res.status_code == 200, res.text
    assert seen.memory is not None and seen.view is not None
    return seen.memory, seen.view, res.content


def _person(c, seen: Seen, tgt: str, eid: str) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    res = c.get(f"/v1/views/c/{tgt}/person/{eid}")
    assert res.status_code == 200, res.text
    assert seen.person is not None and seen.view is not None
    return seen.person, seen.view, res.content


def _entity_id(c, tgt: str, name: str) -> str:
    found = [e for e in c.get(f"/v1/conversations/{tgt}/entities").json()
             if e.get("type") == "character" and name in [e.get("name"), *(e.get("names") or [])]]
    assert len(found) == 1, found
    return str(found[0]["id"])


def _json(d: dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False, default=str)


def test_continue_link_lists_carried_facts_then_carried_open_threads(
    migrated: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = Seen(monkeypatch)
    with make_client(migrated, **ON) as c:
        src, tgt = _setup(c, migrated)
        made = c.post(f"/v1/conversations/{tgt}/carry",
                      json={"source_conversation_id": src, "mode": "continue"}).json()["link"]
        link_id = made["id"]
        got = c.get(f"/v1/conversations/{tgt}/carry").json()["in_force"]

        d, view, _ = _memory(c, seen, tgt)
        carry = d["carry"]
        json.dumps(carry)  # plain JSON as it is, no encoder help
        assert carry["source"] == {"id": src, "character": "세라", "chat": "항구의 밤"}
        assert carry["mode"] == "continue" and carry["names"] == []
        assert carry["created_at"] == got["created_at"]

        facts = [f for f in view["facts"] if f.get("carried")]
        threads = [t for t in view["threads"] if t["status"] == "open" and t.get("carried")]
        assert facts and threads
        lines = carry["lines"]
        assert [x["id"] for x in lines] == [f["id"] for f in facts] + [t["id"] for t in threads]
        assert [x["kind"] for x in lines] == ["fact"] * len(facts) + ["thread"] * len(threads)
        for x in lines:
            assert x["carried"] == link_id
            assert x["carried_from"]["conversation"] == src
            assert isinstance(x["carried_from"]["turn"], int)
            for k in ("predicate", "subject", "object", "value", "knowledge", "known_by", "hidden_from"):
                assert k in x
            assert "when_happened" not in x
        assert any(x["subject"] == "하나" and x["predicate"] == "located_in" and x["object"] == "항구 시장"
                   for x in lines)
        # The target's own fact superseded the carried place of 세라; nothing of the target's own is listed.
        assert not any(x["subject"] == "세라" and x["predicate"] == "located_in" for x in lines)

        (promise,) = [x for x in lines if x["kind"] == "thread"]
        src_thread = next(t for t in c.get(f"/v1/conversations/{src}/threads").json() if "등대 열쇠" in t["text"])
        assert promise["predicate"] == "promised"
        assert (promise["subject"], promise["object"]) == ("세라", "카이토")
        assert promise["value"] == promise["text"] == src_thread["text"]
        assert promise["carried_from"]["turn"] == src_thread["turn"]

        # A person's sheet lists only the lines that person is in (subject, object or a participant; by / to).
        d_hana, _, _ = _person(c, seen, tgt, _entity_id(c, tgt, "하나"))
        assert d_hana["carry"]["mode"] == "continue" and d_hana["carry"]["source"] == carry["source"]
        mine = [x for x in lines if "하나" in (x["subject"], x["object"])]
        assert mine and [x["id"] for x in d_hana["carry"]["lines"]] == [x["id"] for x in mine]
        kaito = _entity_id(c, tgt, "카이토")
        d_kaito, _, _ = _person(c, seen, tgt, kaito)
        assert [x["id"] for x in d_kaito["carry"]["lines"]] == [
            x["id"] for x in lines if "카이토" in (x["subject"], x["object"])]
        assert any(x["kind"] == "thread" for x in d_kaito["carry"]["lines"])


def test_regression_link_lists_its_rows_and_only_a_named_person_sheet_has_them(
    migrated: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = Seen(monkeypatch)
    with make_client(migrated, **ON) as c:
        src, tgt = _setup(c, migrated)
        made = c.post(f"/v1/conversations/{tgt}/carry",
                      json={"source_conversation_id": src, "mode": "regression", "entity_names": ["세라"]})
        assert made.status_code == 200, made.text
        link_id = made.json()["link"]["id"]

        d, view, _ = _memory(c, seen, tgt)
        carry = d["carry"]
        json.dumps(carry)
        assert carry["mode"] == "regression" and carry["names"] == ["세라"]
        assert view["regression"]
        lines = carry["lines"]
        assert [x["id"] for x in lines] == [x["id"] for x in view["regression"]]
        assert [x["kind"] for x in lines] == [x["line"] for x in view["regression"]]
        assert {"fact", "thread"} <= {x["kind"] for x in lines}
        for x in lines:
            assert x["carried"] == link_id and x["carried_from"]["conversation"] == src
            assert x["knowledge"] == "limited" and x["known_by"] == ["세라"]
        thread = next(x for x in lines if x["kind"] == "thread")
        assert thread["predicate"] == "promised" and (thread["subject"], thread["object"]) == ("세라", "카이토")
        assert thread["value"] == thread["text"]

        sera = _entity_id(c, tgt, "세라")
        d_sera, _, _ = _person(c, seen, tgt, sera)
        assert d_sera["carry"]["mode"] == "regression"
        assert [x["id"] for x in d_sera["carry"]["lines"]] == [x["id"] for x in lines]
        assert all("세라" in (x["subject"], x["object"]) for x in d_sera["carry"]["lines"])

        kaito = _entity_id(c, tgt, "카이토")
        d_kaito, _, _ = _person(c, seen, tgt, kaito)
        assert "carry" in d_kaito and d_kaito["carry"]["lines"] == []
        assert d_kaito["carry"]["names"] == ["세라"]


def test_unlinked_chat_data_is_byte_identical_before_linking_and_after_unlinking(
    migrated: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = Seen(monkeypatch)
    with make_client(migrated, **ON) as c:
        src, tgt = _setup(c, migrated)
        sera = _entity_id(c, tgt, "세라")

        mem_before, _, mem_html = _memory(c, seen, tgt)
        person_before, _, person_html = _person(c, seen, tgt, sera)
        assert "carry" not in mem_before and "carry" not in person_before
        mem_before, person_before = _json(mem_before), _json(person_before)

        for body in ({"source_conversation_id": src, "mode": "continue"},
                     {"source_conversation_id": src, "mode": "regression", "entity_names": ["세라"]}):
            assert c.post(f"/v1/conversations/{tgt}/carry", json=body).status_code == 200
            assert "carry" in _memory(c, seen, tgt)[0]
            assert "carry" in _person(c, seen, tgt, _entity_id(c, tgt, "세라"))[0]
            assert c.delete(f"/v1/conversations/{tgt}/carry").status_code == 200

            mem_after, _, mem_html_after = _memory(c, seen, tgt)
            person_after, _, person_html_after = _person(c, seen, tgt, sera)
            assert _json(mem_after) == mem_before and mem_html_after == mem_html
            assert _json(person_after) == person_before and person_html_after == person_html


def test_when_happened_passes_through_a_carried_line(migrated: str, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = Seen(monkeypatch)
    with make_client(migrated, **ON) as c:
        src, tgt = _setup(c, migrated)
        assert c.post(f"/v1/conversations/{tgt}/carry",
                      json={"source_conversation_id": src, "mode": "continue"}).status_code == 200
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            link = conn.execute("SELECT id, snapshot FROM conversation_carry WHERE removed_at IS NULL").fetchone()
            snap = link["snapshot"]
            i = next(i for i, f in enumerate(snap["facts"])
                     if f["subject"] == "하나" and f["predicate"] == "located_in")
            snap["facts"][i]["when_happened"] = WHEN
            conn.execute("UPDATE conversation_carry SET snapshot = %s WHERE id = %s", (Jsonb(snap), link["id"]))
            assertion = snap["facts"][i]["from"]["assertion"]

        lines = _memory(c, seen, tgt)[0]["carry"]["lines"]
        (line,) = [x for x in lines if x["carried_from"]["assertion"] == assertion and x["kind"] == "fact"]
        assert line["when_happened"] == WHEN
        assert all("when_happened" not in x for x in lines if x is not line)
