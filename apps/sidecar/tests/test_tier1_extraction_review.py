"""Tier 1 follow-up: what the independent review of extraction, reveals and settings found (F1–F12).

F7 a carried secret could never be found out under extract-v15..v20; F4 repeated reveal entries stored a row each;
F5 the canon reader's cap; F6 a solo secret found out by any string; F3 the reveal check never listed what only v21
writes; F8 a job stuck `running` held its chat for ever; F10 a reworded secret queued a paid check for every later
turn; F11 a secret the owner reopened was never checked again; F12 a saved whole number written as a float; F1 the
value of a predicate that takes none is stored again. Synthetic names only.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from conftest import active_generation, make_client
from nmos_sidecar import extraction as X, reveals
from test_extraction import drain
from test_generations import LLM
from test_phase60_carry_fold import SECRET, _link_continue, _stub_extract, _world
from test_sidecar_integration import sync

V20 = {**LLM, "summaries": False, "extract_backfill": 100, "extract_compiler": "extract-v20"}
FOUND_LINE = f"카이토는 결국 {SECRET}는 사실을 알아챘다."


def _connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, row_factory=dict_row, autocommit=True)


def _finder(system: str, user: str) -> tuple[dict, str, dict]:
    """The carry tests' stub, which also reports S1 found out by 카이토 when the TARGET says so and S1 is the secret."""
    listed = [line for line in user.split("TARGET", 1)[0].splitlines() if line.startswith("S1. ")]
    found = ([{"secret": "S1", "found_out_by": ["카이토"], "evidence": FOUND_LINE}]
             if listed and SECRET in listed[0] and FOUND_LINE in user.split("TARGET", 1)[-1] else [])
    if system == reveals.PROMPT:
        return {"secrets": found}, "{}", {"calls": 1}
    out, raw, used = _stub_extract(system, user)
    return {**out, "secrets": found}, raw, used


def _learned(conn: psycopg.Connection, conv: UUID) -> list[dict[str, Any]]:
    return conn.execute(
        "SELECT a.subject, a.value, a.status, x.window_hash FROM assertion a JOIN extraction x ON x.id = a.extraction_id"
        " JOIN source_revision sr ON sr.id = x.source_revision_id JOIN source_object so ON so.id = sr.source_object_id"
        " WHERE so.conversation_id = %s AND a.predicate = 'learned' AND x.discarded_at IS NULL", (conv,)).fetchall()


# --- F7: a carried secret is listed and found out under every compiler ---------------------------------------------

def test_a_carried_secret_is_found_out_through_the_worker_under_extract_v20(migrated):
    with make_client(migrated, **V20) as c:
        src, tgt_chat, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            assert active_generation(conn, "extract").spec["compiler"] == "extract-v20"
            _link_continue(conn, tgt, src)
        tgt_chat.user("턴 9.")
        tgt_chat.reply(FOUND_LINE)
        tgt_chat.user("계속.")
        sync(c, tgt_chat, character_name="하나", chat_name="새 이야기", persona_name="유찬")
        drain(migrated, _finder)
        with _connect(migrated) as conn:
            (row,) = _learned(conn, tgt)
            assert (row["subject"], row["status"]) == ("카이토", "valid") and SECRET in row["value"]
        (secret,) = [s for s in c.get(f"/v1/conversations/{tgt}/secrets").json() if SECRET in s["text"]]
        assert "카이토" in secret["ended"] and not secret["open"]


def test_a_carried_secret_is_found_out_through_a_reveal_check(migrated):
    with make_client(migrated, **V20) as c:
        src, tgt_chat, tgt = _world(c, migrated)
        tgt_chat.user("턴 9.")
        tgt_chat.reply(FOUND_LINE)
        tgt_chat.user("계속.")
        sync(c, tgt_chat, character_name="하나", chat_name="새 이야기", persona_name="유찬")
        drain(migrated, _finder)  # extracted before the link: nothing was carried then
        with _connect(migrated) as conn:
            assert _learned(conn, tgt) == []
            _link_continue(conn, tgt, src)
            rv = active_generation(conn, "reveal")
            x = conn.execute(
                "SELECT x.id, x.source_revision_id AS rid, x.window_hash FROM extraction x"
                " JOIN active_membership am ON am.source_revision_id = x.source_revision_id"
                " AND am.turn_hash = x.window_hash JOIN conversation c ON c.head_commit_id = am.commit_id"
                " WHERE c.id = %s ORDER BY am.turn DESC LIMIT 1", (tgt,)).fetchone()
            conn.execute("INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority)"
                         " VALUES ('reveal', %s, %s, %s, %s)",
                         (f"reveal:{x['id']}:{rv.key}", tgt, Jsonb({"extraction_id": str(x["id"]),
                          "revision_id": str(x["rid"]), "window_hash": x["window_hash"], "generation": rv.key}),
                          X.HISTORY_PRIORITY))
        drain(migrated, _finder)
        with _connect(migrated) as conn:
            (row,) = _learned(conn, tgt)
            assert row["subject"] == "카이토" and row["window_hash"].startswith(reveals.WINDOW)
        (secret,) = [s for s in c.get(f"/v1/conversations/{tgt}/secrets").json() if SECRET in s["text"]]
        assert "카이토" in secret["ended"]
