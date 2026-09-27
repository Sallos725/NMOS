"""Which plugin build talks to this sidecar (ADR 0037, K19).

The plugin file carries a build id (`nmos-build:<12 hex>`, a hash of the file set by the plugin's build script)
and sends it with every sync. The sidecar ships the plugin file of its own commit (the image copies it; a
checkout reads it from the repository), so it can say whether the plugin in use is the matching one. What was
seen is kept in memory: after a restart the next generation shows it again.
"""

from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

BUILD = re.compile(r"nmos-build:([0-9a-f]{12})")
RECENT = 5  # builds remembered, newest first
FILENAME = "nmos-pocketrisu.js"


def plugin_file() -> Path | None:
    """The plugin file this sidecar ships: NMOS_PLUGIN_FILE, else the repository's dist."""
    env = os.environ.get("NMOS_PLUGIN_FILE")
    path = Path(env) if env else Path(__file__).resolve().parents[4] / "adapters" / "pocketrisu-plugin" / "dist" / FILENAME
    return path if path.is_file() else None


@lru_cache(maxsize=1)
def expected() -> str | None:
    """The build id of the plugin file this sidecar ships, or None when it has none."""
    path = plugin_file()
    if path is None:
        return None
    found = BUILD.search(path.read_text(encoding="utf-8", errors="replace"))
    return found.group(1) if found else None


class Seen:
    """The plugin builds that synced lately, newest first; None is a plugin too old to send one."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._builds: dict[str | None, datetime] = {}

    def saw(self, build: str | None) -> None:
        build = build if build and BUILD.fullmatch(f"nmos-build:{build}") else None
        with self._lock:
            self._builds.pop(build, None)
            self._builds[build] = datetime.now(timezone.utc)
            while len(self._builds) > RECENT:
                self._builds.pop(next(iter(self._builds)))

    def recent(self) -> list[dict[str, Any]]:
        want = expected()
        with self._lock:
            items = list(self._builds.items())
        return [{"build": b, "at": at.isoformat(), "matches": want is not None and b == want}
                for b, at in reversed(items)]
