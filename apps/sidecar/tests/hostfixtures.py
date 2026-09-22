"""Load recorded Phase 0A host observations (fixtures/host/a14c911-2026-09-22)."""

from __future__ import annotations

import json
from pathlib import Path

from nmos_sidecar.reconcile import Entry

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "host" / "a14c911-2026-09-22"


def snapshot(label: str) -> dict:
    """The (latest) snapshot observation recorded under scenario label `label`."""
    matches = sorted(FIXTURE_DIR.glob(f"*__{label}__snapshot__*.json"))
    if not matches:
        raise FileNotFoundError(f"no snapshot fixture for {label}")
    return json.loads(matches[-1].read_text(encoding="utf-8"))


def entries(label: str) -> list[Entry]:
    return [
        Entry(
            host_logical_id=m["chatId"],
            revision_hash=m["contentHash"],
            role=m["role"],
            disabled=m.get("disabled"),
            is_comment=m.get("isComment"),
            swipe_id=m.get("swipeId"),
            swipe_count=m.get("swipeCount") or 0,
            generation_id=m.get("generationId"),
            special_comments=tuple(m.get("specialComments") or ()),
        )
        for m in snapshot(label)["manifest"]["messages"]
    ]


def chat_id(label: str) -> str:
    return snapshot(label)["manifest"]["chatId"]


def recorded_manifest_hash(label: str) -> str:
    return snapshot(label)["manifest"]["manifestHash"]
