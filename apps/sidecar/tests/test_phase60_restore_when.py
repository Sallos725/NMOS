"""Phase 60 S7: a restored fact keeps `when_happened` (dropped.find and owner repair `fact_restore`).

Synthetic names only (세라, 카이토, 하나).
"""

from __future__ import annotations

import json

import psycopg
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import dropped
from nmos_sidecar.facts import memory_view
from simchat import SimChat
from test_dropped import chat_of
from test_extract_v18 import USED
from test_extraction import drain
from test_generations import LLM, conv_id
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
