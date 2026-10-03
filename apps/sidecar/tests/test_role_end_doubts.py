"""PHASE-28 Q7, the owner's S1 of c0b0a5b (turn 233): the navigator's resignation was called `planned` and its reverse
(the captain's role as employer) left out, so both roles stayed current with nothing for the owner to see. Under
extract-v16 an ending marked planned whose quote passes every other check, and the reverse of an ending (the same two
the other way round, listed from the same turn), are asked of the confirmation; a yes holds them for the owner, never
applies them; anything else drops them. Stand-in models."""
from __future__ import annotations

import re

from conftest import make_client
from nmos_sidecar import extraction as X
from simchat import SimChat
from test_extraction import drain, facts, filler
from test_sidecar_integration import sync

NAV = {"by": "{{user}}", "to": "강무진", "role": "항해사: 청새치호의 항해사로 고용됨", "turn": 149}
CAPTAIN = {"by": "강무진", "to": "{{user}}", "role": "고용주: 청새치호의 항해사로 채용함", "turn": 149}
OTHER = {"by": "강무진", "to": "{{user}}", "role": "스승: 항해를 가르침", "turn": 60}
QUIT = "도윤은 강무진에게 항해사 일을 그만두겠다고 말했고, 무진은 고개를 끄덕였다."
ROLES = [NAV, CAPTAIN, OTHER]


def ending(ref, when, evidence=QUIT):
    return {"role": ref, "when": when, "evidence": evidence}


def doubts(rows):
    return [(r["value"], r.get("doubt"), r.get("held")) for r in rows]


def test_a_planned_ending_with_a_good_quote_is_held_as_a_doubt_not_dropped():
    rows = X.ended_roles({"roles_ended": [ending("R1", "planned")]}, [], ROLES, QUIT)
    assert doubts(rows) == [(NAV["role"], X.DOUBT_PLANNED, f"{X.HELD}: {X.DOUBT_PLANNED}"),
                            (CAPTAIN["role"], X.DOUBT_REVERSE, f"{X.HELD}: {X.DOUBT_REVERSE}")]
    assert all(X.normalize([r], QUIT)[0]["status"] == "pending" for r in rows)  # without a confirmation: no fact


def test_a_planned_ending_placed_later_is_still_nothing():
    later = "도윤은 다음 달에 항해사 일을 그만두겠다고 말했다."
    assert X.ended_roles({"roles_ended": [ending("R1", "planned", later)]}, [], ROLES, later) == []


def test_an_ending_over_now_wins_over_a_doubt_of_the_same_role():
    rows = X.ended_roles({"roles_ended": [ending("R1", "planned"), ending("R1", "now")]}, [], ROLES, QUIT)
    assert doubts(rows) == [(NAV["role"], None, None), (CAPTAIN["role"], X.DOUBT_REVERSE, f"{X.HELD}: {X.DOUBT_REVERSE}")]


def test_only_the_reverse_listed_from_the_same_turn_is_asked_and_never_twice():
    rows = X.ended_roles({"roles_ended": [ending("R1", "now")]}, [], ROLES, QUIT)
    assert OTHER["role"] not in [r["value"] for r in rows]  # the same two, another turn: a mentorship goes on
    both = X.ended_roles({"roles_ended": [ending("R1", "now"), ending("R2", "now")]}, [], ROLES, QUIT)
    assert doubts(both) == [(NAV["role"], None, None), (CAPTAIN["role"], None, None)]


def answers(**by_role):
    """A confirmation answering per listed role value, quoting the TARGET's first message for a yes."""
    asked = []

    def complete(system, user):
        assert system == X.ROLE_CONFIRM_SYSTEM
        role = user.split("\n", 1)[0].split(": ", 1)[1]
        asked.append(role)
        said = by_role[next(k for k, v in VALUES.items() if v in role)]
        if said == "fail":
            raise TimeoutError("no answer")
        first = user.split("\nTARGET:\n", 1)[1].split("\n", 1)[0].split(": ", 1)[1]
        return {"ended": said, "evidence": first if said == "yes" else ""}, "{}"
    return complete, asked


VALUES = {"nav": NAV["role"], "captain": CAPTAIN["role"]}
CTX = {"context": [], "members": [{"content": QUIT, "metadata": {"role": "user"}, "turn": 233}], "target": {"turn": 233}}


