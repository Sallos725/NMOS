"""Smoke-test an unpacked NMOS portable bundle. Run it with the bundle's own Python:

    <bundle>/python/bin/python3 tools/native/smoke.py <bundle>      (Windows: <bundle>\\python\\python.exe)

First start (initdb + migrations), health and the version it reports, pgvector and pg_trgm queries, a clean stop that also stops Postgres,
then a second start on the same data. Then the refusals: a second launcher on the same data while one runs, data
written by a newer NMOS (a migration this bundle does not ship), and the sidecar's port taken by another program.
Last, an update: the data of the version before (this bundle without its last migration) starts here and migrates.

The data lives in a per-user folder outside the bundle (Phase 37); this smoke points that folder at one of its own,
beside the bundle (the platform's LOCALAPPDATA, XDG_DATA_HOME or HOME). Its last check is the move from 0.3.0's
layout: data/ beside the launcher is adopted on the first start, a database in both places is refused, and on a second
drive, where the runner has one, the adoption copies and keeps the old folder.
"""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

WINDOWS = os.name == "nt"
PORT = os.environ.get("NMOS_SIDECAR_PORT", "8795")
REPO = Path(__file__).resolve().parents[2]
DATA = Path()  # the per-user data folder, set by use_user_base()


def use_user_base(bundle: Path, base: Path) -> Path:
    """Point the launcher's per-user folder below base (this process and the launchers it starts); its data folder."""
    sys.path.insert(0, str(bundle))
    import nmos_launcher

    base.mkdir(parents=True, exist_ok=True)
    key = "LOCALAPPDATA" if WINDOWS else "HOME" if sys.platform == "darwin" else "XDG_DATA_HOME"
    os.environ[key] = str(base)
    return nmos_launcher.user_data_dir(dict(os.environ))


def start(bundle: Path) -> tuple[subprocess.Popen, float]:
    env = dict(os.environ, NMOS_SIDECAR_PORT=PORT)
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}
    t0 = time.monotonic()
    proc = subprocess.Popen([sys.executable, str(bundle / "nmos_launcher.py")], cwd=bundle, env=env, **kw)
    deadline = t0 + 180
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"launcher exited with {proc.returncode} before the sidecar answered")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/v1/health", timeout=2) as r:
                health = json.load(r)
            if health.get("ok"):
                return proc, time.monotonic() - t0
        except OSError:
            pass
        time.sleep(0.25)
    proc.kill()
    raise SystemExit("sidecar did not answer /v1/health within 180 s")


def stop(proc: subprocess.Popen, bundle: Path) -> float:
    t0 = time.monotonic()
    if WINDOWS:
        proc.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        os.killpg(proc.pid, signal.SIGINT)
    proc.wait(timeout=60)
    if pg_running(bundle):
        raise SystemExit("Postgres is still running after the launcher stopped")
    return time.monotonic() - t0


def pg_running(bundle: Path, data: Path | None = None) -> bool:
    pgsql, data = bundle / "pgsql", data or DATA
    if WINDOWS:  # pg_ctl reads its arguments through the ANSI code page, as the launcher works around
        sys.path.insert(0, str(bundle))
        from nmos_launcher import ascii_path

        pgsql, data = ascii_path(pgsql), ascii_path(data)
    pg_ctl = pgsql / "bin" / ("pg_ctl.exe" if WINDOWS else "pg_ctl")
    return subprocess.run([str(pg_ctl), "-D", str(data / "pg"), "status"], stdout=subprocess.DEVNULL).returncode == 0


