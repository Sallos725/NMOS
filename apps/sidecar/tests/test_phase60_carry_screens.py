"""PHASE-60 S6 (ADR 0085): a chat's carry link in force reaches only the screens that show carried memory.

`api.view_of` reads the link only with `carried=True`: the read-only lists (`/facts`, `/entities`, `/threads`,
`/secrets`), the panel's memory screen and a person's sheet. Previews, repairs, the author's note, the Inspector's pages,
the hub, the map and every other reader keep the chat's own memory, so a link never moves a preview's fingerprint or
reaches the note. Stub extractor, summarizer and note model only; synthetic names 세라, 카이토, 하나, 유나, 도현, 유찬."""

from __future__ import annotations

import json
from typing import Any

import pytest

from conftest import make_client
from nmos_sidecar import api, inspector, notes, views
from simchat import SimChat
from test_extraction import drain as drain_extract
from test_generations import conv_id
from test_phase60_carry_take import ON, _build_source_chat, _fact, _stub_extract
from test_sidecar_integration import sync
from test_summaries import drain as drain_summaries

SOURCE_LABELS = {"character_name": "세라", "chat_name": "항구의 밤", "persona_name": "도현"}
TARGET_TURN_0 = "세라와 카이토는 아침 항구 광장에 도착했다."
TARGET_TURNS = 13  # enough for the target's own scene summaries: the note's chronicle and custom part read them
STALE_TARGET_TURNS = inspector.STALE_TURNS + 4
SCENE = "세라와 카이토가 광장에서 조용한 아침을 보냈다."
CARRIED_WORDS = ("등대", "항구 시장", "회복됨", "피곤함")  # what only the source chat says
JOIN = {"entity_type": "character", "name": "카이토", "same_as": "세라"}
EXCLUDE = {"kind": "entity_exclude", "entity_type": "character", "item": "카이토"}
ASSEMBLED = {"sections": ["chronicle", "changed", "address"], "model": False}
CUSTOM = {"sections": ["custom"], "custom_prompt": "List where each character is now, one line each."}


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


def _stub_scene(system: str, user: str) -> tuple[dict, str]:
    """Every summary says the target's own words only: a carried value in a note can come from the view alone."""
    return {"summary": SCENE}, "{}"


def _setup(c, migrated: str, turns: int = TARGET_TURNS) -> tuple[str, str]:
    src_sim = _build_source_chat(4)
    sync(c, src_sim, **SOURCE_LABELS)
    tgt_sim = SimChat("tgt-screens-chat")
    for i in range(turns):
        tgt_sim.user(f"턴 {i}을 이어간다.")
        tgt_sim.reply(TARGET_TURN_0 if i == 0 else f"턴 {i}의 조용한 아침이 지나갔다.")
    tgt_sim.user("계속하자.")
    sync(c, tgt_sim, character_name="세라", chat_name="새 이야기", persona_name="유찬")
    drain_extract(migrated, _stub_both)
    drain_summaries(migrated, _stub_scene)
    return conv_id(c, src_sim), conv_id(c, tgt_sim)


def _link(c, tgt: str, src: str, mode: str) -> str:
    body: dict[str, Any] = {"source_conversation_id": src, "mode": mode}
    if mode == "regression":
        body["entity_names"] = ["세라"]
    res = c.post(f"/v1/conversations/{tgt}/carry", json=body)
    assert res.status_code == 200, res.text
    return str(res.json()["link"]["id"])


def _entity_id(c, tgt: str, name: str) -> str:
    found = [e for e in c.get(f"/v1/conversations/{tgt}/entities").json()
             if e.get("type") == "character" and name in [e.get("name"), *(e.get("names") or [])]]
    assert len(found) == 1, found
    return str(found[0]["id"])


class Calls:
    """Every `memory_view` call the routes make: whether it was handed a carry link."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.carried: list[bool] = []
        real = api.memory_view

        def spy(*args: Any, **kwargs: Any) -> dict[str, Any]:
            self.carried.append(kwargs.get("carried") is not None)
            return real(*args, **kwargs)

        monkeypatch.setattr(api, "memory_view", spy)


class Seen:
    """The last data the panel's memory screen and person sheet were built from."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.memory: dict[str, Any] | None = None
        self.person: dict[str, Any] | None = None
        real_memory, real_person = views.memory, views.person

        def memory(d: dict[str, Any], *args: Any, **kw: Any) -> str:
            self.memory = d
            return real_memory(d, *args, **kw)

        def person(d: dict[str, Any], *args: Any, **kw: Any) -> str:
            self.person = d
            return real_person(d, *args, **kw)

        monkeypatch.setattr(views, "memory", memory)
        monkeypatch.setattr(views, "person", person)


