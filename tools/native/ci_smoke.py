"""CI steps for a built bundle (Phase 23). Each unpacks the archive under <parent>/<folder> and runs one check:

    ci_smoke.py smoke  <archive> <parent> [<folder>]          smoke.py with the bundle's Python
    ci_smoke.py refuse <archive> <parent> <folder> <text>     the launcher stops with <text> in its output
    ci_smoke.py suite  <archive> <parent> [<folder>]          the sidecar test suite against the bundle's PostgreSQL
    ci_smoke.py tray   <archive> <parent> [<folder>]          Windows: NMOS.exe, the tray and start at login
    ci_smoke.py ask    <archive> <parent> [<folder>]          Windows: a per-user folder PostgreSQL cannot open asks
                                                              where the data goes (Phase 37 Q6; needs RUNNER_TEMP on
                                                              a drive without short names)
    ci_smoke.py app    <archive> <parent> [<folder>]          macOS: NMOS.app from the .dmg, its menu-bar item and login item

A macOS .dmg is mounted and its NMOS.app copied out; the bundle the smokes run is the app's Contents/Resources.

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
import tempfile
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
    if archive.suffix == ".dmg":
        mount = Path(tempfile.mkdtemp(prefix="nmos-dmg-"))
        subprocess.run(["hdiutil", "attach", "-quiet", "-nobrowse", "-readonly", "-mountpoint", str(mount),
                        str(archive)], check=True)
        try:
            shutil.copytree(mount / "NMOS.app", dest / "NMOS.app", symlinks=True)
        finally:
            subprocess.run(["hdiutil", "detach", "-quiet", str(mount)], check=False)
        return dest / "NMOS.app" / "Contents" / "Resources"
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
    """Start the bundle, then run apps/sidecar's pytest against its PostgreSQL as the test admin. Its data folder is
    its own (NMOS_DATA_DIR): the per-user one may hold another step's (the macOS app's, with its token in .env)."""
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}
    data = bundle.parent / "suite-data"
    launcher = subprocess.Popen([str(bundle_python(bundle)), str(bundle / "nmos_launcher.py")], cwd=bundle,
                                env=dict(os.environ, NMOS_SIDECAR_PORT="8795", NMOS_DATA_DIR=str(data)), **kw)
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
        pw = (data / "db-password").read_text(encoding="utf-8").strip()
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


def ask(bundle: Path) -> int:
    """Phase 37 Q6, through NMOS.bat's console question: LOCALAPPDATA under a Korean folder on a drive without short
    names (the runner's D:), so PostgreSQL could not open the per-user folder. Cancel starts nothing; a folder whose
    path PostgreSQL cannot open either is refused and asked again; the chosen folder is remembered and holds the
    database; the next start does not ask."""
    import ctypes

    root = Path(tempfile.mkdtemp(prefix="nmos-ask-", dir=os.environ["RUNNER_TEMP"]))
    local = root / "한글 사용자" / "AppData" / "Local"
    local.mkdir(parents=True)
    buf = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.kernel32.GetShortPathNameW(str(local), buf, len(buf)) and buf.value.isascii():
        print(f"{root.drive} has short names, so nothing would ask: {buf.value}")
        return 1
    base, pointer = local / "NMOS", local / "NMOS" / "data-location.txt"
    chosen, refused_too = root / "nmos-data", root / "한글 데이터"
    env = {k: v for k, v in os.environ.items() if k != "NMOS_DATA_DIR"}
    env.update(LOCALAPPDATA=str(local), NMOS_SIDECAR_PORT="8795", PYTHONUTF8="1")
    result: dict = {"per_user": str(base)}

    def launch(answers: str, name: str) -> tuple[subprocess.Popen, Path]:
        log = root / f"{name}.log"
        proc = subprocess.Popen([str(bundle_python(bundle)), str(bundle / "nmos_launcher.py")], cwd=bundle, env=env,
                                stdin=subprocess.PIPE, stdout=log.open("w", encoding="utf-8"),
                                stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        proc.stdin.write(answers.encode("utf-8"))
        proc.stdin.close()  # no more answers: a question asked again reads EOF and starts nothing
        return proc, log

    def started(proc: subprocess.Popen, log: Path) -> str:
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:8795/v1/health", timeout=2) as r:
                    if json.load(r).get("ok"):
                        break
            except OSError:
                pass
            if proc.poll() is not None:
                raise SystemExit(f"the launcher exited with {proc.returncode}:\n{log.read_text(encoding='utf-8')}")
            time.sleep(0.5)
        else:
            proc.kill()
            raise SystemExit("the sidecar did not answer within 240 s")
        proc.send_signal(signal.CTRL_BREAK_EVENT)
        proc.wait(timeout=60)
        return log.read_text(encoding="utf-8")

    try:
        proc, log = launch("q\n", "cancel")
        code = proc.wait(timeout=60)
        out = log.read_text(encoding="utf-8")
        if code == 0 or "no folder was chosen" not in out or pointer.exists() or chosen.exists():
            raise SystemExit(f"cancel did not stop the start with nothing made (exit {code}):\n{out}")
        result["cancel"] = "nothing started"

        out = started(*launch(f"{refused_too}\n{chosen}\n", "ask"))
        if "non-English characters too" not in out or refused_too.exists():
            raise SystemExit(f"a folder PostgreSQL cannot open either was not refused:\n{out}")
        if pointer.read_text(encoding="utf-8").strip() != str(chosen) or not (chosen / "pg" / "PG_VERSION").is_file():
            raise SystemExit(f"the chosen folder was not remembered or holds no database:\n{out}")
        result["asked"] = {"refused": str(refused_too), "chosen": str(chosen)}

        out = started(*launch("", "next"))  # no answer to give: it must not ask
        if "Choose another folder" in out:
            raise SystemExit(f"the next start asked again:\n{out}")
        result["next_start"] = "no question"
    except SystemExit as e:
        print(e.code)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


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
    if mode == "app":
        app_smoke = Path(__file__).parent / "macos" / "app_smoke.py"
        return subprocess.run([sys.executable, str(app_smoke), str(bundle.parent.parent)]).returncode
    if mode == "ask":
        return ask(bundle)
    if mode == "tray":
        tray_smoke = Path(__file__).parent / "windows" / "tray_smoke.py"
        return subprocess.run([str(bundle_python(bundle)), str(tray_smoke), str(bundle)]).returncode
    raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    sys.exit(main())
