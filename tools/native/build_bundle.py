"""Build an NMOS bundle for one PocketRisu portable target (Phase 23). Run it on that target's OS.

    python tools/native/build_bundle.py --target linux-x64 --version 0.3.0

Needs uv, a C toolchain for pgvector (make + cc; on Windows nmake from an MSVC developer shell), git and network.
Every download is pinned in sources.json and checked before use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES = json.loads((Path(__file__).parent / "sources.json").read_text(encoding="utf-8"))

TARGETS = {
    "linux-x64": "x86_64-unknown-linux-gnu",
    "linux-arm64": "aarch64-unknown-linux-gnu",
    "macos-arm64": "aarch64-apple-darwin",
    "win-x64": "x86_64-pc-windows-msvc",
}


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(url: str, digest: str, cache: Path) -> Path:
    """Download url into the cache once; the file is checked against its pinned SHA-256 every time it is used."""
    dest = cache / url.rsplit("/", 1)[1].replace("%2B", "+")
    if not dest.exists():
        log(f"download {url}")
        tmp = dest.with_suffix(".part")
        with urllib.request.urlopen(url) as r, tmp.open("wb") as f:
            shutil.copyfileobj(r, f)
        tmp.rename(dest)
    got = sha256(dest)
    if got != digest:
        dest.unlink()
        raise SystemExit(f"{url}: SHA-256 {got} is not the pinned {digest} (tools/native/sources.json)")
    return dest


def source(name: str, triple: str | None = None) -> tuple[str, str]:
    """(url, sha256) of a pinned download, for a target triple when it has one per target."""
    s = SOURCES[name]
    url = s["url"].format(triple=triple, **{k: v for k, v in s.items() if isinstance(v, str)})
    return url, s["sha256"][triple] if triple else s["sha256"]


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
    pin = SOURCES["pgvector"]
    src = work / "pgvector"
    if not src.exists():
        subprocess.run(["git", "-c", "advice.detachedHead=false", "clone", "-q", "--depth", "1", "-b", pin["tag"],
                        pin["repo"], str(src)], check=True)
    # safe.directory: a cached clone made by another user (the build image runs as root over a host-owned cache).
    head = subprocess.run(["git", "-c", "safe.directory=*", "rev-parse", "HEAD"], cwd=src, capture_output=True,
                          text=True, check=True).stdout.strip()
    if head != pin["commit"]:
        raise SystemExit(f"pgvector {pin['tag']} is {head}, not the pinned {pin['commit']} (tools/native/sources.json)")
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
        # With PG_CONFIG, or clean fails and a cached clone keeps objects built elsewhere (another glibc).
        subprocess.run(["make", "-s", "clean", *args], cwd=src, check=True)
        subprocess.run(["make", "-s", *args], cwd=src, check=True)
        subprocess.run(["make", "-s", "install", *args], cwd=src, check=True)
        if sys.platform == "darwin":
            build_macos_pg_trgm(pgsql, work, work.parent, args)


# macOS libc puts Han, Hangul and kana in the ideogram/phonogram classes instead of alpha (glibc: alpha), so stock
# pg_trgm makes no trigrams for Korean there and lexical recall finds nothing. The bundle's pg_trgm counts them as word
# characters, which is what the Linux/Docker build does.
TRGM_H_OLD = "#define ISWORDCHR(c, len)\t(t_isalnum_with_len(c, len))"
TRGM_H_NEW = ("extern bool nmos_ideographic(const char *c, int len);\n"
              "#define ISWORDCHR(c, len)\t(t_isalnum_with_len(c, len) || nmos_ideographic(c, len))")
TRGM_OP_ADD = """
/* NMOS bundle (macOS): Han, Hangul and kana are word characters, as glibc's iswalnum says on Linux. */
#include <wctype.h>
#include "utils/pg_locale.h"

