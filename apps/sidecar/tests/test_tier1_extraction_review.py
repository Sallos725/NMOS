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


# --- F4, F6: what `revealed` makes of the model's `secrets` ----------------------------------------------------------

def test_repeated_reveal_entries_store_one_row_per_secret_and_name():
    secrets = [{"text": "하나 knows: 편지는 가짜다", "holders": ["하나"], "kept_from": ["카이토", "유이"], "turn": 1}]
    quote = "카이토와 유이는 편지가 가짜라는 걸 알아챘다"
    entry = {"secret": "S1", "found_out_by": ["카이토", "유이", "카이토"], "evidence": quote}
    rows = X.revealed({"secrets": [entry] * 200}, secrets, quote)
    assert sorted(r["subject"] for r in rows) == ["유이", "카이토"]


def test_a_solo_secret_is_found_out_only_by_someone_and_by_few():
    from nmos_sidecar.entities import resolve
    from test_semantics import row
    earlier = [row(1, "유이", "located_in", "정원", subject_type="character", object_type="place")]
    r = resolve(UUID("01900000-0000-7000-8000-0000000000f6"), earlier, ["타쿠미"])
    secrets = [{"text": "하나 feels: 카이토를 좋아한다", "holders": ["하나"], "kept_from": [], "turn": 1, "solo": True}]
    quote = "카이토는 하나가 자기를 좋아한다는 걸 알아챘다"
    names = ["카이토", "유이", "타쿠미", "모두", "everyone else", "하나"] + [f"이름{i}" for i in range(100)]
    rows = X.revealed({"secrets": [{"secret": "S1", "found_out_by": names, "evidence": quote}]}, secrets, quote, r)
    # written in the turn, known before, the persona; not a made-up phrase, not a holder
    assert [x["subject"] for x in rows] == ["카이토", "유이", "타쿠미"]
    many = [f"인물{i}" for i in range(20)]
    text = quote + " " + " ".join(many)
    rows = X.revealed({"secrets": [{"secret": "S1", "found_out_by": many, "evidence": quote}]}, secrets, text, r)
    assert len(rows) == X.SOLO_FOUND


# --- F5: the canon reader keeps the model's own at most 40 -----------------------------------------------------------

def test_the_canon_reader_cannot_be_made_to_store_more_than_forty_rows(migrated):
    from test_canon import push
    from test_canon_facts import Model, canon_texts, drain as drain_canon, story

    class Marked(Model):
        def __call__(self, system: str, user: str) -> tuple[dict, str]:
            out, raw = super().__call__(system, user)
            if "CANON" in system and "card's description" in user:
                marked = {"subject": "Hana", "subject_type": "character", "predicate": "identity", "value": "keeper",
                          "modality": "actual", "source": "narration", "listed": {"by": "Hana"}, "listed_pair": True}
                out = {**out, "assertions": [{**marked, "value": f"keeper {i}"} for i in range(150)]
                       + [{**marked, "predicate": "learned", "value": f"[turn 1] x {i}"} for i in range(150)]}
            return out, raw

    chat = story()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, canon_texts())
        drain_canon(migrated, Marked())
    with _connect(migrated) as conn:
        counts = conn.execute(
            "SELECT x.id, count(a.id) AS n, count(a.id) FILTER (WHERE a.predicate = 'learned') AS learned"
            " FROM extraction x JOIN assertion a ON a.extraction_id = x.id JOIN projection_generation g"
            " ON g.key = x.extractor_key WHERE g.kind = 'canon' GROUP BY 1").fetchall()
    assert counts and max(r["n"] for r in counts) == X.MAX_ASSERTIONS and sum(r["learned"] for r in counts) == 0


# --- F8: a job left running by a dead worker is given up on ----------------------------------------------------------

