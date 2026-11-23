"""PHASE-60 S6 (ADR 0085 item 7): a request reads the target's link in force under packet-v20 only, records it
(`recall_options.carry`), and its replay reads that link, removed since or not (D39).

An older trace replayed under packet-v20 reads the link that was in force at its time; packet-v19 never reads a link,
fresh or replayed. Stub extractor only; the worlds of `test_phase60_carry_fold`; synthetic names only."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import audit, carry
from nmos_sidecar.retrieval import RecallOptions
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


def _replay(migrated: str, trace: dict[str, Any], policy: str | None = None) -> dict[str, Any]:
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        out = audit.replay(conn, UUID(trace["id"]), RecallOptions(), policy=policy)
    assert out is not None and out["status"] == "ok", out
    return out


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


def test_a_replay_reads_the_recorded_link_removed_and_replaced_since(migrated: str) -> None:
    with _client(migrated, "packet-v20") as c:
        src, tgt_sim, tgt = _world(c, migrated)
        _, none_trace = _ask(c, tgt_sim)  # a v20 request before any link: it had none
        with _connect(migrated) as conn:
            first = _link(conn, tgt, src)
        text, trace = _ask(c, tgt_sim)
        assert CARRIED in text and trace["recall_options"]["carry"]["link"] == str(first["id"])
        with _connect(migrated) as conn:
            second = _link(conn, tgt, src, "regression", ["세라"])  # replaces the first (removed_at set)
            assert carry.by_id(conn, first["id"])["removed_at"] is not None
        now, _ = _ask(c, tgt_sim)
        assert CARRIED not in now  # the link in force now carries no continue rows
        again = _replay(migrated, trace)
        assert again["text"] == text and again["reproduced"] is True and again["notes"] == []
        # A v20 request that had no link replays with none, whatever is in force now.
        assert CARRIED not in _replay(migrated, none_trace)["text"]
        with _connect(migrated) as conn:
            carry.unlink(conn, tgt)
            assert carry.by_id(conn, second["id"])["removed_at"] is not None
        assert _replay(migrated, trace)["text"] == text  # removed since: still the recorded link


def test_a_replay_whose_link_was_deleted_with_its_chat_reads_none_and_says_so(migrated: str) -> None:
    with _client(migrated, "packet-v20") as c:
        src, tgt_sim, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            _link(conn, tgt, src)
        text, trace = _ask(c, tgt_sim)
        assert CARRIED in text
        res = c.post(f"/v1/conversations/{src}/delete")  # deletes the link with its source (D23)
        assert res.status_code == 200 and res.json()["deleted"]["carry_links"] == 1
        again = _replay(migrated, trace)
    assert "carry link gone" in again["notes"] and "reproduced" not in again
    assert CARRIED not in again["text"]


def test_an_older_trace_replayed_under_v20_reads_the_link_in_force_at_its_time(migrated: str) -> None:
    with _client(migrated, "packet-v19") as c:
        src, tgt_sim, tgt = _world(c, migrated)
        _, unlinked = _ask(c, tgt_sim)
        with _connect(migrated) as conn:
            _link(conn, tgt, src)
        plain, linked = _ask(c, tgt_sim)
        with _connect(migrated) as conn:
            _link(conn, tgt, src, "regression", ["세라"])  # in force now: no continue rows
    assert CARRIED not in plain
    # packet-v19 replays read no link, fresh trace or not
    assert _replay(migrated, linked)["text"] == plain
    # under packet-v20 each reads the link that was in force when it was answered
    assert CARRIED not in _replay(migrated, unlinked, "packet-v20")["text"]
    assert CARRIED in _replay(migrated, linked, "packet-v20")["text"]
