"""PHASE-60 S6 + S7 (ADR 0085, ADR 0086): a carried row that says when it happened, in the packet.

Under packet-v20 a carried fact and a carried open promise whose row has `when_happened` are one line each, carrying
both `source="carried"` (in place of a turn) and `happened="…"`. Under packet-v19 the link is not read at all: no
memory read is handed it, and the packet is byte-identical to the one without a link. Stub extractor only; the world
of `test_phase60_carry_fold`; synthetic names only."""

from __future__ import annotations

import dataclasses
import re
from typing import Any

import pytest

from conftest import make_client
from nmos_sidecar import carry, retrieval
from test_phase60_carry_fold import CANON_ON, PROMISE, _connect, _world
from test_phase60_carry_packet import _link, _packet

QUERY = "세라는 카이토와 어떤 사이야?"
FACT_WHEN = "지난 봄"
THREAD_WHEN = '4월 11일 "새벽"'  # a quote in the value: escaped as attribute text
FACT = '<Fact kind="relationship" source="carried" happened="지난 봄">세라 relationship 카이토: 오랜 동료</Fact>'
THREAD = (f'<Thread kind="promise" by="세라" to="카이토" source="carried" happened="4월 11일 &quot;새벽&quot;">'
          f'{PROMISE}</Thread>')


def _dated(carried: carry.Carried) -> carry.Carried:
    """The link's rows with `when_happened` on its relationship fact and on its promise's opening."""
    rows = []
    for row in carried.rows:
        if row["predicate"] == "relationship" and row["subject"] == "세라":
            row = {**row, "when_happened": FACT_WHEN}
        elif row["predicate"] == "promised":
            row = {**row, "when_happened": THREAD_WHEN}
        rows.append(row)
    assert sum("when_happened" in r for r in rows) == 2, rows
    return dataclasses.replace(carried, rows=tuple(rows))


class Reads:
    """The `carried` argument of every memory read `retrieval.gather` makes."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.carried: list[Any] = []
        real = retrieval.memory_view

        def spy(*args: Any, **kwargs: Any) -> dict[str, Any]:
            self.carried.append(kwargs.get("carried"))
            return real(*args, **kwargs)

        monkeypatch.setattr(retrieval, "memory_view", spy)


def _line(text: str, needle: str) -> str:
    (found,) = [x for x in text.splitlines() if needle in x]
    return found.strip()


def test_v20_puts_source_carried_and_happened_on_one_line_and_v19_never_reads_the_link(
    migrated: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads = Reads(monkeypatch)
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            carried = _dated(_link(conn, tgt, src))
            reads.carried.clear()
            v20, _ = _packet(conn, tgt, QUERY, carried)
            assert reads.carried and all(x is carried for x in reads.carried)
            undated_v20, _ = _packet(conn, tgt, QUERY, _link(conn, tgt, src))
            reads.carried.clear()
            v19, _ = _packet(conn, tgt, QUERY, carried, "packet-v19")
            assert reads.carried and all(x is None for x in reads.carried)  # the link is not read at all
            v19_plain, _ = _packet(conn, tgt, QUERY, None, "packet-v19")

    fact, thread = _line(v20.text, "오랜 동료</Fact>"), _line(v20.text, f"{PROMISE}</Thread>")
    assert fact == FACT and thread == THREAD
    for found in (fact, thread):
        assert not re.search(r"\bturn=", found)  # source="carried" in place of a turn, never turn="-1"
    # without `when_happened` the same rows read as before: only the mark is added
    assert _line(undated_v20.text, "오랜 동료</Fact>") == FACT.replace(' happened="지난 봄"', "")
    assert _line(undated_v20.text, f"{PROMISE}</Thread>") == THREAD.replace(' happened="4월 11일 &quot;새벽&quot;"', "")

    # packet-v19: as if there were no link
    assert v19.text == v19_plain.text and v19.ledger == v19_plain.ledger
    assert 'source="carried"' not in v19.text and "happened=" not in v19.text
    assert FACT_WHEN not in v19.text