def test_a_job_stuck_running_dies_after_its_last_attempt_and_lets_the_chat_go_on(migrated):
    from nmos_sidecar.extraction import claim
    from simchat import SimChat
    from test_extraction import filler

    chat = SimChat()
    filler(chat, 3)
    chat.user("next")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
    with _connect(migrated) as conn:
        handled = {"extract": active_generation(conn, "extract").key}
        stuck = claim(conn, handled)
        assert claim(conn, handled) is None  # its chat's later turns wait behind it
        conn.execute("UPDATE job SET locked_at = now() - interval '11 minutes' WHERE id = %s", (stuck["id"],))
        again = claim(conn, handled)  # requeued: its worker is gone, but it has attempts left
        assert again["id"] == stuck["id"] and again["attempts"] == 2
        conn.execute("UPDATE job SET locked_at = now() - interval '11 minutes', attempts = %s WHERE id = %s",
                     (X.MAX_ATTEMPTS, stuck["id"]))
        later = claim(conn, handled)
        assert later is not None and later["id"] > stuck["id"]  # the chat goes on
        dead = conn.execute("SELECT status, last_error FROM job WHERE id = %s", (stuck["id"],)).fetchone()
        assert dead["status"] == "dead" and dead["last_error"].startswith(X.LOST)


# --- F3: the reveal check lists what only extract-v21 writes ---------------------------------------------------------

GUISE = "하나는 카이토 몰래 유이라는 가명으로 지낸다."
SEEN_THROUGH = "카이토는 유이가 사실 하나라는 걸 알아챘다."


def _v21_stub(system: str, user: str) -> tuple[dict, str]:
    """A cover identity kept from 카이토 in its turn; the reveal check reports it found out when it lists it."""
    target = user.split("TARGET", 1)[-1]
    if system == reveals.PROMPT:
        listed = [line for line in user.split("TARGET", 1)[0].splitlines() if line.startswith("S1. ")]
        found = listed and "유이" in listed[0] and SEEN_THROUGH in target
        return {"secrets": [{"secret": "S1", "found_out_by": ["카이토"], "evidence": SEEN_THROUGH}] if found else []}, "{}"
    items = [{"subject": "하나", "subject_type": "character", "predicate": "cover_identity", "value": "유이",
              "modality": "actual", "source": "narration", "evidence": GUISE, "knowledge": "limited",
              "known_by": ["하나"], "hidden_from": ["카이토"]}] if GUISE in target else []
    return {"assertions": items, "secrets": []}, "{}"  # the turn's own extraction reports nothing found out


def test_the_reveal_check_lists_a_secret_only_extract_v21_writes(migrated):
    from simchat import SimChat
    chat = SimChat()
    for text in (GUISE, SEEN_THROUGH):
        chat.user("턴.")
        chat.reply(text)
    chat.user("계속.")
    with make_client(migrated, **{**V20, "extract_compiler": "extract-v21"}) as c:
        sync(c, chat)
        drain(migrated, _v21_stub)
        with _connect(migrated) as conn:
            conv = conn.execute("SELECT id FROM conversation").fetchone()["id"]
            assert _learned(conn, conv) == []
            rv = active_generation(conn, "reveal")
            x = conn.execute(
                "SELECT x.id, x.source_revision_id AS rid, x.window_hash FROM extraction x"
                " JOIN active_membership am ON am.source_revision_id = x.source_revision_id"
                " AND am.turn_hash = x.window_hash WHERE am.turn = 1").fetchone()
            conn.execute("INSERT INTO job (kind, dedupe_key, conversation_id, payload, priority)"
                         " VALUES ('reveal', %s, %s, %s, %s)",
                         (f"reveal:{x['id']}:{rv.key}", conv, Jsonb({"extraction_id": str(x["id"]),
                          "revision_id": str(x["rid"]), "window_hash": x["window_hash"], "generation": rv.key}),
                          X.HISTORY_PRIORITY))
        drain(migrated, _v21_stub)
        with _connect(migrated) as conn:
            (row,) = _learned(conn, conv)
            assert row["subject"] == "카이토" and "유이" in row["value"] and row["window_hash"].startswith(reveals.WINDOW)
