"""Phase 13 (docs/phases/PHASE-13.md, ADR 0044): the owner repairs threads and secrets.

A repair is owner input: it applies on every read, survives a rebuild and a new extractor generation, matches nothing
once its target's turn is edited, and a replay from before it gives the packet that request had. Synthetic names only.
"""

from __future__ import annotations

import re

from conftest import make_client
from memeval import FOUND, stub_extractor
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
        assert "no fact" in refused(kind="fact_retract", item=str(t["id"]))  # a thread's id is not a fact's
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
                           [owner("secret_keep", target, character="노엘", turn=4)])
    assert s["open"] == [] and s["ended"]["노엘"]["turn"] == 6


def test_a_repair_applies_from_its_turn():
    close = owner("thread_close", AIM_TARGET, outcome="achieved", turn=5)
    assert repairs.live([close], 3) == [] and repairs.live([close], 5) == [close]
    (t,), applied = fold_threads([goal(1)], [close], last_turn=3)  # a read of the head as of turn 3
    assert t["status"] == "open" and applied == {}


def test_a_secret_repair_needs_the_same_head():
    """Another maker's secret of the same turn, worded alike, never takes the repair."""
    luca = {**kept_goal(1), "text": secret_fold.secret_text(kept_goal(1))}
    hana = {**kept_goal(1, id=101), "subject": "하나"}
    hana["text"] = secret_fold.secret_text(hana)
    target = repairs.secret_target(luca)
    assert repairs.match_secret(target, [hana]) is None
    assert repairs.match_secret(target, [hana, luca]) is luca


def test_promises_are_told_apart_by_their_counterpart_and_a_tie_matches_nothing():
    to_kaito = {"id": 1, "kind": "promise", "by": "하나", "to": "카이토", "text": "등대 앞에서 만나기", "turn": 3,
                "turn_hash": None, "position": 3, "status": "open"}
    to_sena = {**to_kaito, "id": 2, "to": "세나"}
    assert repairs.match_thread(repairs.thread_target(to_sena), [to_kaito, to_sena], None) is to_sena
    assert repairs.match_thread(repairs.thread_target(to_sena), [to_sena, {**to_sena, "id": 3}], None) is None
    view = {"threads": [to_sena, {**to_sena, "id": 3}], "secrets": [], "resolution": None}
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


def test_a_repair_of_a_turn_runs_after_every_row_of_that_turn():
    """Copilot review of #145: a repair's turn is the turn it follows, not one it runs before."""
    (t,), _ = fold_threads([goal(1)], [owner("thread_close", AIM_TARGET, outcome="achieved", turn=1)])
    assert t["status"] == "achieved"  # the thread opened in the same turn is there when the close runs
    (t,), _ = fold_threads([goal(1), resolved(2)], [owner("thread_reopen", AIM_TARGET, turn=2)])
    assert t["status"] == "open"  # the story's close of that turn came first


def test_a_secret_repair_needs_the_same_object():
    base = {**kept_goal(1), "predicate": "knows", "object": "카이토"}
    base["text"] = secret_fold.secret_text(base)
    other = {**base, "id": 102, "object": "세나"}
    other["text"] = secret_fold.secret_text(other)
    assert repairs.match_secret(repairs.secret_target(base), [other]) is None


# --- Step 4: facts and names -------------------------------------------------------------------------------------


def place_chat() -> SimChat:
    chat = SimChat()
    for text in ("Hana is in the chapel.", "Kaito is in the harbor.", "Hana is in the garden.", "하나의 특징: 겁이 많다.",
                 "Hana is a knight."):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")
    return chat


def fact(c, cid: str, subject: str, predicate: str) -> dict:
    return next(f for f in c.get(f"/v1/conversations/{cid}/facts").json()
                if f["subject"] == subject and f["predicate"] == predicate)


