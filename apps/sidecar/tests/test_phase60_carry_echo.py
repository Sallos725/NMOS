"""PHASE-60 A12 (K27): a reply that echoes any carry or regression line shape loses it under `packet.clean_text`
(`clean-v3`, no normalizer change).

Line shapes are built with the real packet line builders (`facts.fact_line`, `facts.thread_line`,
`retrieval.carried_story`) over rows from `carry.target_rows`, alongside the literal shapes in the spec, and an
end-to-end check passes real packet-v20 packets of a linked target (continue, then regression) whole through
`clean_text`. Stub extractor only; synthetic names only."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from conftest import make_client
from nmos_sidecar import carry, facts, retrieval, threads
from nmos_sidecar.entities import resolve
from nmos_sidecar.normtext import NORMALIZER_VERSION
from nmos_sidecar.packet import clean_text
from test_phase60_carry_fold import CANON_ON, PROMISE, _connect, _world
from test_phase60_carry_packet import _link as _make_link, _packet

LINK = str(uuid4())
SOURCE = str(uuid4())


def _from(aid: int) -> dict[str, Any]:
    return {"conversation": SOURCE, "assertion": aid, "revision": str(uuid4()), "generation": "extract-test",
            "repair": None}


def _hand_link(mode: str) -> dict[str, Any]:
    """A hand-made link row with a shape-2 snapshot carrying facts, a promise thread and (for continue) a story."""
    fact_rows: list[dict[str, Any]] = [
        {"predicate": "relationship", "subject": "세라", "subject_type": "character", "object": "카이토",
         "object_type": "character", "value": "오랜 동료", "polarity": "positive", "modality": "actual",
         "source": "narration", "turn": 1, "position": 3, "from": _from(11)},
        {"predicate": "located_in", "subject": "세라", "subject_type": "character", "object": "등대",
         "object_type": "place", "value": None, "polarity": "positive", "modality": "actual",
         "source": "narration", "turn": 0, "position": 1, "from": _from(10)},
    ]
    thread_rows: list[dict[str, Any]] = [
        {"kind": "promise", "by": "세라", "to": "카이토", "text": "새벽 등대 열쇠를 찾아주기", "status": "open",
         "turn": 2, "position": 5, "names": ["세라", "카이토"], "closed_turn": None,
         "opening": {"predicate": "promised", "subject": "세라", "subject_type": "character", "object": "카이토",
                     "object_type": "character", "value": "새벽 등대 열쇠를 찾아주기", "polarity": "positive",
                     "modality": "actual", "source": "narration", "turn": 2, "position": 5},
         "from": _from(12)},
        {"kind": "promise", "by": "세라", "to": None, "text": "등대 불빛을 지키기", "status": "open",
         "turn": 3, "position": 7, "names": ["세라"], "closed_turn": None,
         "opening": {"predicate": "promised", "subject": "세라", "subject_type": "character", "object": None,
                     "object_type": None, "value": "등대 불빛을 지키기", "polarity": "positive",
                     "modality": "actual", "source": "narration", "turn": 3, "position": 7},
         "from": _from(13)},
    ]
    story: dict[str, Any] | None = {"text": "세라는 등대에서 카이토와 약속했다.", "first_turn": 0, "last_turn": 3,
                                    "from": {"conversation": SOURCE, "summary": str(uuid4()), "generation": "sum-test"}}
    if mode == "regression":
        for row in (*fact_rows, *thread_rows):
            row.update(knowledge="limited", known_by=["세라"], orig_knowledge=None, orig_known_by=None)
        story = None
    return {"id": UUID(LINK), "source_conversation_id": UUID(SOURCE), "mode": mode,
            "entity_names": ["세라"] if mode == "regression" else [],
            "snapshot": {"shape": 2, "mode": mode, "names": ["세라"] if mode == "regression" else [],
                         "facts": fact_rows, "aliases": [], "threads": thread_rows, "story": story,
                         "story_left_out": None, "characters": ["세라"]}}


def _carried_thread_lines(carried: carry.Carried) -> list[str]:
    openings = [r for r in carried.rows if r["predicate"] in threads.PREDICATES]
    folded, _, _ = threads.fold(openings, resolve(uuid4(), list(carried.rows)))
    for t in folded:
        t["carried"] = carried.link
    return [facts.thread_line(t) for t in folded]


def test_echoed_carried_and_regression_lines_are_dropped_by_clean_text() -> None:
    assert NORMALIZER_VERSION == "clean-v3"

    # Real line builders over rows from `carry.target_rows` of a hand-made continue link.
    cont = carry.target_rows(_hand_link("continue"))
    located = next(r for r in cont.rows if r["predicate"] == "located_in")
    carried_fact = facts.fact_line(located)
    assert 'kind="located_in"' in carried_fact and 'source="carried"' in carried_fact and "등대" in carried_fact

    carried_threads = _carried_thread_lines(cont)
    carried_promise = next(line for line in carried_threads if 'to="카이토"' in line)
    assert 'kind="promise"' in carried_promise and 'by="세라"' in carried_promise and 'source="carried"' in carried_promise

    # Real line builders over rows from `carry.target_rows` of a hand-made regression link.
    reg = carry.target_rows(_hand_link("regression"))
    reg_rel_row = {**next(r for r in reg.regression if r["line"] == "fact" and r["predicate"] == "relationship"),
                   "timeline": "previous"}
    reg_fact = facts.fact_line(reg_rel_row)
    assert 'kind="relationship"' in reg_fact and 'timeline="previous"' in reg_fact and 'known_by="세라"' in reg_fact

    reg_promise_no_to = facts.thread_line(
        {**next(r for r in reg.regression if r["line"] == "thread" and r.get("to") is None), "timeline": "previous"}
    )
    reg_promise_to = facts.thread_line(
        {**next(r for r in reg.regression if r["line"] == "thread" and r.get("to") == "카이토"), "timeline": "previous"}
    )
    assert 'kind="promise"' in reg_promise_no_to and 'timeline="previous"' in reg_promise_no_to
    assert 'known_by="세라"' in reg_promise_no_to

    # Literal shapes from the spec, alongside the builder-produced lines.
    shapes = (
        carried_fact,
        '<Fact kind="located_in" source="carried">세라 is in the lighthouse</Fact>',
        reg_fact,
        '<Fact kind="relationship" timeline="previous" knowledge="limited" known_by="세라">세라 relationship 카이토: 오랜 동료</Fact>',
        carried_promise,
        '<Thread kind="promise" by="세라" to="카이토" source="carried">새벽 등대 열쇠를 찾아주기</Thread>',
        reg_promise_no_to,
        reg_promise_to,
        '<Thread kind="promise" by="세라" timeline="previous" known_by="세라">등대 불빛을 지키기</Thread>',
    )
    for line in shapes:
        assert clean_text(line) == ""
        reply = f"세라가 창밖을 바라보았다. {line} 파도 소리가 들렸다."
        assert clean_text(reply) == "세라가 창밖을 바라보았다. 파도 소리가 들렸다."


def test_echoed_regression_group_drops_both_tags_and_its_lines() -> None:
    reg = carry.target_rows(_hand_link("regression"))
    reg_fact = facts.fact_line(
        {**next(r for r in reg.regression if r["line"] == "fact" and r["predicate"] == "relationship"),
         "timeline": "previous"}
    )
    reg_thread = facts.thread_line(
        {**next(r for r in reg.regression if r["line"] == "thread" and r.get("to") is None),
         "timeline": "previous"}
    )
    for inner in (reg_fact, reg_thread, f"{reg_fact}\n{reg_thread}"):
        group = f'  <Regression remembered_by="세라">\n{inner}\n  </Regression>'
        assert clean_text(group) == ""
        reply = f"세라가 잠시 멈춰 섰다.\n{group}\n\"아무것도 아니야.\""
        cleaned = clean_text(reply)
        assert cleaned == '세라가 잠시 멈춰 섰다.\n"아무것도 아니야."'
        assert "<Regression" not in cleaned and "</Regression>" not in cleaned
        assert "오랜 동료" not in cleaned and "등대 불빛" not in cleaned


def test_echoed_earlier_chat_summary_matches_story_summary_under_clean_text() -> None:
    earlier = '<Summary scope="earlier chat">x y z</Summary>'
    story = '<Summary kind="story" turns="0–9">x y z</Summary>'
    assert clean_text(earlier) == clean_text(story) == "x y z"

    # Pin the same equality with the real carried_story builder and surrounding reply text.
    cont = carry.target_rows(_hand_link("continue"))
    assert cont.story is not None
    built = retrieval.carried_story({"carried": {"link": cont.link, "story": cont.story}}, [], frozenset())
    assert built is not None and 'scope="earlier chat"' in built.xml
    story_same = f'    <Summary kind="story" turns="0–9">{cont.story["text"]}</Summary>'
    assert clean_text(built.xml) == clean_text(story_same) == cont.story["text"]
    assert clean_text(f"앞말.\n{built.xml}\n뒷말.") == clean_text(f"앞말.\n{story_same}\n뒷말.")


def test_whole_v20_packet_of_linked_target_is_dropped_by_clean_text(migrated: str) -> None:
    """End-to-end: a real packet-v20 packet of a linked target (continue, then regression) passed whole through
    `clean_text` leaves no carried fact's value and no regression line's value."""
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            cont = _make_link(conn, tgt, src, "continue")
            cont_out, _ = _packet(conn, tgt, "세라는 카이토와 어떤 사이야?", cont)
            reg = _make_link(conn, tgt, src, "regression", ["세라"])
            reg_out, _ = _packet(conn, tgt, "세라는 카이토를 기억해?", reg)

    # Confirm the packets actually carry the values we expect clean_text to drop.
    assert 'source="carried"' in cont_out.text and "오랜 동료" in cont_out.text and PROMISE in cont_out.text
    assert '<Regression remembered_by="세라">' in reg_out.text
    assert 'timeline="previous"' in reg_out.text and "오랜 동료" in reg_out.text and PROMISE in reg_out.text

    for pkt in (cont_out.text, reg_out.text):
        assert clean_text(pkt) == ""
        wrapped = f"세라가 고개를 들었다.\n{pkt}\n\"출발하자.\""
        cleaned = clean_text(wrapped)
        assert cleaned == '세라가 고개를 들었다.\n"출발하자."'
        assert "오랜 동료" not in cleaned and PROMISE not in cleaned and "등대" not in cleaned
        assert "<Regression" not in cleaned and 'source="carried"' not in cleaned
