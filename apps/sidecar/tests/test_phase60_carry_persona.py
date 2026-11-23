"""PHASE-60 S6 (ADR 0085): the source's persona is the target's persona, by the name the host reports for the target.

A link's snapshot stores the source's persona as the marker {{user}} (`carry.persona_mapped`). A target reads it as its
own persona's host name (`conversation.host_persona_name`, ADR 0023): in packet-v20's carried and regression lines, in
`/facts`, `/entities` and `/threads`, and on the panel's memory screen and person sheet, also when the target's own rows
never name its persona (a fresh chat that continues an old one). The stored snapshot is unchanged. Stub extractor only;
synthetic names 세라, 하나, 도현, 타쿠미."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from conftest import alias_yes, make_client
from nmos_sidecar import carry
from nmos_sidecar.entities import PERSONA
from nmos_sidecar.extraction import ALIAS_CONFIRM_SYSTEM
from nmos_sidecar.facts import memory_view
from simchat import SimChat
from test_extraction import drain as drain_extract
from test_generations import LLM, conv_id
from test_phase60_carry_fold import _connect, _fact, _head, _key
from test_sidecar_integration import recall, sync

USED = {"calls": 1, "input": 100, "output": 10}
PROMISE = "내일 등대 열쇠를 찾아주기"
SOURCE_TURNS = (
    "도현은 등대에 있다.",
    "세라는 도현의 오랜 동료다.",
    "세라는 도현에게 내일 등대 열쇠를 찾아주겠다고 약속했다.",
    "세라와 도현은 폭풍 속에서 배를 고쳤다.",
)
GREETING = "세라가 항구에서 손을 흔들었다."
TARGET_TURN = "하나는 정원에 있다."  # a target row that never names the persona
ROWS: dict[str, list[dict[str, Any]]] = {
    SOURCE_TURNS[0]: [_fact("도현", "located_in", None, "등대", "place")],
    SOURCE_TURNS[1]: [_fact("세라", "relationship", "오랜 동료", "도현", "character")],
    SOURCE_TURNS[2]: [_fact("세라", "promised", PROMISE, "도현", "character")],
    SOURCE_TURNS[3]: [_fact("세라", "event", "폭풍 속에서 배를 고쳤다",
                            participants=[{"name": "도현", "type": "character"}])],
    TARGET_TURN: [_fact("하나", "located_in", None, "정원", "place")],
}
QUERY = "세라와 나는 무슨 약속을 했지? 세라는 나를 기억해?"


def _stub(system: str, user: str) -> tuple[dict, str, dict]:
    if system == ALIAS_CONFIRM_SYSTEM:
        ans, raw = alias_yes(user)
        return ans, raw, USED
    target = user.split("TARGET turn", 1)[-1]
    return {"assertions": [dict(r) for text, rows in ROWS.items() if text in target for r in rows]}, "{}", USED


def _client(migrated: str):
    return make_client(migrated, packet_policy="packet-v20", summaries=False, rest_after=20, extract_backfill=100,
                       **LLM)


def _setup(c: Any, migrated: str, persona: str | None, fresh: bool) -> tuple[str, SimChat, str]:
    """A source chat (persona 도현, character 세라) and a target chat with the persona `persona` whose rows never name
    it: `fresh`, only its greeting and first message (nothing extracted); else one extracted row about 하나."""
    src = SimChat("src-persona")
    for i, text in enumerate(SOURCE_TURNS):
        src.user(f"턴 {i}.")
        src.reply(text)
    src.user("계속.")
    sync(c, src, character_name="세라", chat_name="옛 이야기", persona_name="도현")
    tgt = SimChat("tgt-persona")
    if fresh:
        tgt.reply(GREETING)
        tgt.user("안녕, 세라.")
    else:
        tgt.user("턴 0.")
        tgt.reply(TARGET_TURN)
        tgt.user("계속.")
    sync(c, tgt, character_name="세라", chat_name="새 이야기", **({"persona_name": persona} if persona else {}))
    drain_extract(migrated, _stub)
    return conv_id(c, src), tgt, conv_id(c, tgt)


def _link(c: Any, tgt: str, src: str, mode: str) -> None:
    body: dict[str, Any] = {"source_conversation_id": src, "mode": mode}
    if mode == "regression":
        body["entity_names"] = ["세라"]
    res = c.post(f"/v1/conversations/{tgt}/carry", json=body)
    assert res.status_code == 200, res.text


def _lines(text: str) -> list[str]:
    return [x.strip() for x in text.split("\n") if x.lstrip().startswith(("<Fact ", "<Thread "))
            and ('source="carried"' in x or 'timeline="previous"' in x)]


def _expected(name: str, mode: str) -> list[str]:
    if mode == "continue":
        return [f'<Thread kind="promise" by="세라" to="{name}" source="carried">{PROMISE}</Thread>',
                f'<Fact kind="relationship" source="carried">세라 relationship {name}: 오랜 동료</Fact>',
                '<Fact kind="event" source="carried">세라 event: 폭풍 속에서 배를 고쳤다</Fact>',
                f'<Fact kind="located_in" source="carried">{name} located in 등대</Fact>']
    return [f'<Thread kind="promise" by="세라" to="{name}" timeline="previous" known_by="세라">{PROMISE}</Thread>',
            f'<Fact kind="relationship" timeline="previous" known_by="세라">세라 relationship {name}: 오랜 동료</Fact>',
            '<Fact kind="event" timeline="previous" known_by="세라">세라 event: 폭풍 속에서 배를 고쳤다</Fact>']


@pytest.mark.parametrize("fresh", [True, False], ids=["greeting-only", "rows-without-persona"])
@pytest.mark.parametrize("persona", ["도현", "타쿠미"])
@pytest.mark.parametrize("mode", ["continue", "regression"])
def test_carried_persona_lines_name_the_targets_persona(migrated: str, mode: str, persona: str, fresh: bool) -> None:
    with _client(migrated) as c:
        src, tgt_sim, tgt = _setup(c, migrated, persona, fresh)
        _link(c, tgt, src, mode)
        text = recall(c, tgt_sim, QUERY, budget=3000, previous_ai="세라가 고개를 끄덕였다.")["packet"]["text"]
        assert _lines(text) == _expected(persona, mode)
        assert PERSONA not in text
        if persona != "도현":
            assert "도현" not in text  # the source's persona name is nowhere: it is this chat's persona
        memory = c.get(f"/v1/views/c/{tgt}/memory")
        assert memory.status_code == 200 and PERSONA not in memory.text and persona in memory.text
        if mode == "regression":  # nothing carried enters the chat's own lists
            return
        facts = [f for f in c.get(f"/v1/conversations/{tgt}/facts").json() if f.get("carried")]
        entities = c.get(f"/v1/conversations/{tgt}/entities").json()
        threads = [t for t in c.get(f"/v1/conversations/{tgt}/threads").json() if t.get("text") == PROMISE]
    me = [e for e in entities if e.get("persona")]
    assert [(e["name"], e["names"]) for e in me] == [(persona, [persona])]
    assert not [e for e in entities if PERSONA in (e.get("names") or [])]
    assert {(f["subject"], f.get("object")) for f in facts} == {("세라", None), ("세라", persona), (persona, "등대")}
    for f in facts:  # the persona's rows are its entity's
        for side in ("subject", "object"):
            if f.get(side) == persona:
                assert f[f"{side}_entity"] == {"id": me[0]["id"], "name": persona}
    assert [(t["by"], t["to"], t["status"]) for t in threads] == [("세라", persona, "open")]
    with _client(migrated) as c:
        sheet = c.get(f"/v1/views/c/{tgt}/person/{me[0]['id']}")
        assert sheet.status_code == 200 and PERSONA not in sheet.text and persona in sheet.text


def test_the_persona_keeps_its_entity_and_the_stored_snapshot_its_marker(migrated: str) -> None:
    """Only the spelling changes: the persona's entity id, the fold and the stored rows are as before."""
    with _client(migrated) as c:
        src, _, tgt = _setup(c, migrated, "타쿠미", fresh=False)
        _link(c, tgt, src, "continue")
    with _connect(migrated) as conn:
        link = carry.in_force(conn, UUID(tgt))
        assert link is not None
        stored = carry.target_rows(link)
        head, key = _head(conn, UUID(tgt)), _key(conn)
        named = memory_view(conn, head, key, carried=stored)
        # the same rows spelled with the marker, read with no host name: the persona's entity and every key agree
        conn.execute("UPDATE conversation SET host_persona_name = NULL WHERE id = %s", (tgt,))
        marked = memory_view(conn, head, key, carried=stored)
        assert carry.in_force(conn, UUID(tgt))["snapshot"] == link["snapshot"]
    snap = link["snapshot"]
    assert any(f["subject"] == PERSONA for f in snap["facts"])  # stored as the marker
    assert any(t["to"] == PERSONA for t in snap["threads"])
    assert any(r.get("subject") == PERSONA or r.get("object") == PERSONA for r in stored.rows)  # read rows untouched
    me_named = next(e for e in named["entities"] if e.get("persona"))
    me_marked = next(e for e in marked["entities"] if e.get("persona"))
    assert me_named["id"] == me_marked["id"] and me_named["name"] == "타쿠미" and me_marked["name"] == PERSONA

    def shape(view: dict[str, Any]) -> list[tuple]:
        return sorted((f["predicate"], (f.get("subject_entity") or {}).get("id"),
                       (f.get("object_entity") or {}).get("id"), f.get("value"), f["position"]) for f in view["facts"])

    assert shape(named) == shape(marked)
    assert [(t["id"], t["status"]) for t in named["threads"]] == [(t["id"], t["status"]) for t in marked["threads"]]


