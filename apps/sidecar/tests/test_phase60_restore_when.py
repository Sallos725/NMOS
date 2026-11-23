"""Phase 60 S7: a restored fact keeps `when_happened` (dropped.find and owner repair `fact_restore`).

Synthetic names only (세라, 카이토, 하나).
"""

from __future__ import annotations

import json
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from conftest import active_generation, make_client
from nmos_sidecar import dropped, repairs
from nmos_sidecar.facts import memory_view
from simchat import SimChat
from test_dropped import chat_of, dropped as list_dropped
from test_extract_v18 import USED
from test_extraction import drain
from test_generations import LLM, conv_id
from test_repairs import repair
from test_sidecar_integration import sync

ACTUAL = {"polarity": "positive", "modality": "actual", "source": "narration"}
HARBOR_LINE = "카이토는 항구에 있다."
TURN1_LINE = "어제 세라는 성문을 닫았다. 하나는 기사다."
EVENT_QUOTE = "어제 세라는 성문을 닫았다"
IDENTITY_QUOTE = "하나는 기사다"

# Exact keys returned by dropped.find() for a row without when_happened (pre-Phase 60 shape).
PLAIN_DROPPED_KEYS = {
    "id", "extraction_id", "subject", "subject_type", "predicate", "object", "object_type", "value",
    "epistemic", "confidence", "evidence", "knowledge", "known_by", "hidden_from", "polarity", "modality",
    "source", "asserted_by", "salience", "participants", "outcome", "because",
    "turn", "turn_hash", "text", "replaced", "by",
}


def _extract_v19(system: str, user: str) -> tuple[dict, str, dict]:
    target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
    if HARBOR_LINE in target:
        return {"assertions": [
            {"subject": "카이토", "subject_type": "character", "predicate": "located_in",
             "object": "항구", "object_type": "place", "evidence": HARBOR_LINE, **ACTUAL},
        ]}, "{}", USED
    if TURN1_LINE in target:
        return {"assertions": [
            {"subject": "세라", "subject_type": "character", "predicate": "event",
             "value": "성문을 닫았다", "when_happened": "어제", "evidence": EVENT_QUOTE, **ACTUAL},
            {"subject": "하나", "subject_type": "character", "predicate": "identity",
             "value": "기사", "evidence": IDENTITY_QUOTE, **ACTUAL},
        ]}, "{}", USED
    return {"assertions": []}, "{}", USED


def _forgetful(system: str, user: str) -> tuple[dict, str, dict]:
    """Re-extraction that drops turn 1's event and identity while keeping turn 0."""
    target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
    if TURN1_LINE in target:
        return {"assertions": []}, "{}", USED
    return _extract_v19(system, user)


def _damaged_v19(c, migrated: str) -> tuple[SimChat, str]:
    chat = chat_of(HARBOR_LINE, TURN1_LINE, "카이토는 정원에 있다.")
    sync(c, chat)
    drain(migrated, _extract_v19)
    cid = conv_id(c, chat)
    assert c.post(f"/v1/conversations/{cid}/rebuild").status_code == 200
    drain(migrated, _forgetful)
    return chat, cid


def test_dropped_find_carries_when_happened_and_leaves_plain_rows_unchanged(migrated):
    with make_client(migrated, **LLM, extract_backfill=100, extract_compiler="extract-v19") as c:
        _chat, cid = _damaged_v19(c, migrated)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
            key = active_generation(conn, "extract").key
            view = memory_view(conn, head, key)
            found = dropped.find(conn, head, key, view)
    by_pred = {f["predicate"]: f for f in found}
    assert set(by_pred) == {"event", "identity"}
    assert by_pred["event"]["when_happened"] == "어제"
    plain = by_pred["identity"]
    assert "when_happened" not in plain
    assert set(plain) == PLAIN_DROPPED_KEYS
    # A dropped row without when_happened serializes identically to one without the column.
    expected = {k: plain[k] for k in sorted(PLAIN_DROPPED_KEYS)}
    assert json.dumps(plain, sort_keys=True, default=str) == json.dumps(expected, sort_keys=True, default=str)


