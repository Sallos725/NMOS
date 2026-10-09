"""The bundle launcher's data folder (Phase 37, tools/native/launcher/nmos_launcher.py): the per-user folder (Q1), the
.env beside it (Q2), the data 0.3.0 left beside the launcher adopted on the first start (Q3) or refused when both
places hold a database (Q4), NMOS_DATA_DIR (Q5) and the Windows folder question (Q6, the short-name lookup stubbed).

PostgreSQL is not run here: the bundle smoke (tools/native/smoke.py) adopts a real cluster on each target. These
check the decisions and that every failure leaves the old folder as it was."""

from __future__ import annotations

import errno
import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[3] / "tools/native/launcher/nmos_launcher.py"
_spec = importlib.util.spec_from_file_location("nmos_launcher", TOOL)
launcher = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(launcher)
_pg_running = launcher.pg_running


def digest(root: Path) -> dict[str, tuple[int, str]]:
    return launcher.tree_digest(root) if root.exists() else {}


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    """A bundle folder and a per-user base of this test's own; no PostgreSQL to stop."""
    root = tmp_path / "NMOS-v0.4.0"
    root.mkdir()
    monkeypatch.setattr(launcher, "ROOT", root)
    monkeypatch.setattr(launcher, "pg_running", lambda pgdata: False)
    for key in ("NMOS_DATA_DIR", "NMOS_ENV_FILE", "NMOS_SIDECAR_PORT", "NMOS_DB_PORT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PYTHONUTF8", os.environ.get("PYTHONUTF8", "1"))  # Services() sets it; restored after
    monkeypatch.setenv("LD_LIBRARY_PATH", os.environ.get("LD_LIBRARY_PATH", ""))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    if sys.platform == "darwin":
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return root


def old_data(root: Path, password: str = "old-pw") -> Path:
    """data/ as 0.3.0 leaves it beside the launcher: a cluster, its password, logs and the lock file."""
    old = root / "data"
    (old / "pg" / "base" / "1").mkdir(parents=True)
    (old / "pg" / "PG_VERSION").write_text("16\n")
    (old / "pg" / "base" / "1" / "1259").write_bytes(os.urandom(4096))
    (old / "pg" / "postgresql.conf").write_text("port = 54390\n")
    (old / "db-password").write_text(password)
    (old / "nmos.log").write_text("[nmos] old log\n")
    (old / "launcher.lock").write_text("")
    return old


def per_user() -> Path:
    data, is_per_user = launcher.resolve_data_dir(dict(os.environ))
    assert is_per_user
    data.mkdir(parents=True, exist_ok=True)
    return data


# --- Q1, Q5: where ----------------------------------------------------------------------------------------------------

def test_the_per_user_folder_of_each_system(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "WINDOWS", True)
    assert launcher.user_data_dir({"LOCALAPPDATA": str(tmp_path / "Local")}) == tmp_path / "Local" / "NMOS"
    monkeypatch.setattr(launcher, "WINDOWS", False)
    monkeypatch.setattr(launcher.sys, "platform", "darwin")
    assert launcher.user_data_dir({"HOME": str(tmp_path)}) == tmp_path / "Library" / "Application Support" / "NMOS"
    monkeypatch.setattr(launcher.sys, "platform", "linux")
    xdg = {"HOME": str(tmp_path), "XDG_DATA_HOME": str(tmp_path / "x")}
    assert launcher.user_data_dir(xdg) == tmp_path / "x" / "nmos"
    # A relative XDG_DATA_HOME is invalid by the specification and ignored.
    assert launcher.user_data_dir({"HOME": str(tmp_path), "XDG_DATA_HOME": "x"}) == tmp_path / ".local/share/nmos"
    assert launcher.user_data_dir({"HOME": str(tmp_path)}) == tmp_path / ".local" / "share" / "nmos"


def test_nmos_data_dir_wins_and_a_relative_one_is_beside_the_launcher(bundle, tmp_path):
    assert launcher.resolve_data_dir({"NMOS_DATA_DIR": "data"}) == (bundle / "data", False)
    assert launcher.resolve_data_dir({"NMOS_DATA_DIR": str(tmp_path / "usb")}) == (tmp_path / "usb", False)


def test_a_fresh_start_makes_the_per_user_folder_and_nothing_in_the_bundle(bundle):
    services = launcher.Services()
    assert services.per_user and services.data == launcher.user_data_dir(dict(os.environ))
    assert services.data.is_dir() and not (bundle / "data").exists()


