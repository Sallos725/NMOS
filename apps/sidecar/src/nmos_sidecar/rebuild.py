"""Rebuild active_membership from worldline_commit deltas (derived data is rebuildable)."""

from __future__ import annotations

import argparse

import psycopg
from psycopg.rows import dict_row

from .config import Settings
from .ledger import rebuild_membership


def rebuild_all(database_url: str, conversation_id: str | None = None) -> dict[str, int]:
    out: dict[str, int] = {}
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        if conversation_id:
            ids = [conversation_id]
        else:
            ids = [str(r["id"]) for r in conn.execute("SELECT id FROM conversation ORDER BY created_at").fetchall()]
        for conv_id in ids:
            with conn.transaction():
                conn.execute("SELECT id FROM conversation WHERE id = %s FOR UPDATE", (conv_id,))
                _, count = rebuild_membership(conn, conv_id)  # type: ignore[arg-type]
            out[conv_id] = count
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversation", help="rebuild one conversation id (default: all)")
    args = parser.parse_args()
    for conv_id, count in rebuild_all(Settings().database_url, args.conversation).items():
        print(f"{conv_id}: {count} members")


if __name__ == "__main__":
    main()