def test_restore_target_and_apply_facts_carry_when_happened_only_when_present():
    plain = {
        "turn": 1, "turn_hash": "h1", "subject": "하나", "subject_type": "character",
        "predicate": "identity", "object": None, "object_type": None, "value": "기사",
        "epistemic": "observed", "confidence": 0.9, "evidence": IDENTITY_QUOTE,
        "knowledge": "shared", "known_by": None, "hidden_from": None,
        "polarity": "positive", "modality": "actual", "source": "narration", "asserted_by": None,
        "salience": None, "participants": None, "outcome": None, "because": None,
        "text": "하나 identity: 기사",
    }
    dated = {
        **plain, "subject": "세라", "predicate": "event", "value": "성문을 닫았다",
        "evidence": EVENT_QUOTE, "text": "세라 event: 성문을 닫았다", "when_happened": "어제",
    }
    expected_plain_target = {
        "turn": 1, "turn_hash": "h1", "predicate": "identity", "subject": "하나",
        "object": None, "text": "하나 identity: 기사", "evidence": IDENTITY_QUOTE,
        "fact": {k: plain.get(k) for k in repairs.RESTORED},
    }
    got_plain = repairs.restore_target(plain)
    assert json.dumps(got_plain) == json.dumps(expected_plain_target)
    assert "when_happened" not in got_plain["fact"]

    got_dated = repairs.restore_target(dated)
    assert got_dated["fact"]["when_happened"] == "어제"

    applied: dict[str, str | None] = {}
    reps = [
        {"id": uuid4(), "kind": "fact_restore", "target": got_plain, "value": {}},
        {"id": uuid4(), "kind": "fact_restore", "target": got_dated, "value": {}},
    ]
    rows, _ = repairs.apply_facts([], reps, None, applied, turn_info={1: (3, "h1")})
    by_pred = {r["predicate"]: r for r in rows}
    assert by_pred["event"]["when_happened"] == "어제"
    assert "when_happened" not in by_pred["identity"] and by_pred["identity"].get("when_happened") is None


def test_fact_restore_keeps_when_happened_end_to_end_and_keeps_plain_repair_json_unchanged(migrated):
    with make_client(migrated, **LLM, extract_backfill=100, extract_compiler="extract-v19") as c:
        _chat, cid = _damaged_v19(c, migrated)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
            key = active_generation(conn, "extract").key
            dropped_rows = {f["predicate"]: f for f in dropped.find(conn, head, key, memory_view(conn, head, key))}
        plain_src = dropped_rows["identity"]
        expected_plain_target = {
            "turn": plain_src["turn"], "turn_hash": plain_src["turn_hash"], "predicate": plain_src["predicate"],
            "subject": plain_src["subject"], "object": plain_src.get("object"), "text": plain_src["text"],
            "evidence": plain_src.get("evidence"), "fact": {k: plain_src.get(k) for k in repairs.RESTORED},
        }
        listed = {f["predicate"]: f for f in list_dropped(c, cid)}
        assert set(listed) == {"event", "identity"}

        out_event = repair(c, cid, kind="fact_restore", item=str(listed["event"]["id"]))
        assert out_event["applied"] is not None
        assert out_event["repair"]["target"]["fact"]["when_happened"] == "어제"
        assert out_event["repair"]["value"] == {}

        out_plain = repair(c, cid, kind="fact_restore", item=str(listed["identity"]["id"]))
        assert out_plain["applied"] is not None
        assert set(out_plain["repair"]["target"]["fact"]) == set(repairs.RESTORED)
        assert json.dumps(out_plain["repair"]["target"], sort_keys=True) == json.dumps(expected_plain_target, sort_keys=True)
        assert json.dumps(out_plain["repair"]["value"], sort_keys=True) == "{}"

        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            stored = conn.execute("SELECT target::text AS target_text, value::text AS value_text"
                                  " FROM owner_repair WHERE id = %s",
                                  (out_plain["repair"]["id"],)).fetchone()
            expected_text = conn.execute("SELECT %s::jsonb::text AS target_text, %s::jsonb::text AS value_text",
                                         (Jsonb(expected_plain_target), Jsonb({}))).fetchone()
            assert stored == expected_text
            view = memory_view(conn, head, key)
        restored_assertions = {a["predicate"]: a for a in view["assertions"] if a.get("owner")}
        assert restored_assertions["event"]["when_happened"] == "어제"
        assert "when_happened" not in restored_assertions["identity"]
        assert restored_assertions["identity"].get("when_happened") is None

        facts = {f["predicate"]: f for f in c.get(f"/v1/conversations/{cid}/facts", params={"history": "true"}).json()}
        assert facts["event"]["owner"] is True and facts["event"]["when_happened"] == "어제"
        assert facts["event"]["history"][0]["when_happened"] == "어제"
        assert facts["identity"]["owner"] is True and "when_happened" not in facts["identity"]
        assert facts["identity"].get("when_happened") is None and "when_happened" not in facts["identity"]["history"][0]
        assert list_dropped(c, cid) == []

