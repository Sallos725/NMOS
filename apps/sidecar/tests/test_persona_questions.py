"""PHASE-40: explicit questions about the resolved persona (synthetic)."""
from __future__ import annotations

import pytest

from nmos_sidecar.facts import _annotate, fact_line, relevant_facts
from nmos_sidecar.entities import resolve
from test_persona_name import CONV
from test_semantics import row


def prepared(*rows, name="타쿠미"):
    r = resolve(CONV, list(rows), persona=[name])
    for f in rows:
        _annotate(f, r)
    return list(rows), r


def pick(rows, r, query, **kwargs):
    return relevant_facts(rows, query, "", set(), kwargs.pop("limit", 8), persona=r.persona_names,
                          named_by_words=True, persona_questions=True,
                          persona_entity=r.entity("character", "{{user}}")['id'], **kwargs)


def own(pos, predicate, obj=None, value=None, **kwargs):
    return row(pos, "{{user}}", predicate, obj, value, subject_type="character", **kwargs)


@pytest.mark.parametrize("query,predicate", [
    ("타쿠미는 무슨 일을 해?", "identity"), ("타쿠미의 직업은 뭐였지?", "identity"),
    ("타쿠미는 지금 어디 있어?", "located_in"), ("타쿠미는 예전에 어디 살았어?", "located_in"),
    ("타쿠미는 무엇을 가지고 있어?", "possesses"), ("타쿠미는 어떤 성격이야?", "has_trait"),
    ("타쿠미는 무슨 일이 있었어?", "event"),
])
def test_only_asked_kind_is_added(query, predicate):
    rows, r = prepared(own(1, "identity", value="천문학자"), own(2, "located_in", "북쪽 관측소"),
                       own(3, "possesses", "황동 열쇠"), own(4, "has_trait", value="차분함"),
                       own(5, "event", value="대회 우승", salience="major"))
    assert [f["predicate"] for f in pick(rows, r, query)] == [predicate]


@pytest.mark.parametrize("query,predicate", [
    ("What does Takumi do?", "identity"), ("What is Takumi's job?", "identity"),
    ("Where is Takumi?", "located_in"), ("Where was Takumi before?", "located_in"),
    ("What does Takumi own?", "possesses"), ("What happened to Takumi?", "event"),
])
def test_english_questions(query, predicate):
    rows, r = prepared(own(1, "identity", value="astronomer"), own(2, "located_in", "observatory"),
                       own(3, "possesses", "brass key"), own(4, "event", value="won tournament", salience="major"),
                       name="Takumi")
    assert [f["predicate"] for f in pick(rows, r, query)] == [predicate]


@pytest.mark.parametrize("query", [
    "타쿠미는 고개를 끄덕인다.", "타쿠미는 어디론가 걷는다.",
    "타쿠미는 고개를 끄덕이고 루카는 무슨 일을 해?", "타쿠미는 루카가 어디 있는지 알아?",
    "타쿠미는 웃었다. 루카는 무슨 일을 해?", "타쿠미마는 무슨 일을 해?",
    "타쿠미 선배는 무슨 일을 해?", "타쿠미는 자신의 직업을 소개했다.", "루카는 타쿠미에게 어디 있어?",
    "타쿠미는 자신의 친구가 무슨 일을 하는지 물었다.", "타쿠미의 친구는 어떤 사람이야?",
    "타쿠미는 친구가 어떤 사람이야?", "타쿠미는 고개를 끄덕이고 그 여자는 무슨 일을 해?",
    "타쿠미는 무슨 일을 하는 사람인지 설명했다.",
    "타쿠미는 옆 사람의 직업이 무엇인지 궁금해.",
    "타쿠미는 그 사람의 회사가 어디인지 물어?",
])
def test_other_subject_or_narration_is_unchanged(query):
    rows, r = prepared(own(1, "identity", value="astronomer"), own(2, "located_in", "observatory"),
                       row(3, "루카", "identity", value="baker", subject_type="character"))
    baseline = relevant_facts(rows, query, "", set(), 8, persona=r.persona_names, named_by_words=True)
    assert pick(rows, r, query) == baseline


def test_aliases_and_same_named_item():
    rows, r = prepared(own(1, "identity", value="astronomer"), own(2, "also_called", value="타쿠"),
                       row(3, "타쿠", "located_in", "상자", subject_type="item"))
    assert rows[0] in pick(rows, r, "타쿠는 무슨 일을 해?")
    assert rows[2] not in pick(rows, r, "타쿠는 어디 있어?")


def test_unresolved_subject():
    rows, r = prepared(own(1, "identity", value="astronomer"))
    rows[0]["subject_entity"] = {"status": "ambiguous", "candidates": []}
    assert pick(rows, r, "타쿠미는 무슨 일을 해?") == []


def test_cap_and_existing_limit_never_displace_other_person():
    rows, r = prepared(*(own(i, "identity", value=f"profession {i}") for i in range(1, 5)),
                       row(5, "루카", "located_in", "항구", subject_type="character"))
    query = "루카는 어디 있어? 타쿠미는 무슨 일을 해?"
    assert pick(rows, r, query, limit=1) == [rows[4]]
    got = pick(rows, r, query)
    assert got[0] == rows[4] and len(got) == 3
    assert pick(rows, r, query, limit=0) == []


def test_required_before_rest_and_unchanged_knowledge_marks():
    rows, r = prepared(own(1, "identity", value="astronomer", knowledge="limited",
                           known_by=["타쿠미"], hidden_from=["루카"]))
    named = set()
    got = pick(rows, r, "타쿠미는 무슨 일을 해?", named=named, keep=lambda f: str(f["id"]) in named)
    assert got == rows and named == {"1"}
    assert 'known_by="타쿠미"' in fact_line(got[0]) and 'hidden_from="루카"' in fact_line(got[0])


