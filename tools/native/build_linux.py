"""Build a Linux bundle inside the pinned build image (sources.json linux_build.image), so the libraries it carries
come from pinned Ubuntu packages and not from whatever the host has. Needs Docker and uv on the host.

    python tools/native/build_linux.py --target linux-x64 --version 0.3.0

The image runs on the host's architecture: build linux-x64 on x86-64 and linux-arm64 on arm64.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES = json.loads((Path(__file__).parent / "sources.json").read_text(encoding="utf-8"))

# Toolchain and the libraries the bundle carries; their versions are checked by build_bundle --check-packages.
APT = "gcc libc6-dev make git ca-certificates libxml2"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["linux-x64", "linux-arm64"], required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", type=Path, default=REPO / "dist-native")
    ap.add_argument("--cache", type=Path, default=REPO / ".native-cache")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    a.cache.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("uv is not on PATH")
    script = (
        f"trap 'chown -R {os.getuid()}:{os.getgid()} /out /cache' EXIT; "
        "set -e; export DEBIAN_FRONTEND=noninteractive; "
        f"apt-get update -qq && apt-get install -y -qq --no-install-recommends {APT} >/dev/null; "
        f"uv run -q --no-project --python 3.12 python /repo/tools/native/build_bundle.py --target {a.target} "
        f"--version {a.version} --out /out --cache /cache --check-packages"
    )
    subprocess.run(["docker", "run", "--rm",
                    "-v", f"{REPO}:/repo:ro", "-v", f"{a.out.resolve()}:/out", "-v", f"{a.cache.resolve()}:/cache",
                    "-v", f"{Path(uv).resolve()}:/usr/local/bin/uv:ro", "-e", "UV_CACHE_DIR=/cache/uv",
                    SOURCES["linux_build"]["image"], "bash", "-c", script], check=True)


if __name__ == "__main__":
    main()
