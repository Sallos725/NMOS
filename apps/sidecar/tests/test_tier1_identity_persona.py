"""Tier 1 identity fixes (resolve-v6): alias direction (B1), canon joins (B2), a composite and bilingual persona and
no suffix hijacking (B4), and the name variants and `@name` blind spots (B5). Pure: no database, no model. The names
are synthetic."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid5

import pytest

from nmos_sidecar import entities, extraction, variants
from nmos_sidecar.entities import PERSONA, RESOLVER_VERSION, node, persona_parts, resolve
from nmos_sidecar.mentions import at_mentions

CONV = UUID("01900000-0000-7000-8000-0000000000a1")
NOW = datetime(2026, 11, 25, tzinfo=timezone.utc)


def fact(subject, predicate="has_trait", value="x", stype="character", **kw):
    return {"subject": subject, "subject_type": stype, "predicate": predicate, "value": value, "modality": "actual",
            "source": "narration", **kw}


def alias(subject, value, **kw):
    return fact(subject, "also_called", value, **kw)


def dalias(subject, value, **kw):
    """An alias from a compiler whose prompt states the direction (extract-v16 on; `entities.DIRECTED`)."""
    return alias(subject, value, compiler="extract-v16", **kw)


def key(r, name, kind="character"):
    return r.key(kind, name)


def one(r, *names):
    return len({key(r, n) for n in names}) == 1


def split(name, other, at=NOW):
    return {"id": uuid.uuid4(), "entity_type": "character", "name": name, "other": other, "created_at": at}


def link(name, same_as, at=NOW):
    return {"id": uuid.uuid4(), "entity_type": "character", "name": name, "same_as": same_as, "created_at": at}


# --- B1: an alias has a direction ------------------------------------------------------------------------------------

def test_a_name_with_two_aliases_of_its_own_is_one_person_and_stays_listed():
    r = resolve(CONV, [fact("세라"), dalias("세라", "?은발의 기사"), dalias("세라", "별빛")])
    assert r.status("character", "세라") == "resolved" and one(r, "세라", "?은발의 기사", "별빛")
    assert r.entity("character", "세라")["name"] == "세라"
    assert "세라" in {e["name"] for e in r.entities()}
    r = resolve(CONV, [fact("세라"), dalias("세라", "Sera"), dalias("세라", "별빛")])
    assert r.status("character", "세라") == "resolved" and one(r, "세라", "Sera", "별빛")


def test_rows_of_a_compiler_that_states_no_direction_keep_the_undirected_rule():
    """Coordinator's decision (review finding 8): a direction the model was never asked for must not merge two
    characters, so rows before extract-v16 resolve as under resolve-v5."""
    r = resolve(CONV, [fact("세라"), alias("세라", "Sera"), alias("세라", "별빛")])
    assert r.status("character", "세라") == "ambiguous"
    r = resolve(CONV, [alias("별빛", "세라"), alias("별빛", "카일")])
    assert r.status("character", "별빛") == "ambiguous" and key(r, "세라") != key(r, "카일")
    r = resolve(CONV, [fact("세라"), alias("?은발의 기사", "세라"), alias("세라", "별빛")])
    assert r.status("character", "세라") == "ambiguous"  # a description counts, as before


def test_a_nickname_two_people_give_is_ambiguous_not_the_people():
    r = resolve(CONV, [fact("세라"), fact("카일"), alias("세라", "별빛"), alias("카일", "별빛")])
    assert r.status("character", "별빛") == "ambiguous"
    assert r.status("character", "세라") == r.status("character", "카일") == "resolved"
    assert key(r, "세라") != key(r, "카일")
    assert set(r.candidates("character", "별빛")) == {"세라", "카일"}


def test_an_alias_with_an_alias_of_its_own_keeps_the_undirected_rule():
    r = resolve(CONV, [alias("하나 선배", "하나"), alias("하나", "하나쨩"), fact("하나 후배")])
    assert r.status("character", "하나") == "ambiguous"


def test_a_description_never_makes_a_name_ambiguous():
    # the description written as the subject (reversed): it is still a placeholder for the one person
    r = resolve(CONV, [fact("세라"), dalias("?은발의 기사", "세라"), dalias("세라", "별빛")])
    assert r.status("character", "세라") == "resolved" and one(r, "세라", "?은발의 기사", "별빛")
    # a nickname of the name, and the name revealed as a description
    r = resolve(CONV, [dalias("카일", "세라"), dalias("세라", "?은발의 기사")])
    assert r.status("character", "세라") == "resolved" and one(r, "카일", "세라", "?은발의 기사")


@pytest.mark.parametrize("rows", [
    [dalias("세라", "?검은 망토"), dalias("카일", "?검은 망토")],
    [dalias("?검은 망토", "세라"), dalias("?검은 망토", "카일")],
    [alias("?검은 망토", "세라"), alias("?검은 망토", "카일")],
], ids=["as-written", "reversed", "undirected"])
def test_one_description_revealed_as_two_names_is_ambiguous_either_way(rows):
    r = resolve(CONV, rows)
    assert r.status("character", "?검은 망토") == "ambiguous" and key(r, "세라") != key(r, "카일")


def test_an_owner_link_settles_a_shared_name_and_keeps_its_descriptions():
    """Review finding 8: an owner's link always settles a shared name. It drops every alias of the linked name
    except, on a directed row, a description (or a part) of it."""
    rows = [fact("세라"), fact("카일"), dalias("세라", "별빛"), dalias("카일", "별빛"), dalias("별빛", "별빛이"),
            dalias("별빛", "?노래하는 소녀")]
    r = resolve(CONV, rows, links=[link("별빛", "세라")])
    assert one(r, "세라", "별빛", "?노래하는 소녀") and key(r, "카일") != key(r, "세라")
    assert key(r, "별빛이") != key(r, "세라") and r.status("character", "별빛") == "resolved"


@pytest.mark.parametrize("make", [alias, dalias], ids=["undirected", "directed"])
def test_an_owner_link_to_one_of_a_shared_subjects_names_keeps_the_others_apart(make):
    """The review's sharper variant: the shared name written as the subject, and the owner's link picking one."""
    r = resolve(CONV, [make("별빛", "세라"), make("별빛", "카일")], links=[link("별빛", "세라")])
    assert one(r, "별빛", "세라") and key(r, "카일") != key(r, "세라")


def test_an_owner_link_on_a_shared_description_drops_every_other_name_it_was_revealed_as():
    rows = [alias("?검은 망토", "세라"), alias("?검은 망토", "카일")]
    r = resolve(CONV, rows, links=[link("?검은 망토", "세라")])
    assert one(r, "?검은 망토", "세라") and key(r, "카일") != key(r, "세라")


def test_an_owner_link_elsewhere_leaves_a_characters_aliases_alone():
    rows = [fact("세라"), dalias("세라", "Sera"), dalias("세라", "별빛"), fact("붉은 마녀")]
    r = resolve(CONV, rows, links=[link("붉은 마녀", "세라")])
    assert one(r, "세라", "Sera", "별빛", "붉은 마녀")


def test_an_owner_split_still_cuts_a_direct_alias():
    rows = [fact("세라"), dalias("세라", "Sera"), dalias("세라", "별빛")]
    r = resolve(CONV, rows, splits=[split("세라", "별빛")])
    assert one(r, "세라", "Sera") and key(r, "별빛") != key(r, "세라")


# --- B2: a lorebook entry's keys the story knows under several entities ------------------------------------------

def test_a_lorebook_entry_joins_one_persons_names_the_story_keeps_apart():
    rows = [fact("윤하람"), fact("하람"), fact("카이토")]
    r = resolve(CONV, rows, canon=[{"key": "lore:haram", "names": ["윤하람", "하람", "Haram"]}])
    assert one(r, "윤하람", "하람", "Haram") and key(r, "카이토") != key(r, "윤하람")
    assert {a.get("canon") for a in r.entity("character", "윤하람")["aliases"]} == {"lore:haram"}
    # every key known, the romanized one too
    r = resolve(CONV, rows + [fact("Haram")], canon=[{"key": "lore:haram", "names": ["윤하람", "하람", "Haram"]}])
    assert one(r, "윤하람", "하람", "Haram")


def test_a_lorebook_entry_of_unrelated_characters_joins_nothing():
    rows = [fact("윤하람"), fact("카이토")]
    r = resolve(CONV, rows, canon=[{"key": "lore:pair", "names": ["윤하람", "카이토", "하람"]}])
    assert key(r, "윤하람") != key(r, "카이토") and r.status("character", "하람") == "unresolved"


def test_a_canon_join_respects_the_owners_split_the_persona_other_kinds_and_other_entries():
    rows = [fact("윤하람"), fact("하람")]
    entry = {"key": "lore:haram", "names": ["윤하람", "하람"]}
    assert key(resolve(CONV, rows, splits=[split("윤하람", "하람")], canon=[entry]), "하람") != key(
        resolve(CONV, rows, splits=[split("윤하람", "하람")], canon=[entry]), "윤하람")
    persona = resolve(CONV, rows, persona=["하람"], canon=[entry])
    assert persona.is_persona("character", "하람") and not persona.is_persona("character", "윤하람")
    place = resolve(CONV, rows + [fact("하람", stype="place")], canon=[entry])
    assert key(place, "하람") != key(place, "윤하람")
    # a character's second entry (an item keyed on the name) leaves the join alone; one pulling a name toward another
    # known character stops it
    second = resolve(CONV, rows, canon=[entry, {"key": "lore:sword", "names": ["하람", "하람의 검"]}])
    assert one(second, "하람", "윤하람")
    pulled = resolve(CONV, rows + [fact("카이토")], canon=[entry, {"key": "lore:pair", "names": ["하람", "카이토"]}])
    assert key(pulled, "하람") != key(pulled, "윤하람")


# --- B4: a composite, bilingual persona; no suffix hijacking ------------------------------------------------------

def test_persona_parts_of_a_composite_name():
    primary, derived = persona_parts(["Ronan Voss/ 윤기현"])
    assert primary == {"ronan voss/ 윤기현", "ronan voss", "윤기현"}
    assert {"ronan", "기현"} <= derived and "voss" not in derived
    assert persona_parts(["세라 (Sera)"])[0] == {"세라 (sera)", "세라", "sera"}
    assert persona_parts(["Ethan Vance"])[1] == {"ethan"}
    assert persona_parts(["남궁세연"])[1] == {"세연"} and persona_parts(["윤 기현"])[1] == {"기현"}
    assert "타쿠미" in persona_parts(["아오키 타쿠미"])[1]
    assert persona_parts(["Captain Ronan"])[1] == {"ronan"}  # a title is never the name
    assert persona_parts([]) == (frozenset(), frozenset())


def test_a_composite_bilingual_persona_is_one_entity_under_every_name_it_is_called():
    names = ["Ronan Voss", "윤기현", "Ronan", "기현", "로난", "{{user}}"]
    rows = [fact(n) for n in names] + [fact("카이토")]
    r = resolve(CONV, rows, persona=["Ronan Voss/ 윤기현"])
    assert one(r, *names) and r.is_persona("character", "로난")
    e = r.entity("character", "기현")
    assert e["persona"] and e["id"] == str(uuid5(entities._NS, f"{CONV}:{RESOLVER_VERSION}:character:{PERSONA}"))
    assert {"ronan voss", "윤기현", "ronan", "기현", "로난"} <= r.persona_names
    assert not r.is_persona("character", "카이토") and "카이토" not in r.persona_names
    # the pieces fold into {{user}} wherever node() is asked with the host's raw name
    raw = frozenset({"ronan voss/ 윤기현"})
    assert node("character", "윤기현", raw) == node("character", "Ronan Voss", raw) == ("character", PERSONA)
    assert node("character", "기현", raw) == ("character", "기현")  # a derived name joins in Resolution only


def test_the_persona_named_only_by_a_derived_name_is_still_the_persona_and_splittable():
    rows = [fact("기현"), fact("카이토")]
    r = resolve(CONV, rows, persona=["윤기현"])
    assert r.is_persona("character", "기현") and r.entity("character", "기현")["persona"]
    r = resolve(CONV, rows, persona=["윤기현"], splits=[split("윤기현", "기현")])
    assert not r.is_persona("character", "기현") and not any(e["persona"] for e in r.entities())


def test_a_given_name_another_characters_full_name_holds_is_not_the_persona():
    for rows in ([fact("윤기현"), alias("강기현", "기현"), fact("기현")], [fact("윤기현"), fact("강기현"), fact("기현")]):
        r = resolve(CONV, rows, persona=["윤기현"])
        assert not r.is_persona("character", "기현") and "기현" not in r.persona_names
    r = resolve(CONV, [fact("윤기현")], persona=["윤기현"])
    assert "기현" in r.persona_names  # nobody else holds it


def test_the_reverse_mismatch_a_given_or_first_name_alone_is_the_persona():
    assert resolve(CONV, [fact("한서윤"), fact("서윤")], persona=["한서윤"]).is_persona("character", "서윤")
    assert resolve(CONV, [fact("Ethan Vance"), fact("Ethan")], persona=["Ethan Vance"]).is_persona("character", "Ethan")
    assert resolve(CONV, [fact("엘레나")], persona=["Elena Vance"]).is_persona("character", "엘레나")
    assert resolve(CONV, [fact("Takumi")], persona=["타쿠미"]).is_persona("character", "Takumi")


def test_a_titled_name_is_not_the_persona_and_a_full_name_ending_with_it_is_but_splittably():
    rows = [fact("민수"), fact("경비병 민수"), fact("Captain Smith")]
    r = resolve(CONV, rows, persona=["민수", "Smith"])
    assert not r.is_persona("character", "경비병 민수") and not r.is_persona("character", "Captain Smith")
    rows = [fact("Smith"), fact("John Smith")]
    r = resolve(CONV, rows, persona=["Smith"])
    assert r.is_persona("character", "John Smith")  # resolve-v5's rule still holds
    # node() folds the full name as resolve-v5 did (review finding 5: callers without a resolution); the resolution's
    # own node keeps it apart, so the owner's split below can be planned
    assert node("character", "John Smith", frozenset({"smith"})) == node("character", "Smith", frozenset({"smith"}))
    assert r.node("character", "John Smith") != r.node("character", "Smith")
    r = resolve(CONV, rows, persona=["Smith"], splits=[split("Smith", "John Smith")])
    assert not r.is_persona("character", "John Smith") and r.is_persona("character", "Smith")
    # the owner splits; a later link takes it back
    later = NOW + timedelta(minutes=1)
    r = resolve(CONV, rows, persona=["Smith"], splits=[split("Smith", "John Smith")],
                links=[link("John Smith", "Smith", at=later)])
    assert r.is_persona("character", "John Smith")


def test_the_owners_link_or_split_outranks_a_derived_name():
    rows = [fact("윤기현"), fact("기현"), fact("카이토"), fact("로난")]
    linked = resolve(CONV, rows, persona=["윤기현"], links=[link("기현", "카이토")])
    assert one(linked, "기현", "카이토") and not linked.is_persona("character", "기현")
    # a split between two names the persona would go by keeps the later one off it
    apart = resolve(CONV, rows, persona=["Ronan Voss/ 윤기현"], splits=[split("기현", "로난")])
    assert key(apart, "기현") != key(apart, "로난")
    assert apart.is_persona("character", "기현") != apart.is_persona("character", "로난")


def test_a_full_name_mentioned_first_keeps_the_personas_id():
    r = resolve(CONV, [fact("아오키 타쿠미"), fact("타쿠미")], persona=["타쿠미"])
    plain = resolve(CONV, [fact("{{user}}")])
    assert r.entity("character", "아오키 타쿠미")["id"] == plain.entity("character", "{{user}}")["id"]
    assert "아오키 타쿠미" in r.persona_names and "아오키 타쿠미" in r.entity("character", "타쿠미")["names"]


def test_no_persona_reported_derives_nothing():
    r = resolve(CONV, [fact("기현"), fact("Ronan")])
    assert not any(e["persona"] for e in r.entities())
    assert r.persona_names == frozenset(entities.USER_NAMES)


# --- B5: name variants -------------------------------------------------------------------------------------------

def test_the_two_syllable_family_names_match_extraction():
    assert variants.FAMILY_TWO == extraction.FAMILY_TWO


@pytest.mark.parametrize(("name", "given"), [("남궁세연", "세연"), ("제갈민", None), ("백 이안", "이안"),
                                             ("남궁 세연", "세연"), ("크리스티나", None), ("아오키 타쿠미", None)])
def test_more_given_names(name, given):
    assert variants.given(name) == given


def test_a_western_first_name_is_indexed():
    assert variants.key("elena") in variants.latin_keys("elena vance")
    assert variants.key("arthur") in variants.latin_keys("sir arthur pendragon")
    assert variants.key("sir") not in variants.latin_keys("sir arthur pendragon")
    assert variants.aliases([{"id": "e", "type": "character", "names": ["Elena Vance"]}], [], "엘레나는?") == {
        "elena vance": frozenset({"엘레나"})}
    assert variants.aliases([{"id": "d", "type": "character", "names": ["Ronan Voss"]}], [], "로난이 왔다") == {
        "ronan voss": frozenset({"로난"})}


def test_a_five_syllable_spelling_is_read():
    assert variants.key("yamanouchi") in variants.hangul_keys("야마노우치")
    assert variants.aliases([{"id": "y", "type": "character", "names": ["Yamanouchi"]}], [], "야마노우치는?") == {
        "yamanouchi": frozenset({"야마노우치"})}


# --- B5: @name ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["@하람아 이리 와", "@하람야", "@하람님", "@하람님께서 오셨다", "@하람씨는?", "@하람께"])
def test_a_vocative_or_an_honorific_after_the_name(text):
    assert at_mentions(text, {"하람": "ent-haram"}) == ["ent-haram"]


def test_only_one_particle_and_one_honorific():
    assert at_mentions("@세라에게만 말해", {"세라": "s"}) == []
    assert at_mentions("@세라님님", {"세라": "s"}) == []


def test_three_word_names_and_an_apostrophe_inside_a_word():
    names = {"세라 델 모렌": "ent-sera", "o'connor": "ent-oc", "세라": "ent-other"}
    assert at_mentions("@세라 델 모렌에게 물어봐", names) == ["ent-sera"]
    assert at_mentions("@O'Connor, come here", names) == ["ent-oc"]
    assert at_mentions("@O’Connor!", {"o’connor": "ent-oc"}) == ["ent-oc"]
    assert at_mentions("'@세라'", names) == ["ent-other"]  # a closing quote still closes


def test_aliases_widen_the_names_and_a_shared_one_names_neither():
    names = {"백이안": "ent-ian", "kaito": "ent-kaito"}
    assert at_mentions("@이안 어디?", names) == []
    assert at_mentions("@이안 어디?", names, aliases={"백이안": frozenset({"이안"})}) == ["ent-ian"]
    shared = {"백이안": frozenset({"이안"}), "kaito": frozenset({"이안"})}
    assert at_mentions("@이안 어디?", names, aliases=shared) == []
    # a name the caller gave keeps its own key
    assert at_mentions("@kaito", names, aliases={"백이안": frozenset({"kaito"})}) == ["ent-kaito"]


def test_a_split_from_a_persona_the_story_never_names_does_not_break_a_canon_join():
    """Self-review of e2d7064: the persona's node made for a derived name and dropped again left the owner's split in
    the canon join's split list, and the read raised KeyError."""
    rows = [fact("기현"), fact("윤하람"), fact("하람")]
    r = resolve(CONV, rows, persona=["윤기현"], splits=[split("윤기현", "기현")],
                canon=[{"key": "lore:haram", "names": ["윤하람", "하람"]}])
    assert one(r, "윤하람", "하람") and not r.is_persona("character", "기현")
    assert not any(e["persona"] for e in r.entities())


