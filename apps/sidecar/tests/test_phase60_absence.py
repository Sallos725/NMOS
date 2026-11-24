"""PHASE-60 S4 (A10): pure return-gap and settled-thread rules (`absence.py`)."""

from __future__ import annotations

import pytest

from nmos_sidecar import absence, predicates, repairs, threads


def test_constants_match_spec_and_outcomes():
    assert absence.RUN_GAP == 5
    assert absence.RUN_START_MAX == 5
    assert absence.GAP_MIN == 40
    assert absence.SETTLED_TURNS == 15
    assert absence.SETTLED_MAX == 3
    assert absence.SETTLED_BAD == ("broken", "failed", "abandoned")
    assert absence.SETTLED_GOOD == ("kept", "achieved", "paid", "answered", "averted")
    assert set(absence.SETTLED_BAD) & set(absence.SETTLED_GOOD) == set()
    assert set(absence.SETTLED_BAD) | set(absence.SETTLED_GOOD) == (
        set(predicates.OUTCOMES) | set(repairs.PROMISE_OUTCOMES)
    )


def test_return_gap_exact_threshold_40_vs_39():
    all_served = set(range(0, 200))
    # Turns strictly between 10 and 51 are 11..50: 40 served turns.
    assert absence.return_gap([10, 51], all_served, now=51) == 40
    # Turns strictly between 10 and 50 are 11..49: 39 served turns.
    assert absence.return_gap([10, 50], all_served, now=50) is None


def test_return_gap_unserved_turns_as_set_and_callable():
    # Turns strictly between 10 and 56 are 11..55: 45 turns total.
    unserved_10 = set(range(20, 30))
    served_set_35 = set(range(0, 100)) - unserved_10
    served_fn_35 = lambda t: t not in unserved_10
    assert absence.return_gap([10, 56], served_set_35, now=56) is None
    assert absence.return_gap([10, 56], served_fn_35, now=56) is None

    # With only 5 unserved out of 45, exactly 40 served turns remain.
    unserved_5 = set(range(20, 25))
    served_set_40 = set(range(0, 100)) - unserved_5
    served_fn_40 = lambda t: t not in unserved_5
    assert absence.return_gap([10, 56], served_set_40, now=56) == 40
    assert absence.return_gap([10, 56], served_fn_40, now=56) == 40

    # A list with duplicate turn numbers still counts each served turn once.
    served_list = list(served_set_35) + list(range(11, 20))
    assert absence.return_gap([10, 56], served_list, now=56) is None


def test_return_gap_first_appearance_and_empty():
    all_served = set(range(0, 200))
    assert absence.return_gap([], all_served, now=100) is None
    assert absence.return_gap([100], all_served, now=100) is None
    # A multi-turn first run with no earlier appearance is still a first appearance.
    assert absence.return_gap([96, 98, 100], all_served, now=100) is None
    # Only future appearances (> now) count as empty.
    assert absence.return_gap([101, 105], all_served, now=100) is None


def test_return_gap_run_start_and_end_bounds():
    all_served = set(range(0, 200))
    # Run started 6 turns ago (94 < 100 - 5): excluded.
    assert absence.return_gap([10, 94, 97], all_served, now=100) is None
    # Run started 5 turns ago (95 == 100 - 5): included; gap is 11..94 = 84.
    assert absence.return_gap([10, 95, 98], all_served, now=100) == 84
    # Single appearance at now - 5: run ends at now - 5 and starts at now - 5 -> counts.
    assert absence.return_gap([10, 95], all_served, now=100) == 84
    # Last appearance at now - 6: run does not end at the request -> None.
    assert absence.return_gap([10, 94], all_served, now=100) is None


def test_return_gap_step_5_joins_run_and_step_6_splits_it():
    all_served = set(range(0, 200))
    # Step of 5 (95 -> 100) is one run starting at 95 (within 5 of now=100); previous is 10, gap 84.
    assert absence.return_gap([10, 95, 100], all_served, now=100) == 84
    # Two steps of 5 (90 -> 95 -> 100) stay one run starting at 90 (10 turns ago > 5) -> None.
    assert absence.return_gap([10, 90, 95, 100], all_served, now=100) is None
    # Step of 6 (94 -> 100) splits the run: current run is [100], previous is 94, gap is 5 -> None.
    assert absence.return_gap([10, 94, 100], all_served, now=100) is None
    # Unsorted / duplicate / future appearances behave identically to sorted unique <= now.
    assert absence.return_gap([105, 100, 10, 95, 95, 10], all_served, now=100) == 84


@pytest.mark.parametrize(
    ("gap", "expected"),
    [
        (40, "~40 turns"),
        (44, "~40 turns"),
        (45, "~50 turns"),
        (55, "~60 turns"),
        (65, "~70 turns"),
        (94, "~90 turns"),
        (95, "~100 turns"),
        (99, "~100 turns"),
        (124, "~120 turns"),
        (125, "~130 turns"),
    ],
)
def test_back_after_label_rounds_halves_up(gap: int, expected: str):
    assert absence.back_after_label(gap) == expected


