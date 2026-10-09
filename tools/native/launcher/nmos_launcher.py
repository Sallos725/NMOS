"""NMOS bundle launcher (Phase 23): Postgres, migrations, sidecar and worker without Docker.

Runs under the bundle's own Python. Layout next to this file:

    python/   standalone CPython with the sidecar installed
    pgsql/    portable PostgreSQL 16 with pg_trgm and pgvector
    migrations/, plugin/nmos-pocketrisu.js
    .env      optional, same keys as the Docker install's .env (read under the data folder's own .env)

The data (database cluster, logs, generated DB password, .env) lives outside the bundle, in a per-user folder, so
replacing the bundle folder on an update keeps it (Phase 37): Windows %LOCALAPPDATA%\\NMOS, Linux
$XDG_DATA_HOME/nmos (~/.local/share/nmos), macOS ~/Library/Application Support/NMOS. NMOS_DATA_DIR names another
folder (relative to this one: NMOS_DATA_DIR=data keeps it beside the launcher, as 0.3.0 did). A data/ that 0.3.0 left
beside the launcher is moved to the per-user folder on the first start.
"""

from __future__ import annotations

import errno
import hashlib
import os
import secrets
import shutil
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


def short_ascii(path: Path) -> Path | None:
    """Windows: the 8.3 short form of an existing path when it is all ASCII; None when the drive has no short names."""
    import ctypes

    buf = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf)) and buf.value.isascii():
        return Path(buf.value)
    return None


def ascii_path(path: Path) -> Path:
    """Windows: an all-ASCII spelling of an existing path (its 8.3 short form when it has other characters).

    PostgreSQL on Windows reads its own location and data directory through the ANSI code page, and initdb writes
    the installation path into UTF-8 SQL, so any non-ASCII character (a Korean user or folder name) breaks it.
    """
    if str(path).isascii():
        return path
    short = short_ascii(path)
    if short is not None:
        return short
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