def test_names_persona_reads_one_name_without_a_resolution():
    assert entities.names_persona("character", "Seon Hale", ["Hale"])  # resolve-v5's full name, for extraction
    assert entities.names_persona("character", "기현", ["Ronan Voss/ 윤기현"])
    assert entities.names_persona("character", "{{user}}") and entities.names_persona("character", "윤기현", ["윤기현"])
    assert not entities.names_persona("character", "경비병 민수", ["민수"])
    assert not entities.names_persona("place", "기현", ["윤기현"]) and not entities.names_persona("character", "카이토", [])


def test_a_derived_name_another_name_gives_as_its_alias_is_that_names():
    """Self-review: guard (b) for story aliases that do not contain the derived name."""
    r = resolve(CONV, [fact("윤기현"), alias("카이토", "기현")], persona=["윤기현"])
    assert not r.is_persona("character", "카이토") and not r.is_persona("character", "기현")
    r = resolve(CONV, [fact("Ronan Voss"), alias("Ronan Pryce", "로난")], persona=["Ronan Voss"])
    assert not r.is_persona("character", "Ronan Pryce") and not r.is_persona("character", "로난")
    # the persona's own derived name with an alias of its own still joins
    r = resolve(CONV, [fact("윤기현"), alias("기현", "기현형")], persona=["윤기현"])
    assert r.is_persona("character", "기현형")