def _plain_routes(tgt: str, people: list[str]) -> list[str]:
    """Every page and list that keeps the chat's own memory while a link is in force."""
    out = [
        "/inspector", "/v1/inspector", "/dashboard",
        f"/inspector/c/{tgt}", f"/v1/inspector/c/{tgt}", f"/v1/inspector/c/{tgt}?timeline=lazy&status=lazy",
        f"/v1/inspector/c/{tgt}?part=timeline", f"/v1/inspector/c/{tgt}?part=status",
        f"/inspector/c/{tgt}/t/0", f"/v1/inspector/c/{tgt}/t/0", f"/inspector/c/{tgt}/t/1",
        "/v1/views/chats", "/views/chats", "/v1/views/style",
        f"/v1/views/hub?conversation={tgt}", f"/v1/views/hub?conversation={tgt}&map=true",
        f"/views/hub?conversation={tgt}",
        f"/v1/views/c/{tgt}/working", f"/views/c/{tgt}/working",
        f"/v1/views/c/{tgt}/map", f"/v1/views/c/{tgt}/map/graph", f"/v1/views/c/{tgt}/map/graph?all=true",
        f"/views/c/{tgt}/map", f"/views/c/{tgt}/map?all=true",
        f"/v1/conversations/{tgt}/memory-mode", f"/v1/conversations/{tgt}/replies-only",
        f"/v1/conversations/{tgt}/dropped", f"/v1/conversations/{tgt}/repairs",
        f"/v1/conversations/{tgt}/coverage", f"/v1/conversations/{tgt}/state", f"/v1/conversations/{tgt}/traces",
        f"/v1/conversations/{tgt}/carry", f"/v1/conversations/{tgt}/carry?snapshot=true",
    ]
    for eid in people:
        out += [f"/inspector/c/{tgt}/e/{eid}", f"/v1/inspector/c/{tgt}/e/{eid}",
                f"/v1/inspector/c/{tgt}/e/{eid}?timeline=lazy", f"/v1/inspector/c/{tgt}/e/{eid}?part=timeline",
                f"/v1/views/c/{tgt}/map?focus={eid}", f"/v1/views/c/{tgt}/map/graph?focus={eid}"]
    return out


def _carried_routes(tgt: str, people: list[str]) -> list[str]:
    """The read-only lists and the panel screens that show what a link carries."""
    out = [f"/v1/conversations/{tgt}/facts", f"/v1/conversations/{tgt}/facts?history=true",
           f"/v1/conversations/{tgt}/entities", f"/v1/conversations/{tgt}/threads",
           f"/v1/conversations/{tgt}/secrets",
           f"/v1/views/c/{tgt}/memory", f"/v1/views/c/{tgt}/memory?map=true", f"/views/c/{tgt}/memory"]
    for eid in people:
        out += [f"/v1/views/c/{tgt}/person/{eid}", f"/views/c/{tgt}/person/{eid}"]
    return out