def test_retracting_a_fact_brings_back_the_version_before_it(migrated):
    chat = place_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        garden = fact(c, cid, "Hana", "located_in")
        assert garden["object"] == "garden"
        out = repair(c, cid, kind="fact_retract", item=str(garden["id"]), note="she never went")
        assert out["applied"] == str(garden["id"]) and fact(c, cid, "Hana", "located_in")["object"] == "chapel"
        assert "Hana located in chapel" in memory(packet(c, chat, "Where is Hana?"))
        c.post(f"/v1/conversations/{cid}/repairs/{out['repair']['id']}/remove")
        assert fact(c, cid, "Hana", "located_in")["object"] == "garden"


def test_a_correction_holds_from_its_turn_until_the_story_says_otherwise(migrated):
    chat = place_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        harbor = fact(c, cid, "Kaito", "located_in")
        out = repair(c, cid, kind="fact_correct", item=str(harbor["id"]), new_object="library", turn=3)
        assert out["repair"]["value"] == {"object": "library", "turn": 3}
        now = fact(c, cid, "Kaito", "located_in")
        assert now["object"] == "library" and now["turn"] == 3 and now["owner"] is True
        assert "corrected by the owner" in c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
        chat.user("Kaito is in the garden.")  # the story says otherwise later (Q4)
        chat.reply("Noted.")
        chat.user("Go on.")
        sync(c, chat)
        drain(migrated, stub_extractor)
        assert fact(c, cid, "Kaito", "located_in")["object"] == "garden"
        # A trait accumulates: its correction replaces it at its own turn.
        trait = fact(c, cid, "하나", "has_trait")
        repair(c, cid, kind="fact_correct", item=str(trait["id"]), new_value="용감하다")
        traits = [f["value"] for f in c.get(f"/v1/conversations/{cid}/facts").json() if f["predicate"] == "has_trait"]
        assert traits == ["용감하다"]


def knighted(system: str, user: str) -> tuple[dict, str]:
    """A new model that words an identity differently."""
    out, raw = stub_extractor(system, user)
    return {**out, "assertions": [{**a, "value": f"{a['value']} of the order"} if a["predicate"] == "identity" else a
                                  for a in out["assertions"]]}, raw


def test_a_fact_repair_survives_a_new_generation_that_rewords_the_fact(migrated):
    chat = place_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        out = repair(c, cid, kind="fact_retract", item=str(fact(c, cid, "Hana", "identity")["id"]))
    with make_client(migrated, extract_backfill=100, llm_url=LLM["llm_url"], llm_model="fake-2") as c:
        drain(migrated, knighted)
        assert not [f for f in c.get(f"/v1/conversations/{cid}/facts").json() if f["predicate"] == "identity"]
        assert c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"][0]["applied"] is not None


ALIAS = re.compile(r"(?P<a>\w+) is also called (?P<b>\w+)\.")


def aliased(system: str, user: str) -> tuple[dict, str]:
    out, raw = stub_extractor(system, user)
    target = user.split("TARGET", 1)[1]
    out["assertions"] += [{"subject": m["a"], "subject_type": "character", "predicate": "also_called", "value": m["b"],
                           "modality": "actual", "source": "narration", "evidence": m.group(0)}
                          for m in ALIAS.finditer(target)]
    return out, raw


def test_splitting_two_names_the_story_joined(migrated):
    chat = SimChat()
    for text in ("Mina is in the chapel.", "Rin is in the harbor.", "Mina is also called Rin.", "Go on."):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat, aliased)
        names = {e["name"]: e["names"] for e in c.get(f"/v1/conversations/{cid}/entities").json()}
        assert any({"Mina", "Rin"} <= set(n) for n in names.values())  # one entity (K8)
        res = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "name_split", "item": "Mina"})
        assert res.status_code == 422 and "other name" in res.json()["detail"]
        out = repair(c, cid, kind="name_split", item="Mina", other="Rin")
        entities = c.get(f"/v1/conversations/{cid}/entities").json()
        assert not any({"Mina", "Rin"} <= set(e["names"]) for e in entities) and out["applied"]
        places = {f["subject"]: f["object"] for f in c.get(f"/v1/conversations/{cid}/facts").json()
                  if f["predicate"] == "located_in"}
        assert places == {"Mina": "chapel", "Rin": "harbor"}  # two people again, each with their own place
        assert "Mina ≠ Rin" in c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
        again = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "name_split", "item": "Mina", "other": "Rin"})
        assert again.status_code == 422 and "not one entity" in again.json()["detail"]


