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
    anchor = {"target": {"message": "a5", "revision": "r5", "turn_revisions": ["r4", "r5"]},
              "apply": {"messages": ["a12", "a13"]}}
    mapping = {"a5": "b5", "r4": "s4", "r5": "s5", "a12": "b12", "a13": "b13"}
    assert repairs.reanchor(anchor, mapping) == {
        "target": {"message": "b5", "revision": "s5", "turn_revisions": ["s4", "s5"]},
        "apply": {"messages": ["b12", "b13"]}}
    assert repairs.reanchor(anchor, {k: v for k, v in mapping.items() if k != "a13"}) is not None  # it begins inside
    assert repairs.reanchor(anchor, {k: v for k, v in mapping.items() if k != "a12"}) is None  # applies after it
    assert repairs.reanchor(anchor, {k: v for k, v in mapping.items() if k != "r5"}) is None  # edited in the origin
    assert repairs.reanchor(None, mapping) is None  # a legacy repair: its target is copied as it is


# --- item 4: a correction keeps its row's message, and states only what it gives ------------------------------------

def view_of(url: str, cid: str) -> dict:
    from conftest import active_generation
    from nmos_sidecar.facts import memory_view
    with psycopg.connect(url, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
        return memory_view(conn, head, active_generation(conn, "extract").key, told=True)


def test_a_correction_keeps_its_message_and_inherits_no_feeling_or_cause(migrated):
    chat = SimChat()
    for text in ("Yui is angry at Kaito because he forgot the festival.", "Kaito is in the garden.",
                 "Mina is a guard."):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        with psycopg.connect(migrated) as conn:  # a feeling detail as extract-v18 writes one (PHASE-58)
            conn.execute("UPDATE assertion SET feeling = '{\"intensity\": \"strong\"}' WHERE predicate = 'feels_toward'")
        angry = fact(c, chat, "Yui", "feels_toward")
        assert angry["because"] == "he forgot the festival"
        res = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_correct", "item": str(angry["id"]),
                                                               "new_because": "he forgot the festival"})
        assert res.status_code == 422 and "cause" in res.json()["detail"]  # nothing differs
        repair(c, cid, kind="fact_correct", item=str(angry["id"]), new_value="grateful")
        mine = next(f for f in view_of(migrated, cid)["facts"] if f["subject"] == "Yui")
        assert mine["owner"] and mine["value"] == "grateful"
        assert mine.get("because") is None and "feeling" not in mine  # nothing of the row it replaced
        assert mine["host_logical_id"] == chat.messages[1]["chatId"]  # turn 0's reply: in context, not sent again
        kaito = fact(c, chat, "Kaito")
        repair(c, cid, kind="fact_correct", item=str(kaito["id"]), new_object="porch", new_because="the rain")
        k = next(f for f in view_of(migrated, cid)["facts"] if f["subject"] == "Kaito")
        assert k["because"] == "the rain" and k["host_logical_id"] == chat.messages[3]["chatId"]
        moved = repair(c, cid, kind="fact_correct", item=str(fact(c, chat, "Mina", "identity")["id"]), new_value="spy",
                       turn=3)
        later = next(f for f in view_of(migrated, cid)["facts"] if f.get("repair") == moved["repair"]["id"])
        assert later["turn"] == 3 and later["host_logical_id"] is None  # the owner's word about a later turn


# --- item 5: what else the owner can repair ---------------------------------------------------------------------------

