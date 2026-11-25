"""PHASE-66 part 2 (Tier 3, Wave 3): the read side of `extract-v21`.

What `extract-v21` stores (migration 0041: `condition`, `guise`, `item_kind`, `knowledge_scope`; the ontology's own
predicates) is read, folded and served by `facts`, `dropped`, `repairs` and `carry`; a row of every earlier generation
reads exactly as before (the differential run, `w3-facts-ontology-REPORT.md`). Synthetic names only."""

from __future__ import annotations

import re
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import carry, dropped, facts, repairs
from simchat import SimChat
from test_extraction import drain
from test_generations import LLM, conv_id
from test_sidecar_integration import sync

USED = {"calls": 1, "input": 100, "output": 10}
C = "character"
MARK = re.compile(r"⟦([a-z0-9_-]+)⟧")
PUB, PRIV = {"scope": "public", "when": "회사"}, {"scope": "private", "when": "둘만 있을 때"}
SIT, ALL = {"scope": "situational", "when": "술자리"}, {"scope": "all", "when": None}


def a(subject: str, predicate: str, obj: str | None = None, value: str | None = None, *, st: str = C,
      ot: str = C, polarity: str = "positive", source: str = "narration", modality: str = "actual",
      knowledge: str = "public", known_by: list[str] | None = None, hidden_from: list[str] | None = None,
      **extra: Any) -> dict[str, Any]:
    """A raw assertion as the model answers it."""
    return {"subject": subject, "subject_type": st, "predicate": predicate, "object": obj,
            "object_type": ot if obj else None, "value": value, "polarity": polarity, "modality": modality,
            "source": source, "knowledge": knowledge, "known_by": known_by or [], "hidden_from": hidden_from or [],
            "evidence": "", **extra}


def model_for(script: dict[str, list[dict[str, Any]]], drop: frozenset[tuple[str, str | None]] = frozenset()):
    """A stub extraction model: a TARGET turn's markers ⟦key⟧ name its assertions; `drop` leaves (subject, value)
    pairs out, as a re-extraction that words the turn anew may."""
    def complete(system: str, user: str):
        target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
        out = [x for k in MARK.findall(target) for x in script.get(k, []) if (x["subject"], x["value"]) not in drop]
        return {"assertions": out, "speakers": {}}, "{}", USED
    return complete


class Chat:
    """A scripted chat extracted by a compiler: each key of `script` is one turn, in order."""

    def __init__(self, url: str, script: dict[str, list[dict[str, Any]]], compiler: str = "extract-v21",
                 name: str = "w3-chat") -> None:
        self.url, self.script, self.compiler = url, script, compiler
        self.chat = SimChat(name)
        for k in script:
            self.turn(k)

    def turn(self, key: str) -> None:
        self.chat.user(f"다음 장면 ({key}).")
        self.chat.reply(f"장면 ⟦{key}⟧")

    def client(self):
        return make_client(self.url, **LLM, extract_compiler=self.compiler, packet_policy="packet-v21")

    def run(self, c, drop: frozenset = frozenset()) -> None:
        self.chat.user("계속.")
        sync(c, self.chat)
        drain(self.url, model_for(self.script, drop))
        self.cid = conv_id(c, self.chat)

    def view(self, **kw: Any) -> dict[str, Any]:
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            self.key = active_generation(conn, "extract").key
            self.head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s",
                                     (self.cid,)).fetchone()["head_commit_id"]
            return facts.memory_view(conn, self.head, self.key, **kw)


def current(view: dict[str, Any], predicate: str, subject: str | None = None) -> list[dict[str, Any]]:
    return [f for f in view["facts"] if f["predicate"] == predicate and (subject is None or f["subject"] == subject)]


# --- 1. the four columns are read wherever `address_condition` is -----------------------------------------------

MARKS = {
    "t0": [a("하나", "feels_toward", "도윤", "설렘", condition=PRIV),
           a("하나", "possesses", "회복 물약", None, ot="item", item_kind="fungible"),
           a("하나", "has_status", None, "피곤함", knowledge="public_except", hidden_from=["도윤"]),
           a("하나", "addresses", "도윤", "존댓말, '과장님'", address_condition=PUB)],
    "t1": [a("도윤", "has_status", None, "바쁨")],
}


