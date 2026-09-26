"""Phase 6 (docs/phases/PHASE-6.md): an item's holder, place and end are one whereabouts (Q2, Q3), and
using an item after its end is a conflict (Q1, Q4)."""

from __future__ import annotations

from test_semantics import current, row


def item_at(pos: int, item: str, place: str, **kw):
    return row(pos, item, "located_in", place, subject_type="item", **kw)


def held(pos: int, who: str, item: str, **kw):
    return row(pos, who, "possesses", item, **kw)


def test_a_newer_place_closes_the_holder():
    assert current([held(1, "하나", "지도"), item_at(3, "지도", "탁자")]) == [("지도", "탁자", "positive")]


def test_a_newer_holder_closes_the_place():
    assert current([item_at(1, "지도", "탁자"), held(3, "카이토", "지도")]) == [("카이토", "지도", "positive")]


def test_holder_and_place_from_one_turn_stay_together():
    assert current([held(2, "하나", "지도"), item_at(2, "지도", "도서관")]) == [
        ("하나", "지도", "positive"), ("지도", "도서관", "positive")]
    # A later turn that moves the item keeps only what it states.
    assert current([held(2, "하나", "지도"), item_at(2, "지도", "도서관"), item_at(4, "지도", "항구")]) == [
        ("지도", "항구", "positive")]


def test_negations_end_only_their_own_slot():
    # "Hana lost the map" ends the holder as before (ADR 0013); a denial of another place changes nothing.
    assert current([held(1, "하나", "지도"), held(2, "하나", "지도", polarity="negative")]) == [
        ("하나", "지도", "negative")]
    assert current([item_at(1, "지도", "탁자"), item_at(2, "지도", "항구", polarity="negative")]) == [
        ("지도", "탁자", "positive"), ("지도", "항구", "negative")]
    # A negation is no statement of where the item is now: it does not close the other slot.
    assert current([item_at(1, "지도", "탁자"), held(2, "하나", "지도", polarity="negative")]) == [
        ("지도", "탁자", "positive"), ("하나", "지도", "negative")]


def test_a_characters_place_is_its_own_fact():
    from nmos_sidecar.facts import version_key
    assert version_key(row(1, "하나", "located_in", "도서관")) == ("located_in", "하나")
    assert version_key(held(1, "하나", "지도")) == version_key(item_at(2, "지도", "탁자")) == ("whereabouts", "지도")


def test_messages_without_a_turn_count_alone():
    # Per-message extractions of older generations: two messages are two statements, not one turn.
    a = {**held(5, "하나", "지도"), "turn": None}
    b = {**item_at(6, "지도", "탁자"), "turn": None}
    assert current([a, b]) == [("지도", "탁자", "positive")]


def test_history_names_each_predicate():
    from nmos_sidecar.facts import _versions
    (fact,) = _versions([held(1, "하나", "지도"), item_at(3, "지도", "탁자")])
    assert [(h["predicate"], h["subject"]) for h in fact["history"]] == [("possesses", "하나"), ("located_in", "지도")]
    assert fact["versions"] == 2


def ended(pos: int, item: str, how: str, **kw):
    return row(pos, item, "destroyed", None, how, subject_type="item", **kw)


def test_an_end_closes_holder_and_place():
    assert current([held(1, "하나", "편지"), item_at(1, "편지", "서재"), ended(4, "편지", "불탐")]) == [
        ("편지", "불탐", "positive")]


def test_an_end_closes_the_holder_of_its_own_turn_in_either_order():
    assert current([held(3, "하나", "편지"), ended(3, "편지", "불탐")]) == [("편지", "불탐", "positive")]
    assert current([ended(3, "편지", "불탐"), held(3, "하나", "편지")]) == [("편지", "불탐", "positive")]


def test_a_denied_end_ends_nothing_else():
    # "The letter did not burn" is a negative fact; the holder stays.
    assert current([held(1, "하나", "편지"), ended(2, "편지", "불탐", polarity="negative")]) == [
        ("하나", "편지", "positive"), ("편지", "불탐", "negative")]


def test_destroyed_is_an_item_predicate():
    from nmos_sidecar.predicates import REGISTRY, validate
    assert REGISTRY["destroyed"].subject_types == ("item",)
    assert validate({"predicate": "destroyed", "subject": "편지", "subject_type": "item", "value": "불탐"}) == (
        "valid", None)
    assert validate({"predicate": "destroyed", "subject": "하나", "subject_type": "character", "value": "죽음"})[0] == (
        "pending")


