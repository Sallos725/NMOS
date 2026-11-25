"""Tier 1 wave 1: extraction pipeline, predicate validation, worker order and read-model fixes.

D1 the 40-assertion cap cut derived rows; D2 an unread polarity became "positive", and hints and quote checks read text
the model was never shown; D4 a stray `value` on a predicate that takes none; C4 a reveal named by an alias or the
persona's name was dropped; C5 the hint lists ignored the owner's repairs; G2 the story clock stitched fields of
different turns, and a quote that ends a role today beside a later plan was taken for a plan; D5 several workers could
extract a chat's turns out of story order, `discard_turns` raced a worker's commit, and the read model multiplied
assertion counts by commits and showed a turn an earlier generation serves as unextracted. Synthetic names only.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from conftest import active_generation, make_client, switched_client
from memeval import stub_extractor
from nmos_sidecar import extraction as X, readmodel
from nmos_sidecar.entities import resolve
from nmos_sidecar.extraction import claim, finish
from nmos_sidecar.predicates import polarity_of, semantics, takes_value
from nmos_sidecar.repairs import fact_target, secret_target, thread_target
from nmos_sidecar.secrets import fold as fold_secrets
from nmos_sidecar.threads import fold as fold_threads
from simchat import SimChat
from test_extract_v19 import at, chat_of, head_of, observe
from test_extraction import drain, filler
from test_generations import LLM, conv_id
from test_semantics import row
from test_sidecar_integration import sync

CONV = UUID("01900000-0000-7000-8000-0000000000d1")
CHAR = {"subject_type": "character", "object_type": "character"}


def ctx(text: str, turn: int = 20, persona: str | None = None, repairs: list | None = None) -> dict:
    return {"target": {"conversation_id": CONV, "host_persona_name": persona, "links": (), "splits": (), "canon": (),
                       "turn": turn, **({"repairs": repairs} if repairs else {})},
            "context": [], "members": [{"metadata": {"role": "user"}, "content": text, "turn": turn}]}


def event(i: int) -> dict:
    return {"subject": "하나", "subject_type": "character", "predicate": "event", "value": f"사소한 일 {i}",
            "modality": "actual", "source": "narration", "salience": "minor"}


def owner(kind: str, target: dict, turn: int | None, **value) -> dict:
    return {"id": uuid4(), "kind": kind, "target": target, "value": {**value, **({"turn": turn} if turn is not None
                                                                              else {})},
            "note": None, "created_at": datetime.now(timezone.utc)}


# --- D1: the cap is the model's own, never the derived rows' -----------------------------------------------------------

def test_derived_rows_after_forty_model_assertions_are_all_stored():
    own = [event(i) for i in range(45)]
    learned = {"subject": "카이토", "subject_type": "character", "predicate": "learned", "value": "[turn 1] 비밀",
               "modality": "actual", "source": "narration", "knowledge": "unknown"}
    ending = X._ending({"by": "하나", "to": "카이토", "role": "세입자", "turn": 1}, "하나는 집을 떠났다.", None)
    pair = {"subject": "윤하나", "subject_type": "character", "predicate": "also_called", "value": "하나",
            "modality": "actual", "source": "narration", "listed_pair": True}
    rows = X.normalize([*own, learned, ending, pair], "윤하나가 왔다. 하나는 집을 떠났다.")
    assert [r["predicate"] for r in rows].count("event") == X.MAX_ASSERTIONS == 40
    assert [r["predicate"] for r in rows[40:]] == ["learned", "role_toward", "also_called"]
    assert X.capped(own) == own[:40]  # a raw model list (the evaluation tools) is still capped


def test_the_model_cannot_mark_its_own_rows_as_derived():
    raw = [{**event(0), "listed_pair": True, "held": "x", "doubt": "y", "listed": {"by": "a"}},
           {"subject": "하나", "predicate": "learned", "value": "v"}] + [event(i) for i in range(1, 50)]
    own = X.own_items(raw)
    assert len(own) == 40 and all("listed_pair" not in a and "held" not in a and "listed" not in a for a in own)
    assert all(a["predicate"] == "event" for a in own)  # `learned` comes only from the `secrets` check


def test_a_reveal_on_a_dense_turn_is_stored_past_forty_assertions(migrated, db):
    chat = SimChat()
    chat.user("Hana keeps a secret from Kaito: the letter is forged.")
    chat.reply("Noted.")
    chat.user("Kaito found out that the letter is forged.")
    chat.reply("Noted.")
    chat.user("Go on.")

    def dense(system: str, user: str) -> tuple[dict, str]:
        out, raw = stub_extractor(system, user)
        if "found out" in user.split("TARGET", 1)[1]:
            out = {**out, "assertions": [{**event(i), "subject": "Hana", "value": f"chore {i}",
                                          "evidence": None} for i in range(45)] + out["assertions"]}
        return out, raw

    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, dense)
    rows = db.execute("SELECT a.predicate, a.subject, a.status FROM assertion a JOIN extraction x"
                      " ON x.id = a.extraction_id WHERE x.hints->'secrets' <> '[]'::jsonb ORDER BY a.id").fetchall()
    assert sum(r["predicate"] == "event" for r in rows) == 40
    assert [(r["subject"], r["status"]) for r in rows if r["predicate"] == "learned"] == [("Kaito", "valid")]


# --- D2: polarity ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["negative", "Negated", "NEG", "false", "no", False, " negative "])
def test_every_negative_spelling_is_negative(raw):
    assert polarity_of(raw) == "negative"
    assert semantics({"polarity": raw})[0] == "negative" and semantics({"polarity": raw})[4] is None


@pytest.mark.parametrize("raw", [None, "", "positive", "POS", "true", "yes", True, "null"])
def test_positive_and_empty_spellings_are_positive(raw):
    assert polarity_of(raw) == "positive" and semantics({"polarity": raw})[0] == "positive"
    assert semantics({"polarity": raw})[4] is None


def test_an_unread_polarity_parks_the_row_instead_of_stating_the_opposite():
    assert polarity_of("maybe") is None
    polarity, *_, reason = semantics({"polarity": "maybe"})
    assert polarity == "positive" and reason == "unrecognized polarity: maybe"  # stored positive, never a fact
    both = semantics({"polarity": "uncertain", "source": "character_claim"})[4]
    assert both == "unrecognized polarity: uncertain; character_claim without asserted_by"
    item = {"subject": "하나", "subject_type": "character", "predicate": "possesses", "object": "열쇠",
            "object_type": "item", "modality": "actual"}
    (neg, odd) = X.normalize([{**item, "polarity": "negated"}, {**item, "polarity": "maybe"}], "하나 열쇠")
    assert (neg["status"], neg["polarity"]) == ("valid", "negative")
    assert (odd["status"], odd["reason"]) == ("pending", "unrecognized polarity: maybe")


def test_a_free_negated_role_between_listed_parties_is_dropped_like_a_negative_one():
    roles = [{"by": "하나", "to": "카이토", "role": "세입자: 카이토의 집에 세 들어 삶", "turn": 1}]
    free = {"subject": "하나", "predicate": "role_toward", "object": "카이토", "value": "세입자", "polarity": "negated",
            **CHAR}
    assert X.ended_roles({"roles_ended": []}, [free], roles, "하나와 카이토.") == []


# --- D4: a value on a predicate that takes none --------------------------------------------------------------------

def test_a_stray_value_on_a_predicate_without_one_is_dropped():
    assert [takes_value(p) for p in ("located_in", "possesses", "member_of")] == [False] * 3
    assert takes_value("role_toward") and takes_value("not_a_predicate")
    member = {"subject": "하나", "subject_type": "character", "predicate": "member_of", "object": "기사단",
              "object_type": "group", "value": "정예 단원", "modality": "actual"}
    role = {"subject": "하나", "predicate": "role_toward", "object": "카이토", "value": "제자", "modality": "actual",
            **CHAR}
    odd = {"subject": "하나", "subject_type": "character", "predicate": "hates", "value": "브로콜리"}
    rows = X.normalize([member, role, odd], "하나")
    assert [(r["predicate"], r["value"], r["status"]) for r in rows] == [
        ("member_of", None, "valid"), ("role_toward", "제자", "valid"), ("hates", "브로콜리", "pending")]


# --- D2: what the model was shown -------------------------------------------------------------------------------------

def shown_ctx(text: str) -> dict:
    return {**ctx(text), "target_chars": 100}


def test_a_name_pair_or_a_reveal_past_the_cap_is_not_read():
    hints = [{"name": "윤하나", "type": "character"}]
    cut = "윤하나가 문을 열었다. " + "가" * 120 + " 하나는 웃었다."
    seen = "윤하나가 문을 열었다. 하나는 웃었다. " + "가" * 120
    assert X.name_pairs(hints, X.shown_target(shown_ctx(cut))) == []
    assert X.name_pairs(hints, X.shown_target(shown_ctx(seen))) == [{"full": "윤하나", "part": "하나"}]
    secrets = [{"text": "하나 knows: 편지는 가짜다", "holders": ["하나"], "kept_from": ["카이토"], "turn": 1}]
    answer = {"secrets": [{"secret": "S1", "found_out_by": ["카이토"], "evidence": "카이토는 편지가 가짜라는 걸 알아챘다"}]}
    late = "카이토가 들어왔다. " + "나" * 120 + " 카이토는 편지가 가짜라는 걸 알아챘다."
    assert X.revealed(answer, secrets, late)  # the whole turn holds the quote
    assert X.revealed(answer, secrets, X.shown_target(shown_ctx(late))) == []  # the model never saw it


def test_name_pairs_come_from_the_shown_target_in_the_worker(migrated):
    prompts: list[str] = []

    def capture(system: str, user: str) -> tuple[dict, str]:
        prompts.append(user)
        return stub_extractor(system, user)

    chat = SimChat()
    chat.user("윤하나 is in the garden.")
    chat.reply("Noted.")
    chat.user("윤하나 is in the hall.")
    chat.reply("가" * (X.TARGET_CHARS + 50) + " 하나 smiled.")  # the part only past the cap
    chat.user("Go on.")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, capture)
        assert prompts and not any("NAME PAIRS" in p for p in prompts)
        chat.user("윤하나 is in the attic.")
        chat.reply("하나 smiled. " + "가" * (X.TARGET_CHARS + 50))  # the part before the cap: listed
        chat.user("Again.")
        sync(c, chat)
        drain(migrated, capture)
    assert "NAME PAIRS" in prompts[-1] and "N1. 윤하나 / 하나" in prompts[-1]


# --- C4: a reveal named by an alias or by the persona's name ------------------------------------------------------------

def test_a_reveal_counts_for_the_listed_name_it_resolves_to():
    earlier = [row(1, "한서윤", "also_called", value="서윤", subject_type="character"),
               row(2, "한서윤", "located_in", "정원", subject_type="character", object_type="place")]
    r = resolve(CONV, earlier, ["타쿠미"])
    secrets = [{"text": "카이토 knows: 편지는 가짜다", "holders": ["카이토"], "kept_from": ["한서윤", "{{user}}"],
                "turn": 1}]
    quote = "서윤과 타쿠미는 편지가 가짜라는 걸 알아챘다"
    answer = {"secrets": [{"secret": "S1", "found_out_by": ["서윤", "타쿠미", "카이토"], "evidence": quote}]}
    assert [x["subject"] for x in X.revealed(answer, secrets, quote, r)] == ["한서윤", "{{user}}"]  # as listed
    assert X.revealed(answer, secrets, quote) == []  # without the resolution: exact names only, as before


# --- C5: the owner's repairs in the hint lists ------------------------------------------------------------------------

def test_a_role_the_owner_retracted_leaves_the_current_roles():
    held = row(3, "하나", "role_toward", "카이토", "세입자", turn_hash="h3", **CHAR)
    other = row(4, "유이", "role_toward", "카이토", "제자", turn_hash="h4", **CHAR)
    text = "하나와 유이가 카이토를 찾아갔다."
    assert [x["by"] for x in X.role_hints(ctx(text), [held, other])] == ["유이", "하나"]
    retract = owner("fact_retract", fact_target(held), 5)
    assert [x["by"] for x in X.role_hints(ctx(text, repairs=[retract]), [held, other])] == ["유이"]


def test_a_thread_the_owner_closed_leaves_open_threads_and_a_reopened_one_comes_back():
    goal = row(2, "하나", "goal", value="등대지기를 찾는다", subject_type="character", turn_hash="h2")
    text = "하나는 등대지기를 찾는다며 길을 나섰다."
    (t,) = fold_threads([dict(goal)], None)[0]
    close = owner("thread_close", thread_target(t), 4, outcome="achieved")
    assert [x["text"] for x in X.thread_hints(ctx(text), [goal])] == ["등대지기를 찾는다"]
    assert X.thread_hints(ctx(text, repairs=[close]), [goal]) == []
    reopen = owner("thread_reopen", thread_target(t), 5)
    assert [x["text"] for x in X.thread_hints(ctx(text, repairs=[close, reopen]), [goal])] == ["등대지기를 찾는다"]


def test_a_secret_the_owner_marked_found_out_leaves_open_secrets_and_a_kept_one_comes_back():
    knows = row(2, "하나", "knows", value="편지는 가짜다", subject_type="character", turn_hash="h2",
                knowledge="limited", known_by=["하나"], hidden_from=["카이토"])
    text = "하나는 카이토 앞에서 편지를 숨겼다."
    (s,) = fold_secrets([dict(knows)], None)[0]
    found = owner("secret_found_out", secret_target(s), 4, character="카이토")
    assert [x["kept_from"] for x in X.secret_hints(ctx(text), [knows])] == [["카이토"]]
    assert X.secret_hints(ctx(text, repairs=[found]), [knows]) == []
    keep = owner("secret_keep", secret_target(s), 5, character="카이토")
    assert [x["kept_from"] for x in X.secret_hints(ctx(text, repairs=[found, keep]), [knows])] == [["카이토"]]


def test_the_worker_lists_no_thread_the_owner_closed_and_a_re_extraction_before_the_close_still_does(migrated, db):
    chat = SimChat()
    for text in ("Hana wants to find the keeper.", "Kaito is in the garden.", "Mina is in the hall."):
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")

    def threads_at(turn: int) -> list[str]:
        found = db.execute(
            "SELECT x.hints FROM extraction x JOIN active_membership am ON am.source_revision_id = x.source_revision_id"
            " AND am.turn_hash = x.window_hash JOIN conversation c ON c.head_commit_id = am.commit_id"
            " WHERE am.turn = %s AND x.discarded_at IS NULL ORDER BY x.created_at DESC LIMIT 1", (turn,)).fetchone()
        return [t["text"] for t in ((found or {}).get("hints") or {}).get("threads") or []]

    with make_client(migrated, **LLM, extract_backfill=100) as c:
        sync(c, chat)
        drain(migrated, stub_extractor)
        cid = conv_id(c, chat)
        assert threads_at(1) == ["find the keeper"]  # the persona's own: listed while open
        goal = next(t for t in c.get(f"/v1/conversations/{cid}/threads").json() if t["text"] == "find the keeper")
        res = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "thread_close", "item": str(goal["id"])})
        assert res.status_code == 200, res.text
        at_turn = res.json()["repair"]["value"]["turn"]
        chat.user("Hana is in the attic.")
        chat.reply("Noted.")
        chat.user("Again.")
        sync(c, chat)
        drain(migrated, stub_extractor)
        assert threads_at(at_turn + 1) == []  # closed by the owner: the slot is free
        res = c.post(f"/v1/conversations/{cid}/rebuild")
        assert res.status_code == 200, res.text
        drain(migrated, stub_extractor)
        assert threads_at(1) == ["find the keeper"]  # turn-scoped: the close comes after that turn
        assert threads_at(at_turn + 1) == []


# --- G2: the story clock ----------------------------------------------------------------------------------------------

def test_the_clock_reads_prefixed_and_common_role_play_keys(migrated):
    chat = chat_of("세라는 문을 열었다.", "카이토는 창가에 앉았다.", "하나는 차를 끓였다.")
    with make_client(migrated) as c:
        sync(c, chat)
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        head = head_of(conn, chat)
        observe(conn, head, 5, "상태.날짜", "4월 13일")
        observe(conn, head, 5, "status.현재 시각", "오후 3시")
        observe(conn, head, 5, "요일", "월요일")
        observe(conn, head, 5, "계절", "봄")
        observe(conn, head, 5, "일차", "3일차")
        assert X.story_clock(conn, at(head, 5)) == ("상태.날짜: 4월 13일; 일차: 3일차; 요일: 월요일; 계절: 봄;"
                                                    " status.현재 시각: 오후 3시")
        assert X.clock_key(" 상태창.Day ") == "day"


def test_a_date_is_never_shown_with_a_time_from_a_turn_long_before(migrated):
    chat = chat_of("세라는 문을 열었다.", "카이토는 창가에 앉았다.", "하나는 차를 끓였다.")
    with make_client(migrated) as c:
        sync(c, chat)
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        head = head_of(conn, chat)
        observe(conn, head, 1, "시간", "오전 9시")  # turn 0
        observe(conn, head, 5, "날짜", "4월 13일")  # turn 2: two turns later
        assert X.story_clock(conn, at(head, 5)) == "날짜: 4월 13일"
        observe(conn, head, 3, "시간", "오후 3시")  # turn 1: the next turn's time is one clock with it
        assert X.story_clock(conn, at(head, 5)) == "날짜: 4월 13일; 시간: 오후 3시"
        assert X.story_clock(conn, at(head, 1)) == "시간: 오전 9시"


# --- G2: a role ended today beside a later plan --------------------------------------------------------------------

ROLES = [{"by": "하나", "to": "카이토", "role": "직원: 카이토의 가게에서 일함", "turn": 1}]


@pytest.mark.parametrize("quote", ["하나는 오늘부로 카이토의 가게를 퇴사하고 내일부터 쉬기로 했다.",
                                   "하나는 예정보다 일찍 오늘 카이토의 집에서 방을 뺐다.",
                                   "Hana quit Kaito's shop as of today, and will rest from tomorrow."])
def test_an_ending_done_now_beside_a_later_plan_is_an_ending(quote):
    assert X.LATER.search(quote) and not X.places_later(quote)
    roles = ROLES if "Kaito" not in quote else [{**ROLES[0], "by": "Hana", "to": "Kaito"}]
    (ending,) = X.ended_roles({"roles_ended": [{"role": "R1", "when": "now", "evidence": quote}]}, [], roles, quote)
    assert ending["polarity"] == "negative" and "held" not in ending
    assert X.confirmed({"ended": "yes", "evidence": quote}, quote) == ("yes", quote)


@pytest.mark.parametrize("quote", ["내일 이사할 짐은 이미 다 쌌다.", "하나는 오늘 사직서를 냈고 다음 달에 떠난다.",
                                   "Hana gave notice today and will leave next month.",
                                   "Hana already packed; she will leave tomorrow.", "하나는 당장 내일 떠난다.",
                                   "하나는 내일 떠날 예정이다.", "하나는 당장 짐을 싸고 내일 떠난다.",
                                   "방금 사직서를 내고 다음 달에 떠난다.",
                                   "She gave notice just now and will leave next month.",
                                   "She packed right away and will leave tomorrow."])
def test_a_plan_stays_a_plan_whatever_else_the_quote_says(quote):
    assert X.places_later(quote)
    assert X.ended_roles({"roles_ended": [{"role": "R1", "when": "now", "evidence": quote}]}, [], ROLES,
                         "카이토. " + quote) == []
    assert X.confirmed({"ended": "yes", "evidence": quote}, quote) == ("quote places it later", None)


# --- D5: story order across workers ---------------------------------------------------------------------------------

def extract_jobs(db) -> dict[int, dict]:
    return {r["id"]: r for r in db.execute("SELECT id, conversation_id, status, priority FROM job"
                                           " WHERE kind = 'extract' ORDER BY id").fetchall()}


def test_a_running_turn_holds_the_next_turn_of_its_chat_but_not_another_chat(migrated, db):
    a, b = SimChat(), SimChat()
    filler(a, 3)
    a.user("next")
    filler(b, 2, tag="b")
    b.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, a)
        sync(c, b)
    handled = {"extract": active_generation(db, "extract").key}
    first = claim(db, handled)
    second = claim(db, handled)
    assert second is not None and second["conversation_id"] != first["conversation_id"]  # the other chat
    assert claim(db, handled) is None  # each chat's next turn waits for its running one
    finish(db, first["id"], "done", first["locked_at"])
    third = claim(db, handled)
    assert third["conversation_id"] == first["conversation_id"] and third["id"] > first["id"]
    db.execute("UPDATE job SET status = 'dead', locked_at = NULL WHERE id = %s", (second["id"],))
    assert claim(db, handled)["conversation_id"] == second["conversation_id"]  # a dead job holds nothing


def test_a_live_turn_waits_for_the_earlier_live_turn_and_a_history_turn_holds_neither(migrated, db):
    chat = SimChat()
    filler(chat, 2)
    chat.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated)
        filler(chat, 2, tag="s")
        chat.user("again")
        sync(c, chat)
    jobs = [j for j in extract_jobs(db).values() if j["status"] == "queued"]
    assert [j["priority"] for j in jobs] == [X.LIVE_PRIORITY] * 2
    handled = {"extract": active_generation(db, "extract").key}
    # an older turn queued again at history priority, ahead of both by id: never holds a more urgent turn
    db.execute("UPDATE job SET status = 'queued', priority = %s WHERE id = (SELECT min(id) FROM job"
               " WHERE kind = 'extract' AND status = 'done')", (X.HISTORY_PRIORITY,))
    one = claim(db, handled)
    assert one["id"] == jobs[0]["id"]  # the chat's earlier live turn first (was: newest first)
    history = claim(db, handled)  # it holds no live turn, and no later turn holds it
    assert history["priority"] == X.HISTORY_PRIORITY and history["id"] < one["id"]
    assert claim(db, handled) is None  # the later live turn waits while the earlier one runs
    finish(db, one["id"], "done", one["locked_at"])
    assert claim(db, handled)["id"] == jobs[1]["id"]


def test_parallel_workers_extract_each_chat_in_story_order(migrated, db):
    chats = [SimChat() for _ in range(3)]
    for i, chat in enumerate(chats):
        chat.user(f"Mina{i} is in the kitchen.")
        chat.reply("Noted.")
        filler(chat, 3, tag=f"c{i}")
        chat.user("last")
    with make_client(migrated, **LLM) as c:
        for chat in chats:
            sync(c, chat)
    handled = {"extract": active_generation(db, "extract").key}
    overlap: list[tuple] = []
    running: dict[UUID, int] = {}
    lock = threading.Lock()

    def worker() -> None:
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            idle = 0
            while idle < 20:
                job = claim(conn, handled)
                if job is None:
                    idle += 1
                    time.sleep(0.01)
                    continue
                idle = 0
                with lock:
                    if job["conversation_id"] in running:
                        overlap.append((job["conversation_id"], running[job["conversation_id"]], job["id"]))
                    running[job["conversation_id"]] = job["id"]
                time.sleep(0.01)
                with lock:
                    del running[job["conversation_id"]]
                finish(conn, job["id"], "done", job["locked_at"])

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert overlap == []  # never two turns of one chat at once
    assert db.execute("SELECT count(*) AS n FROM job WHERE kind = 'extract' AND status <> 'done'").fetchone()["n"] == 0


def test_discard_turns_waits_for_a_worker_storing_one_of_them(migrated, db):
    chat = SimChat()
    chat.user("Mina is in the kitchen.")
    chat.reply("Noted.")
    chat.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
    gen = active_generation(db, "extract")
    job = claim(db, {"extract": gen.key})
    rid, h = UUID(job["payload"]["revision_id"]), job["payload"]["window_hash"]
    done = threading.Event()
    with psycopg.connect(migrated, row_factory=dict_row) as worker:  # the worker's last transaction, held open
        worker.execute("SELECT 1 FROM job WHERE id = %s AND status = 'running' FOR UPDATE", (job["id"],))
        stored = uuid4()
        worker.execute("INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key,"
                       " model, raw) VALUES (%s, %s, %s, 'extract-v16', %s, 'fake', %s)",
                       (stored, rid, h, gen.key, Jsonb({})))

        def discard() -> None:
            with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
                X.discard_turns(conn, [{"rid": rid, "turn_hash": h}])
            done.set()

        t = threading.Thread(target=discard)
        t.start()
        assert not done.wait(0.5)  # it waits for the worker's commit
        worker.commit()
    t.join(5)
    assert done.is_set()
    assert db.execute("SELECT discarded_at FROM extraction WHERE id = %s", (stored,)).fetchone()["discarded_at"]
    assert db.execute("SELECT status FROM job WHERE id = %s", (job["id"],)).fetchone()["status"] == "obsolete"


# --- D5: the read model -----------------------------------------------------------------------------------------------

def test_turn_generations_count_each_assertion_once_whatever_the_commits(migrated, db):
    chat = SimChat()
    chat.user("Mina is in the kitchen.")
    chat.reply("Noted.")
    chat.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated)
        chat.user("more")
        sync(c, chat)
        for i in range(3):  # three more commits (an edit makes one) that keep the first turn's messages
            chat.edit(len(chat.messages) - 1, f"more {i}")
            sync(c, chat)
    # The earlier commits' membership, as a database that kept it holds it (the ledger now keeps the head's only).
    db.execute("INSERT INTO active_membership (commit_id, position, source_revision_id, turn, turn_hash)"
               " SELECT w.id, am.position, am.source_revision_id, am.turn, am.turn_hash FROM conversation c"
               " JOIN active_membership am ON am.commit_id = c.head_commit_id"
               " JOIN worldline_commit w ON w.conversation_id = c.id AND w.id <> c.head_commit_id")
    rev = db.execute("SELECT x.source_revision_id AS rid, count(a.id) AS n FROM extraction x"
                     " JOIN assertion a ON a.extraction_id = x.id GROUP BY 1").fetchone()
    assert rev["n"] == 1
    assert db.execute("SELECT count(DISTINCT commit_id) AS n FROM active_membership WHERE source_revision_id = %s",
                      (rev["rid"],)).fetchone()["n"] >= 4
    (gen,) = readmodel.turn_generations(db, [rev["rid"]])
    assert gen["assertions"] == 1 and gen["current_window"]
    head = db.execute("SELECT head_commit_id AS h FROM conversation").fetchone()["h"]
    assert readmodel.turn_generations(db, [rev["rid"]], head)[0]["assertions"] == 1


def test_membership_shows_what_an_earlier_generation_serving_a_turn_read(migrated, db):
    chat = SimChat()
    chat.user("Mina is in the kitchen.")
    chat.reply("Noted.")
    chat.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated)
        old = active_generation(db, "extract").key
    with switched_client(migrated, "fake-2", llm_url=LLM["llm_url"]):  # its turns queued again, not read yet
        new = active_generation(db, "extract").key
    assert new != old and db.execute("SELECT count(*) AS n FROM extraction WHERE extractor_key = %s",
                                     (new,)).fetchone()["n"] == 0
    head = db.execute("SELECT head_commit_id AS h FROM conversation").fetchone()["h"]
    first = [m for m in readmodel.membership(db, head, new) if m["turn"] == 0]
    assert first and all(m["extracted_chars"] == m["clean_chars"] for m in first)  # served by the earlier one
    assert all(m["extracted_chars"] is None for m in readmodel.membership(db, head, None))  # no extractor: none
