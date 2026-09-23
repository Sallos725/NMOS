"""ADR 0008: turn layout over head membership (pure)."""

from __future__ import annotations

from nmos_sidecar.reconcile import Entry, turn_layout


def e(i: int, role: str, **kw) -> Entry:
    return Entry(host_logical_id=f"m{i}", revision_hash=f"h{i}", role=role, **kw)


def turns(layout):
    return [t for t, _ in layout]


def anchors(layout):
    return [i for i, (_, h) in enumerate(layout) if h]


def test_greeting_is_turn_zero_and_each_exchange_is_a_turn():
    members = [e(0, "char"), e(1, "user"), e(2, "char"), e(3, "user"), e(4, "char"), e(5, "user")]
    layout = turn_layout(members, 3)
    assert turns(layout) == [0, 1, 1, 2, 2, 3]
    # The anchor is the last reply of a turn; the tail user message has no reply, so no anchor.
    assert anchors(layout) == [0, 2, 4]


def test_runs_of_user_and_reply_messages_form_one_turn():
    members = [e(0, "user"), e(1, "user"), e(2, "char"), e(3, "char"), e(4, "user"), e(5, "char")]
    layout = turn_layout(members, 3)
    assert turns(layout) == [0, 0, 0, 0, 1, 1]
    assert anchors(layout) == [3, 5]


def test_comments_disabled_and_cut_messages_are_not_members():
    members = [e(0, "user"), e(1, "char"), e(2, "user", disabled="allBefore"), e(3, "char"),
               e(4, "user"), e(5, "char", is_comment=True), e(6, "char", disabled=True), e(7, "char"),
               e(8, "user", disabled="true"), e(9, "user")]
    layout = turn_layout(members, 3)
    # Everything up to and including the allBefore cut is inactive (D15).
    assert turns(layout) == [None, None, None, 0, 1, None, None, 1, None, 2]
    assert anchors(layout) == [3, 7]


def test_hash_covers_the_turn_and_k_previous_turns():
    base = [e(0, "user"), e(1, "char"), e(2, "user"), e(3, "char"), e(4, "user"), e(5, "char"), e(6, "user")]
    before = turn_layout(base, 1)
    edited = list(base)
    edited[0] = Entry("m0", "h0-edited", "user")
    after = turn_layout(edited, 1)
    # Turn 0 changed; turn 1 has it as context (K=1); turn 2 does not see it.
    assert [before[i][1] == after[i][1] for i in (1, 3, 5)] == [False, False, True]


def test_appending_a_second_reply_moves_the_anchor():
    members = [e(0, "user"), e(1, "char")]
    assert anchors(turn_layout(members, 3)) == [1]
    grown = turn_layout(members + [e(2, "char")], 3)
    assert anchors(grown) == [2] and turns(grown) == [0, 0, 0]