def test_every_page_answers_with_either_link_and_only_the_carried_screens_read_it(
    migrated: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, seen = Calls(monkeypatch), Seen(monkeypatch)
    with make_client(migrated, **ON) as c:
        src, tgt = _setup(c, migrated)
        sera = _entity_id(c, tgt, "세라")
        _link(c, tgt, src, "continue")
        hana = _entity_id(c, tgt, "하나")  # a character only the carried rows mention
        for mode, people in (("continue", [sera, hana]), ("regression", [sera])):
            if mode == "regression":
                _link(c, tgt, src, "regression")  # replaces the continue link in force
            for url in _plain_routes(tgt, people + ([hana] if mode == "regression" else [])):
                calls.carried.clear()
                res = c.get(url)
                assert res.status_code == 200, (mode, url, res.text[:300])
                assert not any(calls.carried), (mode, url)  # the chat's own memory only
            for url in _carried_routes(tgt, people):
                calls.carried.clear()
                res = c.get(url)
                assert res.status_code == 200, (mode, url, res.text[:300])
                assert any(calls.carried), (mode, url)
            assert seen.memory is not None and seen.memory["carry"]["mode"] == mode
            assert seen.person is not None and seen.person["carry"]["mode"] == mode
        # a regression link folds nothing into the chat: its carried-only character has no sheet then
        assert c.get(f"/v1/views/c/{tgt}/person/{hana}").status_code == 404
        # the continue link's carried facts are in the list (test_phase60_carry_views pins their shape)
        _link(c, tgt, src, "continue")
        assert any(f.get("carried") for f in c.get(f"/v1/conversations/{tgt}/facts").json())


def _previews(c, tgt: str) -> tuple[dict[str, Any], dict[str, Any]]:
    join = c.post(f"/v1/conversations/{tgt}/entity-links/preview", json=JOIN)
    assert join.status_code == 200, join.text
    exclude = c.post(f"/v1/conversations/{tgt}/repairs/preview", json=EXCLUDE)
    assert exclude.status_code == 200, exclude.text
    return join.json(), exclude.json()


def test_a_link_moves_no_preview_and_lists_no_carried_row_as_a_change(
    migrated: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = Calls(monkeypatch)
    with make_client(migrated, **ON) as c:
        src, tgt = _setup(c, migrated)
        join0, exclude0 = _previews(c, tgt)
        for mode in ("continue", "regression"):
            _link(c, tgt, src, mode)
            assert any(f.get("carried") for f in c.get(f"/v1/conversations/{tgt}/facts").json()) \
                == (mode == "continue")  # the link is in force: the list shows its rows
            calls.carried.clear()
            join, exclude = _previews(c, tgt)
            assert calls.carried and not any(calls.carried), mode
            assert join["fingerprint"] == join0["fingerprint"], mode
            assert exclude["fingerprint"] == exclude0["fingerprint"], mode
            assert join == join0 and exclude == exclude0, mode
            for p in (join, exclude):
                text = json.dumps(p, ensure_ascii=False)
                assert '"carried"' not in text and not any(w in text for w in CARRIED_WORDS), (mode, text[:500])


def test_the_authors_note_is_the_same_with_a_link_and_its_model_never_reads_a_carried_row(
    migrated: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    class Fake:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def complete_metered(self, system: str, user: str) -> tuple[dict[str, Any], str, None]:
            asked.append(system + "\n" + user)
            return {"text": "- 세라: 항구 광장"}, "{}", None

    monkeypatch.setattr(notes, "ChatModel", Fake)
    calls = Calls(monkeypatch)
    with make_client(migrated, **ON) as c:
        src, tgt = _setup(c, migrated)

        def note(body: dict[str, Any]) -> bytes:
            notes.clear_cache()  # every request asks the model again
            res = c.post(f"/v1/conversations/{tgt}/notes", json=body)
            assert res.status_code == 200, res.text
            return res.content

        assembled0, custom0 = note(ASSEMBLED), note(CUSTOM)
        parts = {s["kind"]: s for s in json.loads(assembled0)["sections"]}
        assert parts["chronicle"]["made"] == "assembled"  # the target's scenes are there to tell
        assert json.loads(custom0)["sections"][0]["made"] == "model" and len(asked) == 1
        prompt0 = asked[0]
        for mode in ("continue", "regression"):
            _link(c, tgt, src, mode)
            if mode == "continue":  # a carried open thread the chronicle's "Open threads" would list
                assert any("등대 열쇠" in (t.get("text") or "")
                           for t in c.get(f"/v1/conversations/{tgt}/threads").json() if t["status"] == "open")
            asked.clear()
            calls.carried.clear()
            assert note(ASSEMBLED) == assembled0, mode
            assert note(CUSTOM) == custom0, mode
            assert calls.carried and not any(calls.carried), mode
            assert asked == [prompt0], mode  # the model is handed the very same prompt
            assert not any(w in prompt0 for w in CARRIED_WORDS)


def test_the_memory_screens_attention_count_is_the_chats_own(
    migrated: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen, calls = Seen(monkeypatch), Calls(monkeypatch)
    with make_client(migrated, **ON) as c:
        # past inspector.STALE_TURNS: the carried open promise (turn -1) is one a carried read would call stale
        src, tgt = _setup(c, migrated, turns=STALE_TARGET_TURNS)

        def memory() -> dict[str, Any]:
            res = c.get(f"/v1/views/c/{tgt}/memory")
            assert res.status_code == 200, res.text
            assert seen.memory is not None
            return seen.memory

        calls.carried.clear()
        before = memory()
        assert calls.carried == [False]  # an unlinked chat: one read, as before
        assert "carry" not in before
        for mode in ("continue", "regression"):
            _link(c, tgt, src, mode)
            calls.carried.clear()
            d = memory()
            assert calls.carried == [True, False], mode  # the screen's read, then the chat's own for attention
            assert d["carry"]["mode"] == mode and d["carry"]["lines"], mode
            assert d["attention"] == before["attention"], mode
            if mode == "continue":
                assert d["facts"] > before["facts"]  # the screen does show the carried facts
                last = d["conv"]["turns"]
                carried_open = [t for t in c.get(f"/v1/conversations/{tgt}/threads").json()
                                if t["status"] == "open" and "등대 열쇠" in (t.get("text") or "")]
                # it would be a stale thread to close in a carried read: the attention count must not hold it
                assert carried_open and all(inspector.stale(t, last) for t in carried_open)
