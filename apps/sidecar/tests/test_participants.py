"""Phase 8 (docs/phases/PHASE-8.md): typed participants of an assertion (Q2, Q3)."""

from __future__ import annotations

from conftest import make_client
from nmos_sidecar.extraction import normalize
from nmos_sidecar.predicates import participants
from simchat import SimChat
from test_extraction import drain
from test_generations import LLM
from test_sidecar_integration import sync


def item(predicate="event", **kw):
    return {"subject": "카이토", "subject_type": "character", "predicate": predicate, "value": "유이를 경비병들에게 넘겨주었다",
            "modality": "actual", **kw}


def test_typed_participants_are_kept_on_the_measured_predicates():
    w = [{"name": "유이", "type": "character"}, {"name": "경비병들", "type": "group"}]
    for predicate in ("event", "goal", "knows", "destroyed"):
        assert participants(item(predicate, **{"with": w})) == w
    # Thread resolutions and every other predicate carry none (Q3).
    assert participants(item("fulfilled", **{"with": w})) is None
    assert participants({**item("possesses", **{"with": w}), "object": "지도", "object_type": "item"}) is None
    assert participants(item("has_status", **{"with": w})) is None


def test_participant_validation():
    raw = [
        {"name": "유이", "type": "character"},
        {"name": " 유이 ", "type": "character"},  # a normalized repeat
        {"name": "유이", "type": "group"},  # another type is another entity (ADR 0012)
        {"name": "카이토", "type": "character"},  # the subject
        {"name": "Kaito", "type": "place"},  # not a person
        {"name": "", "type": "character"},
        {"name": "x" * 61, "type": "character"},
        {"name": 3, "type": "character"},
        "유이",  # untyped
        {"type": "character"},
    ]
    assert participants(item(**{"with": raw})) == [{"name": "유이", "type": "character"}, {"name": "유이", "type": "group"}]
    # The object is dropped too, and at most six remain.
    many = [{"name": f"인물{i}", "type": "character"} for i in range(9)]
    got = participants({**item(**{"with": [{"name": "하나", "type": "character"}, *many]}),
                        "object": "하나", "object_type": "character"})
    assert [p["name"] for p in got] == [f"인물{i}" for i in range(6)]
    # Not a list, empty, or everything dropped: none.
    assert participants(item(**{"with": "유이"})) is None
    assert participants(item(**{"with": []})) is None
    assert participants(item(**{"with": [{"name": "카이토", "type": "character"}]})) is None
    # The persona is a valid participant (it only never counts as a mention, Q4).
    assert participants(item(**{"with": [{"name": "{{user}}", "type": "character"}]})) == [
        {"name": "{{user}}", "type": "character"}]


def test_normalize_keeps_participants_only_on_valid_rows():
    rows = normalize([item(**{"with": [{"name": "유이", "type": "character"}]}),
                      {**item("knows", **{"with": [{"name": "유이", "type": "character"}]}), "subject_type": "place"}],
                     "")
    assert rows[0]["participants"] == [{"name": "유이", "type": "character"}]
    assert rows[1]["status"] == "pending" and rows[1]["participants"] is None


def with_complete(system: str, user: str) -> tuple[dict, str]:
    target = user.split("TARGET", 1)[1]
    items = []
    if "betrays" in target:
        items.append({**item(), "source": "narration", "with": [{"name": "유이", "type": "character"},
                                                                {"name": "경비병들", "type": "group"}]})
    return {"assertions": items}, "{}"


def test_participants_are_stored_as_a_json_array(migrated, db):
    chat = SimChat()
    chat.user("Kaito betrays Yui.")
    chat.reply("Noted.")
    chat.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, with_complete)
    row = db.execute("SELECT participants, jsonb_typeof(participants) AS kind FROM assertion").fetchone()
    assert row["kind"] == "array"
    assert row["participants"] == [{"name": "유이", "type": "character"}, {"name": "경비병들", "type": "group"}]