def test_the_four_marks_are_served_dropped_restored_and_carried_and_absent_on_earlier_rows(migrated: str):
    v21 = Chat(migrated, MARKS)
    with v21.client() as c:
        v21.run(c)
        view = v21.view()
        feel = current(view, "feels_toward")[0]
        assert feel["condition"] == PRIV and feel["knowledge_scope"] == "public"
        assert feel["history"][0]["condition"] == PRIV  # a history entry names its slot
        assert current(view, "possesses")[0]["item_kind"] == "fungible"
        status = current(view, "has_status", "하나")[0]
        assert status["knowledge_scope"] == "public_except" and status["hidden_from"] == ["도윤"]
        assert "guise" not in feel and "item_kind" not in feel  # a mark the model did not give stays absent
        addr = current(view, "addresses")[0]
        assert addr["address_condition"] == PUB and "condition" not in addr  # an address keeps its own condition

        # a re-extraction that drops the feeling: dropped.find keeps its marks, and a restore brings them back
        c.post(f"/v1/conversations/{v21.cid}/rebuild")
        drain(migrated, model_for(MARKS, frozenset({("하나", "설렘")})))
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            lost = dropped.find(conn, v21.head, v21.key, v21.view())
        assert [(d["predicate"], d["condition"], d["knowledge_scope"]) for d in lost] == [
            ("feels_toward", PRIV, "public")]
        assert repairs.restore_target(lost[0])["fact"]["condition"] == PRIV
        res = c.post(f"/v1/conversations/{v21.cid}/repairs", json={"kind": "fact_restore", "item": str(lost[0]["id"])})
        assert res.status_code == 200 and res.json()["applied"], res.text
        back = current(v21.view(), "feels_toward")[0]
        assert back["owner"] and back["condition"] == PRIV and back["knowledge_scope"] == "public"

        # a continue link carries the marks into the snapshot and the target's rows
        target = SimChat("w3-target")
        target.user("새 이야기.")
        target.reply("둘은 다시 만났다.")
        target.user("계속.")
        sync(c, target)
        dst = conv_id(c, target)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            carry.link(conn, dst, v21.cid, "continue", None, carry.Keys(extractor=v21.key))
            conn.commit()
            link = carry.in_force(conn, dst)
        snap = {f["predicate"]: f for f in link["snapshot"]["facts"]}
        assert snap["possesses"]["item_kind"] == "fungible" and snap["feels_toward"]["condition"] == PRIV
        rows = {(x["predicate"], x["subject"]): x for x in carry.target_rows(link).rows}
        assert rows[("has_status", "하나")]["knowledge_scope"] == "public_except"


def test_an_earlier_generations_rows_have_none_of_the_four_keys(migrated: str):
    v20 = Chat(migrated, {"t0": [a("하나", "feels_toward", "도윤", "설렘", condition=PRIV, item_kind="fungible"),
                                 a("하나", "addresses", "도윤", "반말", address_condition=PRIV)]},
               compiler="extract-v20")
    with v20.client() as c:
        v20.run(c)
        view = v20.view()
    for f in view["facts"] + view["assertions"]:
        assert not set(facts.ONTOLOGY_MARKS) & set(f), f
        for h in f.get("history") or ():
            assert not set(facts.ONTOLOGY_MARKS) & set(h)
    assert current(view, "addresses")[0]["address_condition"] == PRIV


# --- 2. per-slot folding of `condition` (modelled on PHASE-64's addresses) ------------------------------------------

def row(i: int, predicate: str, value: str | None, cond: dict[str, Any] | None = None, *, subject: str = "하나",
        obj: str | None = "도윤", turn: int | None = None, polarity: str = "positive", canon: str | None = None,
        **extra: Any) -> dict[str, Any]:
    """A served row of an extract-v21 turn (or canon), as `_versions` reads one version key's history."""
    out = {"id": i, "position": -1000 + i if canon else i * 2, "turn": -1 if canon else (i if turn is None else turn),
           "predicate": predicate, "subject": subject, "subject_type": C, "object": obj,
           "object_type": C if obj else None, "value": value, "polarity": polarity, "modality": "actual",
           "source": "narration", "knowledge": "public", "known_by": None, "hidden_from": None, "evidence": "",
           "host_logical_id": f"m{i}", "compiler": "extract-v21", "knowledge_scope": "public", **extra}
    if cond is not None:
        out["condition"] = cond
    if canon:
        out["canon"] = canon
    return out


def by_slot(out: list[dict[str, Any]]) -> dict[tuple, str | None]:
    return {repairs.slot(f): f["value"] for f in out}


@pytest.mark.parametrize("predicate,obj", [("feels_toward", "도윤"), ("role_toward", "도윤"), ("has_status", None),
                                           ("identity", None)])
