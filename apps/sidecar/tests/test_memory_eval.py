"""Track A, A5: the deterministic memory evaluation keeps its baseline (docs/perf/eval-baseline.md)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest

from conftest import ADMIN_URL, _db_url, make_client
from memeval import CASES, MODES, Result, run_mode
from nmos_sidecar.migrate import apply_migrations


@pytest.fixture(scope="module")
def results() -> Iterator[dict[str, list[Result]]]:
    names = [f"nmos_eval_{uuid.uuid4().hex[:10]}" for _ in MODES]
    try:
        admin = psycopg.connect(ADMIN_URL, autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover
        pytest.skip(f"Postgres not reachable at {ADMIN_URL}: {exc}")
    with admin:
        for name in names:
            admin.execute(f'CREATE DATABASE "{name}"')
    try:
        out = {}
        for mode, name in zip(MODES, names):
            apply_migrations(_db_url(name))
            out[mode] = run_mode(mode, make_client, _db_url(name))
        yield out
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            for name in names:
                admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def by_case(rs: list[Result]) -> dict[str, Result]:
    return {r.case: r for r in rs}


@pytest.mark.parametrize("mode", [m for m in MODES if m != "recent"])
def test_no_stale_or_other_branch_memory_ever_reaches_the_model(results, mode):
    assert {r.case: r.stale_hit for r in results[mode] if r.stale_hit} == {}


def test_full_packet_answers_every_case(results):
    missed = [r.case for r in results["full"] if r.gold_hit is False]
    assert missed == []


def test_irrelevant_questions_get_an_empty_packet(results):
    for mode in ("lexical", "hybrid", "full"):
        assert [r.case for r in results[mode] if r.irrelevant_leak] == [], mode


def test_memory_modes_beat_recent_context(results):
    """The comparison the baseline records: without memory the model sees none of the gold."""
    recent = by_case(results["recent"])
    assert all(r.gold_hit is not True for r in recent.values())
    assert sum(r.gold_hit is True for r in results["full"]) == sum(1 for c in CASES if c.gold)


def test_budget_pressure_needs_the_excerpt_room_of_packet_v1(results):
    """Phase 9 (ADR 0027): with fact lines filling the budget, packet-v0 drops the one excerpt that
    answers, packet-v1 keeps room for it. Every other case answers the same under both."""
    pressure = {c.name for c in CASES if c.category == "budget pressure"}
    v0, v1 = by_case(results["full-v0"]), by_case(results["full"])
    assert {name for name in pressure if v0[name].gold_hit is False} == pressure
    assert all(v1[name].gold_hit for name in pressure)
    assert {n for n, r in v0.items() if r.gold_hit is False} == pressure