def test_a_confirmed_doubt_stays_held_for_the_owner_and_an_unconfirmed_one_goes():
    items = X.ended_roles({"roles_ended": [ending("R1", "planned")]}, [], ROLES, QUIT)
    complete, asked = answers(nav="yes", captain="no")
    record, usage = X.confirm_endings(complete, items, CTX, QUIT)
    assert len(asked) == 2
    assert doubts(items) == [(NAV["role"], X.DOUBT_PLANNED, f"{X.HELD}: {X.DOUBT_PLANNED}, confirmation says ended")]
    assert [(c["doubt"], c["outcome"]) for c in record] == [(X.DOUBT_PLANNED, "yes"), (X.DOUBT_REVERSE, "no")]
    (row,) = X.normalize(items, QUIT)
    assert (row["status"], row["reason"]) == ("pending", f"{X.HELD}: {X.DOUBT_PLANNED}, confirmation says ended")


def test_a_failed_confirmation_of_a_doubt_drops_it_and_keeps_the_record():
    items = X.ended_roles({"roles_ended": [ending("R1", "now")]}, [], ROLES, QUIT)
    complete, _ = answers(nav="yes", captain="fail")
    record, _ = X.confirm_endings(complete, items, CTX, QUIT)
    assert doubts(items) == [(NAV["role"], None, None)]  # the ending over now, confirmed, applies as before
    assert record[1]["doubt"] == X.DOUBT_REVERSE and record[1]["outcome"] == "call failed: TimeoutError"


# --- through the worker and the Inspector ---------------------------------------------------------------------------

def resignation(confirm):
    """The crew roles at one turn, the resignation called `planned` at a later one; the confirmation answers `confirm`."""
    def complete(system, user):
        if system == X.ROLE_CONFIRM_SYSTEM:
            first = user.split("\nTARGET:\n", 1)[1].split("\n", 1)[0].split(": ", 1)[1]
            return {"ended": confirm, "evidence": first if confirm == "yes" else ""}, "{}"
        shown = re.split(r"TARGET turn \d+:", user)[1]  # the target turn and what follows it, not the context
        if "강무진은 도윤을 청새치호의" in shown:
            return {"assertions": [
                {"subject": "{{user}}", "subject_type": "character", "predicate": "role_toward", "object": "강무진",
                 "object_type": "character", "value": NAV["role"], "modality": "actual", "source": "narration"},
                {"subject": "강무진", "subject_type": "character", "predicate": "role_toward", "object": "{{user}}",
                 "object_type": "character", "value": CAPTAIN["role"], "modality": "actual", "source": "narration"}]}, "{}"
        if "그만두겠다" in shown:
            return {"assertions": [], "roles_ended": [{"role": "R1", "when": "planned", "evidence": QUIT}]}, "{}"
        return {"assertions": []}, "{}"
    return complete


def run(migrated, confirm):
    chat = SimChat()
    chat.user("강무진은 도윤을 청새치호의 항해사로 고용했다.")
    chat.reply("갑판 위로 바람이 불었다.")
    filler(chat, 2)
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", extract_compiler="extract-v16") as c:
        sync(c, chat)
        drain(migrated, resignation(confirm))
        chat.user(QUIT)
        chat.reply("배는 조용히 흔들렸다.")
        filler(chat, 1, tag="after")
        sync(c, chat)
        drain(migrated, resignation(confirm))
        conv = next(x["id"] for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)
        roles = sorted((f["value"], f["polarity"]) for f in facts(c, chat) if f["predicate"] == "role_toward")
        html = c.get(f"/inspector/c/{conv}", params={"lang": "en"}).text
        items = [x.split('"', 1)[0].split(":", 1)[1] for x in html.split('data-repair="')[1:]
                 if x.startswith("fact_restore:")]
        after = None
        if items:
            for item in items:
                assert c.post(f"/v1/conversations/{conv}/repairs",
                              json={"kind": "fact_restore", "item": item}).status_code == 200
            after = sorted((f["value"], f["polarity"]) for f in facts(c, chat) if f["predicate"] == "role_toward")
    return roles, html, after


def test_a_resignation_called_planned_and_its_reverse_are_listed_when_confirmed(migrated):
    roles, html, after = run(migrated, "yes")
    assert roles == sorted([(NAV["role"], "positive"), (CAPTAIN["role"], "positive")])  # not applied by themselves
    assert "a role ending held, not confirmed: marked planned, confirmation says ended" in html
    assert "a role ending held, not confirmed: reverse of an ending, confirmation says ended" in html
    assert after == sorted([(NAV["role"], "negative"), (CAPTAIN["role"], "negative")])  # the owner applied both


def test_a_doubt_the_confirmation_does_not_confirm_leaves_nothing_to_look_at(migrated):
    roles, html, after = run(migrated, "no")
    assert roles == sorted([(NAV["role"], "positive"), (CAPTAIN["role"], "positive")])
    assert "a role ending held" not in html and after is None