def test_nmos_data_dir_in_the_env_beside_the_launcher_keeps_the_old_layout(bundle):
    (bundle / ".env").write_text("NMOS_DATA_DIR=data\n")
    services = launcher.Services()
    assert (services.data, services.per_user) == (bundle / "data", False)
    assert not (bundle / "data" / ".env").exists()  # a named folder is the user's: the .env is not copied into it


# --- Q2: the .env -----------------------------------------------------------------------------------------------------

def test_the_env_beside_the_launcher_is_copied_once_and_read_under_the_data_folders(bundle, monkeypatch):
    (bundle / ".env").write_text("NMOS_SIDECAR_PORT=8800\nNMOS_AUTH_TOKEN=beside\n")
    services = launcher.Services()
    assert services.env_copied and services.env_file == services.data / ".env"
    assert (services.data / ".env").read_text() == (bundle / ".env").read_text()
    assert services.port == "8800"

    # The user changes the copy in the data folder; the next version's folder has a .env of its own.
    (services.data / ".env").write_text("NMOS_SIDECAR_PORT=8801\n")
    (bundle / ".env").write_text("NMOS_SIDECAR_PORT=8802\nNMOS_EMBED_TIMEOUT_MS=900\n")
    services = launcher.Services()
    assert not services.env_copied
    assert services.port == "8801" and services.env["NMOS_EMBED_TIMEOUT_MS"] == "900"
    assert services.shadowed == ["NMOS_SIDECAR_PORT"]

    monkeypatch.setenv("NMOS_SIDECAR_PORT", "8803")  # the process environment wins over both, as before
    assert launcher.Services().port == "8803"


# --- Q3: adoption -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("status", [1, 4])
@pytest.mark.parametrize("staging", [False, True])
def test_unknown_source_status_preserves_original_and_staging(bundle, monkeypatch, status, staging):
    from types import SimpleNamespace

    old = old_data(bundle)
    data = per_user()
    if staging:
        shutil.copytree(old / "pg", data / "pg.adopting")
    before, target = digest(old), digest(data)
    calls = []

    def child(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=status)

    monkeypatch.setattr(launcher, "pg_running", _pg_running)
    monkeypatch.setattr(launcher.subprocess, "run", child)
    with pytest.raises(SystemExit, match="could not be determined"):
        launcher.adopt_bundle_data(data, 54390)
    assert digest(old) == before and digest(data) == target
    assert len(calls) == 1 and calls[0][-1] == "status" and calls[0][2] == str(old / "pg")
    assert not (bundle / "data.moved").exists()


@pytest.mark.parametrize("status", [0, 3])
def test_source_is_adopted_only_when_stopped_or_successfully_stopped(bundle, monkeypatch, status):
    from types import SimpleNamespace

    old = old_data(bundle)
    cluster = digest(old / "pg")
    data = per_user()
    calls = []

    def child(args, **kwargs):
        calls.append(args[-1])
        return SimpleNamespace(returncode=status if args[-1] == "status" else 0)

    monkeypatch.setattr(launcher, "pg_running", _pg_running)
    monkeypatch.setattr(launcher.subprocess, "run", child)
    launcher.adopt_bundle_data(data, 54390)
    assert calls == (["status", "stop"] if status == 0 else ["status"])
    assert digest(data / "pg") == cluster and (bundle / "data.moved").exists()