def test_a_split_names_the_third_name_that_still_joins_them():
    rows = [row(1, "Mina", "also_called", None, "Rin", subject_type="character"),
            row(2, "Mi", "also_called", None, "Rin", subject_type="character"),
            row(3, "Mina", "located_in", "chapel", None, subject_type="character")]
    link = {"id": "l1", "entity_type": "character", "name": "Mina", "same_as": "Mi", "created_at": 1}
    split = {"id": "s1", "entity_type": "character", "name": "Mina", "other": "Rin", "created_at": 2}
    r = resolve(uuid.uuid4(), rows, links=[link], splits=[split])
    assert r.split_via == {"s1": ["Mi"]}  # the owner's own join through Mi keeps them one
    newer = {**link, "id": "l2", "name": "Mina", "same_as": "Rin", "created_at": 3}
    r = resolve(uuid.uuid4(), rows, links=[newer], splits=[split])  # a newer join of the same pair holds
    assert r.entity("character", "Mina")["id"] == r.entity("character", "Rin")["id"] and r.splits == []


# --- The Codex review of step 4 (AGENTS.md §14) -------------------------------------------------------------------


def test_a_correction_in_place_keeps_its_turn_repairs_position_and_entities(migrated):
    """Findings 1–3: a same-turn correction keeps the turn hash (so the turn's secret repair still matches), the
    source position (so the earlier version is still earlier), and resolves its new object."""
    chat = repair_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        s = secret(c, cid)
        repair(c, cid, kind="secret_found_out", item=str(s["id"]), character="Kaito")
        knows = next(f for f in c.get(f"/v1/conversations/{cid}/facts").json() if f["predicate"] == "knows")
        repair(c, cid, kind="fact_correct", item=str(knows["id"]), new_value="the letter is fake")
        s = next(s for s in c.get(f"/v1/conversations/{cid}/secrets").json() if "letter" in s["text"])
        assert "fake" in s["text"] and s["open"] == []  # still found out: the secret repair found the correction
    chat = place_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        harbor = fact(c, cid, "Kaito", "located_in")
        repair(c, cid, kind="fact_correct", item=str(harbor["id"]), new_object="library")
        now = fact(c, cid, "Kaito", "located_in")
        assert now["position"] == harbor["position"] and now["turn"] == harbor["turn"]
        assert "library" in now["names"] and "harbor" not in now["names"]


def test_a_later_object_correction_that_changes_the_fact_is_refused(migrated):
    """Finding 4: from a later turn a new object of a pair (a relationship) would leave both pairs current."""
    chat = SimChat()
    for text in ("Mina is Rin's classmate.", "Rin is in the harbor.", "Mina is in the chapel."):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        rel = fact(c, cid, "Mina", "relationship")
        res = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_correct", "item": str(rel["id"]),
                                                               "new_object": "Sena", "turn": 2})
        assert res.status_code == 422 and "leave the old fact current" in res.json()["detail"]
        repair(c, cid, kind="fact_correct", item=str(rel["id"]), new_object="Sena")  # at its own turn: replaced
        pairs = [(f["subject"], f["object"]) for f in c.get(f"/v1/conversations/{cid}/facts").json()
                 if f["predicate"] == "relationship"]
        assert pairs == [("Mina", "Sena")]


def test_the_api_checks_a_fact_against_the_assertions_a_read_matches():
    """Finding 5: two assertions of one turn that fold into one fact cannot be told apart."""
    f = {**row(3, "Hana", "has_trait", None, "brave", subject_type="character"), "turn_hash": "h"}
    view = {"facts": [f], "assertions": [f, {**f, "id": 99}], "secrets": [], "threads": [], "resolution": None}
    try:
        repairs.plan("fact_retract", "3", view, 5)
    except repairs.RepairError as e:
        assert "cannot be told apart" in str(e)
    else:
        raise AssertionError("an ambiguous fact was accepted")


