"""extract-v16's role-ending confirmation (ADR 0064 item 4, PHASE-28 Q1): an ending the extraction lists is asked once
more of the model about that one role, with the measured v3 prompt; only a yes that quotes the TARGET turn ends the
role, anything else holds the ending as a pending row with its reason and keeps every answer."""

from __future__ import annotations

import hashlib

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import extraction as X
from simchat import SimChat
from test_extract_v16 import CHAR, confirming, roles_of
from test_extraction import drain, filler
from test_sidecar_integration import sync

ROLE = {"by": "하나", "to": "카이토", "role": "세입자: 카이토의 집에 세 들어 삶", "turn": 0}
MOVED = "하나는 열쇠를 반납하고 카이토의 집에서 짐을 빼 이사했다."


def row(turn, content, name="USER"):
    return {"turn": turn, "metadata": {"role": "user", "name": name}, "content": content}


def ctx(context, members):
    return {"context": context, "members": members, "target": {"turn": 9}}


def test_the_confirmation_prompt_is_the_measured_v3_text_and_in_the_v16_fingerprint():
    assert hashlib.sha256(X.ROLE_CONFIRM_SYSTEM.encode()).hexdigest() == (
        "c5fe766ad7541573ce74e09f6f5282b8d6f4592602bd933f5bd331c85f986413")
    assert X.CONFIRMS == {"extract-v16"} and X.CONFIRM_TURNS == 2


def test_the_user_message_holds_the_role_the_two_preceding_turns_whole_and_the_target():
    long = "가" * (X.CONTEXT_CHARS + 50) + "끝"  # past CONTEXT_CHARS: shown whole, as a TARGET turn is
    user = X.confirm_prompt(ROLE, ctx([row(5, "오래된 턴"), row(6, long), row(7, "어제 일", "카이토"), row(7, "대답")],
                                      [row(8, MOVED), row(8, "카이토는 고개를 끄덕였다.", "카이토")]))
    assert user == "\n".join([
        "ROLE: 하나 → 카이토: 세입자: 카이토의 집에 세 들어 삶", "", "CONTEXT (preceding turns only):",
        f"[turn 6] USER: {long}", "[turn 7] 카이토: 어제 일", "[turn 7] USER: 대답", "", "TARGET:",
        f"USER: {MOVED}", "카이토: 카이토는 고개를 끄덕였다."])
    assert "오래된 턴" not in user
    alone = X.confirm_prompt(ROLE, ctx([], [row(0, MOVED)]))
    assert "CONTEXT (preceding turns only):\n(No preceding context supplied.)\n\nTARGET:" in alone


def test_only_a_yes_that_quotes_the_target_turn_confirms():
    assert X.confirmed({"ended": "yes", "evidence": MOVED}, MOVED) == ("yes", MOVED)
    assert X.confirmed({"ended": "YES ", "evidence": MOVED}, MOVED) == ("yes", MOVED)
    assert X.confirmed({"ended": "no", "evidence": ""}, MOVED) == ("no", None)  # a no needs no quote
    assert X.confirmed({"ended": "no"}, MOVED) == ("no", None)
    assert X.confirmed({"ended": "no", "evidence": "다른 이야기"}, MOVED) == ("no", None)
    assert X.confirmed({"ended": "yes", "evidence": "카이토는 창밖을 내다보며 오래 생각에 잠겼다."}, MOVED) == (
        "quote not in the turn", None)
    assert X.confirmed({"ended": "yes", "evidence": ""}, MOVED) == ("quote not in the turn", None)
    later = "하나는 내일 열쇠를 반납하고 이사한다."
    assert X.confirmed({"ended": "yes", "evidence": later}, later) == ("quote places it later", None)
    for answer in (None, [], {"ended": "maybe"}, {"ended": True}, {"ended": "yes", "evidence": 3}, {"evidence": MOVED}):
        assert X.confirmed(answer, MOVED) == ("invalid answer", None), answer


def ending():
    return {"subject": "하나", "subject_type": CHAR, "predicate": "role_toward", "object": "카이토", "object_type": CHAR,
            "value": ROLE["role"], "polarity": "negative", "modality": "actual", "source": "narration",
            "evidence": MOVED, "knowledge": "public", "epistemic": "stated", "listed": ROLE}