def test_a_conditional_fact_and_the_unconditional_one_coexist_each_with_its_own_history(predicate, obj):
    h = [row(0, predicate, "기본", obj=obj), row(1, predicate, "비밀", PRIV, obj=obj),
         row(2, predicate, "공식", PUB, obj=obj), row(3, predicate, "새 기본", obj=obj),
         row(4, predicate, "술김", SIT, obj=obj)]
    out = facts._versions(h, None)
    assert by_slot(out) == {("default",): "새 기본", ("private",): "비밀", ("public",): "공식",
                            ("situational", "술자리"): "술김"}
    hist = {repairs.slot(f): [(e["value"], e["outcome"]) for e in f["history"]] for f in out}
    assert hist[("default",)] == [("기본", "superseded"), ("새 기본", "current")]  # the private one never enters it
    assert hist[("private",)] == [("비밀", "current")]
    # a denial of the situational one ends only its slot
    ended = facts._versions(h + [row(5, predicate, "술김", SIT, obj=obj, polarity="negative")], None)
    assert {repairs.slot(f): (f["value"], f["polarity"]) for f in ended}[("situational", "술자리")] == ("술김", "negative")
    assert by_slot(ended)[("private",)] == "비밀"


def test_scope_all_unifies_a_split_and_retracting_it_brings_the_split_back():
    h = [row(0, "feels_toward", "존중", PUB), row(1, "feels_toward", "사랑", PRIV), row(2, "feels_toward", "신뢰"),
         row(3, "feels_toward", "편안함", ALL)]
    out = facts._versions(h, None)
    assert [(f["value"], repairs.slot(f)) for f in out] == [("편안함", ("default",))]
    assert {(e["value"], e["outcome"]) for e in out[0]["history"]} == {
        ("존중", "superseded"), ("사랑", "superseded"), ("신뢰", "superseded"), ("편안함", "current")}
    assert by_slot(facts._versions(h[:3], None)) == {("public",): "존중", ("private",): "사랑", ("default",): "신뢰"}


def test_a_split_retires_the_stale_default_as_an_address_split_does():
    h = [row(0, "identity", "회사원", obj=None), row(1, "identity", "회사원", PUB, obj=None),
         row(2, "identity", "조직의 간부", PRIV, obj=None)]
    out = facts._versions(h, None)
    assert by_slot(out) == {("public",): "회사원", ("private",): "조직의 간부"}


def test_a_relationship_folds_per_slot_and_keeps_its_direction_and_symmetry_rules():
    h = [row(0, "relationship", "부하"), row(1, "relationship", "연인", PRIV, subject="도윤", obj="하나"),
         row(2, "relationship", "상사", subject="도윤", obj="하나")]
    out = facts._versions(h, None)
    got = {(repairs.slot(f), f["subject"]): f["value"] for f in out}
    # the private tie of the other direction coexists; in the default slot each (one-way) direction keeps its latest
    assert got == {(("default",), "하나"): "부하", (("default",), "도윤"): "상사", (("private",), "도윤"): "연인"}
    # a symmetric default tie replaces both directions of the default slot only
    sym = facts._versions(h + [row(3, "relationship", "친구")], None)
    assert {(repairs.slot(f), f["subject"]): f["value"] for f in sym} == {
        (("default",), "하나"): "친구", (("private",), "도윤"): "연인"}
    # `all` closes the private tie, whose history joins the unifying statement's
    unified = facts._versions(h + [row(4, "relationship", "가족", ALL)], None)
    assert [(f["value"], repairs.slot(f)) for f in unified if f["subject"] == "하나"] == [("가족", ("default",))]
    assert not any(repairs.slot(f) == ("private",) for f in unified)
    fam = next(f for f in unified if f["value"] == "가족")
    assert ("연인", "superseded") in {(e["value"], e["outcome"]) for e in fam["history"]}
    # a public and a private tie both standing retire the stale default of that direction
    split = facts._versions([row(0, "relationship", "동료"), row(1, "relationship", "동료", PUB),
                             row(2, "relationship", "연인", PRIV)], None)
    assert by_slot(split) == {("public",): "동료", ("private",): "연인"}
    assert [e["value"] for e in next(f for f in split if repairs.slot(f) == ("public",))["history"]] == ["동료", "동료"]


def test_a_lock_holds_off_only_its_own_slot_or_a_unifying_statement():
    locked = row(0, "feels_toward", "사랑", PRIV, owner=True, locked="L")
    later = [row(1, "feels_toward", "미움", PRIV), row(2, "feels_toward", "무관심"),
             row(3, "feels_toward", "평온", ALL)]
    kept, off = facts._hold([locked] + later, None)
    assert [x["value"] for x in kept] == ["사랑", "무관심"]
    assert [b["value"] for _, b in off] == ["미움", "평온"]
    assert by_slot(facts._versions(kept, None)) == {("private",): "사랑", ("default",): "무관심"}
    # a relationship's lock needs both: its slot (or all) and its direction (or a symmetric value)
    rel = row(0, "relationship", "후원자", PRIV, owner=True, locked="L")
    kept, off = facts._hold([rel, row(1, "relationship", "제자", PRIV, subject="도윤", obj="하나"),
                             row(2, "relationship", "원수"), row(3, "relationship", "원수", PRIV)], None)
    assert [b["value"] for _, b in off] == ["원수"] and len(kept) == 3


