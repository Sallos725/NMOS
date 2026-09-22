"""Fact versions over valid assertions whose extraction matches the head window (D8)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from xml.sax.saxutils import escape, quoteattr

from .extraction import COMPILER_VERSION
from .predicates import REGISTRY

ACTIVE_ASSERTIONS = """
WITH m AS (
    SELECT am.position, am.source_revision_id AS rid, am.window_hash, sr.lifecycle, sr.metadata, so.host_logical_id
    FROM active_membership am
    JOIN source_revision sr ON sr.id = am.source_revision_id
    JOIN source_object so ON so.id = sr.source_object_id
    WHERE am.commit_id = %(head)s
),
cut AS (SELECT coalesce(max(position), -1) AS position FROM m WHERE metadata->>'disabled' = 'allBefore')
SELECT a.id, a.subject, a.subject_type, a.predicate, a.object, a.value, a.epistemic, a.confidence, a.evidence,
       m.position, m.host_logical_id
FROM assertion a
JOIN extraction e ON e.id = a.extraction_id AND e.compiler_version = %(ver)s
JOIN m ON m.rid = a.source_revision_id AND m.window_hash = e.window_hash
CROSS JOIN cut
WHERE a.status = 'valid' AND m.lifecycle = 'accepted' AND m.position > cut.position
  AND coalesce(m.metadata->>'disabled', '') NOT IN ('true', 'allBefore')
ORDER BY m.position, a.id
"""


def _norm(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def version_key(a: dict[str, Any]) -> tuple:
    pred = REGISTRY[a["predicate"]]
    if pred.cardinality == "single":
        return (a["predicate"], _norm(a["subject"])) + ((_norm(a["object"]),) if pred.per_object else ())
    return (a["predicate"], _norm(a["subject"]), _norm(a["object"]), _norm(a["value"]))


def fact_versions(conn: psycopg.Connection, head: UUID) -> list[dict[str, Any]]:
    """Current fact per version key (latest by position) with its history, oldest→newest."""
    rows = conn.execute(ACTIVE_ASSERTIONS, {"head": head, "ver": COMPILER_VERSION}).fetchall()
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for row in rows:
        if row["predicate"] in REGISTRY:
            groups.setdefault(version_key(row), []).append(row)
    out = []
    for history in groups.values():
        current = dict(history[-1])
        current["versions"] = len(history)
        current["history"] = [{"position": h["position"], "value": h["value"], "object": h["object"]} for h in history]
        out.append(current)
    out.sort(key=lambda f: f["position"], reverse=True)
    return out


def _grams(text: str) -> set[str]:
    padded = f"  {_norm(text)} "
    return {padded[i: i + 3] for i in range(len(padded) - 2)}


def fact_text(f: dict[str, Any]) -> str:
    parts = [f["subject"], f["predicate"].replace("_", " ")]
    if f.get("object"):
        parts.append(f["object"])
    text = " ".join(parts)
    return f"{text}: {f['value']}" if f.get("value") else text


def relevant_facts(facts: list[dict[str, Any]], query: str, previous_ai: str, in_context: set[str],
                   limit: int) -> list[dict[str, Any]]:
    """Facts about entities mentioned now, then lexically related ones; never from in-context sources."""
    q = _norm(query)
    ai = _norm(previous_ai)
    q_grams = _grams(query)
    scored = []
    for f in facts:
        if f["host_logical_id"] in in_context:
            continue
        names = [n for n in (_norm(f["subject"]), _norm(f.get("object"))) if len(n) >= 2]
        mention = 2.0 if any(n in q for n in names) else (1.0 if any(n in ai for n in names) else 0.0)
        grams = _grams(fact_text(f))
        lexical = len(grams & q_grams) / max(1, len(q_grams))
        score = mention + lexical
        if mention or lexical >= 0.35:
            scored.append((score, f["position"], f))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [f for _, _, f in scored[:limit]]


def fact_line(f: dict[str, Any]) -> str:
    return (f"    <Fact kind={quoteattr(f['predicate'])} turn=\"{f['position']}\""
            f"{' certainty=\"implied\"' if f.get('epistemic') == 'implied' else ''}>{escape(fact_text(f))}</Fact>")
