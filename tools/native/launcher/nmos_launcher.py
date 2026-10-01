"""NMOS bundle launcher (Phase 23): Postgres, migrations, sidecar and worker without Docker.

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
import socket
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
CHILD_FLAGS: dict = {}  # process-creation flags for every child, captured ones too (the tray: CREATE_NO_WINDOW)


def run(cmd: list[str], **kw) -> None:
    subprocess.run(cmd, check=True, **{**CHILD_KW, **kw})  # a call's own stdout/stderr win over CHILD_KW's


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
    running = AlreadyRunning(f"NMOS is already running on {data} (another start.sh, NMOS.bat or NMOS.exe).\n"
                             f"NMOS가 이미 이 데이터 폴더({data})로 실행 중이에요.")
    try:
        f = open(data / "launcher.lock", "a+")
    except PermissionError as e:
        # Windows refuses even the open while the first launcher holds its byte lock (sharing or lock violation);
        # any other permission error is a real one and is shown as it is.
        if getattr(e, "winerror", None) in (32, 33):
            raise running from None
        raise
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
        raise running from None
    return f


def port_in_use(host: str, port: int) -> bool:
    """Whether binding host:port fails, which is what the server about to listen there would hit."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if not WINDOWS:  # as the servers do: a port in TIME_WAIT is free, one with a listener is not
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            return True
    return False


def require_free_port(host: str, port: int, what: str, key: str) -> None:
    """Q10: a fixed port in use stops the start with its name; a changed port would break the plugin's URL."""
    if port_in_use(host, port):
        raise SystemExit(
            f"Port {port} ({what}) is already in use by another program. Close it, or set {key} in .env next to "
            f"NMOS to a free port.\n"
            f"포트 {port}({what})를 다른 프로그램이 이미 쓰고 있어요. 그 프로그램을 닫거나, NMOS 폴더의 .env에서 "
            f"{key}를 비어 있는 포트로 바꿔 주세요.")