def test_repairs_and_dropped_name_a_conditional_fact_by_its_slot():
    pub, priv = row(0, "feels_toward", "존중", PUB, turn=0), row(1, "feels_toward", "존중", PRIV, turn=0)
    target = repairs.fact_target(priv)
    assert target["condition"] == PRIV
    assert repairs.match_fact(target, [pub, priv], None) is priv
    assert repairs.match_fact(repairs.fact_target(pub), [pub, priv], None) is pub
    assert repairs._restates(1, pub, priv, None) is False and repairs._restates(1, priv, dict(priv), None)
    assert facts._restates(pub, priv, None) is False
    assert facts.fact_text(priv) == "하나 feels toward 도윤 [둘만 있을 때]: 존중"


COND = {
    "t0": [a("하나", "feels_toward", "도윤", "존중", condition=PUB),
           a("하나", "feels_toward", "도윤", "사랑", condition=PRIV),
           a("하나", "relationship", "도윤", "동료"),
           a("하나", "relationship", "도윤", "연인", condition=PRIV),
           a("세라", "feels_toward", "도윤", "질투", source="character_claim", asserted_by="세라", condition=PRIV),
           a("하나", "has_status", None, "긴장함", condition=SIT)],
    "t1": [a("하나", "feels_toward", "도윤", "서운함")],
}


def test_retract_claims_dropped_restore_and_carry_work_per_slot(migrated: str):
    v21 = Chat(migrated, COND)
    with v21.client() as c:
        v21.run(c)
        view = v21.view()
        assert by_slot(current(view, "feels_toward", "하나")) == {
            ("public",): "존중", ("private",): "사랑", ("default",): "서운함"}
        assert by_slot(current(view, "relationship")) == {("default",): "동료", ("private",): "연인"}
        assert current(view, "has_status")[0]["condition"] == SIT
        priv = next(f for f in current(view, "feels_toward", "하나") if repairs.slot(f) == ("private",))
        res = c.post(f"/v1/conversations/{v21.cid}/repairs", json={"kind": "fact_retract", "item": str(priv["id"])})
        assert res.status_code == 200 and res.json()["applied"] == str(priv["id"]), res.text
        assert by_slot(current(v21.view(), "feels_toward", "하나")) == {("public",): "존중", ("default",): "서운함"}
        c.post(f"/v1/conversations/{v21.cid}/repairs/{res.json()['repair']['id']}/remove")
        # a correction of the private tie leaves the default one
        rel = next(f for f in current(v21.view(), "relationship") if repairs.slot(f) == ("private",))
        res = c.post(f"/v1/conversations/{v21.cid}/repairs",
                     json={"kind": "fact_correct", "item": str(rel["id"]), "new_value": "약혼자"})
        assert res.status_code == 200 and res.json()["applied"], res.text
        assert by_slot(current(v21.view(), "relationship")) == {("default",): "동료", ("private",): "약혼자"}
        # a re-extraction that drops the private feeling: dropped by its slot (the default one does not hold it)
        c.post(f"/v1/conversations/{v21.cid}/rebuild")
        drain(migrated, model_for(COND, frozenset({("하나", "사랑")})))
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            lost = dropped.find(conn, v21.head, v21.key, v21.view())
        assert [(d["value"], d["condition"]) for d in lost] == [("사랑", PRIV)]
        res = c.post(f"/v1/conversations/{v21.cid}/repairs", json={"kind": "fact_restore", "item": str(lost[0]["id"])})
        assert res.status_code == 200 and res.json()["applied"], res.text
        assert by_slot(current(v21.view(), "feels_toward", "하나"))[("private",)] == "사랑"


# --- 3. the ontology's own slots ----------------------------------------------------------------------------------

