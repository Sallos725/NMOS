"""The docs' counts and "latest" pointers follow the lists they summarize (audit A-07).

Runs `tools/check_release.py:drift` on every change, so a new host fact, decision, known issue, ADR or
phase spec that a summary line misses fails CI instead of surfacing at release time."""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("check_release", ROOT / "tools/check_release.py")
check_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_release)


def test_docs_follow_their_lists():
    assert check_release.drift() == []


def test_a_stale_range_or_pointer_is_reported(tmp_path):
    for path in ("ARCHITECTURE.md", "README.md", "AGENTS.md", "docs/STATUS.md", "docs/KNOWN-ISSUES.md"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / path, tmp_path / path)
    shutil.copytree(ROOT / "docs/adr", tmp_path / "docs/adr")
    shutil.copytree(ROOT / "docs/phases", tmp_path / "docs/phases")
    assert check_release.drift(tmp_path) == []
    (tmp_path / "docs/phases/PHASE-99.md").write_text("# Phase 99\n")
    readme = tmp_path / "README.md"
    readme.write_text(re.sub(r"H1–H\d+", "H1–H1", readme.read_text()))
    errors = check_release.drift(tmp_path)
    assert any(e.startswith("README.md says H1–H1;") for e in errors)
    assert any("PHASE-99.md` is the latest" in e for e in errors)
    assert any("PHASE-0.md`–`PHASE-99.md" in e for e in errors)
