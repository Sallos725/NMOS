"""The reader of a chat's `told` rows (PHASE-60 S8, A3, A6; ADR 0086).

Only extract-v19 asks for `told` and only its rows are read (`facts.served_told`); the packet's fact read keeps
excluding them, so a packet-v19 packet is the same with or without them. Synthetic names only (세라, 카이토, 하나, 유나).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar.facts import memory_view, served_assertions, served_told, told_rows
from simchat import SimChat
from test_extract_v18 import FEELING, USED, chat_of, feels
from test_extract_v19 import EVENT_QUOTE, SCENE, TOLD_QUOTE, event_row, told_row
from test_extraction import drain, filler
from test_generations import LLM, conv_id
from test_sidecar_integration import sync

# A paraphrase found nowhere in SCENE: a packet that carried it could only have it from the told row.
TOLD_VALUE = "유나의 출신에 얽힌 비밀"
QUESTION = "세라가 카이토에게 무슨 말을 했지?"


def complete(system, user):
    """The model: for SCENE, the told row (세라 → 카이토, about 유나, kept from 하나), the event with when_happened and
    a feeling."""
    target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
    if SCENE in target:
        return {"assertions": [told_row(value=TOLD_VALUE), event_row(),
                               feels("고마움", FEELING, "고마운 마음이 가득했지만")]}, "{}", USED
    return {"assertions": []}, "{}", USED


@contextmanager
def extracted(url: str, compiler: str, more: int = 0, **settings: Any) -> Iterator[tuple[Any, SimChat]]:
    """A client and the SCENE chat extracted under `compiler` by the stub (`more` filler turns after it)."""
    chat = chat_of(SCENE)
    filler(chat, more)
    with make_client(url, **LLM, extract_compiler=compiler, **settings) as client:
        sync(client, chat)
        drain(url, complete)
        yield client, chat


def reads(url: str, client, chat: SimChat, upto: int | None = None) -> tuple[list[dict], list[dict], dict]:
    """(served_told, the raw served rows, memory_view) of the chat under the active extract generation."""
    with psycopg.connect(url, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s",
                            (conv_id(client, chat),)).fetchone()["head_commit_id"]
        key = active_generation(conn, "extract").key
        return (served_told(conn, head, key, upto=upto), served_assertions(conn, head, key, upto),
                memory_view(conn, head, key, upto))


def test_told_rows_keeps_told_of_a_compiler_with_the_extension_in_order():
    rows = [{"predicate": "told", "compiler": "extract-v19", "id": 1},
            {"predicate": "knows", "compiler": "extract-v19", "id": 2},
            {"predicate": "told", "compiler": "extract-v18", "id": 3},
            {"predicate": "told", "compiler": None, "id": 4},
            {"predicate": "told", "id": 5},
            {"predicate": "told", "compiler": "extract-v19", "id": 6}]
    assert [r["id"] for r in told_rows(rows)] == [1, 6]
    assert told_rows([]) == []


def test_a6_served_told_reads_the_v19_told_row_and_the_facts_gain_none(migrated):
    with extracted(migrated, "extract-v19") as (client, chat):
        told, served, view = reads(migrated, client, chat)
    [row] = told
    assert row["compiler"] == "extract-v19" and row["predicate"] == "told"
    assert (row["subject"], row["object"], row["value"]) == ("세라", "카이토", TOLD_VALUE)
    assert row["evidence"] == TOLD_QUOTE and row["turn"] == 0
    assert row["participants"] == ({"name": "유나", "type": "character"},)
    assert (row["knowledge"], row["known_by"], row["hidden_from"]) == ("limited", ["세라", "카이토"], ["하나"])
    assert "when_happened" not in row
    assert [r for r in served if r["predicate"] == "told"] == told  # the reader is the served read, filtered
    assert not [f for f in view["facts"] if f["predicate"] == "told"]
    [event] = [f for f in view["facts"] if f["predicate"] == "event"]
    assert event["when_happened"] == "3년 전 겨울" and event["evidence"] == EVENT_QUOTE


def test_a6_under_v18_the_told_row_is_pending_and_never_served(migrated):
    with extracted(migrated, "extract-v18") as (client, chat):
        told, served, _ = reads(migrated, client, chat)
    assert told == [] and not [r for r in served if r["predicate"] == "told"]
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        assert conn.execute("SELECT status FROM assertion WHERE predicate = 'told'").fetchone()["status"] == "pending"


def test_a_told_row_of_another_compiler_forced_valid_is_skipped_by_every_reader(migrated):
    with extracted(migrated, "extract-v18") as (client, chat):
        with psycopg.connect(migrated, autocommit=True) as conn:
            assert conn.execute("UPDATE assertion SET status = 'valid', reason = NULL WHERE predicate = 'told'"
                                ).rowcount == 1
        told, served, view = reads(migrated, client, chat)
        conv = conv_id(client, chat)
        page = client.get(f"/inspector/c/{conv}")
        embedded = client.get(f"/v1/inspector/c/{conv}")
    [forced] = [r for r in served if r["predicate"] == "told"]
    assert forced["compiler"] == "extract-v18"  # served, so only the compiler gate leaves it out
    assert told == []
    assert not [f for f in view["facts"] if f["predicate"] == "told"]
    assert page.status_code == 200 and embedded.status_code == 200


def test_served_told_reads_as_of_upto(migrated):
    with extracted(migrated, "extract-v19") as (client, chat):
        [row], _, _ = reads(migrated, client, chat)
        before, _, _ = reads(migrated, client, chat, upto=row["position"] - 1)
        at, _, _ = reads(migrated, client, chat, upto=row["position"])
    assert before == [] and [r["id"] for r in at] == [row["id"]]


def retrieve(client, chat: SimChat, text: str) -> dict[str, Any]:
    """`test_summaries.ask`, with the policy the request's trace recorded."""
    chat.user(text)
    sync(client, chat)
    out = client.post("/v1/retrieve", json={"chat_id": chat.id, "query": text, "previous_ai": "", "budget_tokens": 2000,
                                            "in_context_ids": [m["chatId"] for m in chat.messages[-6:]]}).json()
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    return {"text": out["packet"]["text"], "policy": trace["policy"]}


@pytest.mark.parametrize("policy", [None, "packet-v20"])
def test_a3_the_packet_is_the_same_with_or_without_told_rows_and_when_happened(migrated, policy):
    """The told turn leaves the prompt's window (8 filler turns), so the packet carries what it reads of it."""
    settings = {} if policy is None else {"packet_policy": policy}
    with extracted(migrated, "extract-v19", more=8, **settings) as (client, chat):
        assert reads(migrated, client, chat)[0]  # the told row is served
        with_rows = retrieve(client, chat, QUESTION)
        with psycopg.connect(migrated, autocommit=True) as conn:
            assert conn.execute("DELETE FROM assertion WHERE predicate = 'told'").rowcount == 1
            assert conn.execute("UPDATE assertion SET when_happened = NULL WHERE when_happened IS NOT NULL"
                                ).rowcount == 1
        without = retrieve(client, chat, QUESTION)
    assert with_rows["policy"] == without["policy"] == (policy or "packet-v19")
    assert "고마움" in with_rows["text"]  # the packet does carry a fact of the told turn
    assert TOLD_VALUE not in with_rows["text"] and 'predicate="told"' not in with_rows["text"]
    assert with_rows["text"] == without["text"]
