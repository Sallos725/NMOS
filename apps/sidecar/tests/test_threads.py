"""Phase 7 (docs/phases/PHASE-7.md): promise threads at read time (Q2, Q3, Q5)."""

from __future__ import annotations

import uuid

from nmos_sidecar.entities import resolve
from nmos_sidecar.threads import fold, relevant_threads, similarity
from test_semantics import row

TYPES = {"subject_type": "character", "object_type": "character"}
PROMISE = "비가 그치면 내일 아침 등대 앞에서 만나기로 함"


def promise(pos: int, who: str = "하나", to: str = "{{user}}", text: str = PROMISE, **kw):
    """A promise said in dialogue by its maker: how the real-model tier extracts one (PHASE-7 evidence)."""
    kw = {"source": "character_claim", "asserted_by": who, **kw}
    return row(pos, who, "promised", to, text, **TYPES, **kw)


def kept(pos: int, who: str = "하나", text: str = PROMISE, **kw):
    return row(pos, who, "fulfilled", None, text, subject_type="character", **kw)


def broken(pos: int, who: str = "하나", to: str = "{{user}}", text: str = PROMISE, **kw):
    return row(pos, who, "promised", to, text, polarity="negative", **TYPES, **kw)


def threads(rows):
    r = resolve(uuid.uuid4(), rows)
    return fold(rows, r)


def status(rows):
    return [(t["by"], t["text"], t["status"]) for t in threads(rows)[0]]


def test_a_promise_said_by_its_maker_opens_a_thread():
    assert status([promise(10)]) == [("하나", PROMISE, "open")]
    # Half the real-model runs label it hypothetical: its content is in the future, the promise is made.
    assert status([promise(10, modality="hypothetical")]) == [("하나", PROMISE, "open")]
    # Narration (and legacy rows without a source) open one too.
    assert status([row(10, "하나", "promised", "{{user}}", PROMISE, **TYPES)]) == [("하나", PROMISE, "open")]
    assert status([row(10, "하나", "promised", "{{user}}", PROMISE, source=None, **TYPES)]) == [("하나", PROMISE, "open")]


def test_reported_dreamed_and_unknown_promises_open_nothing():
    assert status([promise(10, asserted_by="카이토")]) == []
    assert status([promise(10, modality="dreamed")]) == []
    assert status([promise(10, modality="unknown")]) == []
    _, _, used = threads([promise(10, asserted_by="카이토")])
    assert used == set()  # it stays a claim, as before


def test_fulfilled_keeps_and_a_negation_breaks():
    assert status([promise(10), kept(40)]) == [("하나", PROMISE, "kept")]
    assert status([promise(10), broken(40)]) == [("하나", PROMISE, "broken")]
    (t,), unmatched, used = threads([promise(10), kept(40)])
    assert t["closed_by"]["turn"] == 40 and t["turn"] == 10 and unmatched == [] and used == {10, 40}


def test_a_reworded_resolution_matches_by_similarity():
    assert similarity(PROMISE, "등대 앞에서 만나기로 한 약속") >= 0.6
    assert status([promise(10), kept(40, text="등대 앞에서 만나기로 함")]) == [("하나", PROMISE, "kept")]


def test_an_ambiguous_or_foreign_resolution_closes_nothing():
    two = [promise(10, text="등대 앞에서 만나기"), promise(11, text="등대 앞에서 기다리기")]
    result, unmatched, _ = threads([*two, kept(40, text="등대 앞에서")])
    assert [t["status"] for t in result] == ["open", "open"]
    assert [u["turn"] for u in unmatched] == [40]
    # Another character's fulfilment never closes 하나's promise, and unrelated text matches nothing.
    assert status([promise(10), kept(40, who="카이토")]) == [("하나", PROMISE, "open")]
    assert status([promise(10), kept(40, text="편지를 태우기")]) == [("하나", PROMISE, "open")]


def test_who_may_close_a_promise():
    # The maker and the recipient may say so; a bystander's claim closes nothing.
    assert status([promise(10), broken(40, source="character_claim", asserted_by="하나")])[0][2] == "broken"
    assert status([promise(10, to="카이토"),
                   broken(40, to="카이토", source="character_claim", asserted_by="카이토")])[0][2] == "broken"
    assert status([promise(10), kept(40, source="character_claim", asserted_by="유이")])[0][2] == "open"
    # A plan to break it is not a break.
    assert status([promise(10), broken(40, modality="hypothetical")])[0][2] == "open"


def test_a_restated_promise_is_one_thread():
    (t,), _, used = threads([promise(10), promise(30, text=PROMISE + ".")])
    assert t["turn"] == 10 and [x["turn"] for x in t["restated"]] == [30] and used == {10, 30}
    # After it is kept, the same words make a new promise.
    assert status([promise(10), kept(20), promise(30)]) == [("하나", PROMISE, "open"), ("하나", PROMISE, "kept")]


def test_aliases_are_the_same_maker():
    alias = row(5, "하나", "also_called", None, "Hana", subject_type="character")
    result, _, _ = threads([alias, promise(10), kept(40, who="Hana")])
    assert [t["status"] for t in result] == ["kept"]


def test_relevant_threads_need_a_mention_other_than_the_persona():
    (t,), _, _ = threads([promise(10)])
    t["names"] = ["하나", "{{user}}"]
    assert relevant_threads([t], "하나야, 오랜만이야.", "", set(), 3) == [t]
    assert relevant_threads([t], "{{user}}는 걷는다.", "", set(), 3) == []
    assert relevant_threads([t], "잘 잤어?", "하나가 웃었다.", set(), 3) == [t]
    assert relevant_threads([t], "하나야", "", {"m10"}, 3) == []  # still in the prompt (D3)
    t["status"] = "kept"
    assert relevant_threads([t], "하나야", "", set(), 3) == []


def test_thread_line_and_packet_section():
    from nmos_sidecar.facts import thread_line
    from nmos_sidecar.packet import compile_packet

    (t,), _, _ = threads([promise(10, knowledge="limited", known_by=["하나", "{{user}}"])])
    line = thread_line(t)
    assert line == (f'    <Thread kind="promise" by="하나" to="{{{{user}}}}" turn="10" known_by="하나, {{{{user}}}}">'
                    f"{PROMISE}</Thread>")
    text, _, _ = compile_packet([], 600, facts=['    <Fact kind="identity" turn="3">하나 identity: 기사</Fact>'],
                                threads=[line])
    assert text.index("<Threads>") < text.index("<Facts>")
    assert "A Thread is a promise made in the story" in text
    assert "A Thread" not in compile_packet([], 600, facts=['    <Fact kind="x" turn="1">a</Fact>'])[0]
