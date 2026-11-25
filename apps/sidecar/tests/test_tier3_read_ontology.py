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
