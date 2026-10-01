"""Build an NMOS portable bundle for one target (spike). Run it on that target's OS.

    python tools/native/build_bundle.py --target linux-x64 --version 0.0.0-spike

Needs uv, a C toolchain for pgvector (make + cc; on Windows nmake from an MSVC developer shell), and network.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PG_VERSION = "16.15.0"
PGVECTOR_TAG = "v0.8.6"
PBS_TAG = "20260929"
PY_VERSION = "3.12.14"

TARGETS = {
    "linux-x64": "x86_64-unknown-linux-gnu",
    "linux-arm64": "aarch64-unknown-linux-gnu",
    "macos-arm64": "aarch64-apple-darwin",
    "win-x64": "x86_64-pc-windows-msvc",
}


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def fetch(url: str, cache: Path) -> Path:
    dest = cache / url.rsplit("/", 1)[1].replace("%2B", "+")
    if not dest.exists():
        log(f"download {url}")
        tmp = dest.with_suffix(".part")
        with urllib.request.urlopen(url) as r, tmp.open("wb") as f:
            shutil.copyfileobj(r, f)
        tmp.rename(dest)
    return dest


def extract_into(archive: Path, dest: Path) -> None:
    """Extract an archive whose content sits under one top-level directory into dest."""
    tmp = dest.parent / (dest.name + ".x")
    shutil.rmtree(tmp, ignore_errors=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(tmp)
    else:
        with tarfile.open(archive) as t:
            t.extractall(tmp, filter="tar")
    (top,) = list(tmp.iterdir())
    top.rename(dest)
    tmp.rmdir()


def build_pgvector(pgsql: Path, work: Path, windows: bool) -> None:
    src = work / "pgvector"
    if not src.exists():
        subprocess.run(["git", "clone", "-q", "--depth", "1", "-b", PGVECTOR_TAG,
                        "https://github.com/pgvector/pgvector", str(src)], check=True)
    if windows:
        env = dict(os.environ, PGROOT=str(pgsql))
        subprocess.run(["nmake", "/NOLOGO", "/F", "Makefile.win"], cwd=src, env=env, check=True)
        subprocess.run(["nmake", "/NOLOGO", "/F", "Makefile.win", "install"], cwd=src, env=env, check=True)
    else:
        # OPTFLAGS="": no -march=native, so the library runs on any CPU of the target architecture.
        args = [f"PG_CONFIG={pgsql / 'bin' / 'pg_config'}", "OPTFLAGS="]
        if sys.platform == "darwin":
            # pg_config carries the SDK path of the machine that built Postgres; use this machine's SDK.
            sdk = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True, check=True).stdout.strip()
            args.append(f"PG_SYSROOT={sdk}")
        subprocess.run(["make", "-s", "clean"], cwd=src, check=False)
        subprocess.run(["make", "-s", *args], cwd=src, check=True)
        subprocess.run(["make", "-s", "install", *args], cwd=src, check=True)


# glibc itself and the dynamic loader come from the user's system; everything else Postgres links is copied in.
LINUX_SYSTEM_LIBS = ("linux-vdso", "ld-linux", "libc.so", "libm.so", "libdl.so", "libpthread.so", "librt.so",
                     "libresolv.so")


# Server modules NMOS loads (migrations, initdb); a missing dependency of any of these fails the build.
PG_NEEDED_MODULES = {"vector", "pg_trgm", "plpgsql", "dict_snowball", "libpq", "libpgtypes", "libecpg"}


def vendor_linux_libs(pgsql: Path) -> list[str]:
    """Copy the shared libraries Postgres links from the build host into pgsql/lib ($ORIGIN/../lib RUNPATH)."""
    lib = pgsql / "lib"
    elves = [p for p in (pgsql / "bin").iterdir() if p.is_file()] + list(lib.rglob("*.so*"))
    copied: set[str] = set()
    for elf in elves:
        # Resolve as the launcher runs it: pgsql/lib first (LD_LIBRARY_PATH), so Postgres' own libraries resolve.
        out = subprocess.run(["ldd", str(elf)], capture_output=True, text=True,
                             env=dict(os.environ, LD_LIBRARY_PATH=str(lib))).stdout
        for line in out.splitlines():
            parts = line.split()
            if "not found" in line:
                if elf.parent == lib and elf.name.split(".")[0] not in PG_NEEDED_MODULES:
                    log(f"dropped {elf.name}: needs {parts[0]}")  # an optional contrib module NMOS does not use
                    elf.unlink()
                    break
                raise SystemExit(f"{elf.name} needs {parts[0]}, which the build host does not have; install it")
            if "=>" not in parts or len(parts) < 3 or not parts[2].startswith("/"):
                continue
            name, path = parts[0], Path(parts[2])
            if name.startswith(LINUX_SYSTEM_LIBS) or (lib / name).exists() or str(path).startswith(str(pgsql)):
                continue
            shutil.copy2(path.resolve(), lib / name)
            copied.add(name)
    # RUNPATH covers only direct dependencies; the launcher puts pgsql/lib on LD_LIBRARY_PATH for the indirect ones
    # (libxml2 → ICU, gssapi → krb5).
    return sorted(copied)


def install_sidecar(python: Path, work: Path) -> None:
    sidecar = REPO / "apps" / "sidecar"
    req = work / "requirements.txt"
    subprocess.run(["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--no-hashes", "-q", "-o", str(req)],
                   cwd=sidecar, check=True)
    subprocess.run(["uv", "pip", "install", "-q", "--python", str(python), "-r", str(req)], check=True)
    subprocess.run(["uv", "pip", "install", "-q", "--python", str(python), "--no-deps", str(sidecar)], check=True)


PG_KEEP_BINS = {"initdb", "pg_ctl", "postgres", "pg_dump", "pg_restore", "pg_controldata"}


def prune_pg_bins(pgsql: Path) -> None:
    """Keep only what the launcher and a backup need; psql and friends pull in readline and more."""
    for p in (pgsql / "bin").iterdir():
        if p.is_file() and p.name.removesuffix(".exe") not in PG_KEEP_BINS and p.suffix != ".dll":
            p.unlink()
    # Procedural languages link a specific system Python/Perl/Tcl; NMOS uses none of them.
    for p in (pgsql / "lib").iterdir():
        if any(pl in p.name for pl in ("plpython", "plperl", "pltcl")):
            p.unlink()


def prune(stage: Path, windows: bool) -> None:
    pgsql = stage / "pgsql"
    for rel in ("include", "share/doc", "share/man"):
        shutil.rmtree(pgsql / rel, ignore_errors=True)
    for pattern in ("*.a", "*.lib") if not windows else ("*.a",):
        for p in (pgsql / "lib").rglob(pattern):
            p.unlink()
    for p in (stage / "python").rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    for rel in ("lib/python3.12/test", "Lib/test", "lib/python3.12/idlelib", "Lib/idlelib",
                "lib/python3.12/tkinter", "Lib/tkinter"):
        shutil.rmtree(stage / "python" / rel, ignore_errors=True)


def du(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=TARGETS, required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", type=Path, default=REPO / "dist-native")
    ap.add_argument("--cache", type=Path, default=REPO / ".native-cache")
    a = ap.parse_args()

    triple = TARGETS[a.target]
    windows = a.target.startswith("win")
    name = f"NMOS-v{a.version}-{a.target}"
    a.cache.mkdir(parents=True, exist_ok=True)
    work = a.cache / f"work-{a.target}"
    work.mkdir(exist_ok=True)
    stage = a.out / name
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    t0 = time.monotonic()

    pbs = fetch(f"https://github.com/astral-sh/python-build-standalone/releases/download/{PBS_TAG}/"
                f"cpython-{PY_VERSION}%2B{PBS_TAG}-{triple}-install_only_stripped.tar.gz", a.cache)
    pg = fetch(f"https://github.com/theseus-rs/postgresql-binaries/releases/download/{PG_VERSION}/"
               f"postgresql-{PG_VERSION}-{triple}.tar.gz", a.cache)
    extract_into(pbs, stage / "python")
    extract_into(pg, stage / "pgsql")
    python = stage / "python" / ("python.exe" if windows else "bin/python3")

    build_pgvector(stage / "pgsql", work, windows)
    prune_pg_bins(stage / "pgsql")
    if a.target.startswith("linux"):
        log(f"vendored: {', '.join(vendor_linux_libs(stage / 'pgsql'))}")
    install_sidecar(python, work)
    prune(stage, windows)

    shutil.copytree(REPO / "migrations", stage / "migrations")
    (stage / "plugin").mkdir()
    shutil.copy2(REPO / "adapters/pocketrisu-plugin/dist/nmos-pocketrisu.js", stage / "plugin")
    launcher = Path(__file__).parent / "launcher"
    shutil.copy2(launcher / "nmos_launcher.py", stage)
    if windows:
        shutil.copy2(launcher / "NMOS.bat", stage)
    else:
        shutil.copy2(launcher / "start.sh", stage)
        (stage / "start.sh").chmod(0o755)
    shutil.copy2(REPO / ".env.example", stage / ".env.example")
    shutil.copy2(REPO / "LICENSE", stage)

    if windows:
        archive = a.out / f"{name}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for p in sorted(stage.rglob("*")):
                z.write(p, p.relative_to(a.out))
    else:
        archive = a.out / f"{name}.tar.gz"
        with tarfile.open(archive, "w:gz") as t:
            t.add(stage, arcname=name)
    log(f"unpacked {du(stage) / 1e6:.0f} MB (python {du(stage / 'python') / 1e6:.0f}, "
        f"pgsql {du(stage / 'pgsql') / 1e6:.0f}); archive {archive.stat().st_size / 1e6:.0f} MB; "
        f"{time.monotonic() - t0:.0f} s")
    print(archive)


if __name__ == "__main__":
    main()
