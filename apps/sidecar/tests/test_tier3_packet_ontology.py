"""PHASE-65 (extract-v21 render): `packet-v21` shows what the read side of `extract-v21` serves (PHASE-66 part 2).

One block per item of the brief: vital_status gone, conditioned slots, the new predicates, beliefs, forgettings,
public_except, a claim's cause, replay. Every other policy stays byte-identical (the differential run); each test
checks packet-v20 beside packet-v21. Synthetic names only.
"""

from __future__ import annotations

import dataclasses
import uuid
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from nmos_sidecar import audit, packet, retrieval
from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import claim_entry, fact_entry
from nmos_sidecar.packet import (BELIEF_NOTE, FORGOT_NOTE, PRIVATE_NOTE, PUBLIC_EXCEPT_NOTE, SLOT_BUNDLE, Line,
                                 compile_lines)
from nmos_sidecar.retrieval import (Gathered, RecallOptions, Shown, appearances, belief_lines, bundled, cast_groups,
                                    claim_v21, forgot_lines, gone_rows, named_cousins, slot_siblings,
                                    with_slot_siblings)
from test_semantics import row

V20 = RecallOptions(policy="packet-v20")
V21 = RecallOptions(policy="packet-v21")
C = {"subject_type": "character"}
CC = {"subject_type": "character", "object_type": "character"}
SECRETS = [{"holders": ["하나"], "open": ["카이토"], "text": "하나 knows: 열쇠는 우물 속에 숨겨져 있다"}]


def v21row(*args, **kw):
    """A row as extract-v21 serves it: `knowledge_scope` set (`repairs.is_v21`)."""
    return row(*args, **{"knowledge_scope": "public", **kw})


def view_of(facts=(), **more) -> dict:
    return {"facts": list(facts), "claims": [], "other": [], "threads": [], "excluded": {}, **more}


def res(rows, persona=("타쿠미",)):
    return resolve(uuid.UUID(int=11), list(rows), persona=list(persona))


def scene_of(r, *names) -> dict:
    return {r.key("character", n): n for n in names}


# --- 1. gone from vital_status -----------------------------------------------------------------------------------------


def gone(rows, now=30, v21=True):
    view = view_of(rows)
    r = res(rows)
    return [f["subject"] for f in (gone_rows(view, r, now, v21=True) if v21 else gone_rows(view, r, now))]


def test_vital_status_pins_the_dead_under_v21_only():
    dead = v21row(10, "세라", "vital_status", None, "사망", **C)
    assert gone([dead]) == ["세라"] and gone([dead], v21=False) == []
    carried = {**dead, "turn": -1, "carried": "link-1"}
    assert gone([carried]) == ["세라"]  # a carried death too


def test_a_later_status_never_ungones_the_dead_nor_makes_the_living_gone():
    dead = v21row(10, "세라", "vital_status", None, "사망", **C)
    asleep = v21row(15, "세라", "has_status", None, "잠듦", **C)
    seen = v21row(16, "세라", "located_in", "광장", None, **C, object_type="place")
    assert gone([dead, asleep, seen]) == ["세라"]  # only a later vital_status brings her back
    alive = v21row(10, "세라", "vital_status", None, "생존", **C)
    said_dead = v21row(15, "세라", "has_status", None, "사망", **C)
    assert gone([alive, said_dead]) == []
    assert gone([said_dead]) == ["세라"]  # without a vital_status, has_status still says it


# --- 2. conditioned facts ------------------------------------------------------------------------------------------------


def cond(n, value, scope, when=None, **kw):
    return v21row(n, "하나", "relationship", "도윤", value, **CC, condition={"scope": scope, "when": when}, **kw)