@pytest.mark.parametrize("failure", ["status", "stop", "interrupt"])
def test_source_command_failure_preserves_original_and_staging(bundle, monkeypatch, failure):
    from types import SimpleNamespace

    old = old_data(bundle)
    data = per_user()
    shutil.copytree(old / "pg", data / "pg.adopting")
    before, target = digest(old), digest(data)

    def child(args, **kwargs):
        if failure == "interrupt":
            raise KeyboardInterrupt
        if failure == "status":
            raise OSError("status unavailable")
        if args[-1] == "stop":
            raise launcher.subprocess.CalledProcessError(1, args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(launcher, "pg_running", _pg_running)
    monkeypatch.setattr(launcher.subprocess, "run", child)
    expected = KeyboardInterrupt if failure == "interrupt" else (
        OSError if failure == "status" else launcher.subprocess.CalledProcessError)
    with pytest.raises(expected):
        launcher.adopt_bundle_data(data, 54390)
    assert digest(old) == before and digest(data) == target
    assert not (bundle / "data.moved").exists()

def test_data_beside_the_launcher_moves_to_the_per_user_folder_by_a_rename(bundle):
    old = old_data(bundle)
    cluster = digest(old / "pg")
    data = per_user()
    (data / "nmos.log").write_text("[nmos] the tray's log, opened before the start\n")

    launcher.adopt_bundle_data(data, 54390)

    assert digest(data / "pg") == cluster
    assert (data / "db-password").read_text() == "old-pw"
    assert not old.exists()
    moved = bundle / "data.moved"
    assert (moved / "nmos.log").read_text() == "[nmos] old log\n" and "old logs" in (moved / "MOVED.txt").read_text()
    assert not (moved / "pg").exists() and not (moved / "db-password").exists()
    launcher.adopt_bundle_data(data, 54390)  # the next start: nothing left to adopt
    assert digest(data / "pg") == cluster


def test_another_drive_copies_checks_the_copy_and_keeps_the_old_folder(bundle, monkeypatch):
    old = old_data(bundle)
    cluster = digest(old / "pg")
    data = per_user()
    rename = os.rename

    def across_drives(src, dst):
        if Path(src) == old / "pg":
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        rename(src, dst)

    checked = []
    monkeypatch.setattr(os, "rename", across_drives)
    monkeypatch.setattr(launcher, "check_copied_cluster",
                        lambda pgdata, password, port: checked.append((pgdata.name, password, port)))

    launcher.adopt_bundle_data(data, 54391)

    assert checked == [("pg.adopting", "old-pw", 54391)]
    assert digest(data / "pg") == cluster and not (data / "pg.adopting").exists()
    moved = bundle / "data.moved"
    assert digest(moved / "pg") == cluster  # never deleted: the original stays, renamed
    assert "copy" in (moved / "MOVED.txt").read_text()


@pytest.mark.parametrize("fail_at", ["copy", "compare", "check", "rename"])
def test_an_adoption_that_fails_leaves_the_old_folder_byte_identical(bundle, monkeypatch, fail_at):
    old = old_data(bundle)
    before = digest(old)
    data = per_user()
    rename, copytree = os.rename, shutil.copytree

    def fake_rename(src, dst):
        if Path(src) == old / "pg":
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        if fail_at == "rename" and Path(src).name == "pg.adopting":
            raise OSError(errno.EIO, "injected")
        rename(src, dst)

    def fake_copytree(src, dst, **kw):
        copytree(src, dst, **kw)
        if fail_at == "copy":
            raise OSError(errno.ENOSPC, "No space left on device")
        if fail_at == "compare":
            (Path(dst) / "PG_VERSION").write_text("15\n")

    def check(pgdata, password, port):
        if fail_at == "check":
            raise SystemExit("postgres did not start on the copy")

    monkeypatch.setattr(os, "rename", fake_rename)
    monkeypatch.setattr(shutil, "copytree", fake_copytree)
    monkeypatch.setattr(launcher, "check_copied_cluster", check)

    with pytest.raises(SystemExit, match="is as it was"):
        launcher.adopt_bundle_data(data, 54390)

    assert digest(old) == before
    assert not (data / "pg").exists() and not (data / "pg.adopting").exists() and not (data / "db-password").exists()
    assert not (bundle / "data.moved").exists()


def test_a_rename_refused_for_another_reason_changes_nothing(bundle, monkeypatch):
    old = old_data(bundle)
    before = digest(old)
    data = per_user()
    rename = os.rename

    def denied(src, dst):
        if Path(src) == old / "pg":
            raise PermissionError(errno.EACCES, "Permission denied")
        rename(src, dst)

    monkeypatch.setattr(os, "rename", denied)
    with pytest.raises(SystemExit, match="Nothing was changed"):
        launcher.adopt_bundle_data(data, 54390)
    assert digest(old) == before and not (data / "db-password").exists() and not (data / "pg").exists()


def test_an_older_nmos_still_running_on_the_old_data_stops_the_adoption(bundle):
    old = old_data(bundle)
    before = digest(old)
    data = per_user()
    held = launcher.lock_data_dir(old)  # the 0.3.0 launcher's lock
    try:
        with pytest.raises(launcher.AlreadyRunning):
            launcher.adopt_bundle_data(data, 54390)
    finally:
        held.close()
    assert digest(old) == before and not (data / "pg").exists()


def test_a_data_folder_without_a_database_beside_the_launcher_is_left_alone(bundle):
    (bundle / "data").mkdir()
    (bundle / "data" / "nmos.log").write_text("a start that failed\n")
    data = per_user()
    launcher.adopt_bundle_data(data, 54390)
    assert (bundle / "data" / "nmos.log").exists() and not (bundle / "data.moved").exists()


# --- Q4: both ---------------------------------------------------------------------------------------------------------

def test_a_database_in_both_places_stops_the_start_and_changes_neither(bundle):
    old = old_data(bundle)
    data = per_user()
    (data / "pg").mkdir()
    (data / "pg" / "PG_VERSION").write_text("16\n")
    (data / "db-password").write_text("new-pw")
    before_old, before_new = digest(old), digest(data)

    with pytest.raises(SystemExit) as refusal:
        launcher.adopt_bundle_data(data, 54390)

    assert str(old) in str(refusal.value.code) and str(data) in str(refusal.value.code)
    assert digest(old) == before_old and digest(data) == before_new


# --- Q6: Windows, a per-user path PostgreSQL cannot use ---------------------------------------------------------------

@pytest.fixture
def korean_user(tmp_path, monkeypatch):
    """Windows with a Korean user name on a drive without short names (GetShortPathNameW stubbed)."""
    monkeypatch.setattr(launcher, "WINDOWS", True)
    monkeypatch.setattr(launcher, "short_ascii", lambda path: None)
    return {"LOCALAPPDATA": str(tmp_path / "사용자" / "AppData" / "Local")}


def test_a_per_user_path_without_a_short_name_asks_where_the_data_goes(korean_user, tmp_path):
    with pytest.raises(launcher.DataLocationNeeded) as need:
        launcher.resolve_data_dir(korean_user)
    assert need.value.base == tmp_path / "사용자" / "AppData" / "Local" / "NMOS"


def test_the_chosen_folder_is_remembered_for_the_next_start_and_the_next_version(korean_user, tmp_path, monkeypatch):
    base = launcher.user_data_dir(korean_user)
    chosen = launcher.choose_data_dir(base, tmp_path / "NMOS-data")
    assert chosen.is_dir() and (base / launcher.POINTER).read_text(encoding="utf-8").strip() == str(chosen)
    assert launcher.resolve_data_dir(korean_user) == (chosen, True)
    monkeypatch.setattr(launcher, "ROOT", tmp_path / "NMOS-v0.4.1")  # the next version's bundle folder
    assert launcher.resolve_data_dir(korean_user) == (chosen, True)


def test_a_chosen_folder_postgres_cannot_use_either_is_refused_and_not_left_behind(korean_user, tmp_path):
    base = launcher.user_data_dir(korean_user)
    with pytest.raises(ValueError, match="non-English"):
        launcher.choose_data_dir(base, tmp_path / "내 데이터")
    assert not (tmp_path / "내 데이터").exists() and not (base / launcher.POINTER).exists()
    with pytest.raises(ValueError, match="full path"):
        launcher.choose_data_dir(base, Path("NMOS-data"))


def test_nmos_data_dir_still_wins_over_the_question(korean_user, tmp_path):
    assert launcher.resolve_data_dir({**korean_user, "NMOS_DATA_DIR": str(tmp_path / "x")}) == (tmp_path / "x", False)


def test_the_console_asks_again_after_a_bad_answer_and_cancel_starts_nothing(korean_user, tmp_path, monkeypatch,
                                                                              capsys):
    base = launcher.user_data_dir(korean_user)
    answers = iter([str(tmp_path / "한글"), f'"{tmp_path / "NMOS-data"}"'])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert launcher.ask_data_dir_in_console(base) == tmp_path / "NMOS-data"
    assert "non-English" in capsys.readouterr().out

    (base / launcher.POINTER).unlink()
    monkeypatch.setattr("builtins.input", lambda prompt="": "q")
    assert launcher.ask_data_dir_in_console(base) is None
    assert not (base / launcher.POINTER).exists()

    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)  # no console to answer in
    assert launcher.ask_data_dir_in_console(base) is None