def newer_migrations(conn) -> list[str]:
    """Q3: migrations this database has that this bundle does not ship, i.e. data written by a newer NMOS."""
    if conn.execute("SELECT to_regclass('schema_migrations') IS NULL").fetchone()[0]:
        return []
    shipped = {p.name for p in (ROOT / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")}
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    return sorted(applied - shipped)


def restrict_to_this_user(data: Path) -> None:
    """Windows: the data folder (the database and its password) readable by this user and SYSTEM only. A folder made
    under C:\\ inherits access for every signed-in user, and a POSIX mode does not change a Windows ACL."""
    marker = data / ".acl-owner-only"
    if marker.exists():
        return
    sid = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True,
                         **CHILD_FLAGS).stdout.strip().split(",")[-1].strip('"')
    # The folder alone gets the owner-only entries, inherited by what it holds; what it already holds (data from an
    # earlier start) is reset to inherit them. Granting folder inheritance flags to files with /T left an existing
    # file with no usable entry (the lock file could no longer be opened, by its owner either).
    run(["icacls", str(data), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F", "/grant:r", "*S-1-5-18:(OI)(CI)F",
         "/Q"], stdout=subprocess.DEVNULL)
    if any(data.iterdir()):
        run(["icacls", str(data / "*"), "/reset", "/T", "/C", "/Q"], stdout=subprocess.DEVNULL)
    marker.touch()


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
        self.pg_port = int(self.env.get("NMOS_DB_PORT", "54390"))  # the key .env.example names
        self.bind = self.env.get("NMOS_SIDECAR_BIND", "127.0.0.1")
        self.port = self.env.get("NMOS_SIDECAR_PORT", "8790")
        self.url = f"http://{self.bind}:{self.port}"
        self.procs: list[subprocess.Popen] = []
        self.pgdata: Path | None = None
        self.stopped = False
        self.lock = threading.Lock()  # start() spawning and stop() never interleave (quit while starting)
        self._teardown_lock = threading.Lock()
        self._idle = threading.Event()  # set while no start() is running
        self._idle.set()
        self._data_lock = None

    def start(self) -> None:
        """Start everything; on any failure (a refusal, a stop asked meanwhile) undo what was started, PostgreSQL
        included, before raising: nothing is left running for a quit that may never come."""
        self._idle.clear()
        try:
            self._start()
        except BaseException:
            self._teardown()
            raise
        finally:
            self._idle.set()

    def _checkpoint(self) -> None:
        if self.stopped:
            raise SystemExit("stopped while starting")

    def _start(self) -> None:
        data = self.data
        if WINDOWS:
            restrict_to_this_user(data)  # before the lock file and the database are made in it
        self._data_lock = lock_data_dir(data)  # before anything that stop() would undo
        require_free_port(self.bind, int(self.port), "the NMOS sidecar", "NMOS_SIDECAR_PORT")
        if WINDOWS:
            global PGSQL
            PGSQL, data = ascii_path(PGSQL), ascii_path(data)
        self.pgdata = pgdata = data / "pg"
        pw_path = data / "db-password"
        self._checkpoint()
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
            require_free_port("127.0.0.1", self.pg_port, "the NMOS database", "NMOS_DB_PORT")
            self._checkpoint()
            run([pg_bin("pg_ctl"), "-D", str(pgdata), "-l", str(data / "postgres.log"), "-w", "start"])
        log(f"postgres up on 127.0.0.1:{self.pg_port} ({time.monotonic() - t0:.1f} s)")

        import psycopg

        with psycopg.connect(f"postgresql://nmos:{password}@127.0.0.1:{self.pg_port}/postgres", autocommit=True) as c:
            if not c.execute("SELECT 1 FROM pg_database WHERE datname = 'nmos'").fetchone():
                c.execute("CREATE DATABASE nmos")
        with psycopg.connect(f"postgresql://nmos:{password}@127.0.0.1:{self.pg_port}/nmos") as c:
            newer = newer_migrations(c)
        if newer:
            raise SystemExit(
                f"The data in {self.data} was written by a newer NMOS (it has {', '.join(newer)}, which this version "
                "does not know). Start that version or a newer one with this data folder; nothing was changed.\n"
                f"이 데이터({self.data})는 더 새 버전의 NMOS가 쓴 거예요. 그 버전이나 더 새 버전으로 실행해 주세요. "
                "데이터는 바뀌지 않았어요.")
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
            self._checkpoint()
            self.procs.append(subprocess.Popen([py, "-m", "uvicorn", "nmos_sidecar.api:app_factory", "--factory",
                                                "--host", self.bind, "--port", self.port], env=env, **CHILD_KW))
            self.procs.append(subprocess.Popen([py, "-m", "nmos_sidecar.worker"], env=env, **CHILD_KW))
        log(f"sidecar on {self.url} — set this URL in the PocketRisu plugin")

    def alive(self) -> bool:
        return bool(self.procs) and all(p.poll() is None for p in self.procs)

    def stop(self) -> None:
        """Stop everything this launcher started. A start() still running stops at its next checkpoint and undoes
        itself; this waits for that, so PostgreSQL is never started after a stop."""
        with self.lock:
            self.stopped = True
        self._idle.wait(timeout=300)
        self._teardown()

    def _teardown(self) -> None:
        with self._teardown_lock:
            if self._data_lock is None:
                return  # never started, already torn down, or another launcher holds this data: nothing is ours
            self._stop_all()
            self._data_lock.close()
            self._data_lock = None
            log("stopped")

    def _stop_all(self) -> None:
        for p in self.procs:
            if p.poll() is None:
                p.terminate()
        for p in self.procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        if self.pgdata is not None and (self.pgdata / "PG_VERSION").is_file():
            subprocess.run([pg_bin("pg_ctl"), "-D", str(self.pgdata), "-m", "fast", "-w", "stop"],
                           **{**CHILD_KW, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL})


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