G, I, PL = "group", "item", "place"
ONTO = {
    "t0": [a("리안", "vital_status", None, "사망"),
           a("하나", "lives_in", "저택", None, ot=PL),
           a("하나", "possesses", "마검", None, ot=I, item_kind="unique"),
           a("하나", "possesses", "물약", None, ot=I, item_kind="fungible"),
           a("하나", "holds_rank", "기사단", "부단장", ot=G),
           a("하나", "holds_rank", "길드", "회원", ot=G),
           a("하나", "role_toward", "도윤", "제자"),
           a("하나", "role_toward", "기사단", "후원자", ot=G),
           a("하나", "identity", None, "암살자")],
    "t1": [a("리안", "has_status", None, "부상"),
           a("하나", "located_in", "시장", None, ot=PL),
           a("마검", "located_in", "무기고", None, st=I, ot=PL),
           a("도윤", "possesses", "물약", None, ot=I, item_kind="fungible"),
           a("하나", "role_toward", "도윤", "비서"),
           a("하나", "cover_identity", None, "꽃집 주인"),
           a("리안", "disguised_as", "카이", None, knowledge="limited", hidden_from=["아리아"], guise="카이")],
    "t2": [a("리안", "vital_status", None, "생존"),
           a("마검", "contained_in", "상자", None, st=I, ot=I, item_kind="unique"),
           a("하나", "possesses", "물약", None, ot=I, item_kind="fungible", polarity="negative"),
           a("하나", "holds_rank", "기사단", "단장", ot=G),
           a("하나", "role_toward", "도윤", "제자", polarity="negative")],
}


def values(view: dict[str, Any], predicate: str, subject: str | None = None) -> set:
    return {(f["subject"], f.get("object"), f.get("value"), f["polarity"]) for f in current(view, predicate, subject)}


def test_the_ontology_folds_in_its_own_slots(migrated: str):
    v21 = Chat(migrated, ONTO)
    with v21.client() as c:
        v21.run(c)
        view = v21.view()
    # a death has its own slot: a later wound does not overwrite it, a later state of being alive does
    assert values(view, "vital_status") == {("리안", None, "생존", "positive")}
    assert values(view, "has_status", "리안") == {("리안", None, "부상", "positive")}
    # a home is not where one is now
    assert values(view, "lives_in") == {("하나", "저택", None, "positive")}
    assert values(view, "located_in", "하나") == {("하나", "시장", None, "positive")}
    # where a unique thing is kept (a place, a container) is not who owns it
    assert ("하나", "마검", None, "positive") in values(view, "possesses")
    assert values(view, "located_in", "마검") == {("마검", "무기고", None, "positive")}
    assert values(view, "contained_in") == {("마검", "상자", None, "positive")}
    # a fungible item is each holder's own: giving hers away empties no one else's
    potions = {(f["subject"], f["polarity"]) for f in current(view, "possesses") if f["object"] == "물약"}
    assert potions == {("하나", "negative"), ("도윤", "positive")}
    # a rank per group; several roles toward one counterpart, each ended by its own denial; a group counterpart
    assert values(view, "holds_rank") == {("하나", "기사단", "단장", "positive"), ("하나", "길드", "회원", "positive")}
    assert values(view, "role_toward") == {("하나", "도윤", "비서", "positive"), ("하나", "도윤", "제자", "negative"),
                                           ("하나", "기사단", "후원자", "positive")}
    # a cover beside the true identity; a guise as a fact with its guise and knowledge marks
    assert values(view, "identity") == {("하나", None, "암살자", "positive")}
    assert values(view, "cover_identity") == {("하나", None, "꽃집 주인", "positive")}
    guise = current(view, "disguised_as")[0]
    assert (guise["object"], guise["guise"], guise["hidden_from"]) == ("카이", "카이", ["아리아"])
    # the item timeline of the unique item keeps its holder current beside its place
    blade = next(i for i in view["items"] if i["item"] == "마검")
    assert {(e["predicate"], e["outcome"]) for e in blade["history"]} == {("possesses", "current"),
                                                                       ("located_in", "current")}


def test_an_item_placed_by_an_earlier_generation_still_ends_its_holder(migrated: str):
    v20 = Chat(migrated, {"t0": [a("하나", "possesses", "마검", None, ot=I)],
                          "t1": [a("마검", "located_in", "무기고", None, st=I, ot=PL)]}, compiler="extract-v20")
    with v20.client() as c:
        v20.run(c)
        view = v20.view()
    assert not current(view, "possesses")  # as before PHASE-66: the newer whereabouts closes the holder
    assert values(view, "located_in") == {("마검", "무기고", None, "positive")}


def test_only_an_extract_v21_row_is_read_as_one_of_its_predicates():
    old = row(0, "vital_status", "사망", obj=None, compiler="extract-v20", knowledge_scope=None)
    new = row(1, "vital_status", "사망", obj=None)
    assert not repairs.read_predicate(old) and repairs.read_predicate(new)
    assert not repairs.read_predicate(row(2, "believes", "x", obj=None))  # its own kind (item 4)
    assert not repairs.read_predicate(row(3, "told", "x"))  # its own list (PHASE-60 S8)
    assert repairs.cardinality(row(4, "role_toward", "제자")) == "multi"
    assert repairs.cardinality(row(5, "role_toward", "제자", compiler="extract-v20", knowledge_scope=None)) == "single"