bool
nmos_ideographic(const char *c, int len)
{
\twchar_t\t\tw[2];

\tif (len < 2 || char2wchar(w, 2, c, len, NULL) != 1)
\t\treturn false;
\treturn iswideogram((wint_t) w[0]) || iswphonogram((wint_t) w[0]);
}
"""


def build_macos_pg_trgm(pgsql: Path, work: Path, cache: Path, make_args: list[str]) -> None:
    major_minor = SOURCES["postgresql_source"]["version"]
    src_tar = fetch(*source("postgresql_source"), cache)
    src = work / "pg_trgm"
    shutil.rmtree(src, ignore_errors=True)
    prefix = f"postgresql-{major_minor}/contrib/pg_trgm/"
    with tarfile.open(src_tar, "r:bz2") as t:
        members = [m for m in t.getmembers() if m.name.startswith(prefix)]
        t.extractall(work / "pgsrc", members=members, filter="tar")
    (work / "pgsrc" / prefix).rename(src)
    header = (src / "trgm.h").read_text()
    if TRGM_H_OLD not in header:
        raise SystemExit("pg_trgm/trgm.h changed; review the macOS word-character patch")
    (src / "trgm.h").write_text(header.replace(TRGM_H_OLD, TRGM_H_NEW))
    with (src / "trgm_op.c").open("a") as f:
        f.write(TRGM_OP_ADD)
    subprocess.run(["make", "-s", "USE_PGXS=1", *make_args], cwd=src, check=True)
    subprocess.run(["make", "-s", "USE_PGXS=1", "install", *make_args], cwd=src, check=True)


# glibc itself and the dynamic loader come from the user's system; everything else Postgres links is copied in.
LINUX_SYSTEM_LIBS = ("linux-vdso", "ld-linux", "libc.so", "libm.so", "libdl.so", "libpthread.so", "librt.so",
                     "libresolv.so")


# Server modules NMOS loads (migrations, initdb); a missing dependency of any of these fails the build.
PG_NEEDED_MODULES = {"vector", "pg_trgm", "plpgsql", "dict_snowball", "libpq", "libpgtypes", "libecpg"}


def vendor_linux_libs(pgsql: Path) -> dict[str, Path]:
    """Copy the shared libraries Postgres links from the build host into pgsql/lib ($ORIGIN/../lib RUNPATH)."""
    lib = pgsql / "lib"
    elves = [p for p in (pgsql / "bin").iterdir() if p.is_file()] + list(lib.rglob("*.so*"))
    copied: dict[str, Path] = {}
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
            copied[name] = path
    # RUNPATH covers only direct dependencies; the launcher puts pgsql/lib on LD_LIBRARY_PATH for the indirect ones
    # (libxml2 → ICU, gssapi → krb5).
    return copied


def check_linux_packages(copied: dict[str, Path]) -> None:
    """The vendored libraries' Ubuntu packages must be the versions pinned for this architecture (sources.json)."""
    arch = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True, check=True).stdout.strip()
    seen: dict[str, str] = {}
    for path in copied.values():
        owner = subprocess.run(["dpkg", "-S", str(path)], capture_output=True, text=True)
        if owner.returncode:  # /lib is a symlink to /usr/lib on Ubuntu; dpkg knows one spelling
            owner = subprocess.run(["dpkg", "-S", str(path.resolve())], capture_output=True, text=True, check=True)
        package = owner.stdout.split(":")[0].strip()
        seen[package] = subprocess.run(["dpkg-query", "-W", "-f=${Version}", f"{package}:{arch}"], capture_output=True,
                                       text=True, check=True).stdout.strip()
    pinned = SOURCES["linux_build"]["packages"].get(arch, {})
    if seen != pinned:
        raise SystemExit(f"vendored Ubuntu packages for {arch} differ from sources.json linux_build.packages.{arch}:\n"
                         + json.dumps(dict(sorted(seen.items())), indent=2))
    log(f"vendored packages match the pins ({len(seen)})")


