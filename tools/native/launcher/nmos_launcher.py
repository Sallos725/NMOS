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
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WINDOWS = os.name == "nt"
EXE = ".exe" if WINDOWS else ""


LOG = sys.stdout  # the tray points this at data/nmos.log


def log(msg: str) -> None:
    print(f"[nmos] {time.strftime('%Y-%m-%d %H:%M:%S')} {msg}", file=LOG, flush=True)


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


# Child processes: inherit the console, or (tray) write to the log file with no console window of their own.
CHILD_KW: dict = {}
CHILD_KW_NO_OUTPUT: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


def run(cmd: list[str], **kw) -> None:
    subprocess.run(cmd, check=True, **CHILD_KW, **kw)


def write_private(path: Path, text: str) -> None:
    """Write a file only this user can read (the database password; other local users must not see it)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)


class AlreadyRunning(SystemExit):
    pass


def lock_data_dir(data: Path):
    """Hold an exclusive lock on data/launcher.lock for this process's lifetime; a second launcher on the same data
    would otherwise adopt the first one's Postgres and stop it on its way out."""
    f = open(data / "launcher.lock", "a+")
    try:
        if WINDOWS:
            import msvcrt

            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise AlreadyRunning(f"NMOS is already running on {data} (another start.sh, NMOS.bat or NMOS.exe).\n"
                             f"NMOS가 이미 이 데이터 폴더({data})로 실행 중이에요.") from None
    return f


def init_cluster(pgdata: Path, password: str, port: int) -> None:
    pwfile = pgdata.parent / "pg-initpw.tmp"
    write_private(pwfile, password)
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


class Services:
    """Postgres, migrations, the sidecar and the worker of this bundle: start(), alive(), stop()."""

    def __init__(self) -> None:
        os.environ["PYTHONUTF8"] = "1"
        self.env = dict(os.environ)
        for key, value in read_env_file(ROOT / ".env").items():
            self.env.setdefault(key, value)
        if sys.platform.startswith("linux"):
            # The bundle carries the libraries Postgres links (build_bundle.vendor_linux_libs), indirect ones too.
            pglib = str(ROOT / "pgsql" / "lib")
            os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(filter(None, [pglib, os.environ.get("LD_LIBRARY_PATH")]))
        self.data = Path(self.env.get("NMOS_DATA_DIR") or ROOT / "data")
        self.data.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.pg_port = int(self.env.get("NMOS_PG_PORT", "54390"))
        self.bind = self.env.get("NMOS_SIDECAR_BIND", "127.0.0.1")
        self.port = self.env.get("NMOS_SIDECAR_PORT", "8790")
        self.url = f"http://{self.bind}:{self.port}"
        self.procs: list[subprocess.Popen] = []
        self.pgdata: Path | None = None
        self.stopped = False
        self.lock = threading.Lock()  # start() spawning and stop() never interleave (quit while starting)
        self._data_lock = None

    def start(self) -> None:
        data = self.data
        self._data_lock = lock_data_dir(data)  # before anything that stop() would undo
        if WINDOWS:
            global PGSQL
            PGSQL, data = ascii_path(PGSQL), ascii_path(data)
        self.pgdata = pgdata = data / "pg"
        pw_path = data / "db-password"
        if not (pgdata / "PG_VERSION").is_file():
            log(f"first start: creating the database in {pgdata}")
            t0 = time.monotonic()
            password = secrets.token_urlsafe(24)
            init_cluster(pgdata, password, self.pg_port)
            write_private(pw_path, password)
            log(f"initdb took {time.monotonic() - t0:.1f} s")
        if not pw_path.is_file():
            raise SystemExit(f"{pw_path} is missing; the database password cannot be recovered")
        password = pw_path.read_text(encoding="utf-8").strip()

        t0 = time.monotonic()
        status = subprocess.run([pg_bin("pg_ctl"), "-D", str(pgdata), "status"], **{**CHILD_KW, "stdout": subprocess.DEVNULL})
        if status.returncode == 0:
            log("postgres from an earlier run is still up; using it")
        else:
            run([pg_bin("pg_ctl"), "-D", str(pgdata), "-l", str(data / "postgres.log"), "-w", "start"])
        log(f"postgres up on 127.0.0.1:{self.pg_port} ({time.monotonic() - t0:.1f} s)")

        import psycopg

        with psycopg.connect(f"postgresql://nmos:{password}@127.0.0.1:{self.pg_port}/postgres", autocommit=True) as c:
            if not c.execute("SELECT 1 FROM pg_database WHERE datname = 'nmos'").fetchone():
                c.execute("CREATE DATABASE nmos")
        env = dict(self.env)
        env.update({
            "NMOS_DATABASE_URL": f"postgresql://nmos:{password}@127.0.0.1:{self.pg_port}/nmos",
            "NMOS_MIGRATIONS_DIR": str(ROOT / "migrations"),
            "NMOS_PLUGIN_FILE": str(ROOT / "plugin" / "nmos-pocketrisu.js"),
        })
        env.setdefault("NMOS_CORS_ORIGINS", "http://localhost:6001,http://127.0.0.1:6001")
        py = sys.executable
        run([py, "-m", "nmos_sidecar.migrate"], env=env)
        with self.lock:
            if self.stopped:
                raise SystemExit("stopped while starting")
            self.procs.append(subprocess.Popen([py, "-m", "uvicorn", "nmos_sidecar.api:app_factory", "--factory",
                                                "--host", self.bind, "--port", self.port], env=env, **CHILD_KW))
            self.procs.append(subprocess.Popen([py, "-m", "nmos_sidecar.worker"], env=env, **CHILD_KW))
        log(f"sidecar on {self.url} — set this URL in the PocketRisu plugin")

    def alive(self) -> bool:
        return bool(self.procs) and all(p.poll() is None for p in self.procs)

    def stop(self) -> None:
        with self.lock:
            if self.stopped:
                return
            self.stopped = True
        if self._data_lock is None:
            return  # never started, or another launcher holds this data: nothing here is ours to stop
        for p in self.procs:
            if p.poll() is None:
                p.terminate()
        for p in self.procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        if self.pgdata is not None:
            subprocess.run([pg_bin("pg_ctl"), "-D", str(self.pgdata), "-m", "fast", "-w", "stop"], **CHILD_KW)
        self._data_lock.close()
        log("stopped")


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
    """Console mode (start.sh, NMOS.bat): output in this terminal, Ctrl+C stops."""
    # Paths can hold any script (Korean user folders); a legacy console code page must not crash a log line.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    services = Services()
    try:
        services.start()
        log("Ctrl+C stops")
        if WINDOWS:
            install_windows_stop_handlers(services.stop)
        else:
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        while services.alive():
            time.sleep(1)
        log("a process exited; stopping")
        return 1
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit) and isinstance(e.code, str):
            log(e.code)
            return 1
        return 0
    finally:
        services.stop()


if __name__ == "__main__":
    sys.exit(main())
