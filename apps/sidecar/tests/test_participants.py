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


# --- step 2: resolution and recall (Q4) -----------------------------------------------------------------

import uuid  # noqa: E402

from nmos_sidecar.entities import resolve  # noqa: E402
from nmos_sidecar.extraction import entity_hints, hints_block  # noqa: E402
from nmos_sidecar.facts import _annotate, fact_line, participant_entities, relevant_facts, version_key  # noqa: E402

CONV = uuid.uuid4()


def row(pos, subject, predicate, value=None, obj=None, **kw):
    return {"id": pos, "position": pos, "turn": pos, "host_logical_id": f"m{pos}", "subject": subject,
            "subject_type": kw.pop("subject_type", "character"), "predicate": predicate, "object": obj,
            "object_type": kw.pop("object_type", "character" if obj else None), "value": value,
            "polarity": "positive", "modality": "actual", "source": "narration", "asserted_by": None,
            "knowledge": None, "known_by": None, "hidden_from": None, "participants": None, **kw}


def with_(*pairs):
    return [{"name": n, "type": t} for n, t in pairs]


def hints(rows, turn=99, limit=40):
    ctx = {"target": {"conversation_id": CONV, "turn": turn}}
    return "\n".join(hints_block(entity_hints(None, ctx, "k", limit, rows)))


def test_participants_never_change_known_entities_hard_case():
    """PHASE-8 In scope 3: a participant spelling comes before the entity's first subject/object mention
    and before the also_called that joins its aliases; the KNOWN ENTITIES block is byte-for-byte the same."""
    base = [row(1, "카이토", "event", "HANA와 산책", participants=None),
            row(2, "hana", "located_in", obj="도서관", object_type="place"),
            row(3, "hana", "also_called", "하나"),
            row(4, "유이", "event", "편지를 썼다")]
    early = [dict(r) for r in base]
    early[0]["participants"] = with_(("HANA", "character"), ("하나", "character"), ("경비병들", "group"),
                                     ("미나", "character"))
    assert hints(early) == hints(base)
    assert "미나" not in hints(early) and "경비병들" not in hints(early)  # participant-only: no hint
    # The resolver still knows the participant-only entities (Inspector, recall).
    names = {e["name"] for e in resolve(CONV, early).entities()}
    assert {"미나", "경비병들"} <= names
    # And every resolve-v1 entity keeps its id, name, names and aliases.
    before = {e["id"]: {k: e[k] for k in ("name", "names", "aliases", "type")} for e in resolve(CONV, base).entities()}
    after = {e["id"]: {k: e[k] for k in ("name", "names", "aliases", "type")} for e in resolve(CONV, early).entities()}
    assert all(after[i] == before[i] for i in before)


def test_typed_identity_and_ambiguous_aliases():
    rows = [row(1, "카이토", "event", "유이를 도왔다", participants=with_(("유이", "character"), ("유이", "group")))]
    r = resolve(CONV, rows)
    assert r.entity("character", "유이")["id"] != r.entity("group", "유이")["id"]
    # A nickname two people claim is ambiguous (ADR 0012): as a participant it links neither.
    amb = [row(1, "하나", "also_called", "꼬마"), row(2, "유이", "also_called", "꼬마"),
           row(3, "카이토", "event", "꼬마를 불렀다", participants=with_(("꼬마", "character")))]
    r = resolve(CONV, amb)
    assert r.status("character", "꼬마") == "ambiguous"
    a = dict(amb[2])
    _annotate(a, r)
    assert participant_entities(a, r)[0]["entity"]["status"] == "ambiguous"
    assert "하나" not in a["names"] and "유이" not in a["names"]


def annotated(rows):
    r = resolve(CONV, rows)
    for x in rows:
        _annotate(x, r)
    return rows


EVENT = row(10, "카이토", "event", "유이를 경비병들에게 넘겨주었다", salience="major",
            participants=with_(("유이", "character"), ("경비병들", "group")))


