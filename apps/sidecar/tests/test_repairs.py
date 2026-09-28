"""Phase 13 (docs/phases/PHASE-13.md, ADR 0044): the owner repairs threads and secrets.

A repair is owner input: it applies on every read, survives a rebuild and a new extractor generation, matches nothing
once its target's turn is edited, and a replay from before it gives the packet that request had. Synthetic names only.
"""

from __future__ import annotations

import re

from conftest import make_client
from memeval import stub_extractor
from nmos_sidecar import repairs
from nmos_sidecar.rebuild import rebuild_all
from simchat import SimChat
from test_extraction import drain
from test_generations import LLM, conv_id
from test_sidecar_integration import recall, sync

GOAL = "find the keeper"


def repair_chat(*more: str) -> SimChat:
    chat = SimChat()
    for text in ("Hana wants to find the keeper.", "Hana keeps a secret from Kaito: the letter is forged.",
                 "Kaito is in the garden.", *more):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")  # the last turn is extracted once the user continues from it (ADR 0008)
    return chat


def setup(c, migrated, chat: SimChat, complete=stub_extractor) -> str:
    sync(c, chat)
    drain(migrated, complete)
    return conv_id(c, chat)


def thread(c, cid: str, text: str = GOAL) -> dict:
    return next(t for t in c.get(f"/v1/conversations/{cid}/threads").json() if t["text"] == text)


def secret(c, cid: str) -> dict:
    return next(s for s in c.get(f"/v1/conversations/{cid}/secrets").json() if "forged" in s["text"])


