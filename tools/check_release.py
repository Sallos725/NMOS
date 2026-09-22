"""Release consistency check (#14): the tag, package versions, changelog, status and migration list agree.

    python tools/check_release.py v0.1.0-beta.4
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
    return errors


if __name__ == "__main__":
    problems = check(sys.argv[1])
    for p in problems:
        print(f"release check: {p}")
    sys.exit(1 if problems else 0)
