"""PHASE-60 S6 (ADR 0085 items 4, 5): the packet-v20 lines of what a chat's carry link carries.

`continue`: carried facts and open threads are offered as the target's own, marked source="carried" in place of a turn,
their ledger entries naming the link and the source assertion; they never change the target's scene cast, <Cast>,
gone pins, return-gap marks or settled lines. Stub extractor only; the worlds of `test_phase60_carry_fold`; synthetic
names only."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import psycopg

from conftest import make_client
from nmos_sidecar import carry, retrieval
from nmos_sidecar.packet import CARRIED_MARK, CARRIED_NOTE, Compiled
from nmos_sidecar.retrieval import Gathered, RecallOptions
from test_phase60_carry_fold import CANON_ON, PROMISE, _connect, _head, _key, _world

BUDGET = 3000


def _link(conn: psycopg.Connection, tgt: UUID, src: UUID, mode: str = "continue",
          names: list[str] | None = None) -> carry.Carried:
    carry.link(conn, tgt, src, mode, names or [], carry.Keys(extractor=_key(conn)))
    found = carry.in_force(conn, tgt)
    assert found is not None
    return carry.target_rows(found)


def _packet(conn: psycopg.Connection, tgt: UUID, query: str, carried: carry.Carried | None,
            policy: str = "packet-v20", **opts: Any) -> tuple[Compiled, Gathered]:
    options = RecallOptions(policy=policy, extractor_key=_key(conn), **opts)
    g = retrieval.gather(conn, _head(conn, tgt), query, "", set(), options, carried=carried)
    return retrieval.compile_gathered(g, BUDGET, policy), g


def _section(text: str, tag: str) -> str:
    found = re.search(rf"  <{tag}>\n.*?\n  </{tag}>", text, re.DOTALL)
    return found.group(0) if found else ""


def _carried_entries(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in ledger if (e.get("ref") or {}).get("carried")]


# --- continue: the lines ------------------------------------------------------------------------------------------

def test_continue_facts_and_threads_are_marked_carried_with_their_provenance(migrated: str) -> None:
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            carried = _link(conn, tgt, src)
            out, _ = _packet(conn, tgt, "세라는 카이토와 어떤 사이야?", carried)
            plain, _ = _packet(conn, tgt, "세라는 카이토와 어떤 사이야?", None)
    text = out.text
    assert '<Fact kind="relationship" source="carried">세라 relationship 카이토: 오랜 동료</Fact>' in text
    assert f'<Thread kind="promise" by="세라" to="카이토" source="carried">{PROMISE}</Thread>' in text
    assert 'turn="-1"' not in text
    assert CARRIED_NOTE in text and CARRIED_MARK not in plain.text and CARRIED_NOTE not in plain.text
    # The target's story says where 세라 is now: the carried lighthouse is history, not the place.
    assert "세라 located in 항구" in text and "세라 located in 등대" not in text
    # Each carried line's ledger entry names the link and the source assertion it was read from (ADR 0027).
    entries = _carried_entries(out.ledger)
    assert {e["kind"] for e in entries} == {"fact", "thread"}
    by_text = {e["text"]: e for e in entries}
    rel = next(e for t, e in by_text.items() if "오랜 동료" in t)
    assert rel["placed"] and rel["ref"]["carried"] == carried.link and rel["ref"]["assertion"] < 0
    for e in entries:
        assert isinstance(e["ref"]["source_assertion"], int) and e["ref"]["source_assertion"] > 0
        assert e["ref"]["carried"] == carried.link


def test_a_version_a_standing_fact_replaced_is_named_as_the_earlier_chats() -> None:
    """A standing fact that replaced a carried version names it as an earlier chat's, never as turn -1."""
    from nmos_sidecar.facts import _entry, fact_line
    base = {"predicate": "relationship", "subject": "세라", "subject_type": "character", "object": "카이토",
            "object_type": "character", "polarity": "positive"}
    old = {**base, "position": carry.CARRY_BASE, "turn": -1, "value": "오랜 동료", "carried": "L"}
    new = {**base, "position": 5, "turn": 2, "value": "옛 동료"}
    history = [_entry(old, {}), _entry(new, {id(new): "current"})]
    assert history[0]["carried"] == "L" and "carried" not in history[1]
    line = fact_line({**new, "history": history}, before=True)
    assert line == ('    <Fact kind="relationship" turn="2">세라 relationship 카이토: 옛 동료; before, in an earlier chat: '
                    '세라 relationship 카이토: 오랜 동료</Fact>')


# --- continue: what a link never changes --------------------------------------------------------------------------

PERSONA_SPELLINGS = ("{{user}}", "유찬")  # the target's persona, displayed by the first spelling its resolution has


def _scene_parts(out: Compiled, g: Gathered) -> dict[str, Any]:
    return {"cast": _section(out.text, "Cast"), "scene": sorted(g.cast),
            "names": sorted(n for n in g.cast.values() if n not in PERSONA_SPELLINGS), "gone": [x.xml for x in g.gone],
            "marks": dict(g.cast_marks), "settled": [x.xml for x in g.settled],
            "gone_marked": out.text.count('gone="true"'), "back_after": out.text.count("back_after="),
            "status_threads": out.text.count('<Thread status="')}


def _without_aliases(link: dict[str, Any]) -> carry.Carried:
    """The link's rows less its aliases: a carried alias joins the target's names by design (ADR 0085 item 3), which
    regroups the target's own lines; what is compared here is what the carried rows themselves do."""
    return carry.target_rows({**link, "snapshot": {**link["snapshot"], "aliases": []}})


def test_a_continue_link_changes_no_scene_cast_gone_pin_return_mark_or_settled_line(migrated: str) -> None:
    query = "세라는 지금 어디 있어?"
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated, target_turns=4)  # turn 3 keeps the carried promise
        with _connect(migrated) as conn:
            before = _scene_parts(*_packet(conn, tgt, query, None))
            _link(conn, tgt, src)
            carried = _without_aliases(carry.in_force(conn, tgt))
            out, g = _packet(conn, tgt, query, carried)
            view = retrieval.memory_view(conn, _head(conn, tgt), _key(conn), carried=carried)
    # present: a carried death (유나: a gone pin needs no mention) and a carried promise the target's story kept
    assert [(t["status"], t.get("carried")) for t in view["threads"] if t.get("carried")] == [("kept", carried.link)]
    assert any(f.get("carried") and f["value"] == "사망" for f in view["facts"])
    assert _scene_parts(out, g) == before
    assert before["names"] == ["세라"] and "<Character name=\"세라\">" in before["cast"]


def test_a_carried_status_of_a_character_the_message_names_is_a_fact_never_a_cast_line(migrated: str) -> None:
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            carried = _link(conn, tgt, src)
            out, g = _packet(conn, tgt, "유나는 지금 어디 있어?", carried)
    assert "유나" in g.cast.values()  # a name the message says counts, whatever the rows are
    assert '<Fact kind="has_status" source="carried">유나 has status: 사망</Fact>' in _section(out.text, "Facts")
    assert "사망" not in _section(out.text, "Cast") and 'gone="true"' not in out.text