def test_the_owner_adds_a_statement_on_a_message_and_it_follows_the_message(migrated):
    chat = anchor_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        msg = chat.messages[11]["chatId"]  # turn 5's reply

        def add(**fact) -> dict:
            return c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_add", "item": msg, "fact": fact})

        assert "not one memory states" in add(predicate="knows_secretly", subject="Mina").json()["detail"]
        assert "not one memory states" in add(predicate="also_called", subject="Mina", value="Mimi").json()["detail"]
        assert "missing object" in add(predicate="located_in", subject="Mina").json()["detail"]
        assert "states that already" in add(predicate="located_in", subject="Mina", object="yard",
                                            object_type="place").json()["detail"]
        res = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_add", "item": "no-such-message",
                                                               "fact": {"predicate": "has_status", "subject": "Mina",
                                                                        "value": "tired"}})
        assert res.status_code == 422 and "no message" in res.json()["detail"]
        out = add(predicate="possesses", subject="Mina", object="lantern", object_type="item",
                  hidden_from=["Kaito"])
        assert out.status_code == 200, out.text
        rid = out.json()["repair"]["id"]
        assert out.json()["repair"]["anchor"]["target"]["message"] == msg and out.json()["applied"] is not None
        lantern = fact(c, chat, "Mina", "possesses")
        assert lantern["object"] == "lantern" and lantern["turn"] == 5 and lantern["hidden_from"] == ["Kaito"]
        assert any("lantern" in s["text"] and s["open"] == ["Kaito"] for s in
                   c.get(f"/v1/conversations/{cid}/secrets").json())  # a statement kept from Kaito is a secret
        assert next(f for f in view_of(migrated, cid)["facts"]
                    if f["predicate"] == "possesses")["host_logical_id"] == msg
        chat.delete(1)
        chat.delete(0)  # turn 0 gone: the message's turn is 4 now
        resync(c, migrated, chat)
        assert fact(c, chat, "Mina", "possesses")["turn"] == 4
        assert c.post(f"/v1/conversations/{cid}/repairs/{rid}/remove").status_code == 200
        assert fact(c, chat, "Mina", "possesses") is None


def test_a_name_is_kept_from_a_character_or_taken_back(migrated):
    chat = anchor_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        hall = fact(c, chat, "Hana")
        assert c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_hidden", "item": str(hall["id"]),
                                                               "character": "Kaito"}).status_code == 422  # which side
        out = repair(c, cid, kind="fact_hidden", item=str(hall["id"]), character="Kaito", hidden=True)
        assert out["applied"] == str(hall["id"]) and fact(c, chat, "Hana")["hidden_from"] == ["Kaito"]
        assert any(s["text"].startswith("Hana located in hall") and s["open"] == ["Kaito"]
                   for s in c.get(f"/v1/conversations/{cid}/secrets").json())
        forged = next(f for f in facts(c, chat) if f.get("hidden_from") == ["Kaito"] and "forged" in (f["value"] or ""))
        repair(c, cid, kind="fact_hidden", item=str(forged["id"]), character="Kaito", hidden=False)
        assert not any("forged" in s["text"] and s["open"]  # the letter is no longer kept from Kaito
                       for s in c.get(f"/v1/conversations/{cid}/secrets").json())
        res = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_hidden", "item": str(forged["id"]),
                                                               "character": "Kaito", "hidden": False})
        assert res.status_code == 422 and "not kept" in res.json()["detail"]


def test_a_claim_is_retracted_as_a_fact_is(migrated):
    chat = SimChat()
    chat.user('Kaito says: "I am a knight."')
    chat.reply("Noted.")
    chat.user("Go on.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        [claim] = view_of(migrated, cid)["claims"]
        out = repair(c, cid, kind="fact_retract", item=str(claim["id"]))
        assert out["applied"] == str(claim["id"]) and view_of(migrated, cid)["claims"] == []


def test_a_told_row_is_taken_back(migrated):
    from test_extract_v19_read import TOLD_VALUE, complete as told_complete
    from test_extract_v18 import chat_of
    from test_extract_v19 import SCENE
    chat = chat_of(SCENE)
    with make_client(migrated, **LLM, extract_compiler="extract-v19") as c:
        sync(c, chat)
        drain(migrated, told_complete)
        cid = conv_id(c, chat)
        [told] = view_of(migrated, cid)["told"]
        assert told["value"] == TOLD_VALUE
        out = repair(c, cid, kind="told_retract", item=str(told["id"]))
        assert out["applied"] == str(told["id"]) and out["repair"]["anchor"]["target"]["message"]
        assert view_of(migrated, cid)["told"] == []  # packet-v20's told lines read this list
        assert c.post(f"/v1/conversations/{cid}/repairs/{out['repair']['id']}/remove").status_code == 200
        assert len(view_of(migrated, cid)["told"]) == 1


def test_a_held_role_ending_is_dismissed_from_needs_attention(migrated):
    from test_role_end_confirmation import MOVED, tenancy
    complete, _ = tenancy("no")
    chat = SimChat()
    chat.user("하나는 카이토의 집에 세 들어 산다.")
    chat.reply("카이토는 월세 봉투를 받아 들었다.")
    for t in range(2):
        chat.user(f"Idle chatter {t} about clouds.")
        chat.reply("Noted.")
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", extract_compiler="extract-v16") as c:
        sync(c, chat)
        drain(migrated, complete)
        chat.user(MOVED)
        chat.reply("카이토는 빈 다락방을 정리했다.")
        chat.user("Go on.")
        sync(c, chat)
        drain(migrated, complete)
        cid = conv_id(c, chat)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            held = conn.execute("SELECT id FROM assertion WHERE status = 'pending' AND predicate = 'role_toward'"
                                " AND polarity = 'negative'").fetchone()["id"]
        page = lambda: c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text  # noqa: E731
        assert "Role endings held" in page()
        assert c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "attention_dismiss", "item": str(held)}
                      ).status_code == 422  # say what
        out = repair(c, cid, kind="attention_dismiss", item=str(held), attention="role_held")
        assert out["applied"] == str(held) and listed(c, cid)[out["repair"]["id"]]["applied"] == str(held)
        assert "Role endings held" not in page()
        again = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "attention_dismiss", "item": str(held),
                                                                 "attention": "role_held"})
        assert again.status_code == 422  # dismissed already: it needs no look
        assert c.post(f"/v1/conversations/{cid}/repairs/{out['repair']['id']}/remove").status_code == 200
        assert "Role endings held" in page()