@pytest.mark.parametrize("failure", ["start", "check"])
def test_a_copied_cluster_start_attempt_is_always_stopped(bundle, monkeypatch, failure):
    import psycopg
    from types import SimpleNamespace

    data = per_user() / "pg.adopting"
    data.mkdir()
    calls = []
    monkeypatch.setattr(launcher, "require_free_port", lambda *args: None)

    def start(args, **kwargs):
        calls.append("start")
        if failure == "start":
            raise SystemExit("injected failed start after launching PostgreSQL")

    def child(args, **kwargs):
        calls.append(args[-1])
        return SimpleNamespace(returncode=3 if args[-1] == "status" else 0)

    def connect(*args, **kwargs):
        raise psycopg.OperationalError("injected check failure")

    monkeypatch.setattr(launcher, "run", start)
    monkeypatch.setattr(launcher.subprocess, "run", child)
    monkeypatch.setattr(psycopg, "connect", connect)
    with pytest.raises(SystemExit if failure == "start" else psycopg.OperationalError):
        launcher.check_copied_cluster(data, "old-pw", 54390)
    assert calls == ["start", "stop", "status"]
    assert data.exists()


def test_a_copy_with_uncertain_stop_is_kept_and_the_next_attempt_cannot_delete_it(bundle, monkeypatch):
    import psycopg
    from types import SimpleNamespace

    old = old_data(bundle)
    before = digest(old)
    data = per_user()
    rename = os.rename
    calls = []

    def across_drives(src, dst):
        calls.append(("rename", Path(src), Path(dst)))
        if Path(src) == old / "pg":
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        rename(src, dst)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, *args):
            return self

        def fetchone(self):
            return None  # a copied cluster without the NMOS database still needs teardown

    def child(args, **kwargs):
        calls.append((args[-1],))
        return SimpleNamespace(returncode=1 if args[-1] == "stop" else 0)  # still running

    monkeypatch.setattr(os, "rename", across_drives)
    monkeypatch.setattr(launcher, "require_free_port", lambda *args: None)
    monkeypatch.setattr(launcher, "run", lambda *args, **kwargs: calls.append(("start",)))
    monkeypatch.setattr(launcher.subprocess, "run", child)
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: Connection())
    with pytest.raises(SystemExit, match="could not be confirmed stopped"):
        launcher.adopt_bundle_data(data, 54390)
    assert digest(old) == before and digest(data / "pg.adopting") == digest(old / "pg")
    assert not (data / "pg").exists() and not (bundle / "data.moved").exists()
    kept = digest(data)
    attempts = calls.count(("start",))
    with pytest.raises(launcher.CopiedClusterStopUncertain, match="Stop that PostgreSQL"):
        launcher.adopt_bundle_data(data, 54390)
    assert digest(old) == before and digest(data) == kept
    assert calls.count(("start",)) == attempts  # no new start, copy, promotion or retirement