@pytest.mark.parametrize("policy", ["packet-v19", "packet-v20", "packet-v21"])
def test_every_reader_of_the_view_serves_a_chat_with_the_ontology(migrated: str, policy: str):
    """The readers outside the four files (packet, Inspector, panel, author's note, timeline, memory map) take the
    ontology's rows without failing; what they render of them is the next wave's."""
    from test_sidecar_integration import recall
    v21 = Chat(migrated, {**ONTO, **COND})
    with make_client(migrated, **LLM, extract_compiler="extract-v21", packet_policy=policy) as c:
        v21.run(c)
        view = v21.view()
        out = recall(c, v21.chat, "리안은 살아 있어? 하나는 도윤을 어떻게 생각해?", budget=1500)
        assert out["packet"] is not None
        ents = {e["name"]: e["id"] for e in view["entities"]}
        for path in ("facts", "entities", "threads", "secrets", "dropped", "repairs", "state"):
            res = c.get(f"/v1/conversations/{v21.cid}/{path}")
            assert res.status_code == 200, (path, res.text[:300])
        for path in (f"/v1/inspector/c/{v21.cid}", f"/v1/inspector/c/{v21.cid}/e/{ents['하나']}",
                     f"/v1/inspector/c/{v21.cid}/t/1", f"/v1/views/c/{v21.cid}/working",
                     f"/v1/views/c/{v21.cid}/memory", f"/v1/views/c/{v21.cid}/person/{ents['리안']}",
                     f"/v1/views/c/{v21.cid}/map", f"/v1/views/c/{v21.cid}/map/graph"):
            res = c.get(path)
            assert res.status_code == 200, (path, res.text[:300])
        res = c.post(f"/v1/conversations/{v21.cid}/notes", json={"sections": ["changed", "address"]})
        assert res.status_code == 200, res.text[:300]


# --- 4. `believes` and `forgot` -------------------------------------------------------------------------------------

EPI = {
    "t0": [a("카이", "identity", None, "카이의 정체는 왕자"),
           a("아리아", "believes", None, "카이의 정체는 상인"),
           a("아리아", "believes", None, "도윤이 배신했다"),
           a("세라", "believes", None, "하나가 마녀다", source="character_claim", asserted_by="도윤"),
           a("아리아", "knows", None, "비밀 통로의 위치", knowledge="limited", known_by=["아리아"]),
           a("하나", "has_status", None, "임신함", knowledge="limited", known_by=["하나", "아리아"],
             hidden_from=["도윤"])],
    "t1": [a("아리아", "knows", None, "카이의 정체는 왕자"),
           a("도윤", "believes", None, "보물은 동굴에 있다")],
    "t2": [a("아리아", "forgot", None, "all"),
           a("도윤", "forgot", None, "보물은 동굴에 있다")],
    "t3": [a("아리아", "knows", None, "새 암호", knowledge="limited", known_by=["아리아"])],
}