def test_a_split_is_explained_only_by_joins_resolution_accepted():
    """Finding 6: X is ambiguous once A and B are split, so the owner's joins through C and D keep them one."""
    rows = [row(1, "A", "also_called", None, "B", subject_type="character"),
            row(2, "A", "also_called", None, "X", subject_type="character"),
            row(3, "B", "also_called", None, "X", subject_type="character"),
            row(4, "X", "also_called", None, "Y", subject_type="character"),
            row(5, "C", "located_in", "chapel", None, subject_type="character"),
            row(6, "D", "located_in", "harbor", None, subject_type="character")]
    links = [{"id": f"l{i}", "entity_type": "character", "name": a, "same_as": b, "created_at": i}
             for i, (a, b) in enumerate((("A", "C"), ("C", "D"), ("D", "B")))]
    split = {"id": "s1", "entity_type": "character", "name": "A", "other": "B", "created_at": 9}
    r = resolve(uuid.uuid4(), rows, links=links, splits=[split])
    assert r.split_via == {"s1": ["C", "D"]}


def test_the_version_a_retraction_made_current_names_the_repair(migrated):
    """Finding 7: the restored version's packet line carries the repair in its provenance."""
    chat = place_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        out = repair(c, cid, kind="fact_retract", item=str(fact(c, cid, "Hana", "located_in")["id"]))
        assert fact(c, cid, "Hana", "located_in")["repair"] == out["repair"]["id"]
        lines = recall(c, chat, "Where is Hana?", budget=2000)
        ledger = c.get(f"/v1/trace/{lines['trace_id']}/replay").json()["lines"]
        assert any(e["ref"].get("repair") == out["repair"]["id"] and e.get("placed") for e in ledger)


def test_a_correction_follows_the_predicate(migrated):
    """Copilot review of #147: a correction may only set what the predicate has."""
    chat = place_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        place = fact(c, cid, "Kaito", "located_in")
        res = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_correct", "item": str(place["id"]),
                                                               "new_value": "quietly"})
        assert res.status_code == 422 and "has no value" in res.json()["detail"]
        trait = fact(c, cid, "하나", "has_trait")
        res = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_correct", "item": str(trait["id"]),
                                                               "new_object": "Kaito"})
        assert res.status_code == 422 and "has no object" in res.json()["detail"]


# --- Step 5: where the panel repairs, and what needs a look ---------------------------------------------------------


def test_a_thread_needs_a_look_after_more_than_30_turns_without_a_restatement():
    """PHASE-13 Q6 (Codex review of step 5): more than STALE_TURNS turns, counted from its latest statement."""
    from nmos_sidecar.inspector import STALE_TURNS, _attention
    th = {"id": 1, "kind": "goal", "status": "open", "turn": 1, "restated": [], "by": "하나", "to": None, "text": AIM}
    def listed(last: int, **kw) -> bool:
        return bool(_attention({"threads": [{**th, **kw}]}, [], last, "en"))
    assert not listed(STALE_TURNS) and not listed(1 + STALE_TURNS) and listed(2 + STALE_TURNS)
    assert not listed(40, restated=[{"turn": 20}])
    assert not listed(40, status="achieved")


def test_apply_facts_keeps_a_later_turn_correction_s_original_and_lets_a_later_repair_name_it():
    """Codex review of step 6: a correction from a later turn is a new version; the story's version stays history."""
    rows = [{"id": t + 1, "turn": t, "turn_hash": f"h{t}", "position": 2 * t + 1, "predicate": "located_in",
             "source": "narration", "subject": "하나", "subject_type": "character", "object": f"장소{t}",
             "object_type": "place", "value": None} for t in range(5)]
    def owner(kind, row, **value):
        return {"id": uuid.uuid4(), "kind": kind, "target": repairs.fact_target(row), "value": value, "note": None}
    later = owner("fact_correct", rows[1], object="등대", turn=3)
    again = owner("fact_retract", rows[1])
    applied: dict = {}
    out, retracted = repairs.apply_facts(rows, [later, again], None, applied, turn_positions={3: 7})
    assert [x["id"] for x in out if not x.get("owner")] == [1, 3, 4, 5]  # the retraction named the original
    new = next(x for x in out if x.get("owner"))
    assert (new["turn"], new["position"], out.index(new)) == (3, 7, 3)  # at the end of turn 3
    assert applied == {str(later["id"]): "2", str(again["id"]): "2"} and set(retracted) == {str(again["id"])}
    out, _ = repairs.apply_facts(rows, [later], None, {}, turn_positions={3: 7})
    assert [x["id"] for x in out][:5] == [1, 2, 3, 4, new["id"]]  # the story's version stays as history


