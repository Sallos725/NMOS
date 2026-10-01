"""CI (spike): start an unpacked Windows bundle through NMOS.exe, check the sidecar and the tray window, quit it
from the tray's window, and check that Postgres stopped.

    tray_smoke.py <bundle>
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


result: dict = {}
t0 = time.monotonic()
stub = subprocess.run([str(bundle / "NMOS.exe")], timeout=30)
result["exe_exit"] = stub.returncode
while not health():
    if time.monotonic() - t0 > 240:
        print((bundle / "data" / "nmos.log").read_text(encoding="utf-8", errors="replace")[-4000:])
        raise SystemExit("sidecar did not answer within 240 s")
    time.sleep(0.5)
result["first_start_s"] = round(time.monotonic() - t0, 1)
hwnd = user32.FindWindowW("NMOSTrayWindow", None)
result["tray_window"] = bool(hwnd)
log = (bundle / "data" / "nmos.log").read_text(encoding="utf-8", errors="replace")
result["tray_icon_added"] = "tray icon added: True" in log

t0 = time.monotonic()
user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
while health():
    if time.monotonic() - t0 > 60:
        raise SystemExit("sidecar still up 60 s after quitting the tray")
    time.sleep(0.5)
pgsql, data = ascii_path(bundle / "pgsql"), ascii_path(bundle / "data")
for _ in range(60):
    if subprocess.run([str(pgsql / "bin" / "pg_ctl.exe"), "-D", str(data / "pg"), "status"],
                      stdout=subprocess.DEVNULL).returncode != 0:
        break
    time.sleep(0.5)
else:
    raise SystemExit("Postgres still running after quitting the tray")
result["quit_s"] = round(time.monotonic() - t0, 1)
print(json.dumps(result, indent=2))
print((bundle / "data" / "nmos.log").read_text(encoding="utf-8", errors="replace")[-3000:])
if not (result["exe_exit"] == 0 and result["tray_window"]):
    raise SystemExit(1)
