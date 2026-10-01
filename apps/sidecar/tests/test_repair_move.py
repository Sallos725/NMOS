"""Phase 26 (docs/phases/PHASE-26.md, ADR 0060): a repair that matches nothing now suggests the items it may now mean,
and the owner moves it to one in one action. Synthetic names only."""

from __future__ import annotations

import pytest

from conftest import make_client
from memeval import stub_extractor
from nmos_sidecar import inspector, repairs
from simchat import SimChat
from test_extraction import drain
from test_generations import LLM
from test_repairs import fact, repair, setup, thread
from test_sidecar_integration import recall, sync

# A new model's words for one goal and one place, and no quotes: the repair finds neither by text nor by quote, so it
# matches nothing (as on the owner's copy, PHASE-26 "Evidence"). No quote at all, since the stub's sentences share
# their first words ("Hana wants to ") and a quote would name another goal of the same maker (ADR 0044 amendment 2).
REWORDED = {"find the keeper": "look for the lighthouse warden", "harbor": "pier"}


def worded_apart(system: str, user: str) -> tuple[dict, str]:
    out, raw = stub_extractor(system, user)
    items = []
    for a in out["assertions"]:
        a = {**a, "evidence": None}
        if a.get("value") in REWORDED:
            a["value"] = REWORDED[a["value"]]
        elif a.get("object") in REWORDED:
            a["object"] = REWORDED[a["object"]]
        items.append(a)
    return {**out, "assertions": items}, raw


def goals_chat() -> SimChat:
    chat = SimChat()
    for text in ("Hana wants to find the keeper.", "Hana wants to bake bread.", "Kaito wants to sail home."):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")
    return chat


