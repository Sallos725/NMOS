"""Release consistency check (#14): the tag, package versions, changelog, status and migration list agree,
and the docs' counts and "latest" pointers follow the lists they summarize (audit A-07).

    python tools/check_release.py v0.1.0-beta.4

`drift()` alone also runs in CI on every change (`apps/sidecar/tests/test_docs_consistency.py`).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(tag: str) -> list[str]:
    version = tag.removeprefix("v")
    pep440 = re.sub(r"-beta\.(\d+)$", r"b\1", re.sub(r"-rc\.(\d+)$", r"rc\1", version))
    errors = []
    plugin = json.loads((ROOT / "adapters/pocketrisu-plugin/package.json").read_text())["version"]
    sidecar = re.search(r'^version = "([^"]+)"', (ROOT / "apps/sidecar/pyproject.toml").read_text(), re.M)
    if plugin != version:
        errors.append(f"plugin package.json is {plugin}, tag is {version}")
    if not sidecar or sidecar.group(1) != pep440:
        errors.append(f"sidecar pyproject is {sidecar.group(1) if sidecar else '?'}, expected {pep440}")
    changelog = (ROOT / "CHANGELOG.md").read_text()
    section = re.search(rf"^## {re.escape(version)}\n(.*?)(?=^## |\Z)", changelog, re.M | re.S)
    if not section or not section.group(1).strip():
        errors.append(f"CHANGELOG.md has no notes under '## {version}'")
    elif "Known limitations" not in section.group(1):
        errors.append(f"CHANGELOG.md '## {version}' does not list known limitations")
    status = (ROOT / "docs/STATUS.md").read_text()
    if f"v{version}" not in status:
        errors.append(f"docs/STATUS.md does not name v{version}")
    latest = max(p.name[:4] for p in (ROOT / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not re.search(rf"migrations/0001`?–`?{latest}", status):
        errors.append(f"docs/STATUS.md schema row does not end at migration {latest}")
    errors += drift()
    for doc in USER_DOCS:
        if found := re.search(r"\(unreleased|\(다음 릴리스", (ROOT / doc).read_text()):
            errors.append(f"{doc} still says '{found[0]}' for something this release ships")
    return errors


USER_DOCS = ("README.md", "docs/guide.ko.md")


def _highest(pattern: str, text: str) -> int:
    return max(int(n) for n in re.findall(pattern, text, re.M))


def drift(root: Path = ROOT) -> list[str]:
    """Ranges and "latest" pointers in the docs against the lists they stand for: host facts and
    decisions (ARCHITECTURE), known issues, ADR files and phase specs."""
    def read(path: str) -> str:
        return (root / path).read_text()

    status, readme, agents = read("docs/STATUS.md"), read("README.md"), read("AGENTS.md")
    highest = {"H": _highest(r"^\| H(\d+) \|", read("ARCHITECTURE.md")),
               "D": _highest(r"^\*\*D(\d+) —", read("ARCHITECTURE.md")),
               "K": _highest(r"^\| K(\d+) \|", read("docs/KNOWN-ISSUES.md"))}
    adr = max(p.name[:4] for p in (root / "docs/adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
    phase = max(int(m[1]) for p in (root / "docs/phases").iterdir() if (m := re.fullmatch(r"PHASE-(\d+)\.md", p.name)))
    errors = []
    for doc, text, letters in (("docs/STATUS.md", status, "HDK"), ("README.md", readme, "H")):
        for letter in letters:
            ranges = {int(n) for n in re.findall(rf"\b{letter}1–{letter}(\d+)\b", text)}
            if doc == "docs/STATUS.md" and not ranges:
                errors.append(f"{doc} names no {letter}1–{letter}{highest[letter]} range")
            for n in sorted(ranges - {highest[letter]}):
                errors.append(f"{doc} says {letter}1–{letter}{n}; the last is {letter}{highest[letter]}")
    wanted = [("docs/STATUS.md", status, f"adr/0001`–`{adr}"),
              ("docs/STATUS.md", status, f"PHASE-0.md`–`PHASE-{phase}.md"),
              ("AGENTS.md", agents, f"`PHASE-{phase}.md` is the latest")]
    errors += [f"{doc} does not say {text!r}" for doc, body, text in wanted if text not in body]
    return errors


if __name__ == "__main__":
    problems = check(sys.argv[1])
    for p in problems:
        print(f"release check: {p}")
    sys.exit(1 if problems else 0)