@pytest.mark.parametrize("status", [0, 1, 4])
def test_stale_staging_is_not_removed_unless_pg_ctl_reports_stopped(bundle, monkeypatch, status):
    from types import SimpleNamespace

    old = old_data(bundle)
    before = digest(old)
    data = per_user()
    shutil.copytree(old / "pg", data / "pg.adopting")
    kept = digest(data)
    monkeypatch.setattr(launcher.subprocess, "run", lambda args, **kwargs: SimpleNamespace(returncode=status))
    with pytest.raises(launcher.CopiedClusterStopUncertain):
        launcher.adopt_bundle_data(data, 54390)
    assert digest(old) == before and digest(data) == kept
    assert not (data / "pg").exists() and not (bundle / "data.moved").exists()


@pytest.mark.parametrize("error", [OSError("stop command unavailable"), KeyboardInterrupt()])
def test_a_staging_stop_error_or_interrupt_preserves_both_folders(bundle, monkeypatch, error):
    old = old_data(bundle)
    before = digest(old)
    data = per_user()
    shutil.copytree(old / "pg", data / "pg.adopting")
    kept = digest(data)

    def interrupted(*args, **kwargs):
        raise error

    monkeypatch.setattr(launcher.subprocess, "run", interrupted)
    with pytest.raises(launcher.CopiedClusterStopUncertain):
        launcher.adopt_bundle_data(data, 54390)
    assert digest(old) == before and digest(data) == kept
    assert not (data / "pg").exists() and not (bundle / "data.moved").exists()