def test_a_held_ending_is_kept_pending_with_its_reason_and_every_answer_recorded():
    other = {"subject": "하나", "subject_type": CHAR, "predicate": "located_in", "object": "새 집", "object_type": "place"}
    c = ctx([row(7, "전날")], [row(8, MOVED)])
    for answer, outcome in (({"ended": "no"}, "no"), ({"ended": "maybe"}, "invalid answer"),
                            ({"ended": "yes", "evidence": "없는 문장이 여기에 있다고 하자."}, "quote not in the turn")):
        items = [ending(), dict(other)]
        record, usage = X.confirm_endings(lambda s, u, a=answer: (a, "raw", {"calls": 1, "input": 10, "output": 2}),
                                          items, c, MOVED)
        assert items[0]["held"] == f"role ending not confirmed: {outcome}" and "held" not in items[1]
        assert record == [{"role": ROLE, "ending": MOVED, "outcome": outcome, "quote": None, "answer": answer,
                           "reply": "raw", "usage": {"calls": 1, "input": 10, "output": 2}}]
        assert usage == {"calls": 1, "input": 10, "output": 2}
        (held, kept) = X.normalize(items, MOVED, shown=MOVED, apart=True)
        assert (held["status"], held["reason"]) == ("pending", f"role ending not confirmed: {outcome}")
        assert held["polarity"] == "negative" and held["value"] == ROLE["role"] and kept["status"] == "valid"


def test_a_confirmed_ending_stays_valid_and_a_failed_call_holds_it_without_failing():
    items = [ending()]
    record, usage = X.confirm_endings(lambda s, u: ({"ended": "yes", "evidence": MOVED}, "raw"), items,
                                      ctx([], [row(0, MOVED)]), MOVED)
    assert "held" not in items[0] and record[0]["outcome"] == "yes" and record[0]["quote"] == MOVED
    assert usage is None  # a stand-in without usage reports none
    (kept,) = X.normalize(items, MOVED, shown=MOVED, apart=True)
    assert kept["status"] == "valid"

    def broken(system, user):
        raise TimeoutError("the provider did not answer")
    items = [ending()]
    record, usage = X.confirm_endings(broken, items, ctx([], [row(0, MOVED)]), MOVED)
    assert items[0]["held"] == "role ending not confirmed: call failed: TimeoutError"
    assert record[0]["outcome"] == "call failed: TimeoutError" and record[0]["reply"] == "" and usage is None
    assert X.confirm_endings(broken, [{"predicate": "located_in"}], ctx([], [row(0, MOVED)]), MOVED) == ([], None)


def test_the_extractions_usage_counts_its_confirmations_and_keeps_them_apart():
    main = {"calls": 1, "ms": 900, "input": 13000, "output": 900, "model": "m"}
    both = X.with_confirmations(main, {"calls": 2, "ms": 1200, "input": 9000, "output": 60, "cached": 100})
    assert both == {"calls": 3, "ms": 900, "input": 22000, "output": 960, "cached": 100, "model": "m",
                    "confirm": {"calls": 2, "ms": 1200, "input": 9000, "output": 60, "cached": 100}}
    assert X.with_confirmations(main, None) is main
    assert X.with_confirmations(None, {"calls": 1}) == {"calls": 1, "confirm": {"calls": 1}}


# --- through the worker -----------------------------------------------------------------------------------------------

def tenancy(answer: str):
    """The extraction lists the stay and ends it at the move; the confirmation answers `answer` (or raises)."""
    asked = []

    def complete(system, user):
        if system == X.ROLE_CONFIRM_SYSTEM:
            asked.append(user)
            if answer == "fail":
                raise TimeoutError("no answer")
            return confirming(user, answer)
        shown = user.split("TARGET turn", 1)[1]
        if "세 들어" in shown:
            return {"assertions": [{"subject": "하나", "subject_type": CHAR, "predicate": "role_toward",
                                     "object": "카이토", "object_type": CHAR, "value": ROLE["role"],
                                     "modality": "actual", "source": "narration"}]}, "{}"
        if "이사" in shown:
            return {"assertions": [], "roles_ended": [{"role": "R1", "when": "now", "evidence": MOVED}]}, "{}"
        return {"assertions": []}, "{}"
    return complete, asked