def listed(c, cid: str) -> dict[str, dict]:
    return {str(r["id"]): r for r in c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"]}


def orphan_a_close(migrated):
    """A chat whose close of Hana's first goal matches nothing after a new generation reworded that goal."""
    chat = goals_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        made = repair(c, cid, kind="thread_close", item=str(thread(c, cid)["id"]))["repair"]
    return chat, cid, str(made["id"])


def test_a_close_that_matches_nothing_suggests_the_maker_s_open_goals_and_moves_in_one_action(migrated):
    chat, cid, old = orphan_a_close(migrated)
    with make_client(migrated, extract_backfill=100, llm_url=LLM["llm_url"], llm_model="fake-2") as c:
        assert drain(migrated, worded_apart) > 0
        assert listed(c, cid)[old]["applied"] is None
        warden = thread(c, cid, "look for the lighthouse warden")
        bread = thread(c, cid, "bake bread")
        assert warden["status"] == "open"
        page = c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
        # Hana's open goals, nearest turn first; Kaito's goal is another maker's and never suggested
        assert page.index("look for the lighthouse warden") < page.index("bake bread", page.index("may now mean"))
        assert f'data-repair="repair_move:{old}:{warden["id"]}"' in page
        assert f'data-repair="repair_move:{old}:{bread["id"]}"' in page
        assert "repair_move" not in page[page.index("sail home") - 300:page.index("sail home") + 300]
        before = recall(c, chat, "Hana looks around.", budget=2000)

        base = f"/v1/conversations/{cid}/repairs/{old}"
        preview = c.post(f"{base}/move/preview", json={"item": str(warden["id"])}).json()
        assert preview["changes"] and preview["before"] == preview["after"] == []
        assert [(x["kind"], x["thread"]["text"], x["status"]) for x in preview["lines"]] == [
            ("thread_status", "look for the lighthouse warden", "achieved")]
        # nothing written by a preview
        assert thread(c, cid, "look for the lighthouse warden")["status"] == "open"

        moved = c.post(f"{base}/move", json={"item": str(warden["id"]), "expect": preview["fingerprint"]}).json()
        new = moved["repair"]["id"]
        assert moved["moved_from"] == old and moved["applied"] == str(warden["id"]) and moved["locks"] == 0
        now = thread(c, cid, "look for the lighthouse warden")
        assert (now["status"], now["repair"]) == ("achieved", str(new))
        rows = listed(c, cid)
        assert rows[old]["removed_at"] is not None
        assert str(rows[str(new)]["moved_from"]) == old and rows[str(new)]["value"]["outcome"] == "achieved"
        assert "may now mean" not in c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text

        # a request recorded before the move replays as it was (ADR 0027)
        again = c.get(f"/v1/trace/{before['trace_id']}/replay").json()
        assert again["reproduced"] is True and again["text"] == before["packet"]["text"]

        # undo takes the moved repair back; the one it moved from stays removed, so nothing applies twice
        assert c.post(f"/v1/conversations/{cid}/repairs/{new}/remove").status_code == 200
        assert thread(c, cid, "look for the lighthouse warden")["status"] == "open"
        assert listed(c, cid)[old]["removed_at"] is not None


def test_a_move_from_a_stale_preview_is_refused_and_only_candidates_are_taken(migrated):
    chat, cid, old = orphan_a_close(migrated)
    with make_client(migrated, extract_backfill=100, llm_url=LLM["llm_url"], llm_model="fake-2") as c:
        drain(migrated, worded_apart)
        warden = thread(c, cid, "look for the lighthouse warden")
        base = f"/v1/conversations/{cid}/repairs/{old}"
        preview = c.post(f"{base}/move/preview", json={"item": str(warden["id"])}).json()
        repair(c, cid, kind="thread_close", item=str(thread(c, cid, "bake bread")["id"]))  # memory changes meanwhile
        stale = c.post(f"{base}/move", json={"item": str(warden["id"]), "expect": preview["fingerprint"]})
        assert stale.status_code == 409 and stale.json()["detail"]["preview"]["fingerprint"] != preview["fingerprint"]
        assert listed(c, cid)[old]["removed_at"] is None  # nothing moved
        kaito = thread(c, cid, "sail home")  # another maker's goal: not a candidate
        refused = c.post(f"{base}/move", json={"item": str(kaito["id"])})
        assert refused.status_code == 422 and "not one this repair may now mean" in refused.text
        assert c.post(f"/v1/conversations/{cid}/repairs/00000000-0000-7000-8000-000000000000/move",
                      json={"item": str(warden["id"])}).status_code == 404


def place_chat() -> SimChat:
    chat = SimChat()
    for text in ("Hana is in the harbor.", "Kaito is in the library."):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")
    return chat


def test_a_correction_moves_with_its_lock(migrated):
    chat = place_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        harbor = next(f for f in c.get(f"/v1/conversations/{cid}/facts", params={"history": True}).json()
                      if f["predicate"] == "located_in" and f["object"] == "harbor")
        corrected = repair(c, cid, kind="fact_correct", item=str(harbor["id"]), new_object="beach")["repair"]
        owned = next(f for f in c.get(f"/v1/conversations/{cid}/facts", params={"history": True}).json()
                     if f.get("owner") and f["object"] == "beach")
        lock = repair(c, cid, kind="fact_lock", item=str(owned["id"]))["repair"]
    with make_client(migrated, extract_backfill=100, llm_url=LLM["llm_url"], llm_model="fake-2") as c:
        drain(migrated, worded_apart)
        rows = listed(c, cid)
        assert rows[str(corrected["id"])]["applied"] is None and rows[str(lock["id"])]["applied"] is None
        pier = next(f for f in c.get(f"/v1/conversations/{cid}/facts", params={"history": True}).json()
                    if f["predicate"] == "located_in" and f["object"] == "pier")
        base = f"/v1/conversations/{cid}/repairs/{corrected['id']}"
        preview = c.post(f"{base}/move/preview", json={"item": str(pier["id"])}).json()
        moved = c.post(f"{base}/move", json={"item": str(pier["id"]), "expect": preview["fingerprint"]}).json()
        assert moved["locks"] == 1 and moved["applied"] is not None
        rows = listed(c, cid)
        relocked = next(r for r in rows.values() if r["kind"] == "fact_lock" and r["removed_at"] is None)
        assert str(relocked["moved_from"]) == str(lock["id"]) and rows[str(lock["id"])]["removed_at"] is not None
        assert relocked["target"]["repair"] == str(moved["repair"]["id"]) and relocked["applied"] is not None


# --- candidates and the move's plan, without a database --------------------------------------------------------------

def th(i: int, by: str, text: str, turn: int, status: str = "open", kind: str = "goal", **kw) -> dict:
    return {"id": f"t{i}", "kind": kind, "by": by, "to": None, "text": text, "turn": turn, "status": status, **kw}


def close(target_turn: int = 4, text: str = "find the keeper", evidence: str | None = None, **value) -> dict:
    return {"id": "r1", "kind": "thread_close", "applied": None, "note": "dawn",
            "target": {"turn": target_turn, "turn_hash": "h", "kind": "goal", "by": "Hana", "to": None, "text": text,
                       "evidence": evidence},
            "value": {"outcome": "achieved", "turn": target_turn, **value}}


def test_candidates_are_of_the_same_head_and_state_in_a_total_order_at_most_three():
    view = {"resolution": None, "threads": [
        th(1, "Hana", "bake bread", 9), th(2, "Hana", "find the old keeper", 2), th(3, "Kaito", "find the keeper", 4),
        th(4, "Hana", "find the keeper", 4, status="achieved"), th(5, "Hana", "visit the keeper", 6, repair="r9"),
        th(6, "Hana", "water the plants", 3), th(7, "Hana", "climb the tower", 5, evidence="She swore to climb the tower"),
        th(8, "Hana", "aaa", 5), th(9, "Hana", "find the keeper", 4, kind="question")]}
    got = [x["id"] for x in repairs.candidates(close(evidence="She swore to climb the tower at dawn"), view)]
    # the quote first; then the closer text; another maker, a closed goal, one held by a repair, another kind: never
    assert got == ["t7", "t2", "t6"]
    # without a quote: the closer text, then t6 and t7 tie on text and distance (1), so the earlier turn
    assert [x["id"] for x in repairs.candidates(close(), view)] == ["t2", "t6", "t7"]
    # ties on text break by distance from the target's turn, then the earlier turn, then the text
    tied = {"resolution": None, "threads": [th(1, "Hana", "zzz", 6), th(2, "Hana", "yyy", 2), th(3, "Hana", "xxx", 6)]}
    assert [x["id"] for x in repairs.candidates(close(text="find"), tied)] == ["t2", "t3", "t1"]


def test_no_candidates_for_an_applied_or_edited_repair_a_split_or_a_restore():
    view = {"resolution": None, "threads": [th(1, "Hana", "find the old keeper", 4)]}
    assert repairs.candidates(close(), view)
    assert repairs.candidates({**close(), "applied": "t1"}, view) == []
    assert repairs.candidates({**close(), "edited": True}, view) == []
    for kind in ("name_split", "fact_restore"):
        assert repairs.candidates({**close(), "kind": kind}, view) == []


def test_a_secret_candidate_must_still_be_kept_from_or_over_for_the_character():
    def sec(i: int, open_: list[str], ended: dict, text: str = "Hana knows: the letter is forged") -> dict:
        return {"id": i, "predicate": "knows", "subject": "Hana", "object": None, "text": text, "turn": 3,
                "open": open_, "ended": ended}
    view = {"resolution": None, "assertions": [], "secrets": [sec(1, ["Kaito"], {}), sec(2, ["Mira"], {}),
                                                              sec(3, [], {"Kaito": {"turn": 5}})]}
    found = {"id": "r2", "kind": "secret_found_out", "applied": None, "target": {
        "turn": 3, "turn_hash": "h", "subject": "Hana", "predicate": "knows", "object": None, "holders": [],
        "text": "Hana knows: the letter was forged", "evidence": None}, "value": {"character": "Kaito", "turn": 6}}
    assert [x["id"] for x in repairs.candidates(found, view)] == [1]
    assert [x["id"] for x in repairs.candidates({**found, "kind": "secret_keep"}, view)] == [3]


def test_fact_candidates_follow_the_head_and_a_lock_on_a_correction_has_none():
    def f(i: int, obj: str, **kw) -> dict:
        return {"id": i, "predicate": "located_in", "source": "narration", "subject": "Hana", "subject_type": "character",
                "object": obj, "object_type": "place", "value": None, "turn": 2, **kw}
    view = {"resolution": None, "facts": [f(1, "the pier"), f(2, "the pier", owner=True), f(3, "the pier",
                                                                                               subject="Kaito")],
            "assertions": [f(4, "the pier", canon="card:desc", turn=-1), f(5, "the pier", canon="card:desc", turn=-1,
                                                                            locked="r7")]}
    target = {"turn": 2, "turn_hash": "h", "predicate": "located_in", "source": "narration", "subject": "Hana",
              "subject_type": "character", "object": "the pier", "object_type": "place", "text": "x", "evidence": None}
    retract = {"id": "r3", "kind": "fact_retract", "applied": None, "target": target, "value": {}}
    assert [x["id"] for x in repairs.candidates(retract, view)] == [1]
    # a place is one current value per subject: a new generation's other place is a candidate; a relationship's
    # other character is another fact
    elsewhere = {**view, "facts": [f(1, "the old pier")]}
    assert [x["id"] for x in repairs.candidates(retract, elsewhere)] == [1]
    rel = {**target, "predicate": "relationship", "object": "Kaito", "object_type": "character"}
    rel_view = {"resolution": None, "facts": [f(6, "Mira", predicate="relationship", object_type="character", value="friend")]}
    assert repairs.candidates({**retract, "target": rel}, rel_view) == []
    lock = {"id": "r4", "kind": "fact_lock", "applied": None, "target": {**target, "turn": -1}, "value": {}}
    assert [x["id"] for x in repairs.candidates(lock, view)] == [4]
    on_correction = {**lock, "target": {"repair": "r5", "turn": 2, "predicate": "located_in", "subject": "Hana"}}
    assert repairs.candidates(on_correction, view) == []


def test_a_move_keeps_its_turn_when_the_item_allows_it_and_else_takes_the_earliest_it_allows():
    view = {"resolution": None, "threads": [th(1, "Hana", "find the old keeper", 6), th(2, "Hana", "find a keeper", 1)]}
    target, value = repairs.plan_move(close(target_turn=4), "t1", view, last_turn=9)
    assert value == {"outcome": "achieved", "turn": 6} and target["text"] == "find the old keeper"
    _, value = repairs.plan_move(close(target_turn=4), "t2", view, last_turn=9)
    assert value["turn"] == 4  # the old turn, which the item allows
    with pytest.raises(repairs.RepairError, match="not one this repair may now mean"):
        repairs.plan_move(close(), "t9", view, last_turn=9)
    with pytest.raises(repairs.RepairError, match="applies to an item now"):
        repairs.plan_move({**close(), "applied": "t1"}, "t1", view, last_turn=9)


def test_the_inspector_lists_suggestions_under_the_repair_that_matches_nothing():
    rep = {**close(), "removed_at": None}
    rows = inspector._attention({"threads": []}, [rep], None, "en",
                                {"r1": [th(1, "Hana", "find the old keeper", 6)]})
    assert len(rows) == 2 and "matches nothing now" in rows[0][0] and "may now mean" in rows[1][0]
    assert "Hana: find the old keeper" in rows[1][1] and 'data-repair="repair_move:r1:t1"' in rows[1][3]


def test_an_archive_with_a_moved_repair_restores_with_it(migrated, database_url_factory, tmp_path):
    from nmos_sidecar import archive

    chat, cid, old = orphan_a_close(migrated)
    with make_client(migrated, extract_backfill=100, llm_url=LLM["llm_url"], llm_model="fake-2") as c:
        drain(migrated, worded_apart)
        warden = thread(c, cid, "look for the lighthouse warden")
        new = c.post(f"/v1/conversations/{cid}/repairs/{old}/move", json={"item": str(warden["id"])}).json()["repair"]
    path = tmp_path / f"moved{archive.SUFFIX}"
    archive.export_file(migrated, str(path))
    target = database_url_factory()
    archive.restore_file(target, str(path))
    with make_client(target, extract_backfill=100, llm_url=LLM["llm_url"], llm_model="fake-2") as c:
        rows = listed(c, cid)
        assert str(rows[str(new["id"])]["moved_from"]) == old and rows[old]["removed_at"] is not None
        restored = thread(c, cid, "look for the lighthouse warden")
        assert (restored["status"], restored["repair"]) == ("achieved", str(new["id"]))
