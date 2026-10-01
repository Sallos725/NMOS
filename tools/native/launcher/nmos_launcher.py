"""NMOS portable launcher (spike): Postgres, migrations, sidecar and worker without Docker.

Runs under the bundle's own Python. Layout next to this file:

    python/   standalone CPython with the sidecar installed
    pgsql/    portable PostgreSQL 16 with pg_trgm and pgvector
    migrations/, plugin/nmos-pocketrisu.js
    data/     created on first start (database cluster, logs, generated DB password)
    .env      optional, same keys as the Docker install's .env
"""

from __future__ import annotations

import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WINDOWS = os.name == "nt"
EXE = ".exe" if WINDOWS else ""


def log(msg: str) -> None:
    print(f"[nmos] {msg}", flush=True)


def read_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


PGSQL = ROOT / "pgsql"  # on Windows, replaced by its ASCII short path in main()


def pg_bin(name: str) -> str:
    return str(PGSQL / "bin" / f"{name}{EXE}")


def ascii_path(path: Path) -> Path:
    """Windows: an all-ASCII spelling of an existing path (its 8.3 short form when it has other characters).

    PostgreSQL on Windows reads its own location and data directory through the ANSI code page, and initdb writes
    the installation path into UTF-8 SQL, so any non-ASCII character (a Korean user or folder name) breaks it.
    """
    if str(path).isascii():
        return path
    import ctypes

    buf = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf)) and buf.value.isascii():
        return Path(buf.value)
    raise SystemExit(
        f"NMOS cannot run its database under {path}: the path has non-English characters and this drive has no short "
        "(8.3) names. Move the NMOS folder to a path with only English letters and digits, such as C:\\NMOS, and "
        "start it again.\n"
        f"NMOS 데이터베이스는 한글 등 영문이 아닌 글자가 들어간 경로({path})에서 실행할 수 없습니다. "
        "NMOS 폴더를 C:\\NMOS처럼 영문과 숫자로만 된 경로로 옮긴 뒤 다시 실행해 주세요."
    )


def run(cmd: list[str], **kw) -> None:
    subprocess.run(cmd, check=True, **kw)


def init_cluster(pgdata: Path, password: str, port: int) -> None:
    pwfile = pgdata.parent / "pg-initpw.tmp"
    pwfile.write_text(password, encoding="utf-8")
    try:
        # A UTF-8 ctype is required: under the C locale pg_trgm treats Hangul as non-word characters and makes no
        # trigrams, so Korean lexical recall finds nothing. The names differ per OS; the Docker image uses en_US.utf8.
        default_locale = "en-US" if WINDOWS else "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"
        locale = os.environ.get("NMOS_PG_LOCALE", default_locale)
        run([pg_bin("initdb"), "-D", str(pgdata), "-U", "nmos", f"--pwfile={pwfile}", "--auth=scram-sha-256",
             "--encoding=UTF8", f"--locale={locale}", "--no-instructions"])
    finally:
        pwfile.unlink(missing_ok=True)
    with (pgdata / "postgresql.conf").open("a", encoding="utf-8") as f:
        f.write("\n# NMOS portable\n")
        f.write(f"port = {port}\n")
        f.write("listen_addresses = '127.0.0.1'\n")
        f.write("unix_socket_directories = ''\n")


_console_handler = None  # kept referenced so ctypes does not free the callback


def install_windows_stop_handlers(shutdown) -> None:
    """Ctrl+Break stops like Ctrl+C; closing the console window, logoff or shutdown stop Postgres first."""
    import ctypes

    signal.signal(signal.SIGBREAK, signal.default_int_handler)
    CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT = 2, 5, 6

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
    def handler(event: int) -> bool:
        if event in (CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT):
            shutdown()  # Windows allows about 5 s here; a fast Postgres stop takes well under that
            return True
        return False  # Ctrl+C / Ctrl+Break: let Python raise KeyboardInterrupt

    global _console_handler
    _console_handler = handler
    ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)


