"""PHASE-60 S6 (ADR 0085): a target chat's read folds the rows its link carries (`carry.target_rows`,
`facts.memory_view(carried=…)`).

`continue` folds the carried rows like canon: before turn 0, after the target's canon, superseded by the target's story.
`regression` keeps them apart, as memory only. Stub extractor and canon extractor only; synthetic names 세라, 카이토,
하나, 유나, 도현, 유찬."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from conftest import active_generation, alias_yes, make_client
from nmos_sidecar import canonfacts, carry, retrieval, scene
from nmos_sidecar.entities import PERSONA
from nmos_sidecar.extraction import ALIAS_CONFIRM_SYSTEM
from nmos_sidecar.facts import memory_view
from nmos_sidecar.worker import run_once
from simchat import SimChat
from test_canon import push as push_canon
from test_extraction import drain as drain_extract
from test_generations import LLM, conv_id
from test_sidecar_integration import sync

LINK = str(uuid4())
SOURCE = str(uuid4())
USED = {"calls": 1, "input": 100, "output": 10}
CANON_ON = {**LLM, "summaries": False, "canon_facts": True, "extract_backfill": 100}

SECRET = "붉은 벽돌 아래 지하 창고 열쇠가 숨겨져 있다"
PROMISE = "내일 새벽 등대 열쇠를 찾아주기"
SOURCE_TURNS = (
    "세라는 등대에 있다. 세라는 카이토의 오랜 동료다.",
    "세라는 카이토에게 내일 새벽 등대 열쇠를 찾아주겠다고 약속했다. 사람들은 세라를 세짱이라고도 부른다.",
    "도현은 밤새 지쳐 버렸다.",
    f"세라는 카이토 모르게 {SECRET}는 사실을 알고 있다.",
    "유나는 사망했다.",
)
TARGET_TURNS = (
    "아침 햇살이 비춘다.",
    "세짱이 웃었다. 유찬은 졸렸다.",
    "세라는 항구에 있다.",
    "세라는 카이토에게 등대 열쇠를 찾아주었다.",
)


def _fact(subject: str, predicate: str, value: str | None = None, obj: str | None = None,
          obj_type: str | None = None, **kw: Any) -> dict[str, Any]:
    return {"subject": subject, "subject_type": "character", "predicate": predicate, "object": obj,
            "object_type": obj_type, "value": value, "polarity": "positive", "modality": "actual",
            "source": "narration", "evidence": "", **kw}


ROWS: dict[str, list[dict[str, Any]]] = {
    SOURCE_TURNS[0]: [_fact("세라", "located_in", None, "등대", "place"),
                      _fact("세라", "relationship", "오랜 동료", "카이토", "character")],
    SOURCE_TURNS[1]: [_fact("세라", "promised", PROMISE, "카이토", "character"),
                      _fact("세라", "also_called", "세짱")],
    SOURCE_TURNS[2]: [_fact("도현", "has_status", "지침")],
    SOURCE_TURNS[3]: [_fact("세라", "knows", SECRET, knowledge="limited", known_by=["세라"], hidden_from=["카이토"])],
    SOURCE_TURNS[4]: [_fact("유나", "has_status", "사망")],
    TARGET_TURNS[1]: [_fact("세짱", "has_status", "즐거움"), _fact("유찬", "has_status", "졸림")],
    TARGET_TURNS[2]: [_fact("세라", "located_in", None, "항구", "place")],
    TARGET_TURNS[3]: [_fact("세라", "fulfilled", PROMISE, "카이토", "character")],
}


def _stub_extract(system: str, user: str) -> tuple[dict, str, dict]:
    if system == ALIAS_CONFIRM_SYSTEM:
        ans, raw = alias_yes(user)
        return ans, raw, USED
    target = user.split("TARGET turn", 1)[-1]
    return {"assertions": [dict(r) for text, rows in ROWS.items() if text in target for r in rows]}, "{}", USED


def _chat(chat_id: str, turns: tuple[str, ...]) -> SimChat:
    sim = SimChat(chat_id)
    for i, text in enumerate(turns):
        sim.user(f"턴 {i}.")
        sim.reply(text)
    sim.user("계속하자.")
    return sim


def _world(c: Any, migrated: str, target_turns: int = 3) -> tuple[UUID, SimChat, UUID]:
    """A source chat (persona 도현) and a target chat (persona 유찬, character 하나), extracted."""
    src = _chat("src-chat", SOURCE_TURNS)
    sync(c, src, character_name="세라", chat_name="항구의 밤", persona_name="도현")
    tgt = _chat("tgt-chat", TARGET_TURNS[:target_turns])
    sync(c, tgt, character_name="하나", chat_name="새 이야기", persona_name="유찬")
    drain_extract(migrated, _stub_extract)
    return UUID(conv_id(c, src)), tgt, UUID(conv_id(c, tgt))


def _connect(migrated: str) -> psycopg.Connection:
    return psycopg.connect(migrated, row_factory=dict_row, autocommit=True)


def _head(conn: psycopg.Connection, conv: UUID) -> UUID:
    return conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (conv,)).fetchone()["head_commit_id"]


def _key(conn: psycopg.Connection) -> str:
    return active_generation(conn, "extract").key


def _link_continue(conn: psycopg.Connection, tgt: UUID, src: UUID, mode: str = "continue",
                   names: list[str] | None = None) -> carry.Carried:
    carry.link(conn, tgt, src, mode, names or [], carry.Keys(extractor=_key(conn)))
    found = carry.in_force(conn, tgt)
    assert found is not None
    return carry.target_rows(found)


def _carried(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("carried")]


def _entity_id(row: dict[str, Any], side: str = "subject") -> str | None:
    return (row.get(f"{side}_entity") or {}).get("id")


def _shape(view: dict[str, Any]) -> str:
    return repr((view["facts"], view["threads"], view["entities"]))


def _from(aid: int, gen: str = "extract-test") -> dict[str, Any]:
    return {"conversation": SOURCE, "assertion": aid, "revision": str(uuid4()), "generation": gen, "repair": None}


def _snapshot(mode: str = "continue") -> dict[str, Any]:
    """A stored shape-2 snapshot: facts newest first, as `carry.snapshot_of` stores them."""
    facts = [
        {"predicate": "has_status", "subject": "세라", "subject_type": "character", "value": "피곤함",
         "polarity": "positive", "turn": 3, "position": 7, "compiler": "c1", "known_by": None, "hidden_from": None,
         "participants": [{"name": "카이토", "type": "character"}], "from": _from(12)},
        {"predicate": "located_in", "subject": "세라", "subject_type": "character", "object": "등대",
         "object_type": "place", "value": None, "polarity": "positive", "modality": "actual", "source": "narration",
         "turn": 0, "position": 1, "from": _from(10)},
    ]
    threads = [
        {"kind": "promise", "by": "세라", "to": "카이토", "text": "열쇠를 찾아주기", "status": "open", "turn": 1,
         "position": 3, "names": ["세라", "카이토"], "closed_turn": None,
         "opening": {"predicate": "promised", "subject": "세라", "subject_type": "character", "object": "카이토",
                     "object_type": "character", "value": "열쇠를 찾아주기", "polarity": "positive",
                     "modality": "actual", "source": "narration", "turn": 1, "position": 3, "compiler": "c1"},
         "from": _from(11)},
        {"kind": "goal", "by": "세라", "to": None, "text": "등대를 고치기", "status": "open", "turn": 2,
         "position": 5, "names": ["세라"], "closed_turn": None, "opening": None, "from": _from(13)},
    ]
    aliases = [{"entity_type": "character", "name": "세라", "alias": "세짱", "turn": 1, "from": _from(14)}]
    story = {"text": "세라는 등대에 있었다.", "first_turn": 0, "last_turn": 3,
             "from": {"conversation": SOURCE, "summary": str(uuid4()), "generation": "sum-test"}}
    if mode == "regression":
        for row in (*facts, *threads):
            row.update(knowledge="limited", known_by=["세라"], orig_knowledge=None, orig_known_by=None)
        aliases, story = [], None
    return {"shape": 2, "mode": mode, "names": ["세라"] if mode == "regression" else [], "facts": facts,
            "aliases": aliases, "threads": threads, "story": story, "story_left_out": None, "characters": ["세라"]}


def _link(mode: str = "continue") -> dict[str, Any]:
    from uuid import UUID
    return {"id": UUID(LINK), "source_conversation_id": UUID(SOURCE), "mode": mode,
            "entity_names": ["세라"] if mode == "regression" else [], "snapshot": _snapshot(mode)}


# --- pure: carry.target_rows ------------------------------------------------------------------------------------

def test_continue_rows_are_facts_oldest_first_then_openings_then_aliases() -> None:
    got = carry.target_rows(_link())
    assert got.link == LINK and got.source == SOURCE and got.mode == "continue" and got.names == ()
    assert [(r["predicate"], r.get("value") or r.get("object")) for r in got.rows] == [
        ("located_in", "등대"), ("has_status", "피곤함"), ("promised", "열쇠를 찾아주기"), ("also_called", "세짱")]
    assert got.regression == ()
    assert got.story is not None and got.story["text"] == "세라는 등대에 있었다."


def test_continue_rows_carry_the_flag_and_sort_after_canon_before_turn_0() -> None:
    rows = carry.target_rows(_link()).rows
    positions = [r["position"] for r in rows]
    assert positions == sorted(positions) and len(set(positions)) == len(positions)
    assert all(canonfacts.POSITION_BASE < p < 0 for p in positions)
    assert positions[0] == carry.CARRY_BASE
    for r in rows:
        assert r["carried"] == LINK
        assert r["turn"] == -1
        assert r["turn_hash"] == r["host_logical_id"] == f"carried:{LINK}"
        assert r["listed_hash"] is None and r["evidence"] == ""
        assert r["modality"] == "actual" and r["source"] == "narration" and r["polarity"] == "positive"
        assert isinstance(r["id"], int) and r["id"] < 0
    place, status, opening, alias = rows
    assert status["generation"] == "extract-test" and status["compiler"] == "c1"
    assert place["compiler"] is None
    assert status["participants"] == ({"name": "카이토", "type": "character"},)
    assert place["participants"] is None
    assert status["carried_from"]["assertion"] == 12
    assert opening["carried_from"]["assertion"] == 11  # a thread opening's provenance is its thread's
    assert alias == {**alias, "subject": "세라", "subject_type": "character", "value": "세짱",
                     "predicate": "also_called", "object": None, "object_type": None}
    assert alias["carried_from"]["assertion"] == 14


def test_ids_are_negative_unique_and_stable() -> None:
    a, b = carry.target_rows(_link()), carry.target_rows(_link())
    ids = [r["id"] for r in a.rows]
    assert ids == [r["id"] for r in b.rows]
    assert len(set(ids)) == len(ids) and all(i < 0 for i in ids)
    other = dict(_link(), id=uuid4())
    assert not set(ids) & {r["id"] for r in carry.target_rows(other).rows}


def test_target_rows_never_changes_the_stored_snapshot() -> None:
    link = _link()
    before = repr(link["snapshot"])
    got = carry.target_rows(link)
    got.rows[0]["subject"] = "바뀜"
    assert repr(link["snapshot"]) == before


def test_regression_keeps_every_stored_row_apart_with_its_line() -> None:
    got = carry.target_rows(_link("regression"))
    assert got.mode == "regression" and got.names == ("세라",) and got.rows == () and got.story is None
    assert [(r["line"], r.get("predicate") or r.get("kind")) for r in got.regression] == [
        ("fact", "has_status"), ("fact", "located_in"), ("thread", "promise"), ("thread", "goal")]
    for r in got.regression:
        assert r["carried"] == LINK and r["carried_from"]["conversation"] == SOURCE
        assert r["knowledge"] == "limited" and r["known_by"] == ["세라"]


# --- continue: the carried rows fold before the target's story --------------------------------------------------

def test_continue_folds_carried_rows_before_the_story_and_the_story_supersedes_them(migrated: str) -> None:
    with make_client(migrated, **CANON_ON) as c:
        src, tgt_sim, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            head, key = _head(conn, tgt), _key(conn)
            before = memory_view(conn, head, key)
            carried = _link_continue(conn, tgt, src)
            # The off path: with a link in force, a read that passes nothing reads as before the link.
            assert _shape(memory_view(conn, head, key)) == _shape(before)
            assert "carried" not in before and "regression" not in before
            view = memory_view(conn, head, key, carried=carried)
            # The same Carried read twice gives the same view: the read never changes what it was handed.
            assert _shape(memory_view(conn, head, key, carried=carried)) == _shape(view)

        assert view["carried"] == {"link": carried.link, "source": str(src), "mode": "continue", "names": (),
                                   "rows": len([r for r in carried.rows if r["predicate"] != "also_called"]),
                                   "story": None}
        assert view["regression"] == []
        facts = _carried(view["facts"])
        assert {(f["subject"], f["predicate"], f.get("value")) for f in facts} == {
            ("세라", "relationship", "오랜 동료"), ("세라", "knows", SECRET), ("유나", "has_status", "사망")}
        for f in facts:
            assert f["carried"] == carried.link and f["turn"] == -1
            assert carry.CARRY_BASE <= f["position"] < 0 and f["id"] < 0

        # The story supersedes: the target's turn 2 puts 세라 in the harbour; the carried lighthouse is history.
        place = [f for f in view["facts"] if f["predicate"] == "located_in" and f["subject"] == "세라"]
        assert [(f["object"], f["turn"], f.get("carried")) for f in place] == [("항구", 2, None)]
        assert [(h["object"], h["turn"], h["outcome"]) for h in place[0]["history"]] == [
            ("등대", -1, "superseded"), ("항구", 2, "current")]
        assert place[0]["history"][0]["position"] < 0

        # A carried alias joins: the target's 세짱 is the carried 세라.
        sera = next(f for f in facts if f["subject"] == "세라")
        sejjang = next(f for f in view["facts"] if f["subject"] == "세짱")
        assert _entity_id(sera) is not None and _entity_id(sejjang) == _entity_id(sera)
        assert _entity_id(next(f for f in before["facts"] if f["subject"] == "세짱")) != _entity_id(sera)

        # The source's persona is the target's: a carried {{user}} row is 유찬's entity, so 유찬's own status of turn 1
        # supersedes the carried one.
        tired = next(a for a in view["assertions"] if a.get("carried") and a["subject"] == PERSONA)
        sleepy = next(f for f in view["facts"] if f["subject"] == "유찬")
        assert _entity_id(tired) == _entity_id(sleepy)
        assert next(e for e in view["entities"] if e["id"] == _entity_id(tired))["persona"] is True
        assert [(h["value"], h["turn"], h["outcome"]) for h in sleepy["history"]] == [
            ("지침", -1, "superseded"), ("졸림", 1, "current")]

        # Knowledge marks: a carried row takes no part in the secret fold and keeps its stored marks.
        assert not [s for s in view["secrets"] if s["id"] < 0]
        knows = next(f for f in facts if f["predicate"] == "knows")
        assert knows["knowledge"] == "limited" and knows["known_by"] == ["세라"] and knows["hidden_from"] == ["카이토"]

        # A carried open promise is an open thread of the target.
        promise = [t for t in view["threads"] if t.get("carried")]
        assert [(t["kind"], t["by"], t["to"], t["text"], t["status"]) for t in promise] == [
            ("promise", "세라", "카이토", PROMISE, "open")]
        assert promise[0]["carried"] == carried.link and promise[0]["id"] < 0

        # Track 3's gone pins skip a carried row: the carried death of 유나 pins no one.
        assert retrieval.gone_rows(view, view["resolution"], 3) == []

        # The target's story closes the carried promise by its text (ADR 0019).
        tgt_sim.user("턴 3.")
        tgt_sim.reply(TARGET_TURNS[3])
        tgt_sim.user("계속하자.")
        sync(c, tgt_sim, character_name="하나", chat_name="새 이야기", persona_name="유찬")
        drain_extract(migrated, _stub_extract)
        with _connect(migrated) as conn:
            later = memory_view(conn, _head(conn, tgt), _key(conn), carried=carried)
        closed = [t for t in later["threads"] if t.get("carried")]
        assert [(t["status"], (t["closed_by"] or {}).get("turn")) for t in closed] == [("kept", 3)]


def test_carried_rows_sort_after_the_targets_canon(migrated: str) -> None:
    def model(system: str, user: str) -> tuple[dict, str, dict]:
        if "CANON" in system:
            return {"assertions": [_fact("세라", "identity", "북부 등대지기")]}, "{}", USED
        return _stub_extract(system, user)

    with make_client(migrated, **CANON_ON) as c:
        src, tgt_sim, tgt = _world(c, migrated)
        push_canon(c, tgt_sim, {"card:name": ("하나", {"field": "name"}),
                                "card:desc": ("세라는 북부 등대지기다.", {"field": "desc"})})
        with _connect(migrated) as conn:
            cg = active_generation(conn, "canon")
            while run_once(conn, {"canon": (cg.key, lambda cn, job: canonfacts.process(cn, job, model, cg))}):
                pass
            carried = _link_continue(conn, tgt, src)
            view = memory_view(conn, _head(conn, tgt), _key(conn), canon_key=cg.key, carried=carried)
        canon_at = [f["position"] for f in view["facts"] if f.get("canon")]
        carried_at = [f["position"] for f in view["facts"] if f.get("carried")]
        assert canon_at and carried_at
        assert max(canon_at) < min(carried_at) and max(carried_at) < 0
        assert canonfacts.POSITION_BASE <= min(canon_at)
        assert not [f for f in view["facts"] if f.get("canon") and f.get("carried")]


def test_an_owner_exclusion_in_the_target_leaves_carried_facts_out(migrated: str) -> None:
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        res = c.post(f"/v1/conversations/{tgt}/repairs",
                     json={"kind": "entity_exclude", "item": "세라", "scope": "memory"})
        assert res.status_code == 200, res.text
        with _connect(migrated) as conn:
            carried = _link_continue(conn, tgt, src)
            view = memory_view(conn, _head(conn, tgt), _key(conn), carried=carried)
        said = {(f["subject"], f["predicate"]) for f in _carried(view["facts"])}
        assert said == {("유나", "has_status")}
        assert not [a for a in view["assertions"] if a.get("carried") and a["subject"] == "세라"]


# --- regression: memory apart, never in a fold ------------------------------------------------------------------

def test_regression_rows_are_listed_apart_and_enter_no_fold(migrated: str) -> None:
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            head, key = _head(conn, tgt), _key(conn)
            carried = _link_continue(conn, tgt, src, "regression", ["세라"])
            plain = memory_view(conn, head, key)
            view = memory_view(conn, head, key, carried=carried)

        assert view["carried"] == {"link": carried.link, "source": str(src), "mode": "regression", "names": ("세라",),
                                   "rows": 0, "story": None}
        # Nothing reaches the folds or the resolution: the view is the target's own.
        assert _shape(view) == _shape(plain)
        for bucket in ("facts", "claims", "other", "threads", "assertions", "secrets"):
            assert not [x for x in view[bucket] if x.get("carried") or (isinstance(x.get("id"), int) and x["id"] < 0)]
        r = view["resolution"]
        assert r.entity("character", "카이토") is None  # only a regression row names 카이토
        assert r.entity("character", "세짱") != r.entity("character", "세라")  # no carried alias joins them

        listed = view["regression"]
        assert sorted((x["line"], x.get("predicate") or x.get("kind")) for x in listed) == [
            ("fact", "knows"), ("fact", "located_in"), ("fact", "relationship"), ("thread", "promise")]
        sera = r.entity("character", "세라")["id"]
        for x in listed:
            assert x["carried"] == carried.link and x["knowledge"] == "limited" and x["known_by"] == ["세라"]
            assert _entity_id(x) == sera  # annotated with the target's resolution
        rel = next(x for x in listed if x.get("predicate") == "relationship")
        assert rel["object_entity"] == {"status": "unresolved", "candidates": []}
        thread = next(x for x in listed if x["line"] == "thread")
        assert thread["by"] == "세라" and thread["to"] == "카이토" and "카이토" in thread["names"]
        # The read annotated copies: the link's rows are as stored.
        assert not [x for x in carried.regression if "subject_entity" in x]
        assert not [t for t in view["threads"] if t.get("carried")]  # 세라's promise left out with her
