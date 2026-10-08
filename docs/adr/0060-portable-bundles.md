# 0060 — NMOS without Docker: a portable bundle for each PocketRisu portable target

Status: accepted, 2026-10-01. Phase 23 (`docs/phases/PHASE-23.md` Q1–Q10, approved by the owner; AGE-29), an
exception to R7 the owner granted before 1.0. Adds a second way to install; the Docker install, its images and `:edge`
are unchanged. No migration, no plugin change, no sidecar change but the dashboard (step 5).

## Context

PocketRisu ships portable packages for win-x64, macos-arm64, linux-x64 and linux-arm64 as well as Docker. NMOS
installed only with Docker Compose, so a PocketRisu user without Docker could not attach it, and the owner did not want
to send Windows users to Docker Desktop or WSL. Storage stays PostgreSQL (`ARCHITECTURE.md` §2, invariant 9): the hard
part of a Docker-free NMOS is a PostgreSQL with `pg_trgm` and `pgvector` that runs from a user's folder, not Python.

## Decision

1. **One archive per target** (Q1), built by `tools/native/build_bundle.py` (Linux inside a digest-pinned Ubuntu 22.04
   image, `build_linux.py`): a standalone CPython with the sidecar installed from `uv.lock`'s hashes, a portable
   PostgreSQL 16 with `pg_trgm` and `pgvector`, the migrations, the plugin of the same build, and a launcher. Every
   download is pinned by SHA-256 in `tools/native/sources.json` (Q5); the Linux libraries a bundle carries are checked
   against pinned Ubuntu package versions.
2. **The launcher** (`nmos_launcher.py`) creates the cluster on first start (UTF-8 ctype: `pg_trgm` makes no Hangul
   trigrams under C), starts PostgreSQL on `127.0.0.1:54390` and the sidecar on `127.0.0.1:8790` (Q10; both from
   `.env`, the database port passed at every start so a changed one holds for existing data), applies the migrations,
   and starts the sidecar and the worker. It refuses, changing nothing: a second launcher on the same data, data with a
   migration it does not ship (written by a newer NMOS, Q3), a port in use. Quit stops PostgreSQL; a stop during a start
   leaves nothing running. The data and its generated database password are the user's only (Windows: by ACL).
3. **Per system:** Windows a zip with `NMOS.exe` in the notification area and start at login through the user's Run
   key (Q7, step 3), PostgreSQL run through the folder's 8.3 short name (it cannot take a non-ASCII path); macOS a
   menu-bar `NMOS.app` in a `.dmg`, every binary signed ad hoc and allowed once with Open Anyway (Q6), data in
   `~/Library/Application Support/NMOS/`, `pg_trgm` built to count Hangul, Han and kana as word characters as glibc
   does; Linux a tarball with `start.sh` (glibc 2.35+). `NMOS.bat` and `start.sh` stay for servers.
4. **Updates move the data** (Q3): on Windows/Linux, the new version is unpacked beside the old, `data/` moved in
   and the existing `.env` copied beside the new launcher; it migrates on start. On macOS, the app is replaced and
   the data and `.env` stay in Application Support. A bundle stays on PostgreSQL 16; a later major goes through the
   NMOS Archive (ADR 0050, Q4).
5. **Release** (Q9): `release.yml` calls `native.yml` with the tag's version; the four bundles are attached to the
   GitHub release only after, on each target, the smoke (from a folder with a Korean name and a space: first start,
   Korean `pg_trgm`, stop and restart, the three refusals, a stop during a start, an update) and, on linux-x64,
   macos-arm64 and win-x64, the sidecar suite against the bundle's PostgreSQL pass. `:edge` stays Docker-only. A pull
   request touching `tools/native/` runs the same workflow.
6. **The dashboard** (Q8) is the Inspector's first page at `/dashboard` with the version and recent job errors,
   read-only, behind the sidecar's auth; the tray and the menu bar open it.

## Amendment 1 (Phase 37, 2026-10-08; the owner, as proposed, Q6 amended)

Item 4 changes for Windows and Linux: **the data lives outside the bundle**, so an update is replacing the bundle
folder and nothing else. A user lost their database updating 0.2.0 → 0.3.0; the natural way to update a folder,
deleting the old one and unpacking the new one, deleted a bundle's database with it.

- **Where** (Q1, Q2): a per-user folder, Windows `%LOCALAPPDATA%\NMOS`, Linux `$XDG_DATA_HOME/nmos`
  (`~/.local/share/nmos`), macOS unchanged (`~/Library/Application Support/NMOS`, which the launcher now also uses
  when started without the app). It holds the cluster, the password, the logs, the lock and `.env`; a `.env` beside the
  launcher is read under it and copied into it once.
- **Adoption** (Q3, Q4): when the per-user folder has no database and `data/` beside the launcher has one, the first
  start moves it, under both folders' locks: on one drive a rename; across drives a copy compared file by file and
  started once before it is put in place. The old folder is renamed `data.moved` with a note, never deleted; any
  failure leaves it byte-identical and the per-user folder without a database. A database in both places refuses the
  start, changing neither.
- **Elsewhere on purpose** (Q5): `NMOS_DATA_DIR` keeps the last word, relative to the bundle (`data` is the old layout).
- **Windows paths PostgreSQL cannot open** (Q6): when the per-user path has non-ASCII letters and no 8.3 short name,
  the tray asks for a folder (`C:\NMOS-data` suggested, or a folder picker) and `NMOS.bat` asks in its console; the
  choice is a one-line pointer file in the per-user folder. Cancel starts nothing.

## Consequences

- A user without Docker unpacks one archive and double-clicks; the plugin and the URL are the same as with Docker.
- Termux, Windows ARM, Intel macOS, an installer and code signing are out (Termux after 1.0); a Windows user may see
  SmartScreen once, a Mac user Open Anyway once.
- A PostgreSQL patch or a Python update is a new pin in `sources.json`, built and smoke-tested on all four targets.
- Docker and bundle installs share the code, the migrations and the plugin: the sidecar suite runs on both.