def build_windows_tray(stage: Path, work: Path) -> None:
    """NMOS.exe (the plugin's icon; starts pythonw nmos_tray.py) and the tray. Needs an MSVC developer shell."""
    src = Path(__file__).parent / "windows"
    shutil.copy2(src / "nmos_tray.py", stage)
    subprocess.run([sys.executable, str(Path(__file__).parent / "make_icon.py"), str(stage / "nmos.ico")], check=True)
    build = work / "exe"
    shutil.rmtree(build, ignore_errors=True)
    build.mkdir()
    for name in ("nmos_exe.c", "nmos.rc"):
        shutil.copy2(src / name, build)
    shutil.copy2(stage / "nmos.ico", build)
    subprocess.run(["rc", "/nologo", "/fo", "nmos.res", "nmos.rc"], cwd=build, check=True)
    subprocess.run(["cl", "/nologo", "/O2", "/utf-8", "/W3", "nmos_exe.c", "nmos.res",
                    "/link", "/SUBSYSTEM:WINDOWS", "/OUT:NMOS.exe"], cwd=build, check=True)
    shutil.copy2(build / "NMOS.exe", stage)


MACHO = (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xfe\xed\xfa\xcf")
BUNDLE_ID = "io.github.sallos725.nmos"


def apple_version(version: str) -> str:
    m = re.match(r"\d+(\.\d+){0,2}", version)
    return m.group(0) if m else "0.0.0"


def build_macos_app(stage: Path, work: Path, version: str) -> Path:
    """NMOS.app (PHASE-23 Q6): the bundle in Contents/Resources, the menu-bar program in Contents/MacOS, every Mach-O
    file in it signed ad hoc and then the app, so a download is "from an unidentified developer" (Open Anyway) and not
    "damaged". The app is sealed: data, .env and log live in ~/Library/Application Support/NMOS (Q3)."""
    app = stage.parent / "NMOS.app"
    shutil.rmtree(app, ignore_errors=True)
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    shutil.move(str(stage), str(contents / "Resources"))
    res = contents / "Resources"
    # Nothing can be cached inside a sealed app at run time, so the bytecode is compiled now (errors: files in
    # packages' test data that are not Python 3, harmless).
    subprocess.run([str(res / "python" / "bin" / "python3"), "-m", "compileall", "-q", "-j", "0",
                    str(res / "python" / "lib")], check=False, stdout=subprocess.DEVNULL)
    src = Path(__file__).parent / "macos"
    subprocess.run(["swiftc", "-O", "-target", "arm64-apple-macos13.0", str(src / "NMOSApp.swift"),
                    "-o", str(contents / "MacOS" / "NMOS")], check=True)
    iconset = work / "nmos.iconset"
    shutil.rmtree(iconset, ignore_errors=True)
    subprocess.run([sys.executable, str(Path(__file__).parent / "make_icon.py"), "--iconset", str(iconset)], check=True)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(res / "nmos.icns")], check=True)
    with (contents / "Info.plist").open("wb") as f:
        plistlib.dump({
            "CFBundleName": "NMOS", "CFBundleDisplayName": "NMOS", "CFBundleIdentifier": BUNDLE_ID,
            "CFBundleExecutable": "NMOS", "CFBundleIconFile": "nmos", "CFBundlePackageType": "APPL",
            # Apple's version keys take dotted numbers only ("0.3.0-beta.1" → "0.3.0"); the full one is NMOSVersion.
            "CFBundleShortVersionString": apple_version(version), "CFBundleVersion": apple_version(version),
            "NMOSVersion": version,
            "LSMinimumSystemVersion": "13.0", "LSUIElement": True,  # a menu-bar item, no Dock icon
            "NSHumanReadableCopyright": "MIT License",
            # App Transport Security blocks plain http by default; the menu asks the sidecar on 127.0.0.1 over http.
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        }, f)
    signed = 0
    for p in sorted(contents.rglob("*")):
        if p.is_file() and not p.is_symlink():
            with p.open("rb") as f:
                if f.read(4) in MACHO:
                    subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(p)], check=True,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    signed += 1
    subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)], check=True)
    log(f"NMOS.app: {signed} Mach-O files signed ad hoc, then the app")
    return app