def main() -> int:
    # Paths can hold any script (Korean user folders); a legacy console code page must not crash a log line.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    os.environ["PYTHONUTF8"] = "1"
    env = dict(os.environ)
    for key, value in read_env_file(ROOT / ".env").items():
        env.setdefault(key, value)

    if sys.platform.startswith("linux"):
        # The bundle carries the libraries Postgres links (build_bundle.vendor_linux_libs), including indirect ones.
        pglib = str(ROOT / "pgsql" / "lib")
        os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(filter(None, [pglib, os.environ.get("LD_LIBRARY_PATH")]))
    data = Path(env.get("NMOS_DATA_DIR") or ROOT / "data")
    data.mkdir(parents=True, exist_ok=True)
    if WINDOWS:
        global PGSQL
        PGSQL, data = ascii_path(PGSQL), ascii_path(data)
    pgdata = data / "pg"
    pg_port = int(env.get("NMOS_PG_PORT", "54390"))
    sidecar_bind = env.get("NMOS_SIDECAR_BIND", "127.0.0.1")
    sidecar_port = env.get("NMOS_SIDECAR_PORT", "8790")

    pw_path = data / "db-password"
    if not (pgdata / "PG_VERSION").is_file():
        password = secrets.token_urlsafe(24)
        log(f"first start: creating the database in {pgdata}")
        t0 = time.monotonic()
        init_cluster(pgdata, password, pg_port)
        pw_path.write_text(password, encoding="utf-8")
        log(f"initdb took {time.monotonic() - t0:.1f} s")
    password = pw_path.read_text(encoding="utf-8").strip()

    t0 = time.monotonic()
    if subprocess.run([pg_bin("pg_ctl"), "-D", str(pgdata), "status"], stdout=subprocess.DEVNULL).returncode == 0:
        log("postgres from an earlier run is still up; using it")
    else:
        run([pg_bin("pg_ctl"), "-D", str(pgdata), "-l", str(data / "postgres.log"), "-w", "start"])
    log(f"postgres up on 127.0.0.1:{pg_port} ({time.monotonic() - t0:.1f} s)")

    procs: list[subprocess.Popen] = []
    stopped = False

    def shutdown(*_: object) -> None:
        nonlocal stopped
        if stopped:
            return
        stopped = True
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        subprocess.run([pg_bin("pg_ctl"), "-D", str(pgdata), "-m", "fast", "-w", "stop"])
        log("stopped")

    try:
        import psycopg

        admin_url = f"postgresql://nmos:{password}@127.0.0.1:{pg_port}/postgres"
        with psycopg.connect(admin_url, autocommit=True) as conn:
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname = 'nmos'").fetchone():
                conn.execute("CREATE DATABASE nmos")

        env.update({
            "NMOS_DATABASE_URL": f"postgresql://nmos:{password}@127.0.0.1:{pg_port}/nmos",
            "NMOS_MIGRATIONS_DIR": str(ROOT / "migrations"),
            "NMOS_PLUGIN_FILE": str(ROOT / "plugin" / "nmos-pocketrisu.js"),
        })
        env.setdefault("NMOS_CORS_ORIGINS", "http://localhost:6001,http://127.0.0.1:6001")
        py = sys.executable
        run([py, "-m", "nmos_sidecar.migrate"], env=env)
        procs.append(subprocess.Popen([py, "-m", "uvicorn", "nmos_sidecar.api:app_factory", "--factory",
                                       "--host", sidecar_bind, "--port", sidecar_port], env=env))
        procs.append(subprocess.Popen([py, "-m", "nmos_sidecar.worker"], env=env))
        log(f"sidecar on http://{sidecar_bind}:{sidecar_port} — set this URL in the PocketRisu plugin; Ctrl+C stops")

        if WINDOWS:
            install_windows_stop_handlers(shutdown)
        else:
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        log("a process exited; stopping")
        return 1
    except (KeyboardInterrupt, SystemExit):
        return 0
    finally:
        shutdown()


if __name__ == "__main__":
    sys.exit(main())
