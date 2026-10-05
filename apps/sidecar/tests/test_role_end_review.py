"""PHASE-28 Q7, ADR 0064 item 4: the owner sees every role ending extract-v16 applied (recently) or held, in the
Inspector's "Needs attention", with one action each: retract an applied ending (the role is current again), restore a
held one (the role ends at its turn). Stand-in models; the confirmation answers as the test says."""
from __future__ import annotations

import pytest

from conftest import make_client
from nmos_sidecar import endings
from simchat import SimChat
from test_extract_v16 import roles_of
from test_extraction import drain, facts, filler
from test_role_end_confirmation import MOVED, ROLE, tenancy
from test_sidecar_integration import sync

ENDED = [("하나", "카이토", ROLE["role"], "negative")]
CURRENT = [("하나", "카이토", ROLE["role"], "positive")]


def story(c, migrated, answer):
    """The stay at turn 0, the move at turn 3 (its ending confirmed or not), one turn after; the chat's id."""
    complete, _ = tenancy(answer)
    chat = SimChat()
    chat.user("하나는 카이토의 집에 세 들어 산다.")
    chat.reply("카이토는 월세 봉투를 받아 들었다.")
    filler(chat, 2)
    sync(c, chat)
    drain(migrated, complete)
    chat.user(MOVED)
    chat.reply("카이토는 빈 다락방을 정리했다.")
    filler(chat, 1, tag="after")
    sync(c, chat)
    drain(migrated, complete)
    conv = next(x["id"] for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)
    return chat, conv


def page(c, conv):
    return c.get(f"/inspector/c/{conv}", params={"lang": "en"}).text


def client(migrated):
    return make_client(migrated, llm_url="http://fake/v1", llm_model="fake", extract_compiler="extract-v16")


def test_an_applied_ending_is_listed_and_one_retraction_keeps_the_role(migrated):
    with client(migrated) as c:
        chat, conv = story(c, migrated, "yes")
        assert roles_of(c, chat) == ENDED
        (f,) = [f for f in facts(c, chat) if f["predicate"] == "role_toward"]
        html = page(c, conv)
        assert "a role ended automatically (retract it to keep the role)" in html
        assert f'data-repair="fact_retract:{f["id"]}"' in html and MOVED in html  # the confirmation's quote
        r = c.post(f"/v1/conversations/{conv}/repairs", json={"kind": "fact_retract", "item": str(f["id"])})
        assert r.status_code == 200 and r.json()["applied"] is not None
        assert roles_of(c, chat) == CURRENT
        assert "a role ended automatically" not in page(c, conv)  # retracted: nothing left to look at
        assert "a role ending held" not in page(c, conv)


def test_a_held_ending_is_listed_and_one_restore_ends_the_role_at_its_turn(migrated):
    with client(migrated) as c:
        chat, conv = story(c, migrated, "no")
        assert roles_of(c, chat) == CURRENT
        html = page(c, conv)
        assert "a role ending held, not confirmed: no (restore it to end the role at its turn)" in html
        assert "a role ended automatically" not in html
        held = [x for x in html.split('data-repair="')[1:] if x.startswith("fact_restore:")]
        assert len(held) == 1
        item = held[0].split('"', 1)[0].split(":", 1)[1]
        r = c.post(f"/v1/conversations/{conv}/repairs", json={"kind": "fact_restore", "item": item})
        assert r.status_code == 200 and r.json()["applied"] is not None
        assert roles_of(c, chat) == ENDED
        (f,) = [f for f in facts(c, chat) if f["predicate"] == "role_toward"]
        assert f["turn"] == 3 and f["owner"]  # the owner's version at the ending's own turn
        html = page(c, conv)
        assert "a role ending held" not in html and "a role ended automatically" not in html  # the owner's, not listed
        again = c.post(f"/v1/conversations/{conv}/repairs", json={"kind": "fact_restore", "item": item})
        assert again.status_code == 422  # applied once: no longer held


def test_a_failed_confirmation_is_held_with_its_outcome(migrated):
    with client(migrated) as c:
        _, conv = story(c, migrated, "fail")
        assert "a role ending held, not confirmed: call failed: TimeoutError" in page(c, conv)


def test_an_older_applied_ending_leaves_the_list_but_can_still_be_retracted(migrated, monkeypatch):
    monkeypatch.setattr(endings, "RECENT_TURNS", 0)  # the ending (turn 3) is older than the last turn (4)
    with client(migrated) as c:
        chat, conv = story(c, migrated, "yes")
        assert "a role ended automatically" not in page(c, conv)
        (f,) = [f for f in facts(c, chat) if f["predicate"] == "role_toward"]
        r = c.post(f"/v1/conversations/{conv}/repairs", json={"kind": "fact_retract", "item": str(f["id"])})
        assert r.status_code == 200 and roles_of(c, chat) == CURRENT


@pytest.mark.parametrize("answer", ["yes", "no"])
def test_extract_v15_lists_no_role_ending(migrated, answer):
    complete, _ = tenancy(answer)
    chat = SimChat()
    chat.user("하나는 카이토의 집에 세 들어 산다.")
    chat.reply("카이토는 월세 봉투를 받아 들었다.")
    chat.user(MOVED)
    chat.reply("카이토는 빈 다락방을 정리했다.")
    filler(chat, 2)
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", extract_compiler="extract-v15") as c:
        sync(c, chat)
        drain(migrated, complete)
        conv = next(x["id"] for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)
        html = page(c, conv)
    assert "a role ended automatically" not in html and "a role ending held" not in html