def require_free_port(host: str, port: int, what: str, key: str, env_file: Path) -> None:
    """Q10: a fixed port in use stops the start with its name; a changed port would break the plugin's URL."""
    if port_in_use(host, port):
        raise SystemExit(
            f"Port {port} ({what}) is already in use by another program. Close it, or set {key} in {env_file} "
            f"to a free port.\n"
            f"포트 {port}({what})를 다른 프로그램이 이미 쓰고 있어요. 그 프로그램을 닫거나, {env_file}에서 "
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


# --- where the data lives (Phase 37) ----------------------------------------------------------------------------------

POINTER = "data-location.txt"  # Q6: in the per-user folder, the folder the user chose instead of it
SUGGESTED_DATA_DIR = Path("C:\\NMOS-data")


def user_data_dir(environ: dict[str, str]) -> Path:
    """Q1: the per-user folder outside the bundle."""
    if WINDOWS:
        local = environ.get("LOCALAPPDATA")
        return (Path(local) if local else Path.home() / "AppData" / "Local") / "NMOS"
    home = Path(environ.get("HOME") or Path.home())
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "NMOS"
    xdg = environ.get("XDG_DATA_HOME", "")
    return (Path(xdg) if xdg and Path(xdg).is_absolute() else home / ".local" / "share") / "nmos"


class DataLocationNeeded(Exception):
    """Q6: on Windows the per-user folder's path has non-English letters and its drive no short names, so PostgreSQL
    cannot use it; the user picks another folder (the tray's picker, the console's question)."""

    def __init__(self, base: Path) -> None:
        super().__init__(str(base))
        self.base = base


def resolve_data_dir(environ: dict[str, str]) -> tuple[Path, bool]:
    """The data folder, and whether it is the per-user one (True) rather than one NMOS_DATA_DIR names (Q5).

    The per-user one gets the bundle's old data/ (Q3) and .env (Q2); a named one is the user's to manage."""
    named = environ.get("NMOS_DATA_DIR")
    if named:
        return ROOT / Path(named).expanduser(), False  # relative to the bundle; an absolute path stays as it is
    base = user_data_dir(environ)
    if WINDOWS:
        pointer = base / POINTER
        if pointer.is_file():
            chosen = pointer.read_text(encoding="utf-8").strip()
            if chosen:
                return Path(chosen), True
        if not str(base).isascii():
            base.mkdir(parents=True, exist_ok=True)  # only an existing path has a short name
            if short_ascii(base) is None:
                raise DataLocationNeeded(base)
    return base, True


def choose_data_dir(base: Path, chosen: Path) -> Path:
    """Q6: make the folder the user chose and remember it in the per-user folder, so the next start and the next
    version use it without asking. ValueError (with the reason to show) when PostgreSQL could not use it either."""
    chosen = chosen.expanduser()
    if not chosen.is_absolute():
        raise ValueError(f"{chosen}: a full path is needed, such as {SUGGESTED_DATA_DIR}.\n"
                         f"{chosen}: {SUGGESTED_DATA_DIR}처럼 드라이브부터 시작하는 전체 경로를 적어 주세요.")
    made = not chosen.exists()
    chosen.mkdir(parents=True, exist_ok=True)
    if not str(chosen).isascii() and short_ascii(chosen) is None:
        if made:
            chosen.rmdir()
        raise ValueError(f"{chosen} has non-English characters too. Choose a folder whose path has only English "
                         "letters and digits.\n"
                         f"{chosen}에도 영문이 아닌 글자가 있어요. 영문과 숫자로만 된 경로의 폴더를 골라 주세요.")
    base.mkdir(parents=True, exist_ok=True)
    (base / POINTER).write_text(f"{chosen}\n", encoding="utf-8")
    return chosen


def ask_data_dir_in_console(base: Path) -> Path | None:
    """Q6 for NMOS.bat: ask in the console. None when the user cancels (nothing is started)."""
    print(f"NMOS cannot keep its database in {base}: the path has non-English characters and the drive has no short "
          "names. Choose another folder for NMOS's data; it is remembered, so the next start and the next version "
          "do not ask again.\n"
          f"Windows 사용자 이름에 한글이 있어서, NMOS 데이터베이스를 기본 위치({base})에 둘 수 없어요. 데이터를 둘 "
          "폴더를 정해 주세요. 한 번 정하면 기억해 두니, 다음 실행이나 업데이트 때는 다시 묻지 않아요.\n"
          f"Enter: {SUGGESTED_DATA_DIR} / 다른 경로 입력 / q: 취소", flush=True)
    while True:
        try:
            answer = input("> ").strip().strip('"')
        except (EOFError, KeyboardInterrupt):
            return None
        if answer.lower() in ("q", "quit"):
            return None
        try:
            return choose_data_dir(base, Path(answer) if answer else SUGGESTED_DATA_DIR)
        except (ValueError, OSError) as e:
            print(e, flush=True)


def pg_running(pgdata: Path) -> bool:
    pgdata = ascii_path(pgdata) if WINDOWS else pgdata
    return subprocess.run([pg_bin("pg_ctl"), "-D", str(pgdata), "status"],
                          **{**CHILD_KW, "stdout": subprocess.DEVNULL}).returncode == 0


def tree_digest(root: Path) -> dict[str, tuple[int, str]]:
    """Every file under root by its relative path: size and SHA-256."""
    out: dict[str, tuple[int, str]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            h = hashlib.sha256()
            with path.open("rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
            out[path.relative_to(root).as_posix()] = (path.stat().st_size, h.hexdigest())
    return out


class CopiedClusterStopUncertain(SystemExit):
    """The staging copy may still be running, so it must neither be moved nor removed."""


def stop_copied_cluster(pgdata: Path) -> None:
    try:
        pg = ascii_path(pgdata) if WINDOWS else pgdata
        subprocess.run([pg_bin("pg_ctl"), "-D", str(pg), "-m", "fast", "-w", "stop"],
                       **{**CHILD_KW, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL})
        status = subprocess.run([pg_bin("pg_ctl"), "-D", str(pg), "status"],
                                **{**CHILD_KW, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL})
        if status.returncode == 3:  # pg_ctl status: the server is not running; other errors are not that evidence
            return
    except BaseException as error:  # interruption during teardown also leaves the process uncertain
        reason = str(error) or type(error).__name__
    else:
        reason = f"pg_ctl status returned {status.returncode}"
    raise CopiedClusterStopUncertain(
        f"PostgreSQL on the adoption copy {pgdata} could not be confirmed stopped ({reason}). "
        "The original and copy were kept. Stop that PostgreSQL, then retry; do not remove the copy while it runs."
        f"\n복사본({pgdata})의 PostgreSQL이 종료됐는지 확인하지 못했어요. 원본과 복사본을 보존했습니다. "
        "그 PostgreSQL을 종료한 뒤 다시 시도하세요. 실행 중인 복사본을 지우지 마세요.")


def check_copied_cluster(pgdata: Path, password: str, port: int) -> None:
    """Q3 across drives: PostgreSQL starts on the copy and reads from it; it is stopped again either way."""
    import psycopg

    require_free_port("127.0.0.1", port, "the NMOS database", "NMOS_DB_PORT", pgdata.parent / ".env")
    pg = ascii_path(pgdata) if WINDOWS else pgdata
    try:
        run([pg_bin("pg_ctl"), "-D", str(pg), "-l", str(pg.parent / "postgres.log"), "-o", f"-p {port}", "-w", "start"])
        url = f"postgresql://nmos:{password}@127.0.0.1:{port}"
        with psycopg.connect(f"{url}/postgres") as c:
            has_nmos = c.execute("SELECT 1 FROM pg_database WHERE datname = 'nmos'").fetchone()
        if has_nmos:
            with psycopg.connect(f"{url}/nmos") as c:
                if not c.execute("SELECT to_regclass('schema_migrations') IS NULL").fetchone()[0]:
                    c.execute("SELECT count(*) FROM schema_migrations").fetchone()
    finally:
        stop_copied_cluster(pgdata)


def cross_device(e: OSError) -> bool:
    return e.errno == errno.EXDEV or getattr(e, "winerror", None) == 17  # ERROR_NOT_SAME_DEVICE


def adopt_bundle_data(data: Path, pg_port: int) -> None:
    """Q3, Q4: the database 0.3.0 kept in data/ beside the launcher moves to the per-user folder on the first start.

    Fails closed: one folder or the other holds the whole database at every step, nothing is deleted but this
    function's own unfinished copy, and a database in both places stops the start with neither changed."""
    old = ROOT / "data"
    if not (old / "pg" / "PG_VERSION").is_file() or old.resolve() == data.resolve():
        return
    if (data / "pg" / "PG_VERSION").is_file():
        raise SystemExit(
            f"NMOS found a database in two places: {data} (where this version keeps it) and {old} (beside NMOS, where "
            "0.3.0 and earlier kept it). It will not choose one for you. Keep the one you use: move or rename the "
            "other folder (for example to data.old), then start NMOS again. Nothing was changed.\n"
            f"NMOS 데이터베이스가 두 곳에 있어요: {data}(이 버전의 위치)와 {old}(NMOS 옆, 0.3.0까지의 위치). 어느 쪽을 쓸지 "
            "NMOS가 대신 고르지 않아요. 쓰시던 쪽을 남기고 다른 쪽 폴더를 옮기거나 이름을 바꾼 뒤(예: data.old) 다시 "
            "실행해 주세요. 아무것도 바뀌지 않았어요.")
    old_pw = old / "db-password"
    if not old_pw.is_file():
        raise SystemExit(f"{old} holds a database but not its password (db-password), so it cannot be moved to {data}. "
                         "Nothing was changed.\n"
                         f"{old}에 데이터베이스는 있지만 비밀번호 파일(db-password)이 없어서 {data}로 옮기지 못했어요. "
                         "아무것도 바뀌지 않았어요.")
    old_lock = lock_data_dir(old)  # an older NMOS still running on it stops this start here
    try:
        staging = data / "pg.adopting"
        if staging.exists():
            stop_copied_cluster(staging)  # a previous start may have left a running copy
            shutil.rmtree(staging)  # only after pg_ctl confirms it is stopped
        if pg_running(old / "pg"):  # left by an earlier run that did not stop it; no launcher holds it (the lock)
            log(f"stopping the PostgreSQL an earlier run left running on {old}")
            subprocess.run([pg_bin("pg_ctl"), "-D", str(ascii_path(old / "pg") if WINDOWS else old / "pg"), "-m",
                            "fast", "-w", "stop"], check=True, **{**CHILD_KW, "stdout": subprocess.DEVNULL})
        password = old_pw.read_text(encoding="utf-8").strip()
        log(f"moving the database from {old} to {data} (Phase 37: the data lives outside the bundle)")
        write_private(data / "db-password", password)
        copied = False
        try:
            os.rename(old / "pg", data / "pg")  # on one drive the move is this rename
        except OSError as e:
            if not cross_device(e):
                (data / "db-password").unlink(missing_ok=True)
                raise SystemExit(f"The database in {old} could not be moved to {data}: {e}. Nothing was changed.\n"
                                 f"{old}의 데이터베이스를 {data}로 옮기지 못했어요: {e}. 아무것도 바뀌지 않았어요.")
            copied = True
            try:
                log("another drive: copying, checking the copy, then keeping the old folder as it is")
                shutil.copytree(old / "pg", staging)
                if tree_digest(staging) != tree_digest(old / "pg"):
                    raise SystemExit("the copy differs from the original")
                check_copied_cluster(staging, password, pg_port)
                os.rename(staging, data / "pg")
            except BaseException as e:
                if not isinstance(e, CopiedClusterStopUncertain):
                    shutil.rmtree(staging, ignore_errors=True)
                    (data / "db-password").unlink(missing_ok=True)
                reason = e.code if isinstance(e, SystemExit) else repr(e)
                raise SystemExit(f"The database in {old} could not be copied to {data}: {reason}. {old} is as it was."
                                 f"\n{old}의 데이터베이스를 {data}로 복사하지 못했어요: {reason}. {old}는 그대로예요.") from e
        else:
            try:
                os.replace(old_pw, data / "db-password")  # the same password: no copy of it is left behind
            except OSError as e:
                log(f"{old_pw} stays where it was ({e}); the database's folder has its copy")
    finally:
        old_lock.close()
    retire_old_data(old, data, copied)


def retire_old_data(old: Path, data: Path, copied: bool) -> None:
    """After a move, the old data/ is renamed data.moved with a note; never deleted. A rename that fails is logged:
    the database is already in the per-user folder (a copy left in both places stops the next start, Q4)."""
    n = 1
    while (moved := old.with_name("data.moved" if n == 1 else f"data.moved-{n}")).exists():
        n += 1
    try:
        os.rename(old, moved)
        (moved / "MOVED.txt").write_text(
            f"{time.strftime('%Y-%m-%d %H:%M')}: NMOS moved its database from this folder to {data}.\n"
            + ("This folder still holds a copy of it, kept in case. Once NMOS works, you can delete this folder.\n"
               "NMOS가 데이터베이스를 이 폴더에서 위 위치로 옮겼어요. 이 폴더에는 만약을 위한 복사본이 남아 있어요. NMOS가 잘 "
               "되는 걸 확인한 뒤 지워도 돼요.\n" if copied else
               "What is left here are old logs. You can delete this folder.\n"
               "NMOS가 데이터베이스를 이 폴더에서 위 위치로 옮겼어요. 여기 남은 건 예전 로그예요. 지워도 돼요.\n"),
            encoding="utf-8")
        log(f"the old folder is now {moved}")
    except OSError as e:
        log(f"the old folder {old} could not be renamed ({e}); rename or remove it before the next start")


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
        """Raises DataLocationNeeded (Q6) before anything is made when the user has to choose the data folder."""
        os.environ["PYTHONUTF8"] = "1"
        self.env = dict(os.environ)
        beside = read_env_file(ROOT / ".env")
        self.data, self.per_user = resolve_data_dir({**beside, **self.env})  # NMOS_DATA_DIR: process env, then here
        self.data.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Q2: the .env in the data folder survives an update; the one beside the launcher is read under it, and copied
        # there once so the settings move with the data. NMOS_ENV_FILE: the macOS app names its own.
        self.env_file = Path(os.environ.get("NMOS_ENV_FILE") or self.data / ".env")
        self.env_copied = False
        if self.per_user and not self.env_file.exists() and (ROOT / ".env").is_file():
            shutil.copy2(ROOT / ".env", self.env_file)
            self.env_copied = True
        own = read_env_file(self.env_file)
        self.shadowed = sorted(k for k, v in beside.items() if k in own and own[k] != v and k not in os.environ)
        for key, value in [*own.items(), *beside.items()]:
            self.env.setdefault(key, value)
        if sys.platform.startswith("linux"):
            # The bundle carries the libraries Postgres links (build_bundle.vendor_linux_libs), indirect ones too.
            pglib = str(ROOT / "pgsql" / "lib")
            os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(filter(None, [pglib, os.environ.get("LD_LIBRARY_PATH")]))
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
        log(f"data folder: {data}")
        if self.env_copied:
            log(f"copied the .env beside NMOS to {self.env_file}; NMOS's settings are read there first from now on")
        if self.shadowed:
            log(f"the .env beside NMOS sets {', '.join(self.shadowed)} differently; {self.env_file} wins")
        if WINDOWS:
            restrict_to_this_user(data)  # before the lock file and the database are made in it
        self._data_lock = lock_data_dir(data)  # before anything that stop() would undo
        require_free_port(self.bind, int(self.port), "the NMOS sidecar", "NMOS_SIDECAR_PORT", self.env_file)
        if WINDOWS:
            global PGSQL
            PGSQL = ascii_path(PGSQL)
        if self.per_user:
            adopt_bundle_data(data, self.pg_port)  # Q3, Q4: under this folder's lock, before anything is made in it
        self._checkpoint()
        if WINDOWS:
            data = ascii_path(data)
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
            require_free_port("127.0.0.1", self.pg_port, "the NMOS database", "NMOS_DB_PORT", self.env_file)
            self._checkpoint()
            # -p: NMOS_DB_PORT changed after the first start (the port-in-use message says to) wins over the port
            # init_cluster wrote into postgresql.conf.
            run([pg_bin("pg_ctl"), "-D", str(pgdata), "-l", str(data / "postgres.log"), "-o", f"-p {self.pg_port}",
                 "-w", "start"])
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
            "NMOS_INSTALL": "bundle",  # the panel reaches the PC's own Ollama at 127.0.0.1 (no host.docker.internal here)
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
    try:
        services = Services()
    except DataLocationNeeded as need:
        if ask_data_dir_in_console(need.base) is None:
            log("no folder was chosen for NMOS's data; nothing was started")
            return 1
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
