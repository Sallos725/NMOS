"""What re-extractions lose (docs/phases/PHASE-22.md, Q8): read only, counts only, no model call.

For each conversation of a database, on its head as it is now:

- **same generation** (what "Needs attention" lists, PHASE-22 Q5): each turn whose serving extraction of the active
  generation replaced a discarded one of the same generation and turn hash. The replaced extraction's narrated actual
  facts, how many the new extraction states again (`repairs.restated`, one to one), how many the turn lost, and how many
  of those memory holds nowhere else (`dropped.find`), by predicate;
- **across generations** (measured only, never listed): each turn the active generation extracted that an older
  generation's live extraction also covers, the older one's facts against the active one's, the same way.

    cd apps/sidecar && uv run python ../../tools/reextract_loss.py postgresql://nmos:nmos@127.0.0.1:5436/copy [...]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from typing import Any

import psycopg
from psycopg.rows import dict_row

from nmos_sidecar import dropped
from nmos_sidecar.facts import memory_view
from nmos_sidecar.predicates import stored_knowledge
from nmos_sidecar.repairs import restated

# Each turn's extraction of the active generation and the latest live extraction of another generation of the same turn.
ACROSS = """
SELECT am.turn, n.id AS new, o.id AS old
FROM active_membership am
JOIN extraction n ON n.source_revision_id = am.source_revision_id AND n.window_hash = am.turn_hash
                 AND n.extractor_key = %(key)s AND n.discarded_at IS NULL
JOIN LATERAL (SELECT o.id FROM extraction o JOIN projection_generation g ON g.key = o.extractor_key
              WHERE o.source_revision_id = n.source_revision_id AND o.window_hash = n.window_hash
                AND o.extractor_key <> n.extractor_key AND o.discarded_at IS NULL
              ORDER BY g.activated_at DESC, g.key LIMIT 1) o ON true
WHERE am.commit_id = %(head)s AND am.turn_hash IS NOT NULL
"""


def rows_of(conn: psycopg.Connection, ids: list[Any]) -> dict[Any, list[dict[str, Any]]]:
    by: dict[Any, list[dict[str, Any]]] = {}
    for row in conn.execute(dropped.ROWS, (ids,)).fetchall():
        row = dict(row)
        row["participants"] = json.loads(row["participants"]) if row["participants"] else None
        if row["known_by"] or row["hidden_from"]:
            stored_knowledge(row)
        by.setdefault(row["extraction_id"], []).append(row)
    return by


def compare(conn: psycopg.Connection, pairs: list[dict[str, Any]], r: Any) -> dict[str, Any]:
    by = rows_of(conn, [p["old"] for p in pairs] + [p["new"] for p in pairs])
    facts = again = 0
    lost: Counter[str] = Counter()
    for p in pairs:
        old = [a for a in by.get(p["old"], []) if dropped._fact(a)]
        hit = restated(old, by.get(p["new"], []), r)
        facts += len(old)
        again += len(hit)
        lost.update(a["predicate"] for i, a in enumerate(old) if i not in hit)
    return {"turns": len(pairs), "facts": facts, "stated_again": again, "lost": sum(lost.values()),
            "lost_by_predicate": dict(lost.most_common())}


def measure(url: str) -> list[dict[str, Any]]:
    out = []
    with psycopg.connect(url, row_factory=dict_row) as conn:
        key = (conn.execute("SELECT key FROM projection_generation WHERE kind = 'extract'"
                            " ORDER BY activated_at DESC, key LIMIT 1").fetchone() or {}).get("key")
        for conv in conn.execute("SELECT id, head_commit_id FROM conversation WHERE head_commit_id IS NOT NULL"
                                 " ORDER BY id").fetchall():
            head = conv["head_commit_id"]
            view = memory_view(conn, head, key)
            same = conn.execute(dropped.PAIRS, {"head": head, "key": key}).fetchall()
            gone = dropped.find(conn, head, key, view)
            out.append({"conversation": str(conv["id"]),
                        "same_generation": {**compare(conn, same, view.get("resolution")), "dropped": len(gone),
                                            "dropped_by_predicate": dict(Counter(f["predicate"] for f in gone).most_common())},
                        "across_generations": compare(conn, conn.execute(ACROSS, {"head": head, "key": key}).fetchall(),
                                                      view.get("resolution"))})
    return out


def main(argv: list[str]) -> None:
    if not argv:
        sys.exit(__doc__)
    for url in argv:
        for c in measure(url):
            s, a = c["same_generation"], c["across_generations"]
            print(f"{url.rsplit('/', 1)[-1]} {c['conversation'][:8]}: same generation: turns {s['turns']}, facts "
                  f"{s['facts']}, stated again {s['stated_again']}, lost {s['lost']} {s['lost_by_predicate']}, dropped "
                  f"{s['dropped']} {s['dropped_by_predicate']}; across generations: turns {a['turns']}, facts {a['facts']}, "
                  f"stated again {a['stated_again']}, lost {a['lost']} {a['lost_by_predicate']}")


if __name__ == "__main__":
    main(sys.argv[1:])