def pick(facts, q, **kw):
    return relevant_facts(facts, q, "", set(), 8, events_limit=3, **kw)


def test_an_addressed_participant_brings_the_fact_back():
    (f,) = annotated([dict(EVENT)])
    assert pick([f], "유이야, 오랜만이야.") == [f]
    assert pick([f], "경비병들은 어디 있지?") == [f]
    assert pick([f], "카이토야.") == [f]  # the subject still counts
    # In the previous reply it counts like the subject there (1.0).
    assert relevant_facts([f], "잘 지냈어?", "유이가 고개를 들었다.", set(), 8, events_limit=3) == [f]
    # Without participant data (older generations, Q5) it does not.
    (old,) = annotated([{**EVENT, "participants": None}])
    assert pick([old], "유이야, 오랜만이야.") == []


def test_participant_aliases_and_the_persona():
    rows = annotated([row(1, "유이", "also_called", "Yui"), dict(EVENT),
                      row(11, "하나", "event", "{{user}}에게 고백했다", salience="major",
                          participants=with_(("{{user}}", "character")))])
    event, confession = rows[1], rows[2]
    assert pick([event], "Yui, long time no see.") == [event]
    # The persona is never a mention (a query that repeats the value's words still matches lexically,
    # as before Phase 8).
    assert pick([confession], "{{user}}는 창밖을 보며 오늘 저녁에 무엇을 먹을지 한참 동안 고민했다.") == []
    assert "{{user}}" not in confession["names"]


def test_claims_count_participants_too():
    claim = annotated([row(12, "하나", "knows", "카이토가 편지를 읽으면 모든 게 끝난다", source="character_claim",
                           asserted_by="하나", participants=with_(("카이토", "character")))])[0]
    assert pick([claim], "카이토, 괜찮아?") == [claim]


def test_minor_events_and_the_cap_are_unchanged():
    minor = annotated([row(13, "하나", "event", "유이와 빵을 구웠다", salience="minor",
                           participants=with_(("유이", "character")))])[0]
    assert pick([minor], "유이야, 오랜만이야.") == []  # a minor event needs the query to be about it
    many = annotated([row(20 + i, "카이토", "event", f"유이와 일 {i}", participants=with_(("유이", "character")))
                      for i in range(6)])
    assert len(pick(many, "유이야")) == 3


def test_a_participant_is_not_part_of_the_version_key():
    a = annotated([dict(EVENT)])[0]
    b = annotated([{**EVENT, "id": 11, "participants": with_(("하나", "character"))}])[0]
    assert version_key(a) == version_key(b)


def test_a_participant_is_not_a_knower():
    """PHASE-8 'participant is not a knower' (owner-reported case): marks are exactly as stored."""
    limited = annotated([row(14, "카이토", "event", "유이의 수업에서 거짓말을 하고 일찍 나갔다", salience="major",
                             knowledge="limited", known_by=["카이토", "하나"], hidden_from=["유이"],
                             participants=with_(("유이", "character")))])[0]
    assert pick([limited], "유이야, 오랜만이야.") == [limited]
    assert 'known_by="카이토, 하나" hidden_from="유이"' in fact_line(limited)
    unmarked = annotated([{**limited, "hidden_from": None}])[0]
    line = fact_line(unmarked)
    assert 'known_by="카이토, 하나"' in line and "hidden_from" not in line


def test_extract_v8_asks_for_typed_participants():
    from nmos_sidecar.extraction import COMPILER_VERSION, SYSTEM_PROMPT
    from nmos_sidecar.predicates import registry_prompt
    prompt = SYSTEM_PROMPT.format(registry=registry_prompt())
    assert COMPILER_VERSION == "extract-v8"
    assert "`with`, for `event`, `goal`, `knows` and `destroyed` only" in prompt
    assert '"with": [{"name": "...", "type": "character|group"}]' in prompt
    assert "Being there does not mean knowing" in prompt  # PHASE-8: a participant is not a knower