def test_a_conditioned_facts_other_slots_come_with_it_and_situational_ones_are_capped():
    pub, priv = cond(1, "동료", "public"), cond(2, "연인", "private", "둘만 있을 때")
    sits = [cond(3 + i, f"사이 {i}", "situational", f"상황 {i}") for i in range(5)]
    rows = [pub, priv, *sits]
    r = res(rows)
    got = with_slot_siblings([pub], rows, set(), r)
    assert got[0] is pub and priv in got
    assert [x["value"] for x in got if x["condition"]["scope"] == "situational"] == ["사이 4", "사이 3", "사이 2"]
    assert slot_siblings(v21row(9, "하나", "relationship", "도윤", "친구", **CC), [v21row(9, "하나", "relationship",
                                                                                     "도윤", "친구", **CC)])  # alone
    lines = bundled([fact_entry(x) for x in got], got, r)
    assert len({line.marks[SLOT_BUNDLE] for line in lines}) == 1


def test_a_slot_bundle_is_placed_whole_or_not_at_all():
    pub = dataclasses.replace(fact_entry(cond(1, "동료", "public")), marks={SLOT_BUNDLE: "slot:x"})
    priv = dataclasses.replace(fact_entry(cond(2, "연인 " * 20, "private", "둘만 있을 때")), marks={SLOT_BUNDLE: "slot:x"})
    other = fact_entry(v21row(5, "카이토", "event", None, "걸었다", **C))
    for budget in range(150, 700, 5):
        out = compile_lines([], budget, lead=[pub, priv], facts=[other], policy="packet-v21")
        placed = {e["ref"]["assertion"] for e in out.ledger if e["placed"]}
        assert placed & {1, 2} in (set(), {1, 2}), budget
        plain = compile_lines([], budget, lead=[pub, priv], facts=[other], policy="packet-v20")
        bare = compile_lines([], budget, lead=[fact_entry(cond(1, "동료", "public")),
                                               fact_entry(cond(2, "연인 " * 20, "private", "둘만 있을 때"))],
                             facts=[other], policy="packet-v20")
        assert plain.text == bare.text  # packet-v20 never reads the mark
    assert "[in public]" in pub.xml or "[" in pub.xml  # the label `fact_text` gives


# --- 3. the new predicates ---------------------------------------------------------------------------------------------


def test_cast_shows_vital_status_rank_and_cover_beside_the_older_lines_under_v21():
    rows = [v21row(1, "하나", "located_in", "광장", None, **C, object_type="place"),
            v21row(2, "하나", "vital_status", None, "생존", **C),
            v21row(3, "하나", "holds_rank", "기사단", "부단장", **C, object_type="group"),
            v21row(4, "하나", "cover_identity", None, "떠돌이 상인", **C),
            v21row(5, "하나", "lives_in", "북부 성채", None, **C, object_type="place")]
    r = res(rows)
    cast = scene_of(r, "하나", "도윤")
    v21 = dict(cast_groups(view_of(rows), cast, r, "", V21, shown_v21=Shown())[0])
    v20 = dict(cast_groups(view_of(rows), cast, r, "", V20)[0])
    assert {line.ref["assertion"] for line in v21["하나"]} == {1, 2, 3, 4}  # not lives_in: where they are is 1
    assert {line.ref["assertion"] for line in v20["하나"]} == {1}


def test_lives_in_is_not_where_they_are_and_fungible_holders_both_hold():
    rows = [v21row(2, "세라", "lives_in", "광장", None, **C, object_type="place")]
    r = res(rows)
    assert r.key("character", "세라") not in appearances(view_of(rows), r, v21=True)
    a = v21row(1, "하나", "possesses", "금화", None, **C, object_type="item", item_kind="fungible")
    b = v21row(2, "도윤", "possesses", "금화", None, **C, object_type="item", item_kind="fungible")
    r = res([a, b])
    groups = dict(cast_groups(view_of([a, b]), scene_of(r, "하나", "도윤"), r, "", V21, shown_v21=Shown())[0])
    assert [line.ref["assertion"] for line in groups["하나"]] == [1]
    assert [line.ref["assertion"] for line in groups["도윤"]] == [2]


