"""PHASE-51 step 2: a thread's horizon (how long it is meant to last) decides when it is stale, for the Inspector's
"needs a look", the author's note and the panel's memory; a thread without one behaves exactly as before."""

from __future__ import annotations

import random

from nmos_sidecar import inspector, predicates, threads, views


def row(i, predicate="goal", turn=1, value=None, salience=None, subject="Hana", **kw):
    return {"id": i, "predicate": predicate, "subject": subject, "subject_type": "character", "object": kw.pop("object", None),
            "value": value or f"aim {i}", "turn": turn, "position": turn, "polarity": "positive", "modality": "actual",
            "salience": salience, **kw}


def test_the_vocabulary_is_by_predicate():
    assert predicates.horizon({"predicate": "goal", "horizon": "Arc "}) == "arc"
    assert predicates.horizon({"predicate": "owes", "horizon": "lasting"}) == "lasting"
    assert predicates.horizon({"predicate": "event", "horizon": "scene"}) is None  # an event's is major / minor
    assert predicates.horizon({"predicate": "goal", "horizon": "major"}) is None
    assert predicates.horizon_of({"predicate": "promised", "salience": "scene"}) == "scene"
    assert predicates.horizon_of({"predicate": "event", "salience": "major"}) is None
    assert predicates.horizon_of({"predicate": "goal", "salience": "major"}) is None


def test_a_thread_takes_its_opening_horizon_and_a_restatement_can_change_it():
    out, _, _ = threads.fold([row(1, turn=2, value="find the bell", salience="scene"),
                              row(2, turn=9, value="find the bell", salience="lasting"),
                              row(3, predicate="owes", turn=4, value="a life", object="Kaito", object_type="character")])
    by = {t["text"]: t for t in out}
    assert by["find the bell"]["horizon"] == "lasting" and len(by["find the bell"]["restated"]) == 1
    assert by["a life"]["horizon"] is None


def test_stale_by_horizon():
    def th(horizon, turn=0):
        return {"status": "open", "turn": turn, "restated": [], "horizon": horizon}
    assert not inspector.stale(th("scene"), 10) and inspector.stale(th("scene"), 11)
    assert not inspector.stale(th("arc"), 30) and inspector.stale(th("arc"), 31)
    assert not inspector.stale(th("lasting"), 10_000)
    assert not inspector.stale(th(None), 30) and inspector.stale(th(None), 31)
    assert not inspector.stale({**th("scene"), "status": "kept"}, 99)


def test_without_horizons_stale_is_what_it_was():
    """Parity with main before PHASE-51: the old rule, on random threads that carry no horizon."""
    def old(th, last_turn):
        latest = inspector.last_said(th)
        return th["status"] == "open" and last_turn is not None and latest is not None and latest < last_turn - 30
    rnd = random.Random(51)
    for _ in range(2000):
        th = {"status": rnd.choice(["open", "open", "kept", "achieved"]), "turn": rnd.choice([None, *range(0, 90)]),
              "restated": [{"turn": rnd.choice([None, *range(0, 90)])} for _ in range(rnd.randrange(3))]}
        if rnd.random() < 0.5:
            th["horizon"] = None
        last = rnd.choice([None, *range(0, 130)])
        assert inspector.stale(th, last) == old(th, last)


def test_the_screens_say_the_horizon():
    th = {"id": 1, "kind": "goal", "by": "Hana", "to": None, "text": "find the bell", "turn": 5, "status": "open",
          "restated": [], "horizon": "arc", "closed_by": None}
    assert views.thread_meta(th, "ko") == "목표 · 이야기 줄기 · t5부터"
    assert views.thread_meta({**th, "horizon": None}, "en") == "goal · since t5"
    assert "이야기 줄기" in inspector._threads_table([th], "ko")