def test_without_a_host_persona_name_the_marker_stays() -> None:
    """A target the host names no persona for (the permission refused) reads the rows as stored: there is no name."""
    rows = (_fact(PERSONA, "located_in", None, "등대", "place"),)
    got = carry.Carried("L", "S", "continue", (), rows, (), None)
    assert got.for_persona(None) is got and got.for_persona("") is got and got.for_persona(PERSONA) is got


def test_only_character_name_fields_take_the_name() -> None:
    """Every field `persona_mapped` writes the marker into, and a regression thread's opening; a place, an item, a
    value and a thread's text keep the marker as written."""
    fact = {**_fact(PERSONA, "relationship", f"{PERSONA}의 동료", PERSONA, "character"),
            "asserted_by": PERSONA, "known_by": [PERSONA, "세라", "타쿠미"], "hidden_from": [PERSONA],
            "participants": ({"type": "character", "name": PERSONA}, {"type": "item", "name": PERSONA})}
    place = _fact(PERSONA, "located_in", None, PERSONA, "place") | {"subject_type": "place"}
    thread = {"line": "thread", "kind": "promise", "by": PERSONA, "to": PERSONA, "text": f"{PERSONA}에게 돌려주기",
              "names": [PERSONA, "세라"], "known_by": ["세라"], "opening": dict(fact)}
    got = carry.Carried("L", "S", "regression", ("세라",), (fact, place), (thread,), None).for_persona("타쿠미")
    f, p = got.rows
    assert (f["subject"], f["object"], f["value"], f["asserted_by"]) == ("타쿠미", "타쿠미", f"{PERSONA}의 동료", "타쿠미")
    assert f["known_by"] == ["타쿠미", "세라"] and f["hidden_from"] == ["타쿠미"]
    assert f["participants"] == ({"type": "character", "name": "타쿠미"}, {"type": "item", "name": PERSONA})
    assert (p["subject"], p["object"]) == (PERSONA, PERSONA)  # not a character
    (t,) = got.regression
    assert (t["by"], t["to"], t["text"], t["names"]) == ("타쿠미", "타쿠미", f"{PERSONA}에게 돌려주기", ["타쿠미", "세라"])
    assert t["opening"]["subject"] == "타쿠미" and t["opening"]["value"] == f"{PERSONA}의 동료"
    assert fact["subject"] == PERSONA and thread["opening"]["subject"] == PERSONA  # the inputs are left as they were