def test_a_name_alone_names_the_new_predicates():
    f = v21row(3, "하나", "holds_rank", "기사단", "부단장", **C, object_type="group")
    r = res([f])
    assert named_cousins([f], "하나는 요즘 어때?", r, None) == {"3"}
    assert named_cousins([f], "오늘 날씨 어때?", r, None) == set()


# --- 4. beliefs ---------------------------------------------------------------------------------------------------------


def belief(n, who, value, status="held", **kw):
    return {**v21row(n, who, "believes", None, value, **C, **kw), "status": status}


def beliefs(view, cast_names, opts=V21, query="", rows=()):
    r = res([*view.get("beliefs", []), *rows, row(99, "카이토", "event", None, "x", **C)])
    g = Gathered()
    g.cast = scene_of(r, *cast_names)
    return g, belief_lines(g, view, r, query, "", set(), opts)


def test_a_held_belief_is_its_own_line_and_an_ended_one_is_never_offered():
    view = view_of(beliefs=[belief(1, "하나", "도윤이 범인이다"), belief(2, "하나", "비가 온다", "ended")])
    _, lines = beliefs(view, ["하나"])
    assert [line.kind for line in lines] == ["belief"]
    assert lines[0].xml.startswith('    <Belief by="하나" turn="1"') and "<Fact" not in lines[0].xml
    assert "하나 believes: 도윤이 범인이다" in lines[0].xml
    out = compile_lines([], 2000, facts=lines, policy="packet-v21").text
    assert BELIEF_NOTE in out
    assert BELIEF_NOTE not in compile_lines([], 2000, facts=lines, policy="packet-v20").text


def test_a_belief_that_says_a_secret_is_withheld_and_strict_mode_keeps_a_quiet_one_private():
    leaky = belief(1, "하나", "열쇠는 우물 속에 숨겨져 있다")
    g, lines = beliefs(view_of(beliefs=[leaky], secrets=SECRETS), ["하나", "카이토"])
    assert lines == [] and g.hidden_entries[0]["why"] == "secret_gate"
    quiet = belief(2, "하나", "도윤이 범인이다", knowledge="limited", known_by=["하나"])
    _, lines = beliefs(view_of(beliefs=[quiet]), ["하나", "카이토"], dataclasses.replace(V21, strict=True))
    assert lines[0].kind == "belief" and lines[0].private  # readable in <Private>, not a <Secret>
    plotted = belief(3, "하나", "도윤이 범인이다", knowledge="limited", known_by=["하나"], hidden_from=["카이토"])
    _, lines = beliefs(view_of(beliefs=[plotted]), ["하나", "카이토"], dataclasses.replace(V21, strict=True))
    assert lines[0].kind == "secret" and "범인" not in lines[0].xml


# --- 5. forgetting ---------------------------------------------------------------------------------------------------


def forgetting(n, who, withdrew, **kw):
    return {**v21row(n, who, "forgot", None, "그 일", **C, **kw), "who": who, "scope": "matter", "since": None,
            "withdrew": withdrew}


def forgets(view, cast_names):
    r = res([row(98, n, "event", None, "x", **C) for n in cast_names])
    g = Gathered()
    g.cast = scene_of(r, *cast_names)
    return g, forgot_lines(g, view, r, V21)


def test_a_forgetting_is_offered_where_its_character_is_and_in_its_facts_class():
    w = [{"id": 5, "turn": 3, "predicate": "addresses", "text": "하나 addresses 도윤: 반말", "how": "fact"}]
    g, lines = forgets(view_of(forgotten=[forgetting(9, "하나", w)]), ["하나"])
    assert lines[0].kind == "forgot" and "하나 does not remember: 하나 addresses 도윤: 반말" in lines[0].xml
    assert lines[0].marks["class"] == "lead"
    assert forgets(view_of(forgotten=[forgetting(9, "하나", w)]), ["도윤"])[1] == []  # not in the scene
    out = compile_lines([], 2000, lead=lines, policy="packet-v21").text
    assert FORGOT_NOTE in out


