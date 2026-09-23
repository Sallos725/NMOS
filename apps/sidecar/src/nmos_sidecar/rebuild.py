"""Rebuild active_membership from worldline_commit deltas (derived data is rebuildable)."""

from __future__ import annotations

import argparse

import psycopg
from psycopg.rows import dict_row

from . import normtext
from .config import Settings
from .ledger import rebuild_membership
from .parsers import load_rules
from .state import rebuild_state


def rebuild_all(database_url: str, conversation_id: str | None = None, window: int = 6,
                turns: int = 3) -> dict[str, int]:
    out: dict[str, int] = {}
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        if conversation_id:
            ids = [conversation_id]
        else:
            ids = [str(r["id"]) for r in conn.execute("SELECT id FROM conversation ORDER BY created_at").fetchall()]
        for conv_id in ids:
            with conn.transaction():
                conn.execute("SELECT id FROM conversation WHERE id = %s FOR UPDATE", (conv_id,))
                _, count = rebuild_membership(conn, conv_id, window, turns)  # type: ignore[arg-type]
            out[conv_id] = count
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversation", help="rebuild one conversation id (default: all)")
    parser.add_argument("--state", action="store_true", help="also re-parse state with NMOS_PARSERS_FILE")
    parser.add_argument("--text", action="store_true",
                        help="drop and rewrite the normalized-text projection for the current normalizer")
    args = parser.parse_args()
    settings = Settings()
    for conv_id, count in rebuild_all(settings.database_url, args.conversation, settings.extract_window,
                                          settings.extract_turns).items():
        print(f"{conv_id}: {count} members")
    if args.text:
        with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                conn.execute("DELETE FROM revision_text WHERE normalizer = %s", (normtext.NORMALIZER_VERSION,))
            print(f"text: {normtext.backfill(conn)} revisions ({normtext.NORMALIZER_VERSION})")
    if args.state:
        with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
            print(f"state: {rebuild_state(conn, load_rules(settings.parsers_file))} observations")


if __name__ == "__main__":
    main()
