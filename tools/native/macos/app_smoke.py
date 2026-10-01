"""CI (Phase 23 step 4): NMOS.app as a user installs and runs it, on a macOS runner.

    app_smoke.py <NMOS.app copied out of the .dmg>

The app goes to ~/Applications (as dragged from the .dmg), its signature is verified, it is opened, the sidecar
answers with its data in ~/Library/Application Support/NMOS and the app still verifies afterwards (nothing written
inside it); the login item is switched on and off through the app's own --login-item; the app quits through
AppleScript and the sidecar and PostgreSQL stop.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BUNDLE_ID = "io.github.sallos725.nmos"
SUPPORT = Path.home() / "Library" / "Application Support" / "NMOS"


def health() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8790/v1/health", timeout=2) as r:
            return json.load(r).get("ok") is True
    except OSError:
        return False


def wait(condition, seconds: float, what: str) -> float:
    t0 = time.monotonic()
    while not condition():
        if time.monotonic() - t0 > seconds:
            log = (SUPPORT / "nmos.log").read_text(errors="replace")[-4000:] if (SUPPORT / "nmos.log").exists() else ""
            raise SystemExit(f"{what} not within {seconds:.0f} s\n{log}")
        time.sleep(0.5)
    return round(time.monotonic() - t0, 1)


def verify(app: Path) -> bool:
    r = subprocess.run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)],
                       capture_output=True, text=True)
    print(r.stderr.strip())
    return r.returncode == 0


def app_running(app: Path) -> bool:
    ps = subprocess.run(["ps", "-ax", "-o", "command"], capture_output=True, text=True).stdout
    return str(app / "Contents" / "MacOS" / "NMOS") in ps


def pg_stopped(app: Path) -> bool:
    pg_ctl = app / "Contents" / "Resources" / "pgsql" / "bin" / "pg_ctl"
    return subprocess.run([str(pg_ctl), "-D", str(SUPPORT / "pg"), "status"], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode != 0


def login_item(app: Path, what: str) -> str:
    out = subprocess.run([str(app / "Contents" / "MacOS" / "NMOS"), "--login-item", what], capture_output=True,
                         text=True, timeout=30).stdout.strip()
    return out.splitlines()[-1] if out else ""


def main() -> int:
    copied = Path(sys.argv[1]).resolve()
    app = Path.home() / "Applications" / "NMOS.app"
    shutil.rmtree(app, ignore_errors=True)
    app.parent.mkdir(exist_ok=True)
    shutil.move(str(copied), str(app))
    shutil.rmtree(SUPPORT, ignore_errors=True)
    result: dict = {"verified_before": verify(app)}
    assess = subprocess.run(["spctl", "--assess", "--type", "execute", "-vv", str(app)], capture_output=True, text=True)
    result["gatekeeper (diagnostic)"] = (assess.stdout + assess.stderr).strip()

    subprocess.run(["open", str(app)], check=True)
    result["first_start_s"] = wait(lambda: health() and app_running(app), 240, "the sidecar and the app")
    result["data_in_support"] = (SUPPORT / "pg" / "PG_VERSION").is_file() and (SUPPORT / "db-password").is_file()
    result["plugin_copied"] = (SUPPORT / "plugin" / "nmos-pocketrisu.js").is_file()
    result["nothing_written_inside"] = not (app / "Contents" / "Resources" / "data").exists()
    result["verified_while_running"] = verify(app)

    result["login_item_on"] = login_item(app, "on")
    result["login_item_off"] = login_item(app, "off")

    subprocess.run(["osascript", "-e", f'tell application id "{BUNDLE_ID}" to quit'], check=True, timeout=90)
    result["quit_s"] = wait(lambda: not health() and pg_stopped(app) and not app_running(app), 90,
                            "the app, the sidecar and PostgreSQL to stop")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    ok = (result["verified_before"] and result["verified_while_running"] and result["data_in_support"]
          and result["plugin_copied"] and result["nothing_written_inside"]
          and result["login_item_on"] in ("enabled", "requiresApproval") and result["login_item_off"] == "notRegistered")
    shutil.rmtree(app, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
