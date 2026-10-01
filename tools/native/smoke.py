"""Smoke-test an unpacked NMOS portable bundle (spike). Run it with the bundle's own Python:

    <bundle>/python/bin/python3 tools/native/smoke.py <bundle>      (Windows: <bundle>\\python\\python.exe)

First start (initdb + migrations), health, pgvector and pg_trgm queries, a clean stop that also stops Postgres,
then a second start on the same data.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

WINDOWS = os.name == "nt"
PORT = os.environ.get("NMOS_SIDECAR_PORT", "8795")


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
    pgsql, data = bundle / "pgsql", bundle / "data"
    if WINDOWS:  # pg_ctl reads its arguments through the ANSI code page, as the launcher works around
        sys.path.insert(0, str(bundle))
        from nmos_launcher import ascii_path

        pgsql, data = ascii_path(pgsql), ascii_path(data)
    pg_ctl = pgsql / "bin" / ("pg_ctl.exe" if WINDOWS else "pg_ctl")
    status = subprocess.run([str(pg_ctl), "-D", str(data / "pg"), "status"], stdout=subprocess.DEVNULL)
    if status.returncode == 0:
        raise SystemExit("Postgres is still running after the launcher stopped")
    return time.monotonic() - t0


def check_sql(bundle: Path) -> dict:
    import psycopg

    pw = (bundle / "data" / "db-password").read_text(encoding="utf-8").strip()
    port = os.environ.get("NMOS_PG_PORT", "54390")
    with psycopg.connect(f"postgresql://nmos:{pw}@127.0.0.1:{port}/nmos") as conn:
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
    result: dict = {"bundle": str(bundle), "platform": sys.platform}
    proc, result["first_start_s"] = start(bundle)
    try:
        result["sql"] = check_sql(bundle)
    finally:
        result["stop_s"] = stop(proc, bundle)
    proc, result["second_start_s"] = start(bundle)
    stop(proc, bundle)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
