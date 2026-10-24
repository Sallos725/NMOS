"""The panel's design tokens (PHASE-52 D8), as the sidecar's stylesheet uses them. `fixtures/unit/design-tokens-v1.json`
holds the same values, and the plugin's `palette.ts` is checked against it too: both languages' tests compare."""

from __future__ import annotations

import re
from typing import Any

TOKENS: dict[str, Any] = {
    "color": {
        "bg": "#0a0b0e", "sunken": "#0d0e13", "surface": "#121318", "raised": "#1a1b22", "raisedHover": "#23242e",
        "line": "rgba(255,255,255,0.07)", "lineStrong": "rgba(255,255,255,0.10)", "lineHover": "rgba(255,255,255,0.16)",
        "textStrong": "#f4f4f7", "text": "#e2e2e8", "textSoft": "#c0c3d0", "textMuted": "#9294a0",
        "textFaint": "#7c7e8b", "textGhost": "#5c5e6b",
        "accent": "#4a6af5", "accentHover": "#3f5ee6", "link": "#7ca0ff", "ok": "#4fd18b", "err": "#f05d5e",
        "warn": "#e8ac43",
    },
    "type": {"body": 16, "secondary": 14, "caption": 13, "h1": 20, "h2": 17, "line": 1.65, "weights": [400, 600]},
    "space": [4, 8, 12, 16, 24, 32],
    "radius": {"control": 6, "block": 12},
}


def _kebab(name: str) -> str:
    return re.sub(r"[A-Z]", lambda m: "-" + m[0].lower(), name)


def css_vars() -> str:
    """`--c-*` colours (the plugin's names, `paletteVars`), `--t-*` type sizes, `--r-*` radii."""
    out = [f"--c-{_kebab(k)}:{v}" for k, v in TOKENS["color"].items()]
    out += [f"--t-{k}:{v}px" for k, v in TOKENS["type"].items() if k not in ("line", "weights")]
    out += [f"--r-{k}:{v}px" for k, v in TOKENS["radius"].items()]
    return ";".join(out)