def test_the_new_kinds_go_through_a_batch_and_its_undo(migrated):
    chat = anchor_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        items = [{"kind": "fact_hidden", "item": str(fact(c, chat, "Hana")["id"]), "character": "Mina", "hidden": True},
                 {"kind": "fact_add", "item": chat.messages[9]["chatId"],
                  "fact": {"predicate": "has_status", "subject": "Kaito", "value": "tired"}}]
        res = c.post(f"/v1/conversations/{cid}/repairs/batch", json={"items": items})
        assert res.status_code == 200, res.text
        assert fact(c, chat, "Hana")["hidden_from"] == ["Mina"] and fact(c, chat, "Kaito", "has_status")["value"] == "tired"
        assert c.post(f"/v1/conversations/{cid}/repairs/batch/{res.json()['batch']}/remove").status_code == 200
        assert fact(c, chat, "Hana")["hidden_from"] is None and fact(c, chat, "Kaito", "has_status") is None


# --- export / restore: the anchor round-trips; an archive from before migration 0044 restores ----------------------

def test_an_anchor_round_trips_through_an_archive_and_an_older_archive_restores(migrated, database_url_factory,
                                                                                tmp_path):
    from nmos_sidecar import archive
    chat = anchor_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        ids = four_repairs(c, chat, cid)
    path = tmp_path / f"new{archive.SUFFIX}"
    archive.export_file(migrated, str(path))
    target = database_url_factory()
    archive.restore_file(target, str(path))
    assert [(r["id"], r["anchor"], r["anchored_at"]) for r in rows(target, cid)] == \
        [(r["id"], r["anchor"], r["anchored_at"]) for r in rows(migrated, cid)]
    with make_client(target, **LLM) as c:
        all_applied(c, chat, cid)
        chat.delete(3)
        chat.delete(2)  # the restored anchors name the same messages: a renumbering keeps them
        resync(c, target, chat)
        all_applied(c, chat, cid)
    # An archive written before migration 0044: its owner_repair rows have no anchor columns at all.
    import io
    import zipfile
    from test_restore import reseal
    old = reseal(path, tmp_path / f"old{archive.SUFFIX}", "owner_repair",
                 lambda row: {k: v for k, v in row.items() if k not in ("anchor", "anchored_at")})
    assert b'"anchor"' not in zipfile.ZipFile(io.BytesIO(old.read_bytes())).read("tables/owner_repair.jsonl")
    again = database_url_factory()
    archive.restore_file(again, str(old))
    assert all(r["anchor"] is None for r in rows(again, cid))
    with make_client(again, **LLM) as c:
        assert all(listed(c, cid)[i]["applied"] is not None for i in ids.values())  # legacy, and anchored now
    assert all(r["anchor"] for r in rows(again, cid))