def build_dmg(app: Path, dmg: Path) -> Path:
    """NMOS.app beside a link to /Applications: dragged there it is installed as a Mac app is, out of App
    Translocation (PHASE-23 Q9)."""
    staging = app.parent / "dmg"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    shutil.move(str(app), str(staging / "NMOS.app"))
    (staging / "Applications").symlink_to("/Applications")
    dmg.unlink(missing_ok=True)
    subprocess.run(["hdiutil", "create", "-quiet", "-volname", "NMOS", "-srcfolder", str(staging), "-ov",
                    "-format", "UDZO", str(dmg)], check=True)
    return dmg


def install_sidecar(python: Path, work: Path) -> None:
    """The sidecar's dependencies from uv.lock, each checked against the lock's SHA-256 and taken only as a built
    wheel (no build step that could fetch an unpinned build backend); the sidecar itself is pure Python and is copied
    in as source, so its own build backend (hatchling) is never downloaded either."""
    sidecar = REPO / "apps" / "sidecar"
    req = work / "requirements.txt"
    subprocess.run(["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "-q", "-o", str(req)],
                   cwd=sidecar, check=True)
    subprocess.run(["uv", "pip", "install", "-q", "--python", str(python), "--require-hashes", "--only-binary", ":all:",
                    "-r", str(req)], check=True)
    purelib = subprocess.run([str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                             capture_output=True, text=True, check=True).stdout.strip()
    shutil.copytree(sidecar / "src" / "nmos_sidecar", Path(purelib) / "nmos_sidecar",
                    ignore=shutil.ignore_patterns("__pycache__"))


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
    ap.add_argument("--check-packages", action="store_true",
                    help="Linux, inside the pinned build image (build_linux.py): fail unless the vendored libraries "
                         "come from the pinned package versions")
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

    pbs = fetch(*source("python", triple), a.cache)
    pg = fetch(*source("postgresql", triple), a.cache)
    extract_into(pbs, stage / "python")
    extract_into(pg, stage / "pgsql")
    python = stage / "python" / ("python.exe" if windows else "bin/python3")

    build_pgvector(stage / "pgsql", work, windows)
    prune_pg_bins(stage / "pgsql")
    if a.target.startswith("linux"):
        copied = vendor_linux_libs(stage / "pgsql")
        log(f"vendored: {', '.join(sorted(copied))}")
        if a.check_packages:
            check_linux_packages(copied)
    install_sidecar(python, work)
    prune(stage, windows)

    shutil.copytree(REPO / "migrations", stage / "migrations")
    (stage / "plugin").mkdir()
    shutil.copy2(REPO / "adapters/pocketrisu-plugin/dist/nmos-pocketrisu.js", stage / "plugin")
    launcher = Path(__file__).parent / "launcher"
    shutil.copy2(launcher / "nmos_launcher.py", stage)
    if windows:
        shutil.copy2(launcher / "NMOS.bat", stage)  # for advanced users; NMOS.exe is the one to double-click
        build_windows_tray(stage, work)
    else:
        shutil.copy2(launcher / "start.sh", stage)
        (stage / "start.sh").chmod(0o755)
    shutil.copy2(REPO / ".env.example", stage / ".env.example")
    shutil.copy2(REPO / "LICENSE", stage)

    sizes = (f"unpacked {du(stage) / 1e6:.0f} MB (python {du(stage / 'python') / 1e6:.0f}, "
             f"pgsql {du(stage / 'pgsql') / 1e6:.0f})")
    if a.target.startswith("macos"):
        archive = build_dmg(build_macos_app(stage, work, a.version), a.out / f"{name}.dmg")
    elif windows:
        archive = a.out / f"{name}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for p in sorted(stage.rglob("*")):
                z.write(p, p.relative_to(a.out))
    else:
        archive = a.out / f"{name}.tar.gz"
        with tarfile.open(archive, "w:gz") as t:
            t.add(stage, arcname=name)
    log(f"{sizes}; archive {archive.stat().st_size / 1e6:.0f} MB; {time.monotonic() - t0:.0f} s")
    print(archive)


if __name__ == "__main__":
    main()