def test_a_disputed_owner_correction_offers_its_undo_not_a_retraction():
    """Copilot review of step 5: the API refuses to repair an owner's version; the owner takes the repair back."""
    from nmos_sidecar.inspector import _attention
    rid = str(uuid.uuid4())
    view = {"facts": [{"id": -7, "owner": True, "repair": rid}, {"id": 8}],
            "conflicts": [{"fact": -7, "text": "the owner's version", "turn": 3},
                          {"fact": 8, "text": "the story's", "turn": 4}]}
    acts = [row[-1] for row in _attention(view, [], 10, "en")]
    assert acts == [f'<span class="rp" data-repair="undo:{rid}"></span>',
                    '<span class="rp" data-repair="fact_retract:8"></span>']


def test_a_mark_carries_any_name_as_data_and_offers_each_field_a_correction_can_set():
    """Codex review of step 5: a name with a quote, an ampersand or a colon keeps its button; a relationship can be
    corrected in its counterpart or in its value."""
    from nmos_sidecar.inspector import _act, _corrections
    assert _act("secret_found_out", 3, "O'Neil & Co: 1") == (
        '<span class="rp" data-repair="secret_found_out:3:O%27Neil%20%26%20Co%3A%201"></span>')
    assert _act("secret_keep", 3, "하나") == '<span class="rp" data-repair="secret_keep:3:%ED%95%98%EB%82%98"></span>'
    assert _act("thread_close", 5, "kept,broken").endswith(':kept,broken"></span>')
    assert _corrections({"predicate": "relationship", "object": "카이토", "value": "친구"}) == ["object", "value"]
    assert _corrections({"predicate": "located_in", "object": "등대", "value": None}) == ["object"]