def test_a_belief_is_its_own_kind_and_ends_when_its_holder_learns_or_forgets_the_matter(migrated: str):
    v21 = Chat(migrated, EPI)
    with v21.client() as c:
        v21.run(c)
        view = v21.view()
        beliefs = {b["value"]: b for b in view["beliefs"]}
        assert set(beliefs) == {"카이의 정체는 상인", "도윤이 배신했다", "보물은 동굴에 있다"}
        # never a fact about the world, never a conflict or a disputed mark against what it contradicts
        assert not current(view, "believes") and not view["conflicts"]
        assert not any(f.get("disputed_by") for f in view["facts"])
        assert values(view, "identity") == {("카이", None, "카이의 정체는 왕자", "positive")}
        # learning the matter ends it; forgetting it ends it; "all" ends every belief of the forgetter
        assert beliefs["카이의 정체는 상인"]["status"] == "ended"
        assert beliefs["카이의 정체는 상인"]["ended_by"]["predicate"] == "knows"
        assert beliefs["도윤이 배신했다"]["status"] == "ended"  # 아리아 forgot all at t2
        assert beliefs["보물은 동굴에 있다"]["ended_by"]["predicate"] == "forgot"
        # another's claim of a belief is another assertion (stored, inspectable, never in the packet)
        assert any(o["predicate"] == "believes" and o["source"] == "character_claim" for o in view["other"])
        assert not any(s["text"].startswith("아리아 believes") for s in view["secrets"])

        # a forgetting withdraws the character's knowledge from its turn on, and is itself in the view
        forgot = {g["who"]: g for g in view["forgotten"]}
        assert forgot["아리아"]["scope"] == "all" and forgot["도윤"]["scope"] == "matter"
        withdrawn = {(w["predicate"], w["how"]) for w in forgot["아리아"]["withdrew"]}
        assert ("knows", "fact") in withdrawn and ("has_status", "known_by") in withdrawn
        assert not {f["value"] for f in current(view, "knows", "아리아")} & {"비밀 통로의 위치", "카이의 정체는 왕자"}
        assert {f["value"] for f in current(view, "knows", "아리아")} == {"새 암호"}  # learned after it: stands
        status = current(view, "has_status", "하나")[0]
        # her name leaves known_by; nothing is added to hidden_from
        assert status["known_by"] == ["하나"] and status["hidden_from"] == ["도윤"]
        assert status["forgotten_by"] == ["아리아"]

        # the owner's repairs reach a belief and a forgetting as they reach a fact
        # (a correction is planned and read here; api.py's own fact_correct guard looks in view["facts"] only, the
        # one-line change the report names)
        bid = str(beliefs["도윤이 배신했다"]["id"])
        target, value = repairs.plan("fact_correct", bid, view, 3, new_value="도윤이 배신했을지도 모른다")
        fixed = v21.view(what_if={"add_repairs": [{"id": "0193e3c0-0000-7000-8000-000000000001", "kind": "fact_correct",
                                                   "target": target, "value": value, "note": None,
                                                   "created_at": None}]})
        assert "도윤이 배신했을지도 모른다" in {b["value"] for b in fixed["beliefs"]}
        assert "도윤이 배신했다" not in {b["value"] for b in fixed["beliefs"]}
        gid = str(forgot["아리아"]["id"])
        res = c.post(f"/v1/conversations/{v21.cid}/repairs", json={"kind": "fact_retract", "item": gid})
        assert res.status_code == 200 and res.json()["applied"] == gid, res.text
        after = v21.view()
        assert {g["who"] for g in after["forgotten"]} == {"도윤"}
        assert "비밀 통로의 위치" in {f["value"] for f in current(after, "knows", "아리아")}
        assert current(after, "has_status", "하나")[0]["known_by"] == ["하나", "아리아"]


def test_forgot_reads_one_matter_all_or_since_a_turn():
    assert facts.forgot_scope("all") == ("all", None) and facts.forgot_scope("모든 기억") == ("all", None)
    assert facts.forgot_scope("since turn 12") == ("since", 12)
    assert facts.forgot_scope("어젯밤의 일") == ("matter", None)


def test_an_earlier_chat_without_beliefs_has_neither_new_key(migrated: str):
    v21 = Chat(migrated, ONTO)
    with v21.client() as c:
        v21.run(c)
        view = v21.view()
    assert "beliefs" not in view and "forgotten" not in view


# --- 5. the owner's repairs on the new rows, and on a carried fact ------------------------------------------------

def post(c, cid: str, **body: Any) -> dict[str, Any]:
    res = c.post(f"/v1/conversations/{cid}/repairs", json=body)
    assert res.status_code == 200, (body, res.status_code, res.text)
    return res.json()


def test_retract_correct_lock_and_restore_reach_the_ontologys_rows(migrated: str):
    v21 = Chat(migrated, ONTO)
    with v21.client() as c:
        v21.run(c)
        view = v21.view()
        # retract a death: the state before it (none) is current again, the wound stays
        vital = current(view, "vital_status")[0]
        assert post(c, v21.cid, kind="fact_retract", item=str(vital["id"]))["applied"] == str(vital["id"])
        after = v21.view()
        assert values(after, "vital_status") == {("리안", None, "사망", "positive")}
        assert values(after, "has_status", "리안") == {("리안", None, "부상", "positive")}
        # correct a rank at its own turn, then lock the correction: a later rank in the same group is held off
        rank = next(f for f in current(after, "holds_rank") if f["object"] == "길드")
        post(c, v21.cid, kind="fact_correct", item=str(rank["id"]), new_value="길드장")
        owner = next(f for f in current(v21.view(), "holds_rank") if f["object"] == "길드")
        assert owner["owner"] and owner["value"] == "길드장"
        post(c, v21.cid, kind="fact_lock", item=str(owner["id"]))
        v21.script["t3"] = [a("하나", "holds_rank", "길드", "평회원", ot=G)]
        v21.turn("t3")
        v21.run(c)
        locked = v21.view()
        assert next(f for f in current(locked, "holds_rank") if f["object"] == "길드")["value"] == "길드장"
        assert any(x["kind"] == "locked" and x["against"]["value"] == "평회원" for x in locked["conflicts"])
        # one role of several toward one counterpart is retracted alone
        role = next(f for f in current(locked, "role_toward") if f["value"] == "비서")
        post(c, v21.cid, kind="fact_retract", item=str(role["id"]))
        assert ("하나", "도윤", "비서", "positive") not in values(v21.view(), "role_toward")
        assert ("하나", "기사단", "후원자", "positive") in values(v21.view(), "role_toward")
        # a re-extraction that drops the home: listed, restored with its marks
        c.post(f"/v1/conversations/{v21.cid}/rebuild")
        drain(migrated, model_for(v21.script, frozenset({("하나", None)})))
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            lost = dropped.find(conn, v21.head, v21.key, v21.view())
        home = next(d for d in lost if d["predicate"] == "lives_in")
        post(c, v21.cid, kind="fact_restore", item=str(home["id"]))
        restored = current(v21.view(), "lives_in")[0]
        assert restored["owner"] and restored["object"] == "저택" and restored["knowledge_scope"] == "public"