def run_tenancy(migrated, answer):
    complete, asked = tenancy(answer)
    chat = SimChat()
    chat.user("하나는 카이토의 집에 세 들어 산다.")
    chat.reply("카이토는 월세 봉투를 받아 들었다.")
    filler(chat, 2)
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", extract_compiler="extract-v16") as c:
        sync(c, chat)
        drain(migrated, complete)
        chat.user(MOVED)
        chat.reply("카이토는 빈 다락방을 정리했다.")
        filler(chat, 1, tag="after")
        sync(c, chat)
        drain(migrated, complete)
        roles = roles_of(c, chat)
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        held = conn.execute("SELECT a.status, a.reason, a.polarity, a.value, a.evidence, x.raw, x.usage, x.extractor_key,"
                            " x.compiler_version FROM assertion a JOIN extraction x ON x.id = a.extraction_id"
                            " WHERE a.predicate = 'role_toward' AND a.polarity = 'negative'").fetchall()
        failed = conn.execute("SELECT count(*) AS n FROM job WHERE status <> 'done'").fetchone()["n"]
    return roles, held, asked, failed


def test_a_confirmed_ending_ends_the_role_through_the_worker(migrated):
    roles, held, asked, failed = run_tenancy(migrated, "yes")
    assert roles == [("하나", "카이토", ROLE["role"], "negative")]
    assert len(asked) == 1 and asked[0].startswith("ROLE: 하나 → 카이토: 세입자: 카이토의 집에 세 들어 삶\n")
    (h,) = held
    assert h["status"] == "valid" and h["compiler_version"] == "extract-v16"
    (c,) = h["raw"]["confirmations"]
    assert c["outcome"] == "yes" and c["quote"] == MOVED and c["ending"] == MOVED and failed == 0


def test_an_unconfirmed_ending_is_held_pending_and_the_role_stays_current(migrated):
    """Held, not dropped: the extraction's row stays (pending, with its reason) and its raw reply keeps both answers;
    the role stays current, and nothing resolves it by itself."""
    roles, held, asked, failed = run_tenancy(migrated, "no")
    assert roles == [("하나", "카이토", ROLE["role"], "positive")]
    (h,) = held
    assert (h["status"], h["reason"]) == ("pending", "role ending not confirmed: no")
    assert h["value"] == ROLE["role"] and h["evidence"] == MOVED and h["extractor_key"].startswith("extract-")
    assert '"roles_ended"' in h["raw"]["reply"] or h["raw"]["reply"] == "{}"
    (c,) = h["raw"]["confirmations"]
    assert c["outcome"] == "no" and c["answer"]["ended"] == "no" and c["role"]["role"] == ROLE["role"]
    assert failed == 0 and len(asked) == 1


def test_a_failed_confirmation_holds_the_ending_and_the_job_still_succeeds(migrated):
    roles, held, asked, failed = run_tenancy(migrated, "fail")
    assert roles == [("하나", "카이토", ROLE["role"], "positive")]
    (h,) = held
    assert (h["status"], h["reason"]) == ("pending", "role ending not confirmed: call failed: TimeoutError")
    assert h["raw"]["confirmations"][0]["outcome"] == "call failed: TimeoutError"
    assert failed == 0 and len(asked) == 1  # asked once: no retry, and the extraction was not asked again


def test_extract_v15_never_asks_for_a_confirmation(migrated):
    complete, asked = tenancy("no")
    chat = SimChat()
    chat.user("하나는 카이토의 집에 세 들어 산다.")
    chat.reply("카이토는 월세 봉투를 받아 들었다.")
    chat.user(MOVED)
    chat.reply("카이토는 빈 다락방을 정리했다.")
    filler(chat, 2)
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake") as c:
        sync(c, chat)
        drain(migrated, complete)
    assert asked == []
