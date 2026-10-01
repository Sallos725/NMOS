"""CI steps for a built bundle (Phase 23). Each unpacks the archive under <parent>/<folder> and runs one check:

    ci_smoke.py smoke  <archive> <parent> [<folder>]          smoke.py with the bundle's Python
    ci_smoke.py refuse <archive> <parent> <folder> <text>     the launcher stops with <text> in its output
    ci_smoke.py suite  <archive> <parent> [<folder>]          the sidecar test suite against the bundle's PostgreSQL
    ci_smoke.py tray   <archive> <parent> [<folder>]          Windows: NMOS.exe, the tray and start at login

The default folder is "한글 폴더": a Korean name with a space, as a Windows user folder can be.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WINDOWS = os.name == "nt"


def unpack(archive: Path, parent: Path, folder: str) -> Path:
    dest = parent / folder
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    else:
        with tarfile.open(archive) as t:
            t.extractall(dest, filter="tar")
    (bundle,) = list(dest.iterdir())
    return bundle


def bundle_python(bundle: Path) -> Path:
    return bundle / ("python/python.exe" if WINDOWS else "python/bin/python3")


def smoke(bundle: Path) -> int:
    return subprocess.run([str(bundle_python(bundle)), str(Path(__file__).with_name("smoke.py")), str(bundle)]).returncode


def refuse(bundle: Path, text: str) -> int:
    r = subprocess.run([str(bundle_python(bundle)), str(bundle / "nmos_launcher.py")], cwd=bundle, timeout=180,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, PYTHONUTF8="1"))
    out = r.stdout + r.stderr
    print(out[-2000:])
    ok = r.returncode != 0 and text in out
    print(f"refused with {text!r}: {ok}")
    return 0 if ok else 1


def suite(bundle: Path) -> int:
    """Start the bundle, then run apps/sidecar's pytest against its PostgreSQL as the test admin."""
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}
    launcher = subprocess.Popen([str(bundle_python(bundle)), str(bundle / "nmos_launcher.py")], cwd=bundle,
                                env=dict(os.environ, NMOS_SIDECAR_PORT="8795"), **kw)
    try:
        deadline = time.monotonic() + 240
        while True:
            try:
                with urllib.request.urlopen("http://127.0.0.1:8795/v1/health", timeout=2) as r:
                    if json.load(r).get("ok"):
                        break
            except OSError:
                pass
            if launcher.poll() is not None or time.monotonic() > deadline:
                print("the bundle did not start")
                return 1
            time.sleep(0.5)
        pw = (bundle / "data" / "db-password").read_text(encoding="utf-8").strip()
        # UTF-8 mode, as the launcher runs the sidecar: on Windows the tests read the repository's docs and fixtures,
        # which a cp1252 default cannot decode.
        env = dict(os.environ, NMOS_TEST_ADMIN_URL=f"postgresql://nmos:{pw}@127.0.0.1:54390/postgres", PYTHONUTF8="1")
        return subprocess.run(["uv", "run", "pytest", "-q"], cwd=REPO / "apps" / "sidecar", env=env).returncode
    finally:
        if WINDOWS:
            launcher.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(launcher.pid, signal.SIGINT)
        launcher.wait(timeout=60)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    mode, archive, parent = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    folder = sys.argv[4] if len(sys.argv) > 4 else "한글 폴더"
    bundle = unpack(archive, parent, folder)
    if mode == "smoke":
        return smoke(bundle)
    if mode == "refuse":
        return refuse(bundle, sys.argv[5])
    if mode == "suite":
        return suite(bundle)
    if mode == "tray":
        smoke = Path(__file__).parent / "windows" / "tray_smoke.py"
        return subprocess.run([str(bundle_python(bundle)), str(smoke), str(bundle)]).returncode
    raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    sys.exit(main())