def test_lexical_persona_answer_is_named_before_the_rest_callback():
    rows, r = prepared(own(1, "identity", value="타쿠미의 직업은 천문학자"))
    named, rested = set(), []

    def keep(f):
        if str(f["id"]) not in named:
            rested.append(f["id"])
            return False
        return True

    assert pick(rows, r, "타쿠미의 직업은 뭐였지?", named=named, keep=keep) == rows
    assert rested == []  # an offered answer must not also increment the resting counter


def test_event_quota_and_context():
    rows, r = prepared(own(1, "event", value="won tournament", salience="major"),
                       own(2, "event", value="lost tournament", salience="major"))
    assert pick(rows, r, "타쿠미는 무슨 일이 있었어?", events_limit=0) == []
    assert len(pick(rows, r, "타쿠미는 무슨 일이 있었어?", events_limit=1)) == 1
    assert relevant_facts(rows, "타쿠미는 무슨 일이 있었어?", "", {"m1", "m2"}, 8,
                          persona=r.persona_names, persona_questions=True,
                          persona_entity=r.entity("character", "{{user}}")['id']) == []
    assert pick(rows, r, "타쿠미는 처음 무슨 일이 있었어?", events_limit=1, first_cue=True) == [rows[0]]


def test_flag_off_preserves_old_behavior():
    rows, r = prepared(own(1, "identity", value="astronomer"))
    for query in ("타쿠미는 무슨 일을 해?", "타쿠미는 웃는다.", "내 직업은 뭐야?"):
        old = relevant_facts(rows, query, "", set(), 8, persona=r.persona_names)
        assert relevant_facts(rows, query, "", set(), 8, persona=r.persona_names,
                              persona_questions=False, persona_entity="unused") == old


def test_content_question_and_claim_cap_are_shared_without_mutation():
    facts, r = prepared(own(1, "event", value="Entered the first 게이트", salience="major"),
                        own(2, "identity", value="별빛 연구소 직원", source="character_claim", asserted_by="타쿠미"))
    added = set()
    assert pick(facts[:1], r, "타쿠미는 처음 들어간 게이트 어디였지?", first_cue=True,
                persona_added=added) == facts[:1]
    claim = facts[1].copy()
    assert pick(facts[1:], r, "타쿠미는 다니는 회사 이름이 뭐였더라?", persona_added=added) == facts[1:]
    assert added == {"1", "2"} and facts[1] == claim
    extra, r = prepared(own(3, "identity", value="astronomer"))
    assert pick(extra, r, "타쿠미는 무슨 일을 해?", persona_added=added) == []


def test_query_only_name_does_not_change_narration_mentions():
    rows, r = prepared(own(1, "identity", value="astronomer"), name="아오키 타쿠미")
    assert pick(rows, r, "타쿠미는 무슨 일을 해?", persona_query_names=frozenset({"타쿠미"})) == rows
    assert pick(rows, r, "타쿠미는 웃는다.", persona_query_names=frozenset({"타쿠미"})) == []
    assert pick(rows, r, "타쿠미는 무슨 일을 해?", persona_query_names=frozenset()) == []


def test_generic_job_words_do_not_add_an_unrelated_event():
    rows, r = prepared(own(1, "identity", value="astronomer"),
                       own(2, "event", value="친구와 일을 마쳤다", salience="major"))
    assert pick(rows, r, "타쿠미는 무슨 일을 해?") == rows[:1]


def test_existing_event_uses_quota_before_additional_persona_event():
    rows, r = prepared(own(1, "event", value="tournament victory", salience="major"),
                       row(2, "루카", "event", value="opened a bakery", subject_type="character", salience="major"))
    assert pick(rows, r, "루카는 무슨 일이 있었어? 타쿠미는 무슨 일이 있었어?", events_limit=1) == [rows[1]]


def test_minor_event_keeps_legacy_lexical_bar_without_first_cue():
    rows, r = prepared(own(1, "event", value="청색 게이트 입장", salience="minor"))
    query = "타쿠미는 처음 혼자 들어간 게이트 어디였지?"
    assert pick(rows, r, query, first_cue=False) == []
    assert pick(rows, r, query, first_cue=True) == rows


def test_question_does_not_boost_persona_in_hidden_marks():
    rows, r = prepared(own(1, "identity", value="astronomer", knowledge="limited", hidden_from=["타쿠미"]),
                       own(2, "identity", value="astronomer", knowledge="public"))
    assert pick(rows, r, "타쿠미는 무슨 일을 해?", limit=1) == [rows[1]]


def test_explicit_persona_event_competes_with_previous_reply_events_within_quota():
    rows, r = prepared(own(9, "event", value="청색 게이트 입장", salience="minor"),
                       *(row(pos, "루카", "event", value=f"unrelated tournament {pos}",
                             subject_type="character", salience="major") for pos in (3, 4, 24)))
    query = "타쿠미는 처음 혼자 들어간 게이트 어디였지?"
    kwargs = dict(events_limit=3, persona=r.persona_names, first_cue=True, named_by_words=True)
    baseline = relevant_facts(rows, query, "루카는 고개를 끄덕였다.", set(), 8, **kwargs)
    assert {f["id"] for f in baseline} == {3, 4, 24}
    added = set()
    got = relevant_facts(rows, query, "루카는 고개를 끄덕였다.", set(), 8, **kwargs,
                         persona_questions=True, persona_entity=r.entity("character", "{{user}}")['id'],
                         persona_added=added)
    assert {f["id"] for f in got} == {3, 4, 9}
    assert added == {"9"} and len(got) == 3
