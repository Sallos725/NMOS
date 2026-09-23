"""Deterministic memory evaluation (Track A, A5): print the baseline table for docs/perf/eval-baseline.md.

Synthetic cases with a stub extractor and embedder (apps/sidecar/tests/memeval.py); one throwaway
database per mode on the compose PostgreSQL.

    cd apps/sidecar && uv run python ../../tools/eval_memory.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "sidecar" / "tests"))
from conftest import make_client  # noqa: E402
from memeval import CASES, MODES, run_mode, summary  # noqa: E402

from nmos_sidecar.migrate import apply_migrations  # noqa: E402

ADMIN_URL = os.environ.get("NMOS_TEST_ADMIN_URL", "postgresql://nmos:nmos@127.0.0.1:5436/postgres")


def main() -> None:
    results = []
    for mode in MODES:
        name = f"nmos_eval_{uuid.uuid4().hex[:8]}"
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{name}"')
        url = ADMIN_URL.rpartition("/")[0] + f"/{name}"
        try:
            apply_migrations(url)
            results += run_mode(mode, make_client, url)
        finally:
            with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
                admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')

    mark = {True: "yes", False: "**no**", None: "—"}
    print("| Case | Category | " + " | ".join(MODES) + " |")
    print("|---|---|" + "---|" * len(MODES))
    for case in CASES:
        cells = []
        for mode in MODES:
            r = next(x for x in results if x.case == case.name and x.mode == mode)
            cell = mark[r.gold_hit] if not case.irrelevant else ("—" if r.irrelevant_leak is None
                                                                 else ("**leak**" if r.irrelevant_leak else "empty"))
            if r.stale_hit:
                cell += " · **stale: " + ", ".join(r.stale_hit) + "**"
            cells.append(cell)
        print(f"| {case.name} | {case.category} | " + " | ".join(cells) + " |")
    print()
    print("| Mode | gold reached | cases with stale memory | irrelevant packets | mean packet tokens |")
    print("|---|---:|---:|---:|---:|")
    for mode, s in summary(results).items():
        print(f"| {mode} | {s['gold']} | {s['stale']} | {s['irrelevant_leaks']} | {s['tokens_mean']} |")


if __name__ == "__main__":
    main()