def test_the_persona_introducing_itself_under_another_of_its_names():
    claim = {"source": "character_claim", "asserted_by": "아오키 타쿠미"}
    r = resolve(CONV, [fact("타쿠미"), alias("타쿠미", "타쿠", **claim)], persona=["타쿠미"])
    assert one(r, "타쿠미", "타쿠") and r.is_persona("character", "타쿠")
    other = {"source": "character_claim", "asserted_by": "카이토"}
    r = resolve(CONV, [fact("타쿠미"), alias("타쿠미", "타쿠", **other)], persona=["타쿠미"])
    assert not r.is_persona("character", "타쿠")


@pytest.mark.parametrize(("persona", "names", "a", "b"), [
    (["Smith"], ["Smith", "John Smith"], "Smith", "John Smith"),
    (["윤기현"], ["윤기현", "기현"], "윤기현", "기현"),
    (["Ronan Voss/ 윤기현"], ["{{user}}", "로난"], "{{user}}", "로난"),
])
def test_the_owner_can_plan_a_split_of_a_derived_persona_name(persona, names, a, b):
    """The brief's symptom: a name folded into {{user}} by node() could not be split ("the two names are the same",
    422). The repair plan now accepts it, and the split it stores takes effect."""
    from nmos_sidecar.repairs import _plan_split

    rows = [fact(n) for n in names]
    r = resolve(CONV, rows, persona=persona)
    target, _ = _plan_split(a, b, "character", r)
    after = resolve(CONV, rows, persona=persona, splits=[{**target, "id": uuid.uuid4(), "created_at": NOW}])
    assert key(after, a) != key(after, b) and after.is_persona("character", a)