def test_prompt_asks_for_destroyed_only_when_the_item_is_gone():
    from nmos_sidecar.extraction import SYSTEM_PROMPT
    from nmos_sidecar.predicates import registry_prompt
    assert "- destroyed (subject: item, value: text)" in registry_prompt()
    assert "Not when it is only damaged, hidden, dropped or lost" in SYSTEM_PROMPT


def disputes(history):
    from nmos_sidecar.facts import _versions
    return [(f["subject"], (f.get("disputed_by") or {}).get("value")) for f in _versions(history)]


def test_holding_an_item_after_its_end_is_disputed():
    assert disputes([held(1, "하나", "편지"), ended(3, "편지", "불탐"), held(5, "하나", "편지")]) == [("하나", "불탐")]
    # The dispute follows the item while it keeps being used, in holder and place alike.
    assert disputes([ended(3, "편지", "불탐"), held(5, "하나", "편지"), item_at(7, "편지", "서재")]) == [
        ("편지", "불탐")]


def test_a_new_end_or_a_denied_end_settles_the_dispute():
    used = [ended(3, "편지", "불탐"), held(5, "하나", "편지")]
    assert disputes(used + [ended(7, "편지", "찢김")]) == [("편지", None)]
    # "It did not burn after all": the holder stands, undisputed, next to the denied end.
    assert sorted(disputes(used + [ended(7, "편지", "불탐", polarity="negative")])) == [("편지", None), ("하나", None)]


def test_the_same_turn_is_not_a_dispute():
    assert disputes([ended(3, "편지", "불탐"), held(3, "하나", "편지")]) == [("편지", None)]


def test_disputed_fact_line_shows_both_sides():
    from nmos_sidecar.facts import _versions, fact_line
    (fact,) = _versions([ended(3, "편지", "불탐"), held(5, "하나", "편지")])
    assert fact_line(fact) == ('    <Fact kind="possesses" turn="5" disputed="true">'
                               "하나 possesses 편지; but turn 3: 편지 destroyed: 불탐</Fact>")


def test_packet_note_explains_disputed_only_when_used():
    from nmos_sidecar.packet import compile_packet
    plain, _, _, _ = compile_packet([], 400, facts=['    <Fact kind="possesses" turn="1">a possesses b</Fact>'])
    marked, _, _, _ = compile_packet([], 400, facts=['    <Fact kind="possesses" turn="1" disputed="true">a</Fact>'])
    assert "contradicts itself" not in plain and "contradicts itself" in marked


# --- outcomes and the Inspector (step 4) -----------------------------------------------------------

def outcomes(history):
    from nmos_sidecar.facts import _versions
    return [(h["predicate"], h["outcome"]) for h in _versions(history)[0]["history"]]


def test_every_assertion_has_an_outcome():
    assert outcomes([held(1, "하나", "편지"), held(2, "카이토", "편지"), item_at(3, "편지", "서재")]) == [
        ("possesses", "superseded"), ("possesses", "superseded"), ("located_in", "current")]
    assert outcomes([held(1, "하나", "편지"), held(2, "하나", "편지", polarity="negative")]) == [
        ("possesses", "ended"), ("possesses", "current")]
    assert outcomes([held(1, "하나", "편지"), ended(3, "편지", "불탐")]) == [
        ("possesses", "ended"), ("destroyed", "current")]
    assert outcomes([ended(3, "편지", "불탐"), held(5, "하나", "편지")]) == [
        ("destroyed", "conflicting"), ("possesses", "current")]


def test_inspector_shows_item_timelines_and_conflicts(migrated, db):
    from conftest import make_client
    from memeval import stub_extractor
    from simchat import SimChat
    from test_extraction import drain
    from test_generations import LLM
    from test_sidecar_integration import sync

    chat = SimChat()
    for line in ("Hana has the letter.", "Hana burns the letter.", "Hana has the letter."):
        chat.user(line)
        chat.reply("Noted.")
    chat.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, stub_extractor)
        conv = c.get("/v1/conversations").json()[0]["id"]
        page = c.get(f"/inspector/c/{conv}").text
        assert "충돌 (이야기가 앞뒤가 맞지 않음)" in page and "letter destroyed: burned" in page
        assert "Hana 보유" in page and "소멸: burned" in page and "끝남" in page and ">충돌<" in page
        en = c.get(f"/inspector/c/{conv}?lang=en").text
        assert "held by Hana" in en and "destroyed: burned" in en and "conflicting" in en
        facts = c.get(f"/v1/conversations/{conv}/facts?history=true").json()
        assert [h["outcome"] for h in facts[0]["history"]] == ["ended", "conflicting", "current"]
