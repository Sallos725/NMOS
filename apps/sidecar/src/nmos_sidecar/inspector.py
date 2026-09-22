"""Read-only inspector: plain server-rendered HTML, every value escaped."""

from __future__ import annotations

from collections.abc import Iterable
from html import escape
from typing import Any

STYLE = """
:root{color-scheme:light dark;--bg:#fbfbfa;--fg:#1d1d1f;--muted:#6b6b70;--line:#e3e3e0;--chip:#efefec;--accent:#3b5bdb}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--fg:#ececec;--muted:#9a9aa0;--line:#2c2c30;--chip:#26262a;--accent:#8ea2ff}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Noto Sans KR",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:28px 0 8px}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
.muted{color:var(--muted)} .mono{font-family:ui-monospace,monospace;font-size:12px}
table{width:100%;border-collapse:collapse} th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:12px}
.chip{display:inline-block;padding:0 6px;border-radius:4px;background:var(--chip);font-size:12px}
.wrap{overflow-x:auto}
"""


def page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
            f"content=\"width=device-width,initial-scale=1\"><title>{escape(title)}</title><style>{STYLE}</style>"
            f"</head><body><main>{body}</main></body></html>")


def _v(value: Any) -> str:
    return escape("" if value is None else str(value))


def table(headers: list[str], rows: Iterable[list[str]]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<div class=\"wrap\"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def index(conversations: list[dict[str, Any]], q: str, jobs: dict[str, int] | None = None) -> str:
    rows = [[f"<a href=\"/inspector/c/{c['id']}{q}\" class=\"mono\">{_v(c['host_chat_ref'])}</a>",
             _v(c["messages"]), _v(c["commits"]), _v(c["branched_from_host_chat_ref"] or ""),
             _v(str(c["last_retrieval"] or "")[:19])] for c in conversations]
    queue = " · ".join(f"{escape(k)} {v}" for k, v in sorted((jobs or {}).items())) or "empty"
    return page("NMOS inspector", "<h1>NMOS inspector</h1><p class=\"muted\">Read-only view of the source ledger."
                f" Background jobs: {queue}</p>"
                + table(["Host chat", "Messages", "Commits", "Branched from", "Last retrieval"], rows))


def detail(conv: dict[str, Any], state: list[dict[str, Any]], members: list[dict[str, Any]],
           commits: list[dict[str, Any]], traces: list[dict[str, Any]], facts: list[dict[str, Any]], q: str) -> str:
    parts = [f"<p><a href=\"/inspector{q}\">← conversations</a></p>",
             f"<h1 class=\"mono\">{_v(conv['host_chat_ref'])}</h1>",
             f"<p class=\"muted\">conversation {_v(conv['id'])} · head {_v(conv['head_commit_id'])}"
             + (f" · branched from {_v(conv['branched_from_host_chat_ref'])} at {_v(conv['branched_from_message_ref'])}"
                if conv.get("branched_from_host_chat_ref") else "") + "</p>"]
    parts.append("<h2>Current state</h2>" + (table(["Key", "Value", "As of turn", "Rule"],
                 [[_v(s["key"]), _v(s["value"]), _v(s["position"]), _v(s["rule_id"])] for s in state])
                 if state else "<p class=\"muted\">No parser state.</p>"))
    if facts:
        parts.append("<h2>Current facts</h2>" + table(["Subject", "Predicate", "Object / value", "Turn", "Versions"],
                     [[_v(f["subject"]), f"<span class=\"chip\">{_v(f['predicate'])}</span>",
                       _v(f.get("object") or f.get("value")), _v(f["position"]), _v(f.get("versions", 1))] for f in facts]))
    parts.append("<h2>Recent retrievals</h2>" + table(
        ["When", "Query", "Fresh", "Cand.", "Sel.", "In-ctx", "Tokens", "ms"],
        [[_v(str(t["created_at"])[:19]), _v(t["query"]), _v(t["freshness"]), _v(t["candidates"]), _v(t["selected"]),
          _v(t["excluded"]), _v(t["token_estimate"]), _v((t["latency_ms"] or {}).get("sidecar_total"))] for t in traces]))
    parts.append("<h2>Commits</h2>" + table(["#", "Reason", "Changes", "Kinds", "When"],
                 [[_v(c["seq"]), f"<span class=\"chip\">{_v(c['reason'])}</span>", _v(c["changes"]), _v(c["kinds"]),
                   _v(str(c["created_at"])[:19])] for c in commits]))
    parts.append("<h2>Head membership (newest first)</h2>" + table(["Turn", "Role", "Lifecycle", "Disabled", "Text"],
                 [[_v(m["position"]), _v(m["role"]), f"<span class=\"chip\">{_v(m['lifecycle'])}</span>",
                   _v(m["disabled"] or ""), _v(m["preview"]) + ("…" if m["length"] > 240 else "")] for m in members]))
    return page(f"NMOS · {conv['host_chat_ref']}", "".join(parts))