def test_the_inspector_marks_where_each_repair_can_be_made_and_lists_what_needs_a_look(migrated):
    chat = repair_chat()
    for i in range(33):  # the goal stays open, not restated, for more than STALE_TURNS turns
        chat.user(f"Turn {i} passes.")
        chat.reply("Noted.")
    chat.user("Go on.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        t, s = thread(c, cid), secret(c, cid)
        page = c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
        # a goal: its default outcome first, then the others its kind may close with
        assert f'data-repair="thread_close:{t["id"]}:achieved,abandoned,failed,answered,averted,paid"' in page
        assert f'data-repair="secret_found_out:{s["id"]}:Kaito"' in page
        located = fact(c, cid, "Kaito", "located_in")
        assert f'data-repair="fact_retract:{located["id"]}"' in page and f'data-repair="fact_correct:{located["id"]}:object"' in page
        attention = page[page.index('id="s-attention"'):page.index("</details>", page.index('id="s-attention"'))]
        assert "open for more than 30 turns without a restatement" in attention and GOAL in attention
        out = repair(c, cid, kind="thread_close", item=str(t["id"]))
        page = c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
        assert f'data-repair="undo:{out["repair"]["id"]}"' in page and f'data-repair="thread_close:{t["id"]}' not in page
        assert "Nothing needs a look." in page


# --- Stage 6's done criterion (docs/ROADMAP-1.0.md): every repair kind survives a rebuild and a new generation --------


def surviving(c, cid: str) -> dict[str, str | None]:
    """{repair kind: the id of what it applies to now} for the chat's repairs in force (one of each kind)."""
    return {r["kind"]: r["applied"] for r in c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"]
            if r["removed_at"] is None}


def rebuild(c, migrated, cid: str, complete) -> None:
    """The chat's rebuild (every extraction discarded, every turn extracted again) and the membership rebuild."""
    assert c.post(f"/v1/conversations/{cid}/rebuild").status_code == 200
    assert drain(migrated, complete) > 0  # every turn extracted again
    assert rebuild_all(migrated)


# A new model's words: a word inside the text, so neither text contains the other (a suffix would match exactly).
ANEW = {"find the keeper": "find the old keeper", "bake bread": "bake fresh bread",
        "the letter is forged": "the letter is surely forged", "the key is lost": "the key is surely lost",
        "겁이 많다": "겁이 꽤 많다", "knight": "sworn knight"}


def worded_anew(system: str, user: str) -> tuple[dict, str]:
    """A new model that words every goal, end, secret, trait and identity differently; a reveal names the secret
    in the new words."""
    out, raw = stub_extractor(system, user)
    before, target = user.split("TARGET", 1)
    listed = [line.split(". ", 1) for line in before.splitlines() if re.match(r"S\d+\. ", line)]
    secrets = [{"secret": number, "found_out_by": [m["who"]], "evidence": m.group(0)}
               for m in FOUND.finditer(target) for number, text in listed if ANEW.get(m["what"], m["what"]) in text]
    return {"assertions": [{**a, "value": ANEW.get(a["value"], a["value"])} if isinstance(a.get("value"), str) else a
                           for a in out["assertions"]], "secrets": secrets}, raw


def test_every_thread_and_secret_repair_survives_a_rebuild_and_a_new_generation(migrated):
    chat = SimChat()
    for text in ("Hana wants to find the keeper.", "Kaito wants to bake bread.", "Kaito's goal is achieved: bake bread.",
                 "Hana keeps a secret from Kaito: the letter is forged.", "Mira keeps a secret from Sena: the key is lost."):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        chat.reply("Sena found out that the key is lost.")  # after the secret's turn was extracted (K29)
        chat.user("Go on.")
        setup(c, migrated, chat)
        letter = secret(c, cid)
        key = next(s for s in c.get(f"/v1/conversations/{cid}/secrets").json() if "key is lost" in s["text"])
        assert key["open"] == [] and "Sena" in key["ended"]  # the story's reveal
        made = {
            "thread_close": repair(c, cid, kind="thread_close", item=str(thread(c, cid)["id"])),
            "thread_reopen": repair(c, cid, kind="thread_reopen", item=str(thread(c, cid, "bake bread")["id"])),
            "secret_found_out": repair(c, cid, kind="secret_found_out", item=str(letter["id"]), character="Kaito"),
            "secret_keep": repair(c, cid, kind="secret_keep", item=str(key["id"]), character="Sena"),
        }

        def holds(words: dict[str, str]) -> None:
            applied = surviving(c, cid)
            ids = {kind: out["repair"]["id"] for kind, out in made.items()}
            hana, kaito = thread(c, cid, words.get(GOAL, GOAL)), thread(c, cid, words.get("bake bread", "bake bread"))
            assert (hana["status"], hana["repair"]) == ("achieved", ids["thread_close"])
            assert (kaito["status"], kaito["repair"]) == ("open", ids["thread_reopen"])
            assert applied["thread_close"] == str(hana["id"]) and applied["thread_reopen"] == str(kaito["id"])
            secrets = {s["text"]: s for s in c.get(f"/v1/conversations/{cid}/secrets").json()}
            found = secrets["Hana knows: " + words.get("the letter is forged", "the letter is forged")]
            kept = secrets["Mira knows: " + words.get("the key is lost", "the key is lost")]
            assert found["open"] == [] and found["ended"]["Kaito"]["owner"] == ids["secret_found_out"]
            assert kept["open"] == ["Sena"] and kept["repair"] == ids["secret_keep"]
            assert applied["secret_found_out"] == str(found["id"]) and applied["secret_keep"] == str(kept["id"])

        holds({})
        before = surviving(c, cid)
        rebuild(c, migrated, cid, stub_extractor)
        holds({})
        assert set(surviving(c, cid).values()).isdisjoint(before.values())  # new rows, found again by what they say
    with make_client(migrated, extract_backfill=100, llm_url=LLM["llm_url"], llm_model="fake-2") as c:
        assert drain(migrated, worded_anew) > 0  # the new generation extracted every turn
        holds(ANEW)


def test_every_fact_repair_survives_a_rebuild_and_a_new_generation(migrated):
    chat = place_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        retract = repair(c, cid, kind="fact_retract", item=str(fact(c, cid, "Hana", "located_in")["id"]))
        repair(c, cid, kind="fact_correct", item=str(fact(c, cid, "Kaito", "located_in")["id"]), new_object="library",
               turn=3)
        trait = repair(c, cid, kind="fact_correct", item=str(fact(c, cid, "하나", "has_trait")["id"]), new_value="용감하다")

        def holds() -> None:
            repairs_now = {r["id"]: r["applied"] for r in c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"]}
            assert all(repairs_now.values()), repairs_now  # each found its target again
            hana, kaito = fact(c, cid, "Hana", "located_in"), fact(c, cid, "Kaito", "located_in")
            assert (hana["object"], hana["repair"]) == ("chapel", retract["repair"]["id"])
            assert (kaito["object"], kaito["turn"], kaito["owner"]) == ("library", 3, True)
            traits = [f for f in c.get(f"/v1/conversations/{cid}/facts").json() if f["predicate"] == "has_trait"]
            assert [(f["value"], f["repair"]) for f in traits] == [("용감하다", trait["repair"]["id"])]

        holds()
        rebuild(c, migrated, cid, stub_extractor)
        holds()
    with make_client(migrated, extract_backfill=100, llm_url=LLM["llm_url"], llm_model="fake-2") as c:
        assert drain(migrated, worded_anew) > 0  # the new generation extracted every turn
        assert fact(c, cid, "Hana", "identity")["value"] == "sworn knight"  # the new generation's words
        holds()


def test_a_name_split_and_an_owner_join_survive_a_rebuild_and_a_new_generation(migrated):
    chat = SimChat()
    for text in ("Mina is in the chapel.", "Rin is in the harbor.", "Mina is also called Rin.", "Kai is in the tower.",
                 "Kaito is in the tower."):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat, aliased)
        split = repair(c, cid, kind="name_split", item="Mina", other="Rin")
        join = c.post(f"/v1/conversations/{cid}/entity-links",
                      json={"entity_type": "character", "name": "Kai", "same_as": "Kaito"})
        assert join.status_code == 200, join.text

        def holds() -> None:
            names = [set(e["names"]) for e in c.get(f"/v1/conversations/{cid}/entities").json()]
            assert not any({"Mina", "Rin"} <= n for n in names) and any({"Kai", "Kaito"} <= n for n in names)
            places = {f["subject"]: f["object"] for f in c.get(f"/v1/conversations/{cid}/facts").json()
                      if f["predicate"] == "located_in"}
            assert places["Mina"] == "chapel" and places["Rin"] == "harbor"
            assert surviving(c, cid)["name_split"] == split["applied"]

        holds()
        rebuild(c, migrated, cid, aliased)
        holds()
    with make_client(migrated, extract_backfill=100, llm_url=LLM["llm_url"], llm_model="fake-2") as c:
        assert drain(migrated, aliased) > 0  # the new generation extracted every turn
        holds()


# --- ADR 0044 amendment 2: a repair finds a new generation's item by its quote of the raw text ----------------------


def quoted_anew(system: str, user: str) -> tuple[dict, str]:
    """A new model that words a goal and a secret too differently for the text match, quoting the same message."""
    out, raw = stub_extractor(system, user)
    words = {"find the keeper": "locate a lighthouse warden", "the letter is forged": "a fake missive"}
    return {**out, "assertions": [{**a, "value": words.get(a["value"], a["value"])} if isinstance(a.get("value"), str)
                                  else a for a in out["assertions"]]}, raw


def test_a_repair_finds_a_new_generation_s_item_by_its_quote_when_the_words_differ(migrated):
    chat = repair_chat()
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = setup(c, migrated, chat)
        closed = repair(c, cid, kind="thread_close", item=str(thread(c, cid)["id"]))
        found = repair(c, cid, kind="secret_found_out", item=str(secret(c, cid)["id"]), character="Kaito")
        stored = {r["kind"]: r["target"] for r in c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"]}
        assert stored["thread_close"]["evidence"] == "Hana wants to find the keeper."
        assert stored["secret_found_out"]["evidence"] == "Hana keeps a secret from Kaito: the letter is forged."
    with make_client(migrated, extract_backfill=100, llm_url=LLM["llm_url"], llm_model="fake-2") as c:
        assert drain(migrated, quoted_anew) > 0
        t = thread(c, cid, "locate a lighthouse warden")
        assert repairs.similarity(GOAL, t["text"]) < repairs.MATCH_MIN  # the text match alone would miss it
        assert (t["status"], t["repair"]) == ("achieved", closed["repair"]["id"])
        s = next(s for s in c.get(f"/v1/conversations/{cid}/secrets").json() if "missive" in s["text"])
        assert s["open"] == [] and s["ended"]["Kaito"]["owner"] == found["repair"]["id"]
        assert all(r["applied"] for r in c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"])


QUOTE = "Hana swore she would find the keeper before dawn."


def test_a_quote_names_one_item_at_any_turn_but_an_edited_target_turn():
    target = {"turn": 3, "turn_hash": "h3", "kind": "goal", "by": "Hana", "to": None, "text": "find the keeper",
              "evidence": QUOTE}
    later = {"id": 1, "turn": 5, "turn_hash": "h5", "kind": "goal", "by": "Hana", "text": "reach the old tower",
             "evidence": "she would find the keeper before dawn"}
    assert repairs.match_thread(target, [later], None) is later  # another turn, other words, the same quote
    assert repairs.match_thread({**target, "evidence": None}, [later], None) is None  # a repair made before the quote
    assert repairs.match_thread(target, [later, {**later, "id": 2}], None) is None  # two quote it: neither
    assert repairs.match_thread(target, [{**later, "by": "Kaito"}], None) is None  # another maker
    edited = {**later, "turn": 3, "turn_hash": "edited"}
    assert repairs.match_thread(target, [edited], None) is None  # the target's turn changed: still nothing (Q3)
    assert repairs.match_thread(target, [{**later, "evidence": "Hana swore it."}], None) is None  # too short a run


def test_a_fact_repair_finds_its_fact_by_its_quote_at_another_turn():
    a = {**row(3, "Hana", "identity", None, "knight", subject_type="character"), "turn_hash": "h3", "evidence": QUOTE}
    target = repairs.fact_target(a)
    moved = {**a, "id": 9, "turn": 4, "turn_hash": "h4", "value": "a sworn blade"}
    assert repairs.match_fact(target, [moved], None) is moved
    applied: dict = {}
    rep = {"id": uuid.uuid4(), "kind": "fact_retract", "target": target, "value": {}, "note": None}
    out, _ = repairs.apply_facts([moved], [rep], None, applied)
    assert out == [] and applied == {str(rep["id"]): "9"}
    # a correction made at the fact's own turn stays in place where the new generation states the fact
    fix = {**rep, "id": uuid.uuid4(), "kind": "fact_correct", "value": {"value": "squire", "turn": 3}}
    (now,), _ = repairs.apply_facts([moved], [fix], None, {})
    assert (now["value"], now["turn"], now["position"], now["owner"]) == ("squire", 4, moved["position"], True)
    # the story's repair never takes a canon fact that quotes the same words
    canon = {**moved, "turn": -1, "turn_hash": "card:desc", "canon": "card:desc"}
    assert repairs.match_fact(target, [canon], None) is None


def test_a_quote_is_as_long_as_extraction_asks_of_a_quote():
    from nmos_sidecar.extraction import EVIDENCE_MIN_CHARS
    assert repairs.QUOTE_MIN_CHARS == EVIDENCE_MIN_CHARS
    assert repairs.quoted("the keeper waits", "THE  KEEPER waits here") and not repairs.quoted("the keeper", "the keeper")