def repair(c, cid: str, **body) -> dict:
    res = c.post(f"/v1/conversations/{cid}/repairs", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def packet(c, chat: SimChat, query: str) -> str:
    return recall(c, chat, query, budget=2000)["packet"]["text"]


def memory(text: str) -> str:
    """The packet without its excerpts: raw text is evidence, never repaired (invariant 1)."""
    return re.sub(r"<Excerpt[^>]*>.*?</Excerpt>", "", text, flags=re.S)


def test_closing_a_thread_takes_it_out_of_memory_and_undo_brings_it_back(migrated):
    chat = repair_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        t = thread(c, cid)
        assert t["status"] == "open" and GOAL in memory(packet(c, chat, "Hana, did you find the keeper?"))
        out = repair(c, cid, kind="thread_close", item=str(t["id"]), outcome="achieved", note="found at the pier")
        assert out["applied"] == str(t["id"]) and out["repair"]["value"] == {"outcome": "achieved", "turn": 3}
        closed = thread(c, cid)
        assert closed["status"] == "achieved" and closed["closed_by"]["owner"] == out["repair"]["id"]
        assert GOAL not in memory(packet(c, chat, "Hana, did you find the keeper?"))
        page = c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
        assert "closed by the owner" in page and "Repairs (what the owner fixed)" in page and ">applied<" in page
        assert c.post(f"/v1/conversations/{cid}/repairs/{out['repair']['id']}/remove").status_code == 200
        assert thread(c, cid)["status"] == "open" and GOAL in memory(packet(c, chat, "Hana, did you find the keeper?"))
        listed = c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"]
        assert listed[0]["removed_at"] is not None and listed[0]["applied"] is None
        assert ">taken back<" in c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text


def reworded(system: str, user: str) -> tuple[dict, str]:
    """A new model that words the same goal differently."""
    out, raw = stub_extractor(system, user)
    return {**out, "assertions": [{**a, "value": f"{a['value']} soon"} if a["predicate"] == "goal" else a
                                  for a in out["assertions"]]}, raw


def test_a_repair_survives_a_rebuild_and_a_new_generation_that_rewords_its_target(migrated):
    chat = repair_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        out = repair(c, cid, kind="thread_close", item=str(thread(c, cid)["id"]))
    assert rebuild_all(migrated)
    drain(migrated, stub_extractor)
    with make_client(migrated, extract_backfill=100, llm_url=LLM["llm_url"], llm_model="fake-2") as c:
        drain(migrated, reworded)
        t = thread(c, cid, f"{GOAL} soon")  # a new assertion, from another generation, in other words
        assert t["status"] == "achieved" and t["repair"] == out["repair"]["id"]
        assert c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"][0]["applied"] == str(t["id"])


def test_a_repair_whose_turn_is_edited_matches_nothing_and_is_listed(migrated):
    chat = repair_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        repair(c, cid, kind="thread_close", item=str(thread(c, cid)["id"]))
        chat.edit(0, "Hana wants to find the keeper at dawn.")  # the same wish, but the turn changed
        sync(c, chat)
        drain(migrated, stub_extractor)
        assert thread(c, cid, f"{GOAL} at dawn")["status"] == "open"
        assert c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"][0]["applied"] is None
        assert "matches nothing now" in c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text


def test_the_owner_reopens_a_thread_the_story_closed(migrated):
    chat = repair_chat("Hana's goal is achieved: find the keeper.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        t = thread(c, cid)
        assert t["status"] == "achieved"
        assert c.post(f"/v1/conversations/{cid}/repairs",
                      json={"kind": "thread_close", "item": str(t["id"])}).status_code == 422  # already closed
        assert c.post(f"/v1/conversations/{cid}/repairs",
                      json={"kind": "thread_reopen", "item": str(t["id"]), "turn": 2}).status_code == 422  # before its close
        out = repair(c, cid, kind="thread_reopen", item=str(t["id"]))
        assert out["repair"]["value"] == {"turn": 4}
        assert thread(c, cid)["status"] == "open" and thread(c, cid)["closed_by"] is None


def test_a_secret_marked_found_out_leaves_private_and_a_story_reveal_can_be_kept(migrated):
    chat = repair_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        s = secret(c, cid)
        assert s["open"] == ["Kaito"]
        ask = "Kaito and Hana, what about the letter?"
        assert "forged" not in packet(c, chat, ask).split("<Private>")[0]  # kept: only in <Private>
        out = repair(c, cid, kind="secret_found_out", item=str(s["id"]), character="kaito", turn=2)
        s = secret(c, cid)
        assert s["open"] == [] and s["ended"]["Kaito"]["owner"] == out["repair"]["id"] and s["ended"]["Kaito"]["turn"] == 2
        assert "forged" in packet(c, chat, ask).split("<Private>")[0]  # no longer a secret in that scene
        assert "marked by the owner" in c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
    story = repair_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        setup(c, migrated, story)
        story.reply("Kaito found out that the letter is forged.")  # after the secret's turn was extracted (K29)
        story.user("Go on.")
        cid = setup(c, migrated, story)
        s = secret(c, cid)
        assert s["open"] == [] and "Kaito" in s["ended"]  # the story's reveal
        repair(c, cid, kind="secret_keep", item=str(s["id"]), character="Kaito")
        assert secret(c, cid)["open"] == ["Kaito"]


def test_a_replay_from_before_a_repair_gives_the_packet_that_request_had(migrated):
    chat = repair_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        before = recall(c, chat, "Hana, did you find the keeper?", budget=2000)
        assert GOAL in memory(before["packet"]["text"])
        repair(c, cid, kind="thread_close", item=str(thread(c, cid)["id"]))
        replayed = c.get(f"/v1/trace/{before['trace_id']}/replay").json()
        assert replayed["status"] == "ok" and replayed["reproduced"] is True
        after = recall(c, chat, "Hana, did you find the keeper?", budget=2000)
        assert c.get(f"/v1/trace/{after['trace_id']}/replay").json()["reproduced"] is True


def test_repairs_that_cannot_be_made_are_refused(migrated):
    chat = repair_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        t, s = thread(c, cid), secret(c, cid)

        def refused(**body) -> str:
            res = c.post(f"/v1/conversations/{cid}/repairs", json=body)
            assert res.status_code == 422, res.text
            return res.json()["detail"]

        assert "no thread" in refused(kind="thread_close", item="999999999")
        assert "closes as one of" in refused(kind="thread_close", item=str(t["id"]), outcome="kept")
        assert "between" in refused(kind="thread_close", item=str(t["id"]), turn=99)
        assert "the thread is open" in refused(kind="thread_reopen", item=str(t["id"]))
        assert "name the character" in refused(kind="secret_found_out", item=str(s["id"]))
        assert "not kept from" in refused(kind="secret_found_out", item=str(s["id"]), character="Hana")
        assert "not over" in refused(kind="secret_keep", item=str(s["id"]), character="Kaito")
        assert "not available yet" in refused(kind="fact_retract", item=str(t["id"]))
        assert c.post(f"/v1/conversations/{cid}/repairs/00000000-0000-0000-0000-000000000000/remove").status_code == 404


def test_deleting_the_chat_deletes_its_repairs(migrated, db):
    chat = repair_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        repair(c, cid, kind="thread_close", item=str(thread(c, cid)["id"]))
        assert c.post(f"/v1/conversations/{cid}/delete").status_code == 200
    assert db.execute("SELECT count(*) AS n FROM owner_repair").fetchone()["n"] == 0


def test_a_thread_is_found_by_its_turn_maker_and_closest_text():
    t1 = {"id": 1, "kind": "goal", "by": "Hana", "text": "find the keeper", "turn": 3, "turn_hash": "h3", "position": 6}
    t2 = {**t1, "id": 2, "text": "bake bread for the keeper", "position": 7}
    target = repairs.thread_target(t1)
    assert repairs.match_thread(target, [t2, t1], None) is t1
    assert repairs.match_thread(target, [{**t1, "text": "find the old keeper again"}], None) is not None  # reworded
    assert repairs.match_thread(target, [{**t1, "turn_hash": "edited"}], None) is None  # the turn changed
    assert repairs.match_thread(target, [{**t1, "by": "Kaito"}], None) is None  # another maker
    assert repairs.match_thread(target, [{**t1, "kind": "question"}], None) is None
    assert repairs.match_thread(target, [{**t1, "text": "sail to the island"}], None) is None  # too different


# --- The Codex review of step 3 (AGENTS.md §14): the fold, pure ------------------------------------------------------

import uuid  # noqa: E402

from nmos_sidecar import facts as facts_mod  # noqa: E402
from nmos_sidecar import secrets as secret_fold  # noqa: E402
from nmos_sidecar import threads as thread_fold  # noqa: E402
from nmos_sidecar.entities import resolve  # noqa: E402
from test_secrets import learned, secret as kept_goal  # noqa: E402
from test_semantics import row  # noqa: E402

AIM = "등대지기를 찾기"


def goal(pos: int, who: str = "하나", text: str = AIM, **kw) -> dict:
    return row(pos, who, "goal", None, text, subject_type="character", **kw)


def resolved(pos: int, who: str = "하나", text: str = AIM) -> dict:
    return row(pos, who, "resolved", None, text, subject_type="character", outcome="achieved")


def owner(kind: str, target: dict, **value) -> dict:
    return {"id": f"{kind}-{value.get('turn')}", "kind": kind, "target": target, "value": value, "note": None}


def fold_threads(rows: list[dict], reps: list[dict], last_turn: int = 99):
    r, applied = resolve(uuid.uuid4(), rows), {}
    out, _, _ = thread_fold.fold(rows, r, repairs.thread_events(repairs.live(reps, last_turn), r, applied))
    return sorted(out, key=lambda t: t["position"]), applied


def fold_secrets(rows: list[dict], reps: list[dict]):
    r, applied = resolve(uuid.uuid4(), rows), {}
    out, _, _ = secret_fold.fold(rows, r, repairs.secret_events(reps, r, applied))
    return out, applied


AIM_TARGET = {"turn": 1, "turn_hash": None, "kind": "goal", "by": "하나", "to": None, "text": AIM}


def test_the_story_goes_on_after_a_repair():
    """PHASE-13 Q4: a repair is an event of its turn; what the story says later still counts."""
    # Closed at turn 3; the same aim stated at turn 5 is a new thread, not a restatement of the closed one.
    (old, new), _ = fold_threads([goal(1), goal(5)], [owner("thread_close", AIM_TARGET, outcome="achieved", turn=3)])
    assert (old["status"], new["status"]) == ("achieved", "open")
    # Reopened at turn 4 after the story closed it at 2; the story closes it again at 6.
    (t,), _ = fold_threads([goal(1), resolved(2), resolved(6)], [owner("thread_reopen", AIM_TARGET, turn=4)])
    assert t["status"] == "achieved" and t["closed_by"]["turn"] == 6
    # Kept at turn 4 after a reveal at 2; a reveal at 6 ends it again.
    target = repairs.secret_target({**kept_goal(1), "text": secret_fold.secret_text(kept_goal(1))})
    (s,), _ = fold_secrets([kept_goal(1), learned(2), learned(6)],
                           [owner("secret_keep", target, character="블랑", turn=4)])
    assert s["open"] == [] and s["ended"]["블랑"]["turn"] == 6


def test_a_repair_applies_from_its_turn():
    close = owner("thread_close", AIM_TARGET, outcome="achieved", turn=5)
    assert repairs.live([close], 3) == [] and repairs.live([close], 5) == [close]
    (t,), applied = fold_threads([goal(1)], [close], last_turn=3)  # a read of the head as of turn 3
    assert t["status"] == "open" and applied == {}


def test_a_secret_repair_needs_the_same_head():
    """Another maker's secret of the same turn, worded alike, never takes the repair."""
    elpi = {**kept_goal(1), "text": secret_fold.secret_text(kept_goal(1))}
    hana = {**kept_goal(1, id=101), "subject": "하나"}
    hana["text"] = secret_fold.secret_text(hana)
    target = repairs.secret_target(elpi)
    assert repairs.match_secret(target, [hana]) is None
    assert repairs.match_secret(target, [hana, elpi]) is elpi


def test_promises_are_told_apart_by_their_counterpart_and_a_tie_matches_nothing():
    to_kaito = {"id": 1, "kind": "promise", "by": "하나", "to": "카이토", "text": "등대 앞에서 만나기", "turn": 3,
                "turn_hash": None, "position": 3, "status": "open"}
    to_sora = {**to_kaito, "id": 2, "to": "소라"}
    assert repairs.match_thread(repairs.thread_target(to_sora), [to_kaito, to_sora], None) is to_sora
    assert repairs.match_thread(repairs.thread_target(to_sora), [to_sora, {**to_sora, "id": 3}], None) is None
    view = {"threads": [to_sora, {**to_sora, "id": 3}], "secrets": [], "resolution": None}
    try:
        repairs.plan("thread_close", "2", view, 5)
    except repairs.RepairError as e:
        assert "cannot be told apart" in str(e)
    else:
        raise AssertionError("an ambiguous thread was accepted")


def test_a_secret_repair_names_itself_on_the_thread_and_claim_lines_it_changed():
    (t,), _ = fold_threads([{**goal(1), "repair": "found-1"}], [])
    assert t["repair"] == "found-1"
    assert facts_mod._ref({"id": 7, "repair": "found-1"}) == {"assertion": 7, "repair": "found-1"}
    assert facts_mod._ref({"id": 7}) == {"assertion": 7}