def _thread(
    tid: int,
    status: str,
    closed_turn: int | None,
    *,
    by: str = "세라",
    to: str | None = "카이토",
    position: int = 10,
    closed_position: int | None = None,
) -> dict:
    closed_by = None if closed_turn is None and closed_position is None else {
        "turn": closed_turn,
        "position": closed_position,
    }
    return {
        "id": tid,
        "kind": "promise" if status in ("kept", "broken") else "goal",
        "by": by,
        "to": to,
        "text": f"thread-{tid}",
        "position": position,
        "status": status,
        "closed_by": closed_by,
    }


def test_settled_cap_3_bad_before_good_and_newest_first():
    items = [
        _thread(1, "kept", 49, position=10, closed_position=98),
        _thread(2, "broken", 40, position=12, closed_position=80),
        _thread(3, "achieved", 50, position=14, closed_position=100),
        _thread(4, "failed", 46, position=16, closed_position=92),
    ]
    snapshot = list(items)
    result = absence.settled(items, now=50, involved=lambda _: True)
    assert items == snapshot  # input not mutated
    # Bad (failed@46, broken@40) before good (achieved@50); kept@49 capped at SETTLED_MAX=3.
    assert [t["id"] for t in result] == [4, 2, 3]


def test_settled_window_boundaries():
    items = [
        _thread(1, "broken", 34, closed_position=68),  # 16 turns ago -> excluded
        _thread(2, "broken", 35, closed_position=70),  # exactly 15 turns ago -> included
        _thread(3, "kept", 50, closed_position=100),   # at now -> included
        _thread(4, "broken", 51, closed_position=102), # after now -> excluded
    ]
    result = absence.settled(items, now=50, involved=lambda _: True)
    assert [t["id"] for t in result] == [2, 3]


def test_settled_turn_zero_and_position_tiebreak():
    # Closed at turn 0 is valid (not falsy-skipped).
    t0 = _thread(1, "kept", 0, position=0, closed_position=0)
    assert [t["id"] for t in absence.settled([t0], now=10, involved=lambda _: True)] == [1]

    # Same bucket and same closing turn: newest closing position first, then newest thread position.
    same_turn = [
        _thread(1, "broken", 48, position=30, closed_position=96),
        _thread(2, "failed", 48, position=10, closed_position=97),
        _thread(3, "abandoned", 48, position=20, closed_position=97),
    ]
    result = absence.settled(same_turn, now=50, involved=lambda _: True)
    assert [t["id"] for t in result] == [3, 2, 1]

    # When closing position is None (e.g. owner repair), thread position breaks ties.
    repairs_same_turn = [
        _thread(10, "kept", 48, position=5, closed_position=None),
        _thread(11, "paid", 48, position=12, closed_position=None),
        _thread(12, "answered", 48, position=0, closed_position=None),
    ]
    result = absence.settled(repairs_same_turn, now=50, involved=lambda _: True)
    assert [t["id"] for t in result] == [11, 10, 12]


def test_settled_skips_open_uninvolved_missing_close_and_unknown_status():
    items = [
        _thread(1, "open", 49, by="세라"),
        _thread(2, "broken", None, by="세라"),
        _thread(3, "broken", 49, by="하나"),       # involved -> False
        _thread(4, "partial", 49, by="세라"),      # unknown status (NMOS has no partial)
        _thread(5, "cancelled", 49, by="세라"),    # unknown status
        _thread(6, "averted", 48, by="세라"),      # valid
        _thread(7, "abandoned", 45, by="세라"),    # valid (bad -> comes first)
    ]
    result = absence.settled(items, now=50, involved=lambda t: t["by"] == "세라")
    assert [t["id"] for t in result] == [7, 6]


def test_threads_fold_reopens_similar_promise_30_turns_after_close():
    """PHASE-60 S4: a promise restated after its earlier thread closed opens afresh (30 turns later)."""
    rows = [
        {
            "id": 1,
            "turn": 10,
            "position": 20,
            "predicate": "promised",
            "subject": "세라",
            "subject_type": "character",
            "object": "카이토",
            "object_type": "character",
            "value": "등대 앞에서 만나기",
            "polarity": "positive",
            "modality": "actual",
            "source": "narration",
        },
        {
            "id": 2,
            "turn": 12,
            "position": 24,
            "predicate": "fulfilled",
            "subject": "세라",
            "subject_type": "character",
            "object": "카이토",
            "object_type": "character",
            "value": "등대 앞에서 만나기",
            "polarity": "positive",
            "modality": "actual",
            "source": "narration",
        },
        {
            "id": 3,
            "turn": 42,
            "position": 84,
            "predicate": "promised",
            "subject": "세라",
            "subject_type": "character",
            "object": "카이토",
            "object_type": "character",
            "value": "등대 앞에서 만나기",
            "polarity": "positive",
            "modality": "actual",
            "source": "narration",
        },
    ]
    folded, unmatched, _ = threads.fold(rows)
    assert unmatched == []
    assert len(folded) == 2
    assert folded[0]["id"] == 3 and folded[0]["status"] == "open"
    assert folded[1]["id"] == 1 and folded[1]["status"] == "kept"
    assert folded[1]["closed_by"]["turn"] == 12
