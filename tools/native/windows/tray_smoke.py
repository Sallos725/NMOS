"""CI (Phase 23 step 3): an unpacked Windows bundle through NMOS.exe and its tray.

    tray_smoke.py <bundle>

NMOS.exe brings up the tray and the sidecar; start at login is turned on (this NMOS.exe in the user's Run key), off
and on again from the tray's own commands; the tray quits and PostgreSQL stops; the Run entry's command starts NMOS
again (as a sign-in would) and the tray quits once more; the entry is removed. The data is in the per-user folder
(Phase 37), %LOCALAPPDATA%\\NMOS.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
bundle = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(bundle))
import nmos_tray  # noqa: E402  (the bundle's own tray module: the same shortcut code the menu runs)
from nmos_launcher import ascii_path, user_data_dir  # noqa: E402

DATA = user_data_dir(dict(os.environ))

user32 = ctypes.WinDLL("user32")
user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
WM_CLOSE = 0x0010


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
            log = (DATA / "nmos.log").read_text(encoding="utf-8", errors="replace")[-4000:]
            raise SystemExit(f"{what} not within {seconds:.0f} s\n{log}")
        time.sleep(0.5)
    return round(time.monotonic() - t0, 1)


def window():
    return user32.FindWindowW(nmos_tray.CLASS_NAME, None)


def pg_stopped() -> bool:
    pgsql, data = ascii_path(bundle / "pgsql"), ascii_path(DATA)
    return subprocess.run([str(pgsql / "bin" / "pg_ctl.exe"), "-D", str(data / "pg"), "status"],
                          stdout=subprocess.DEVNULL).returncode != 0


def command(cmd: int) -> None:
    user32.PostMessageW(window(), nmos_tray.WM_COMMAND_POST, cmd, 0)


def quit_tray() -> float:
    user32.PostMessageW(window(), WM_CLOSE, 0, 0)
    return wait(lambda: not health() and pg_stopped() and not window(), 90, "the tray, the sidecar and PostgreSQL to stop")


nmos_tray.set_autostart(False)
result: dict = {}

result["exe_exit"] = subprocess.run([str(bundle / "NMOS.exe")], timeout=30).returncode
result["first_start_s"] = wait(lambda: health() and window(), 240, "the sidecar and the tray")
log = (DATA / "nmos.log").read_text(encoding="utf-8", errors="replace")
result["tray_icon_added"] = "tray icon added: True" in log
result["data_outside_bundle"] = (DATA / "pg" / "PG_VERSION").is_file() and not (bundle / "data").exists()

command(nmos_tray.CMD_AUTOSTART)
wait(lambda: nmos_tray.autostart_command() is not None, 30, "the Run entry")
result["autostart_command"] = nmos_tray.autostart_command()
result["autostart_points_here"] = nmos_tray.autostart_enabled()
command(nmos_tray.CMD_AUTOSTART)
wait(lambda: nmos_tray.autostart_command() is None, 30, "the Run entry to go")
command(nmos_tray.CMD_AUTOSTART)
wait(lambda: nmos_tray.autostart_command() is not None, 30, "the Run entry again")
result["quit_s"] = quit_tray()

# What Windows does with the Run entry at sign-in: start the command it holds.
target = nmos_tray.autostart_command().strip('"')
subprocess.Popen([target], cwd=str(Path(target).parent))
result["start_from_run_entry_s"] = wait(lambda: health() and window(), 120, "NMOS started from the Run entry")
result["second_quit_s"] = quit_tray()
nmos_tray.set_autostart(False)

print(json.dumps(result, ensure_ascii=False, indent=2))
if not (result["exe_exit"] == 0 and result["tray_icon_added"] and result["autostart_points_here"]
        and result["data_outside_bundle"]):
    raise SystemExit(1)
