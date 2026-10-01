"""Spike diagnostic: which initdb locales give pg_trgm Hangul trigrams on this OS? Run with the bundle's Python:

    <python> tools/native/locale_probe.py <bundle> <locale> [<locale> ...]

A locale is a libc name, "icu:<icu locale>" or "builtin:<builtin locale>" (PostgreSQL 17+). NMOS_PROBE_PGSQL points
at another PostgreSQL tree to probe instead of the bundle's.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
bundle = Path(sys.argv[1]).resolve()
exe = ".exe" if os.name == "nt" else ""
binp = Path(os.environ.get("NMOS_PROBE_PGSQL") or bundle / "pgsql") / "bin"
port = 54391


def locale_args(loc: str) -> list[str]:
    provider, _, name = loc.rpartition(":")
    if provider == "icu":
        return ["--locale-provider=icu", f"--icu-locale={name}", "--locale=en_US.UTF-8"]
    if provider == "builtin":
        return ["--locale-provider=builtin", f"--builtin-locale={name}", "--locale=en_US.UTF-8"]
    return [f"--locale={name}"]


for loc in sys.argv[2:]:
    with tempfile.TemporaryDirectory() as tmp:
        pgdata, pwfile = Path(tmp) / "pg", Path(tmp) / "pw"
        pw = secrets.token_hex(8)
        pwfile.write_text(pw)
        r = subprocess.run([str(binp / f"initdb{exe}"), "-D", str(pgdata), "-U", "nmos", f"--pwfile={pwfile}",
                            "--auth=scram-sha-256", "--encoding=UTF8", *locale_args(loc)], capture_output=True, text=True)
        if r.returncode:
            print(f"{loc!r}: initdb failed: {r.stderr.strip().splitlines()[-1]}")
            continue
        with (pgdata / "postgresql.conf").open("a") as f:
            f.write(f"\nport = {port}\nlisten_addresses = '127.0.0.1'\nunix_socket_directories = ''\n")
        subprocess.run([str(binp / f"pg_ctl{exe}"), "-D", str(pgdata), "-l", str(Path(tmp) / "log"), "-w", "start"],
                       check=True, capture_output=True)
        try:
            with psycopg.connect(f"postgresql://nmos:{pw}@127.0.0.1:{port}/postgres") as c:
                c.execute("CREATE EXTENSION pg_trgm")
                row = c.execute("SELECT version(), similarity('하나와 카이토', '하나랑 카이토'), show_trgm('등대')"
                                " FROM pg_database WHERE datname = 'postgres'").fetchone()
            print(f"{loc!r} on {row[0].split(' on ')[0]}: similarity={row[1]} trgm={row[2]}")
        finally:
            subprocess.run([str(binp / f"pg_ctl{exe}"), "-D", str(pgdata), "-m", "fast", "-w", "stop"],
                           capture_output=True)
