"""A missing entity type is filled only when the same reply or the known entities settle it."""

from __future__ import annotations

from conftest import make_client
from nmos_sidecar.predicates import fill_types, validate
from simchat import SimChat
from test_extraction import drain, filler
from test_sidecar_integration import sync

AKARI = {"subject": "다나카 아카리", "subject_type": "character", "predicate": "event", "value": "불치병으로 사망"}
FRIEND = {"subject": "켄지", "subject_type": "character", "predicate": "relationship", "object": "다나카 아카리",
          "object_type": None, "value": "소꿉친구"}


def test_a_type_given_elsewhere_in_the_reply_fills_the_gap():
    (akari, _), (friend, note) = fill_types([AKARI, FRIEND])
    assert friend["object_type"] == "character" and note == "object_type inferred"
    assert validate(friend) == ("valid", None)
    assert akari == AKARI and FRIEND["object_type"] is None  # inputs are not mutated
    assert validate(FRIEND)[0] == "pending"


def test_known_entities_fill_the_gap_by_name_or_other_name():
    hints = [{"name": "Tanaka Akari", "type": "character", "also": ["다나카 아카리"]}]
    for value in (None, "", "null"):
        [(item, note)] = fill_types([{**FRIEND, "object_type": value}], hints)
        assert item["object_type"] == "character" and note == "object_type inferred"
    [(item, note)] = fill_types([{**FRIEND, "subject_type": None}], [{"name": "켄지", "type": "character"}])
    assert item["subject_type"] == "character" and note == "subject_type inferred"


def test_no_guess_when_nothing_or_conflicting_evidence():
    assert fill_types([FRIEND]) == [(FRIEND, None)]
    place = {"subject": "다나카 아카리", "subject_type": "place", "predicate": "world_fact", "value": "x"}
    [_, _, (item, note)] = fill_types([AKARI, place, FRIEND])
    assert item["object_type"] is None and note is None
    wrong = {**FRIEND, "object_type": "person"}  # a type that was given is never overridden
    assert fill_types([AKARI, wrong])[1] == (wrong, None)


def test_filled_relationship_is_a_valid_fact(migrated, db):
    def complete(system, user):
        if "소꿉친구" not in user.split("TARGET", 1)[1]:
            return {"assertions": []}, "{}"
        return {"assertions": [{**AKARI, "modality": "actual"}, {**FRIEND, "modality": "actual"}]}, "{}"
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake") as c:
        chat = SimChat()
        chat.user("아카리 얘기를 꺼낸다.")
        chat.reply("켄지와 다나카 아카리는 소꿉친구였다. 아카리는 불치병으로 세상을 떠났다.")
        filler(chat, 5)
        sync(c, chat)
        drain(migrated, complete)
    row = db.execute("SELECT object_type, status, reason FROM assertion WHERE predicate = 'relationship'").fetchone()
    assert row == {"object_type": "character", "status": "valid", "reason": "object_type inferred"}