def test_a_carried_fact_is_retracted_and_corrected_through_the_api(migrated: str):
    """The Wave 1 leftover: `match_fact` read turn -1 as canon's, so a repair of a carried fact answered 422."""
    src = Chat(migrated, {"t0": [a("하나", "located_in", "항구", None, ot=PL), a("하나", "lives_in", "저택", None, ot=PL),
                                 a("하나", "feels_toward", "도윤", "그리움", condition=PRIV)]}, name="w3-src")
    with src.client() as c:
        src.run(c)
        src.view()
        dst = Chat(migrated, {"d0": []}, name="w3-dst")
        dst.run(c)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            carry.link(conn, dst.cid, src.cid, "continue", None, carry.Keys(extractor=src.key))
            conn.commit()
            carried = carry.target_rows(carry.in_force(conn, dst.cid))
        view = dst.view(carried=carried)
        place = next(f for f in current(view, "located_in") if f.get("carried"))
        feel = next(f for f in current(view, "feels_toward") if f.get("carried"))
        assert feel["condition"] == PRIV
        out = post(c, dst.cid, kind="fact_retract", item=str(place["id"]))
        assert out["applied"] == str(place["id"]) and out["repair"]["target"]["carried"] == carried.link
        out = post(c, dst.cid, kind="fact_correct", item=str(feel["id"]), new_value="미련")
        assert out["applied"] == str(feel["id"])
        after = dst.view(carried=carried)
        assert not current(after, "located_in")
        fixed = current(after, "feels_toward")[0]
        assert fixed["value"] == "미련" and fixed["owner"] and fixed["condition"] == PRIV
        assert values(after, "lives_in") == {("하나", "저택", None, "positive")}


# --- 6. carry ------------------------------------------------------------------------------------------------------

def test_a_carried_death_is_a_current_carried_fact_and_the_marks_survive_every_link(migrated: str):
    from nmos_sidecar import retrieval
    src = Chat(migrated, {"t0": [a("리안", "vital_status", None, "사망"),
                                 a("하나", "feels_toward", "도윤", "그리움", condition=PRIV),
                                 a("하나", "believes", None, "리안이 살아 있다")]}, name="w3-carry-src")
    with src.client() as c:
        src.run(c)
        src.view()
        mid = Chat(migrated, {"m0": [a("하나", "has_status", None, "슬픔")]}, name="w3-carry-mid")
        mid.run(c)
        end = Chat(migrated, {"e0": []}, name="w3-carry-end")
        end.run(c)
        reg = Chat(migrated, {"r0": []}, name="w3-carry-reg")
        reg.run(c)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            keys = carry.Keys(extractor=src.key)
            carry.link(conn, mid.cid, src.cid, "continue", None, keys)
            conn.commit()
            carry.link(conn, end.cid, mid.cid, "continue", None, keys)  # chained: mid's carried rows come along
            conn.commit()
            carry.link(conn, reg.cid, src.cid, "regression", ["하나"], keys)
            conn.commit()
            links = {n: carry.target_rows(carry.in_force(conn, x.cid)) for n, x in (("mid", mid), ("end", end),
                                                                                     ("reg", reg))}
        for n in ("mid", "end"):
            view = (mid if n == "mid" else end).view(carried=links[n])
            death = current(view, "vital_status")[0]
            assert death["carried"] == links[n].link and death["value"] == "사망" and death["knowledge_scope"]
            assert retrieval.says_gone(death)  # the gone rule's word list reads it (the gone pin: report)
            assert current(view, "feels_toward")[0]["condition"] == PRIV
            assert {b["value"] for b in view["beliefs"]} == {"리안이 살아 있다"} and view["beliefs"][0]["carried"]
            assert view["beliefs"][0]["carried_from"]["revision"]  # its provenance names the source's message
        lines = {x.get("predicate"): x for x in links["reg"].regression if x["line"] == "fact"}
        assert lines["feels_toward"]["condition"] == PRIV and lines["feels_toward"]["knowledge_scope"] == "public"
