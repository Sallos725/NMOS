"""Relationship history per pair (PHASE-11 step 3, Q5; K24). Pinned before the fix as a strict xfail: a fix makes the
run fail until the marker is removed. The case is K24's own example (`docs/KNOWN-ISSUES.md`)."""

from __future__ import annotations

import pytest

from conftest import make_client
from simchat import SimChat
from test_extraction import drain, facts, filler
from test_sidecar_integration import recall, sync

CHAR = "character"


def relationship(subject, obj, value):
    return {"subject": subject, "subject_type": CHAR, "predicate": "relationship", "object": obj, "object_type": CHAR,
            "value": value, "modality": "actual", "source": "narration", "knowledge": "public"}


def flipped(system, user):
    """The story makes them lovers, and extraction records it in the other direction than the old relationship."""
    target = user.split("TARGET", 1)[1]
    items = []
    if "같은 반" in target:
        items.append(relationship("유이", "카이토", "같은 반 친구"))
    if "사귀기로" in target:
        items.append(relationship("카이토", "유이", "연인"))
    return {"assertions": items}, "{}"


@pytest.mark.xfail(strict=True, reason="K24: relationships are versioned per direction (PHASE-11 step 3)")
def test_a_symmetric_relationship_changed_in_the_other_direction_ends_the_old_one(migrated):
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake") as c:
        chat = SimChat()
        chat.user("유이와 카이토는 같은 반이다.")
        chat.reply("유이는 카이토의 옆자리에 앉았다.")
        filler(chat, 3)
        chat.user("카이토가 고백했고, 둘은 사귀기로 했다.")
        chat.reply("유이는 고개를 끄덕였다.")
        filler(chat, 5)
        sync(c, chat)
        drain(migrated, flipped)
        rows = [f for f in facts(c, chat) if f["predicate"] == "relationship"]
        packet = recall(c, chat, "유이와 카이토가 함께 하교한다.", budget=400)["packet"]["text"]
    assert {(f["subject"], f["object"], f["value"]) for f in rows} == {("카이토", "유이", "연인")}
    assert "연인" in packet and "같은 반 친구" not in packet
