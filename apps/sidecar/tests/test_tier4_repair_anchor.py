"""PHASE-67 part 4 (audit D7, owner decision 11b): an owner repair is anchored to the message it was made on.

A repair made by hand must not quietly disappear: deleting an earlier message (every later turn renumbered) or fixing
a typo in another turn keeps it applying; an edit of its own turn detaches it as before, and it is listed with the
reason; a repair made on a continuation the chat abandoned does not fire when a new continuation reaches the same turn
number. A repair written before migration 0044 keeps applying through the legacy rule and a live read records its
anchor once. Synthetic names only.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from memeval import stub_extractor
from nmos_sidecar import repairs
from simchat import SimChat
from test_extraction import drain, facts
from test_generations import LLM, conv_id
from test_sidecar_integration import recall, sync

GOAL = "find the keeper"
LINES = ("Kaito is in the garden.", "Hana is in the hall.", "Hana wants to find the keeper.",
         "Hana keeps a secret from Kaito: the letter is forged.", "Kaito is in the kitchen.", "Mina is in the yard.")


def anchor_chat(go_on: bool = True) -> SimChat:
    """Turns 0-5 (one user message and one reply each), and with `go_on` turn 6, the user's "Go on." (ADR 0008)."""
    chat = SimChat()
    for text in LINES:
        chat.user(text)
        chat.reply("Noted.")
    if go_on:
        chat.user("Go on.")
    return chat


def setup(c, url: str, chat: SimChat) -> str:
    sync(c, chat)
    drain(url, stub_extractor)
    return conv_id(c, chat)


def resync(c, url: str, chat: SimChat) -> None:
    sync(c, chat)
    drain(url, stub_extractor)


def thread(c, cid: str) -> dict:
    return next(t for t in c.get(f"/v1/conversations/{cid}/threads").json() if t["text"] == GOAL)


def secret(c, cid: str) -> dict:
    return next(s for s in c.get(f"/v1/conversations/{cid}/secrets").json() if "forged" in s["text"])


def fact(c, chat: SimChat, subject: str, predicate: str = "located_in") -> dict | None:
    return next((f for f in facts(c, chat) if f["subject"] == subject and f["predicate"] == predicate), None)