def refused(bundle: Path, expect: str) -> str:
    """Run the launcher to completion; it must fail with `expect` in its output (and leave no Postgres it started)."""
    env = dict(os.environ, NMOS_SIDECAR_PORT=PORT, PYTHONUTF8="1")
    r = subprocess.run([sys.executable, str(bundle / "nmos_launcher.py")], cwd=bundle, env=env, timeout=180,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout + r.stderr
    if r.returncode == 0 or expect not in out:
        raise SystemExit(f"expected a refusal with {expect!r}, got exit {r.returncode}:\n{out[-3000:]}")
    return next(line for line in out.splitlines() if expect in line).strip()


def connect(bundle: Path, data: Path | None = None, port: str | None = None):
    import psycopg

    pw = ((data or DATA) / "db-password").read_text(encoding="utf-8").strip()
    return psycopg.connect(f"postgresql://nmos:{pw}@127.0.0.1:{port or os.environ.get('NMOS_DB_PORT', '54390')}/nmos")


def check_owner_only_acl(data: Path) -> str:
    """Windows: nobody but this user and SYSTEM may read the database or its password (launcher, Q5 review)."""
    acl = "".join(subprocess.run(["icacls", str(data / name)], capture_output=True, text=True).stdout
                  for name in ("db-password", "launcher.lock"))
    # Administrators can take any file anyway; the point is every other signed-in user.
    broad = [g for g in ("BUILTIN\\Users", "Authenticated Users", "Everyone", "INTERACTIVE") if g in acl]
    if broad:  # inherited entries are fine: they come from data/, which the launcher limits to the owner
        raise SystemExit(f"db-password is readable beyond its owner ({broad}):\n{acl}")
    return " ".join(acl.split())


def stop_while_starting(bundle: Path) -> dict:
    """A stop that comes while a first start is still creating the database leaves nothing running: PostgreSQL is
    not started after the stop, and no sidecar or worker is left behind."""
    import tempfile
    import threading

    sys.path.insert(0, str(bundle))
    import nmos_launcher

    data = Path(tempfile.mkdtemp(prefix="nmos-race-", dir=bundle))
    os.environ.update(NMOS_DATA_DIR=str(data), NMOS_SIDECAR_PORT="8797", NMOS_DB_PORT="54397")
    services = nmos_launcher.Services()
    outcome: dict = {}

    def run() -> None:
        try:
            services.start()
            outcome["start"] = "finished"
        except SystemExit as e:
            outcome["start"] = str(e.code)

    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.3)  # inside initdb
    services.stop()
    t.join(timeout=120)
    pgsql, pgdata = bundle / "pgsql", data / "pg"
    if WINDOWS:
        pgsql, pgdata = nmos_launcher.ascii_path(pgsql), nmos_launcher.ascii_path(data) / "pg"
    running = subprocess.run([str(pgsql / "bin" / ("pg_ctl.exe" if WINDOWS else "pg_ctl")), "-D", str(pgdata), "status"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if running or any(p.poll() is None for p in services.procs) or t.is_alive():
        raise SystemExit(f"something is left running after a stop during start: {outcome}, postgres={running}")
    for key in ("NMOS_DATA_DIR", "NMOS_SIDECAR_PORT", "NMOS_DB_PORT"):
        os.environ.pop(key)
    return outcome


def update_keeps_data(bundle: Path) -> dict:
    """Q3's update: data written by the version before, moved into this one, starts and migrates with nothing lost.
    The version before is this bundle without its last migration (a release adds migrations; the code that applies
    them is this bundle's either way)."""
    import tempfile

    sys.path.insert(0, str(bundle))
    import nmos_launcher

    data = Path(tempfile.mkdtemp(prefix="nmos-update-", dir=bundle))
    os.environ.update(NMOS_DATA_DIR=str(data), NMOS_SIDECAR_PORT="8798")
    last = max((bundle / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    held_back = last.with_name(last.name + ".next")

    def start_and_stop(write_marker: bool, db_port: str) -> set[str]:
        os.environ["NMOS_DB_PORT"] = db_port
        services = nmos_launcher.Services()
        services.start()  # returns once the migrations are applied and the sidecar and worker are spawned
        try:
            with connect(bundle, data, db_port) as conn:
                if write_marker:
                    conn.execute("CREATE TABLE smoke_update_marker (note text)")
                    conn.execute("INSERT INTO smoke_update_marker VALUES ('written before the update')")
                elif conn.execute("SELECT note FROM smoke_update_marker").fetchone() != ("written before the update",):
                    raise SystemExit("the data written before the update is gone after it")
                return {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        finally:
            services.stop()
            if pg_running(bundle, data):
                raise SystemExit("Postgres is still running after the update check's stop")

    try:
        last.rename(held_back)
        try:
            before = start_and_stop(write_marker=True, db_port="54398")
        finally:
            held_back.rename(last)
        # On another database port, as after the port-in-use message: NMOS_DB_PORT holds for data made on the old one.
        after = start_and_stop(write_marker=False, db_port="54399")
    finally:
        for key in ("NMOS_DATA_DIR", "NMOS_SIDECAR_PORT", "NMOS_DB_PORT"):
            os.environ.pop(key, None)  # NMOS_DB_PORT is unset if the first start never came
    if last.name in before or after - before != {last.name}:
        raise SystemExit(f"the update did not apply exactly {last.name}: {sorted(after - before)}")
    return {"migrated": last.name, "migrations": len(after)}


def adoption(bundle: Path) -> dict:
    """Phase 37, Q3–Q5: data/ beside the launcher as 0.3.0 kept it (written here with a relative NMOS_DATA_DIR=data,
    the version before being this bundle without its last migration) is moved to the per-user folder on the first
    start and migrated with what it held; a database in both places stops the start with neither changed; on another
    drive (Linux /dev/shm, Windows D:), the adoption copies, checks the copy and keeps the old folder."""
    import shutil

    import nmos_launcher

    os.environ.update(NMOS_SIDECAR_PORT="8796", NMOS_DB_PORT="54396")
    last = max((bundle / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    held_back = last.with_name(last.name + ".next")
    old = bundle / "data"
    result: dict = {}

    def write_old_data(note: str) -> None:
        os.environ["NMOS_DATA_DIR"] = "data"  # Q5: relative to the bundle, today's layout on purpose
        last.rename(held_back)
        try:
            services = nmos_launcher.Services()
            services.start()
            try:
                with connect(bundle, old, "54396") as conn:
                    conn.execute("CREATE TABLE smoke_adoption_marker (note text)")
                    conn.execute("INSERT INTO smoke_adoption_marker VALUES (%s)", (note,))
            finally:
                services.stop()
        finally:
            held_back.rename(last)
            del os.environ["NMOS_DATA_DIR"]
        if not (old / "pg" / "PG_VERSION").is_file():
            raise SystemExit(f"NMOS_DATA_DIR=data did not put the database beside the launcher: {old}")

    def start_adopting(data: Path, note: str) -> set[str]:
        services = nmos_launcher.Services()
        if services.data != data or not services.per_user:
            raise SystemExit(f"the start did not use the per-user folder {data}: {services.data}")
        services.start()
        try:
            with connect(bundle, data, "54396") as conn:
                if conn.execute("SELECT note FROM smoke_adoption_marker").fetchone() != (note,):
                    raise SystemExit("the data written beside the launcher is not in the per-user folder")
                return {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        finally:
            services.stop()
            if pg_running(bundle, data):
                raise SystemExit("Postgres is still running after the adoption check's stop")

    try:
        data = use_user_base(bundle, bundle.parent / "옮긴 데이터")
        write_old_data("beside the launcher, before the update")
        applied = start_adopting(data, "beside the launcher, before the update")
        moved = bundle / "data.moved"
        if last.name not in applied or old.exists() or not (moved / "MOVED.txt").is_file() or (moved / "pg").exists():
            raise SystemExit(f"the adoption by a rename left {sorted(p.name for p in bundle.iterdir())}")
        result["renamed"] = {"to": str(data), "migrated": last.name}

        write_old_data("a second database beside the launcher")  # Q4: now both places hold one
        before = nmos_launcher.tree_digest(old / "pg"), nmos_launcher.tree_digest(data / "pg")
        result["refused_both"] = refused(bundle, "two places")
        if (nmos_launcher.tree_digest(old / "pg"), nmos_launcher.tree_digest(data / "pg")) != before:
            raise SystemExit("the refusal of two databases changed one of them")

        other = Path("D:/") if WINDOWS else Path("/dev/shm") if sys.platform.startswith("linux") else None
        if other is None or not other.is_dir() or other.stat().st_dev == bundle.stat().st_dev:
            result["copied"] = "no second drive on this runner"
        else:
            far = other / "nmos-adoption"
            try:
                data = use_user_base(bundle, far)
                start_adopting(data, "a second database beside the launcher")
                kept = bundle / "data.moved-2"
                if old.exists() or nmos_launcher.tree_digest(kept / "pg") != before[0] or \
                        "copy" not in (kept / "MOVED.txt").read_text(encoding="utf-8"):
                    raise SystemExit(f"the adoption by a copy did not keep the old folder: {kept}")
                result["copied"] = {"to": str(data), "kept": str(kept)}
            finally:
                shutil.rmtree(far, ignore_errors=True)
    finally:
        for key in ("NMOS_DATA_DIR", "NMOS_SIDECAR_PORT", "NMOS_DB_PORT"):
            os.environ.pop(key, None)
    return result


def check_version() -> str:
    """The sidecar reports the version apps/sidecar/pyproject.toml declares (v0.3.0's bundles all said 0.0.0)."""
    want = re.search(r'^version\s*=\s*"([^"]+)"', (REPO / "apps" / "sidecar" / "pyproject.toml").read_text(encoding="utf-8"),
                     re.M).group(1)
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/v1/health", timeout=10) as r:
        got = json.load(r).get("version")
    if got != want:
        raise SystemExit(f"the sidecar reports version {got!r}, not {want!r}")
    return got


def check_dashboard() -> str:
    """/dashboard (the tray's and the menu bar's) reaches the Inspector's first page with the version on it."""
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/dashboard", timeout=10) as r:
        page = r.read().decode("utf-8")
        final = r.geturl()
    if "/inspector" not in final or "버전" not in page:
        raise SystemExit(f"/dashboard did not reach the Inspector with its version: {final}")
    return final


def check_sql(bundle: Path) -> dict:
    with connect(bundle) as conn:
        ext = dict(conn.execute("SELECT extname, extversion FROM pg_extension").fetchall())
        dist = conn.execute("SELECT '[1,2,3]'::vector <=> '[1,2,4]'::vector").fetchone()[0]
        sim = conn.execute("SELECT similarity('하나와 카이토', '하나랑 카이토')").fetchone()[0]
        migrations = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
    assert "vector" in ext and "pg_trgm" in ext, ext
    assert 0 < dist < 0.1 and 0 < sim < 1, (dist, sim)
    return {"extensions": ext, "cosine": round(dist, 5), "trgm_similarity": round(sim, 3), "migrations": migrations}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    bundle = Path(sys.argv[1]).resolve()
    global DATA
    DATA = use_user_base(bundle, bundle.parent / "사용자 데이터")  # Korean, with a space: as a user folder can be
    result: dict = {"bundle": str(bundle), "platform": sys.platform, "data": str(DATA)}
    proc, result["first_start_s"] = start(bundle)
    try:
        if not (DATA / "pg" / "PG_VERSION").is_file() or (bundle / "data").exists():
            raise SystemExit(f"the first start did not make its database in {DATA} alone")
        result["sql"] = check_sql(bundle)
        result["version"] = check_version()
        result["dashboard"] = check_dashboard()
        if WINDOWS:
            result["data_acl"] = check_owner_only_acl(DATA)
        result["refused_second_launcher"] = refused(bundle, "already running")
    finally:
        result["stop_s"] = stop(proc, bundle)
    proc, result["second_start_s"] = start(bundle)
    try:
        with connect(bundle) as conn:  # as if a newer NMOS had migrated this data
            conn.execute("INSERT INTO schema_migrations (version, checksum) VALUES ('9999_from_a_newer_nmos.sql', '-')")
    finally:
        stop(proc, bundle)
    result["refused_newer_data"] = refused(bundle, "newer NMOS")
    if pg_running(bundle):
        raise SystemExit("Postgres is still running after the newer-data refusal")
    with socket.socket() as taken:  # another program on the sidecar's port
        if not WINDOWS:  # the last sidecar's connections may still be in TIME_WAIT
            taken.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        taken.bind(("127.0.0.1", int(PORT)))
        taken.listen()
        result["refused_port"] = refused(bundle, f"Port {PORT}")
    result["stop_while_starting"] = stop_while_starting(bundle)
    result["update_keeps_data"] = update_keeps_data(bundle)
    result["adoption"] = adoption(bundle)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
