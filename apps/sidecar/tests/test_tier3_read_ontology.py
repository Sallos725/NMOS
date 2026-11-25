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