def test_a_forgetting_that_names_a_secret_is_withheld():
    w = [{"id": 5, "turn": 3, "predicate": "knows", "text": "하나 knows: 열쇠는 우물 속에 숨겨져 있다", "how": "fact"}]
    g, lines = forgets(view_of(forgotten=[forgetting(9, "하나", w)], secrets=SECRETS), ["하나", "카이토"])
    assert lines == [] and g.hidden_entries[0]["why"] == "secret_gate"


# --- 6. public_except -------------------------------------------------------------------------------------------------


def test_public_except_is_known_to_all_but_the_listed_and_not_gated_as_limited():
    f = v21row(4, "하나", "has_status", None, "임신함", **C, knowledge="limited", knowledge_scope="public_except",
               hidden_from=["도윤"])
    r = res([f, row(9, "도윤", "event", None, "x", **C), row(8, "카이토", "event", None, "x", **C)])
    assert not retrieval._private(f, scene_of(r, "하나", "카이토"), r, True)
    assert retrieval._private(f, scene_of(r, "하나", "카이토"), r, False)  # v20 gates it as limited
    assert retrieval._private(f, scene_of(r, "하나", "도윤"), r, True)
    line = retrieval.entry_v21(f, False, False, False, False, Shown())
    assert 'knowledge="public_except" hidden_from="도윤"' in line.xml
    assert PUBLIC_EXCEPT_NOTE in compile_lines([], 2000, facts=[line], policy="packet-v21").text
    assert retrieval.missing_v21(f, scene_of(r, "하나", "도윤"), r) == (["하나"], ["도윤"])
    assert retrieval.narrator_knows_v21(f, "카이토", r) and not retrieval.narrator_knows_v21(f, "도윤", r)


# --- 7. a claim's cause -----------------------------------------------------------------------------------------------


def test_a_claims_cause_that_says_a_secret_is_dropped_under_v21():
    c = row(6, "하나", "has_status", None, "초조함", **C, source="character_claim", asserted_by="도윤",
            because="열쇠는 우물 속에 숨겨져 있다")
    present = frozenset({"카이토", "하나"})
    assert "because" not in claim_v21(c, False, True, Shown(SECRETS, present)).xml
    assert claim_v21(c, False, True, None) == claim_entry(c, False, True)  # packet-v20's call, exactly
    assert "because: 열쇠는" in claim_entry(c, False, True).xml
    assert "because: 열쇠는" in claim_v21(c, True, True, Shown(SECRETS, present)).private_xml  # private: kept


# --- 8. replay ------------------------------------------------------------------------------------------------------


def test_a_v21_request_with_beliefs_and_forgettings_replays_to_the_same_ledger(migrated):
    from test_sidecar_integration import recall
    from test_tier3_read_ontology import Chat, a
    script = {"t0": [a("하나", "believes", None, "도윤이 범인이다"),
                     a("하나", "knows", None, "북쪽 다리의 암호", knowledge="limited", known_by=["하나"])],
              "t1": [a("하나", "forgot", None, "북쪽 다리의 암호"), a("하나", "located_in", "광장", None, ot="place")]}
    v21 = Chat(migrated, script, name="w4-replay")
    with v21.client() as c:
        v21.run(c)
        out = recall(c, v21.chat, "하나는 지금 뭘 생각해?", budget=1500)
        text = out["packet"]["text"]
    assert "<Belief " in text and "하나 believes: 도윤이 범인이다" in text
    assert "<Forgot " in text and "북쪽 다리의 암호" in text
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        again = audit.replay(conn, UUID(out["trace_id"]), RecallOptions(), policy=None)
        v20 = audit.replay(conn, UUID(out["trace_id"]), RecallOptions(), policy="packet-v20")
    assert again["status"] == "ok" and again["reproduced"] is True and again["text"] == text
    assert "<Belief " not in v20["text"] and "<Forgot " not in v20["text"]
