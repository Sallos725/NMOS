"""The panel's design tokens (PHASE-52 D8), as the sidecar's stylesheet uses them. `fixtures/unit/design-tokens-v1.json`
holds the same values, and the plugin's `palette.ts` is checked against it too: both languages' tests compare."""

from __future__ import annotations

from html import escape
import re
from typing import Any
from urllib.parse import quote

TOKENS: dict[str, Any] = {
    "color": {
        "bg": "#16181e", "sunken": "#12141a", "surface": "#1e212a", "raised": "#262a35", "raisedHover": "#303543",
        "line": "rgba(255,255,255,0.08)", "lineStrong": "rgba(255,255,255,0.13)", "lineHover": "rgba(255,255,255,0.2)",
        "textStrong": "#eef1f7", "text": "#dce1ec", "textSoft": "#b6bece", "textMuted": "#9294a0",
        "textFaint": "#878b99", "textGhost": "#676c7d",
        "accent": "#4a6af5", "accentHover": "#3f5ee6", "link": "#85a6ff", "ok": "#4fd18b", "err": "#f05d5e",
        "warn": "#e8ac43", "violet": "#a78bfa", "cyan": "#38bdf8",
    },
    "type": {"body": 16, "secondary": 14, "caption": 13, "h1": 20, "h2": 17, "line": 1.65, "weights": [400, 600]},
    "space": [4, 8, 12, 16, 24, 32],
    "radius": {"control": 6, "block": 12},
}

# Official NMOS mark (`adapters/pocketrisu-plugin/src/icon.ts`): one-stroke N with a memory node.
NMOS_MARK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="none" '
    'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M6 19V5l12 14V9.5"/><circle cx="18" cy="5.5" r="1.75" fill="currentColor" stroke="none"/></svg>'
)

ARROW_UP_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="15" height="15" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M12 19V5"/><polyline points="5 12 12 5 19 12"/></svg>'
)

# Shared sticky top bar + floating Back-to-Top button for standalone browser pages (`/views/*` and `/inspector/*`).
BROWSER_BAR_STYLE = """
.nm-bar{position:sticky;top:0;z-index:30;background:rgba(22,24,30,0.9);backdrop-filter:blur(16px);border-bottom:1px solid var(--c-line)}
.nm-bar-in{max-width:1120px;margin:0 auto;padding:10px 22px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.nm-bar-brand{display:inline-flex;align-items:center;gap:8px;color:var(--c-text-strong);font-size:16px;font-weight:750;letter-spacing:-0.02em;text-decoration:none;padding:3px 6px 3px 2px;border-radius:9px}
.nm-bar-brand:hover{background:var(--c-raised);text-decoration:none}
.nm-bar-logo{width:28px;height:28px;border-radius:7px;display:inline-flex;align-items:center;justify-content:center;background:var(--c-raised);border:1px solid var(--c-line-strong);color:var(--c-text-strong)}
.nm-bar-nav{display:inline-flex;align-items:center;gap:4px;padding:3px;background:var(--c-sunken);border:1px solid var(--c-line);border-radius:11px}
.nm-bar-nav a{display:inline-flex;align-items:center;padding:6px 12px;border-radius:8px;font-size:13.5px;font-weight:550;color:var(--c-text-muted);text-decoration:none;border:1px solid transparent;transition:background .15s ease,color .15s ease,border-color .15s ease}
.nm-bar-nav a:hover{color:var(--c-text-strong);background:var(--c-raised);text-decoration:none}
.nm-bar-nav a.on{background:var(--c-raised-hover);color:var(--c-text-strong);border-color:var(--c-line-strong);box-shadow:0 1px 4px rgba(0,0,0,0.28)}
.nm-top{position:fixed;right:20px;bottom:22px;z-index:42;display:inline-flex;align-items:center;gap:5px;padding:8px 13px;border-radius:999px;background:rgba(38,42,53,0.94);backdrop-filter:blur(12px);border:1px solid var(--c-line-hover);color:var(--c-text-strong);font:600 13px/1 system-ui,-apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,0.45);opacity:0;pointer-events:none;transform:translateY(8px);transition:opacity .15s ease,transform .15s ease,border-color .15s ease,background .15s ease}
.nm-top.show{opacity:1;pointer-events:auto;transform:translateY(0)}
.nm-top:hover{background:var(--c-raised-hover);border-color:rgba(74,106,245,0.65);color:#fff}
.nm-top:focus-visible{outline:2px solid rgba(74,106,245,0.7);outline-offset:2px}
@media (max-width:720px){.nm-bar-in{padding:8px 14px;gap:8px}.nm-bar-nav{width:100%;justify-content:space-between}.nm-bar-nav a{flex:1;justify-content:center;padding:6px 8px;font-size:13px}.nm-top{right:14px;bottom:16px;padding:7px 11px}}
"""


def browser_top_button(lang: str = "ko", *, tab_labels: bool = False) -> str:
    """Floating Back-to-Top button for standalone browser pages (`/views/*` and `/inspector/*`)."""
    label = "맨 위로" if lang == "ko" else "Back to top"
    extra = ""
    if tab_labels:
        all_lbl = "전체 펼치기" if lang == "ko" else "Show all"
        one_lbl = "탭으로 보기" if lang == "ko" else "Tab view"
        extra = f' data-all="{escape(all_lbl)}" data-one="{escape(one_lbl)}"'
    return (
        f'<button type="button" class="nm-top" aria-label="{escape(label)}" title="{escape(label)}"{extra}>'
        f'{ARROW_UP_SVG}<span>Top</span></button>'
    )


def browser_bar(active: str, lang: str = "ko", token: str | None = None) -> str:
    """Unified top bar for browser pages (`/views/*` and `/inspector/*`), carrying `?lang=` and `?token=` when set."""
    q_parts = [f"lang={quote(lang)}"] if lang and lang != "ko" else []
    if token:
        q_parts.append(f"token={quote(token)}")
    qs = ("?" + "&".join(q_parts)) if q_parts else ""
    labels = (
        ("hub", "/views/hub", "허브" if lang == "ko" else "Hub"),
        ("chats", "/views/chats", "채팅 목록" if lang == "ko" else "Chats"),
        ("inspector", "/inspector", "인스펙터" if lang == "ko" else "Inspector"),
    )
    links = "".join(
        f'<a href="{escape(path + qs)}"{" class=\"on\"" if key == active else ""}>{escape(label)}</a>'
        for key, path, label in labels
    )
    return (
        f'<header class="nm-bar"><div class="nm-bar-in">'
        f'<a class="nm-bar-brand" href="{escape("/views/hub" + qs)}">'
        f'<span class="nm-bar-logo">{NMOS_MARK_SVG}</span><span>NMOS</span></a>'
        f'<nav class="nm-bar-nav" aria-label="NMOS">{links}</nav>'
        f'</div></header>'
    )


def _kebab(name: str) -> str:
    return re.sub(r"[A-Z]", lambda m: "-" + m[0].lower(), name)


def css_vars() -> str:
    """`--c-*` colours (the plugin's names, `paletteVars`), `--t-*` type sizes, `--r-*` radii."""
    out = [f"--c-{_kebab(k)}:{v}" for k, v in TOKENS["color"].items()]
    out += [f"--t-{k}:{v}px" for k, v in TOKENS["type"].items() if k not in ("line", "weights")]
    out += [f"--r-{k}:{v}px" for k, v in TOKENS["radius"].items()]
    return ";".join(out)
