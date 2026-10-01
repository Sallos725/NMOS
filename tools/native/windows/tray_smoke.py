"""CI (Phase 23 step 3): an unpacked Windows bundle through NMOS.exe and its tray.

    tray_smoke.py <bundle>

NMOS.exe brings up the tray and the sidecar; start at login is turned on (a Startup shortcut to this NMOS.exe), off
and on again from the tray's own commands; the tray quits and PostgreSQL stops; the Startup shortcut starts NMOS
again (as a sign-in would) and the tray quits once more; the shortcut is removed.
"""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
bundle = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(bundle))
import nmos_tray  # noqa: E402  (the bundle's own tray module: the same shortcut code the menu runs)
from nmos_launcher import ascii_path  # noqa: E402

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
            log = (bundle / "data" / "nmos.log").read_text(encoding="utf-8", errors="replace")[-4000:]
            raise SystemExit(f"{what} not within {seconds:.0f} s\n{log}")
        time.sleep(0.5)
    return round(time.monotonic() - t0, 1)


def window():
    return user32.FindWindowW(nmos_tray.CLASS_NAME, None)


def pg_stopped() -> bool:
    pgsql, data = ascii_path(bundle / "pgsql"), ascii_path(bundle / "data")
    return subprocess.run([str(pgsql / "bin" / "pg_ctl.exe"), "-D", str(data / "pg"), "status"],
                          stdout=subprocess.DEVNULL).returncode != 0


def command(cmd: int) -> None:
    user32.PostMessageW(window(), nmos_tray.WM_COMMAND_POST, cmd, 0)


def quit_tray() -> float:
    user32.PostMessageW(window(), WM_CLOSE, 0, 0)
    return wait(lambda: not health() and pg_stopped() and not window(), 90, "the tray, the sidecar and PostgreSQL to stop")


lnk = nmos_tray.startup_shortcut()
lnk.unlink(missing_ok=True)
result: dict = {"shortcut": str(lnk)}

result["exe_exit"] = subprocess.run([str(bundle / "NMOS.exe")], timeout=30).returncode
result["first_start_s"] = wait(lambda: health() and window(), 240, "the sidecar and the tray")
log = (bundle / "data" / "nmos.log").read_text(encoding="utf-8", errors="replace")
result["tray_icon_added"] = "tray icon added: True" in log

command(nmos_tray.CMD_AUTOSTART)
wait(lambda: lnk.exists(), 30, "the Startup shortcut")
result["autostart_points_here"] = nmos_tray.autostart_enabled()
command(nmos_tray.CMD_AUTOSTART)
wait(lambda: not lnk.exists(), 30, "the Startup shortcut to go")
command(nmos_tray.CMD_AUTOSTART)
wait(lambda: lnk.exists(), 30, "the Startup shortcut again")
result["quit_s"] = quit_tray()

# What Windows does with it at sign-in: start its target in its working directory. (os.startfile cannot open a .lnk
# on the CI runner, a service session without the shell's associations; a desktop session can.)
def shortcut(field: str) -> str:
    return nmos_tray.powershell(f"(New-Object -ComObject WScript.Shell).CreateShortcut({nmos_tray.ps_quote(lnk)}).{field}")


target, workdir = shortcut("TargetPath"), shortcut("WorkingDirectory")
result["shortcut_target"], result["shortcut_workdir"] = target, workdir
# NMOS.exe finds its folder from its own path, so an empty working directory would not stop it.
subprocess.Popen([target], cwd=workdir or str(Path(target).parent))
result["start_from_shortcut_s"] = wait(lambda: health() and window(), 120, "NMOS started from the Startup shortcut")
result["second_quit_s"] = quit_tray()
lnk.unlink(missing_ok=True)

print(json.dumps(result, ensure_ascii=False, indent=2))
if not (result["exe_exit"] == 0 and result["autostart_points_here"]):
    raise SystemExit(1)
