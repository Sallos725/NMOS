"""PHASE-60 S6 (ADR 0085 item 7): a request reads the target's link in force under packet-v20 only, records it
(`recall_options.carry`), and its replay reads that link, removed since or not (D39).

An older trace replayed under packet-v20 reads the link that was in force at its time; packet-v19 never reads a link,
fresh or replayed. Stub extractor only; the worlds of `test_phase60_carry_fold`; synthetic names only."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from conftest import make_client
from nmos_sidecar import carry
from test_generations import LLM
from test_phase60_carry_fold import _connect, _key, _world
from test_sidecar_integration import recall

QUERY = "세라는 카이토와 어떤 사이야?"
CARRIED = "오랜 동료"  # only the source chat says how 세라 and 카이토 stand


def _client(migrated: str, policy: str):
    # rest_after well above the requests a test makes: a line placed in each of them never rests, so two requests of
    # one policy on the same state compile alike whatever came between them
    return make_client(migrated, packet_policy=policy, summaries=False, rest_after=20, extract_backfill=100, **LLM)


def _ask(c: Any, chat: Any) -> tuple[str, dict[str, Any]]:
    out = recall(c, chat, QUERY, in_context=[m["chatId"] for m in chat.messages[-2:]], budget=1500,
                 previous_ai="세라가 고개를 끄덕였다.")
    trace = c.get(f"/v1/trace/{out['trace_id']}").json()
    return out["packet"]["text"], trace


def _link(conn: psycopg.Connection, tgt: UUID, src: UUID, mode: str = "continue",
          names: list[str] | None = None) -> dict[str, Any]:
    return carry.link(conn, tgt, src, mode, names or [], carry.Keys(extractor=_key(conn)))["link"]


def _record(link: dict[str, Any]) -> dict[str, Any]:
    return {"link": str(link["id"]), "source": str(link["source_conversation_id"]),
            "commit": str(link["cutoff_commit_id"]), "position": link["cutoff_position"], "mode": link["mode"],
            "names": list(link["entity_names"])}


def test_a_v20_request_records_the_link_it_read_and_v19_reads_none(migrated: str) -> None:
    with _client(migrated, "packet-v20") as c:
        src, tgt_sim, tgt = _world(c, migrated)
    with _client(migrated, "packet-v19") as c:
        before, _ = _ask(c, tgt_sim)
    with _connect(migrated) as conn:
        link = _link(conn, tgt, src)
    with _client(migrated, "packet-v20") as c:
        text, trace = _ask(c, tgt_sim)
    assert trace["policy"] == "packet-v20"
    assert trace["recall_options"]["carry"] == _record(link)
    assert CARRIED in text  # the request read the carried rows
    with _client(migrated, "packet-v19") as c:
        after, trace19 = _ask(c, tgt_sim)
    assert trace19["policy"] == "packet-v19" and "carry" not in trace19["recall_options"]
    assert CARRIED not in after
    assert after == before  # byte-identical: packet-v19 reads no link (A3)


def test_a_v20_request_on_a_chat_without_a_link_records_none(migrated: str) -> None:
    with _client(migrated, "packet-v20") as c:
        _, tgt_sim, _ = _world(c, migrated)
        _, trace = _ask(c, tgt_sim)
    assert "carry" not in trace["recall_options"]