def repair(c, cid: str, **body) -> dict:
    res = c.post(f"/v1/conversations/{cid}/repairs", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def listed(c, cid: str) -> dict[str, dict]:
    return {r["id"]: r for r in c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"]}


def four_repairs(c, chat: SimChat, cid: str) -> dict[str, str]:
    """A close (turn 2, from the last turn), a reveal (turn 3, from turn 4), a correction (turn 4, in place) and a
    retraction (turn 5): one of each way a repair names its target and its turn."""
    made = {
        "close": repair(c, cid, kind="thread_close", item=str(thread(c, cid)["id"]), outcome="achieved"),
        "found": repair(c, cid, kind="secret_found_out", item=str(secret(c, cid)["id"]), character="Kaito", turn=4),
        "correct": repair(c, cid, kind="fact_correct", item=str(fact(c, chat, "Kaito")["id"]), new_object="porch"),
        "retract": repair(c, cid, kind="fact_retract", item=str(fact(c, chat, "Mina")["id"])),
    }
    return {k: v["repair"]["id"] for k, v in made.items()}


def all_applied(c, chat: SimChat, cid: str) -> None:
    assert thread(c, cid)["status"] == "achieved"
    assert secret(c, cid)["open"] == []
    assert fact(c, chat, "Kaito")["object"] == "porch"
    assert fact(c, chat, "Mina") is None


def rows(url: str, cid: str) -> list[dict]:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        return conn.execute("SELECT id, kind, target, value, anchor, anchored_at, created_at FROM owner_repair"
                            " WHERE conversation_id = %s ORDER BY created_at, id", (cid,)).fetchall()


def as_written_before(url: str, cid: str) -> None:
    """The chat's repairs as a release before migration 0044 wrote them: the same target and value, no anchor."""
    with psycopg.connect(url) as conn:
        conn.execute("UPDATE owner_repair SET anchor = NULL, anchored_at = NULL WHERE conversation_id = %s", (cid,))


def test_a_new_repair_is_anchored_to_its_messages(migrated):
    chat = anchor_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        ids = four_repairs(c, chat, cid)
    by_id = {str(r["id"]): r for r in rows(migrated, cid)}
    close, found, correct = by_id[ids["close"]], by_id[ids["found"]], by_id[ids["correct"]]
    # the target's turn anchor (its reply), and the first and last message of the turn it applies from
    assert close["anchor"]["target"]["message"] == chat.messages[5]["chatId"]
    assert close["anchor"]["apply"] == {"messages": [chat.messages[12]["chatId"]]}  # turn 6: "Go on." alone
    assert found["anchor"]["apply"] == {"messages": [chat.messages[8]["chatId"], chat.messages[9]["chatId"]]}
    assert correct["anchor"]["target"]["message"] == chat.messages[9]["chatId"]
    assert all(r["anchored_at"] == r["created_at"] for r in by_id.values())
    # the stored target and value are what a release before 0044 stored: an older reader reads them as before
    assert close["value"] == {"outcome": "achieved", "turn": 6} and close["target"]["turn"] == 2


def test_deleting_an_earlier_message_keeps_every_later_repair(migrated):
    chat = anchor_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        ids = four_repairs(c, chat, cid)
        all_applied(c, chat, cid)
        chat.delete(3)
        chat.delete(2)  # turn 1 is gone: turns 2-6 are 1-5 now
        resync(c, migrated, chat)
        assert thread(c, cid)["turn"] == 1
        all_applied(c, chat, cid)
        out = listed(c, cid)
        assert all(out[i]["applied"] is not None and "detached" not in out[i] for i in ids.values())


def test_the_same_deletion_detaches_a_legacy_repair_it_renumbers(migrated):
    """The defect (D7 item 1) the anchor fixes, kept as a contrast: without one, the renumbered repairs stop
    matching at once; nothing is deleted, and no anchor is recorded for a repair that matches nothing."""
    chat = anchor_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        ids = four_repairs(c, chat, cid)
        chat.delete(3)
        chat.delete(2)
        resync(c, migrated, chat)
        as_written_before(migrated, cid)
        assert thread(c, cid)["status"] == "open"
        out = listed(c, cid)
        assert out[ids["close"]]["applied"] is None and out[ids["close"]]["removed_at"] is None
    assert [r["anchor"] for r in rows(migrated, cid) if str(r["id"]) == ids["close"]] == [None]


def test_a_typo_fixed_in_another_turn_keeps_the_repairs_after_it(migrated):
    chat = anchor_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        ids = four_repairs(c, chat, cid)
        chat.edit(2, "Hana is in the hall!")  # turn 1: the window hash of turns 1-4 moves, their own turns do not
        resync(c, migrated, chat)
        all_applied(c, chat, cid)
        assert all(listed(c, cid)[i]["applied"] is not None for i in ids.values())


def test_an_edit_of_its_own_turn_detaches_a_repair_and_lists_why(migrated):
    chat = anchor_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        ids = four_repairs(c, chat, cid)
        chat.edit(5, "Noted, at dawn.")  # turn 2's reply: the turn the closed thread was stated in
        resync(c, migrated, chat)
        assert thread(c, cid)["status"] == "open"
        out = listed(c, cid)
        assert out[ids["close"]]["applied"] is None and out[ids["close"]]["detached"] == "edited"
        assert out[ids["found"]]["applied"] is not None  # the other turns' repairs are untouched
        chat.edit(5, "Noted.")  # the turn reads as it did: the repair is back
        resync(c, migrated, chat)
        assert thread(c, cid)["status"] == "achieved"


def test_a_repair_made_on_an_abandoned_continuation_does_not_fire_on_a_new_one(migrated):
    chat = anchor_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        close = repair(c, cid, kind="thread_close", item=str(thread(c, cid)["id"]))["repair"]["id"]  # from turn 6
        assert thread(c, cid)["status"] == "achieved"
        del chat.messages[8:]  # the owner rewinds the chat to the end of turn 3
        resync(c, migrated, chat)
        assert thread(c, cid)["status"] == "open"
        assert listed(c, cid)[close]["detached"] == "turn_gone"
        for text in ("Kaito is in the cellar.", "Mina is in the attic."):  # a different continuation: turns 4, 5
            chat.user(text)
            chat.reply("Noted.")
        chat.user("Go on.")  # turn 6 again
        resync(c, migrated, chat)
        assert thread(c, cid)["status"] == "open"
        out = listed(c, cid)[close]
        assert out["applied"] is None and out["detached"] == "turn_gone" and out["removed_at"] is None
        as_written_before(migrated, cid)  # the defect (D7 item 2): the legacy rule fires it on the new continuation
        assert thread(c, cid)["status"] == "achieved"


def test_a_reroll_of_the_turn_it_applies_from_keeps_the_repair(migrated):
    chat = anchor_chat(go_on=False)  # the chat ends with turn 5's reply
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        close = repair(c, cid, kind="thread_close", item=str(thread(c, cid)["id"]))
        assert close["repair"]["value"]["turn"] == 5
        chat.reroll("Noted, again.")  # a new message id for turn 5's reply; its user message stays
        resync(c, migrated, chat)
        assert thread(c, cid)["status"] == "achieved"


def test_a_legacy_repair_keeps_applying_and_one_read_records_its_anchor(migrated):
    """Item 3: a database whose repairs were written before migration 0044 (the same rows, no anchor)."""
    chat = anchor_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        ids = four_repairs(c, chat, cid)
        anchors = {str(r["id"]): r["anchor"] for r in rows(migrated, cid)}
        as_written_before(migrated, cid)
        assert all(r["anchor"] is None for r in rows(migrated, cid))
        out = listed(c, cid)  # one request: everything applies as before, and each gets its anchor
        assert all(out[i]["applied"] is not None for i in ids.values())
        after = {str(r["id"]): r for r in rows(migrated, cid)}
        assert {i: after[i]["anchor"] for i in ids.values()} == anchors
        assert all(after[i]["anchored_at"] > after[i]["created_at"] for i in ids.values())
        stamped = {i: after[i]["anchored_at"] for i in ids.values()}
        listed(c, cid)  # idempotent: a later read writes nothing
        assert {str(r["id"]): r["anchored_at"] for r in rows(migrated, cid)} == stamped
        chat.delete(3)
        chat.delete(2)  # and so it survives the next renumbering
        resync(c, migrated, chat)
        all_applied(c, chat, cid)


def test_a_replay_from_before_an_anchor_was_recorded_reads_the_legacy_target(migrated):
    chat = anchor_chat()
    ask = "Hana, did you find the keeper?"
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        four_repairs(c, chat, cid)
        before = recall(c, chat, ask, budget=2000)
        as_written_before(migrated, cid)
        middle = recall(c, chat, ask, budget=2000)  # legacy then; this read records the anchors
        listed(c, cid)
        for trace in (before, middle):
            replayed = c.get(f"/v1/trace/{trace['trace_id']}/replay").json()
            assert replayed["status"] == "ok" and replayed["reproduced"] is True


def test_reanchor_moves_an_anchor_onto_a_branchs_messages():
    anchor = {"target": {"message": "a5", "revision": "r", "turn_revisions": "t"}, "apply": {"messages": ["a12", "a13"]}}
    moved = repairs.reanchor(anchor, {"a5": "b5", "a12": "b12", "a13": "b13"})
    assert moved == {"target": {"message": "b5", "revision": "r", "turn_revisions": "t"},
                     "apply": {"messages": ["b12", "b13"]}}
    assert repairs.reanchor(anchor, {"a5": "b5"}) is None  # it applies from a turn after the branch point
    assert repairs.reanchor(anchor, {"a12": "b12", "a13": "b13"}) is None  # its target is outside the prefix
    assert repairs.reanchor(None, {"a5": "b5"}) is None  # a legacy repair: its target is copied as it is
