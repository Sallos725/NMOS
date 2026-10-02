# Phase 23 — NMOS without Docker: a bundle for each PocketRisu portable target

> **Status: approved 2026-10-01 (Q6 as amended below; every other proposed answer), complete 2026-10-02 after
> the owner's Windows and Mac checks; not released.**
> Not a roadmap stage: the owner pulled it in before 1.0 by name (2026-10-01, an exception to R7 in
> `docs/ROADMAP-1.0.md`), tracked as AGE-29. The spike behind it is on the
> branch `spike/native-bundle` (`tools/native/`, CI run 36807358696).

## Decided (owner, 2026-10-01)

- PocketRisu ships portable packages for **win-x64, macos-arm64, linux-x64 and linux-arm64** and a Termux build, as
  well as Docker. NMOS installs only with Docker Compose, so a PocketRisu user without Docker cannot attach NMOS. This
  phase gives the four portable targets an NMOS that runs without Docker; Termux follows separately (Q2). The Docker
  install stays as it is.
- **Windows ships as PocketRisu does: a zip with a double-click `NMOS.exe`** that sits in the notification area. No
  installer, no `.msi`. `NMOS.bat` and `start.sh` stay for servers and advanced users only.
- **Storage stays PostgreSQL** (`ARCHITECTURE.md` §2, invariant 9): each bundle carries a portable PostgreSQL 16 with `pg_trgm`
  and `pgvector`, a standalone Python with the sidecar, the migrations and the plugin of the same build.
- **Dashboard refresh (owner, 2026-10-02, AGE-29):** add a manual Refresh button if it is a small change. The
  standalone first page submits a read-only GET, keeping its token and language, to read the current status again.

## What the spike measured

| Target | Archive | First start | Checked |
|---|---|---|---|
| linux-x64 | 71 MB | 3–4 s | the sidecar test suite (766) against the bundle's PostgreSQL; Debian 12, Ubuntu 22.04 and 24.04 |
| linux-arm64 | 67 MB | — | CI smoke |
| macos-arm64 | 45 MB | 2.3 s | the sidecar test suite (766) against the bundle's PostgreSQL |
| win-x64 | 71 MB | 13–18 s | `NMOS.exe` → tray, quit stops PostgreSQL; under a Korean folder |

The smoke on every target: first start (initdb and every migration), `/v1/health`, a `pgvector` distance and a Korean
`pg_trgm` similarity, a clean stop that also stops PostgreSQL, a second start on the same data. PocketRisu's own
packages are 129–144 MB.

Findings the phase builds on:

1. **The cluster needs a UTF-8 ctype.** Under the C locale `pg_trgm` makes no trigrams for Hangul and Korean lexical
   recall finds nothing: five suite tests that go through lexical recall failed under C and pass with a UTF-8 locale.
2. **macOS libc does not call Hangul a letter.** It puts Hangul and kana in its *phonogram* class and Han in
   *ideogram*, never *alpha*, so stock `pg_trgm` makes no Korean trigrams on macOS under any locale or PostgreSQL 16–18
   (probed). The macOS bundle builds `pg_trgm` with those classes counted as word characters, which is what glibc
   does on Linux; with it the suite passes on macOS.
3. **PostgreSQL on Windows cannot run from a non-ASCII folder.** It reads its own location through the ANSI code page,
   and initdb writes the install path into UTF-8 SQL (`invalid byte sequence for encoding "UTF8"`). The launcher runs
   it through the folder's 8.3 short name, which the system drive has by default; where a drive has no short names it
   stops with a message to move the folder to an English-only path.
4. **The Linux PostgreSQL binaries link the system's ICU, OpenSSL and libxml2.** The bundle carries them, built on
   Ubuntu 22.04: it needs glibc 2.35 or later (Ubuntu 22.04+, Debian 12, Raspberry Pi OS bookworm; not RHEL 9).
5. Windows' first start is slow (initdb 8 s of it, probably the antivirus scanning new files); later starts take 1–2 s.

## Questions and proposed answers

| # | Question | Proposed answer | Alternatives |
|---|---|---|---|
| Q1 | Which targets? | **The four PocketRisu portable targets** (win-x64, macos-arm64, linux-x64, linux-arm64). PocketRisu ships no Windows ARM or Intel mac package; those users keep Docker. | Add Intel mac (theseus-rs builds exist). |
| Q2 | Termux? | **Not in this phase, and not a 1.0 condition (owner, 2026-10-01).** PocketRisu builds from source on the phone; NMOS would need PostgreSQL, `pgvector` and the Python wheels built there too, on a 2 GB phone that also runs PocketRisu. A follow-up once the four bundles are out. | A build script in this phase, checked in a Termux container. |
| Q3 | Where does the data live? | **`data/` inside the bundle folder**, as PocketRisu keeps `save/`; `NMOS_DATA_DIR` moves it. **macOS (owner, 2026-10-01, step 4): `~/Library/Application Support/NMOS/`.** An app downloaded and opened with Open Anyway runs from a random read-only copy (App Translocation, which PocketRisu's `xattr -cr` turns off), so a folder beside the app is neither stable nor writable. An update unpacks the new version and moves `data/` over (documented; the launcher refuses a `data/` written by a newer NMOS). | A per-user folder (`%LOCALAPPDATA%\NMOS`, `~/Library/Application Support/NMOS`). |
| Q4 | A later PostgreSQL major? | **The bundles stay on PostgreSQL 16.** A move to a later major goes through the NMOS Archive (ADR 0050: export in the old bundle, restore in the new), which does not depend on the server version. | Ship `pg_upgrade` with the old binaries. |
| Q5 | The supply chain? | **Every download pinned by SHA-256** in `tools/native/sources.json` (Python, PostgreSQL binaries and source, `pgvector` at a commit); a mismatch fails the build. | Pin versions only (the spike). |
| Q6 | macOS? | **A menu-bar `NMOS.app`** (no Dock icon) with the Windows menu, from a small Swift program built in CI that starts and stops the services. **Owner, 2026-10-01: no `xattr -cr`.** Python and PostgreSQL go inside the app and every binary in it is signed ad hoc (free, no Apple account), so a downloaded copy is "from an unidentified developer", not "damaged": the user allows it once in System Settings → Privacy & Security → Open Anyway. `xattr -cr` stays in the docs as the fallback. | Developer ID signing and notarization (Apple Developer Program, $99 a year; a plain double-click); only `start.sh`; PyObjC (a new runtime package). |
| Q7 | The tray menu? | **Status, copy the sidecar URL, open the dashboard, open the plugin folder, open the log folder, start at login, quit** (quit stops PostgreSQL). | The spike's menu without a dashboard or start at login. |
| Q8 | The dashboard? | **A read-only page the sidecar serves at `/dashboard`** (step 5: the Inspector's first page, which already showed the plugin build, the generations and the job counts, with the version and the recent job errors added; `/dashboard` leads there, keeping the token and language): version and plugin-build match, the LLM and embedding settings in use (no keys), queued and failed jobs, the last errors. Settings stay in the PocketRisu panel. It follows the sidecar's auth: with `NMOS_AUTH_TOKEN` set it asks for the token. | No dashboard (the menu only); settings editable there too. |
| Q9 | Release? | **`release.yml` builds the four bundles and attaches them to the GitHub release** (`NMOS-vX-<target>.zip` / `.tar.gz`; **macOS a `.dmg`** (owner, 2026-10-01, step 4): `NMOS.app` beside an Applications link, so it is dragged there and installed as a Mac app is, out of App Translocation) after their smokes pass; a pull request touching `tools/native/` runs the smokes. `:edge` stays Docker-only. | Bundles on every `main` merge too. |
| Q10 | Ports? | **The sidecar on 127.0.0.1:8790 as in Docker; PostgreSQL on 127.0.0.1:54390**, both changeable in `.env`; a port in use stops the start with a message naming it. | Pick a free port automatically (the plugin's URL would change). |

## Goal

A PocketRisu user downloads one archive for their system, unpacks it, starts NMOS with a double-click (or `start.sh`),
installs the plugin from the bundle and sets the URL shown in the tray: memory works as with Docker, with no Docker.

## In scope (Phase 23)

1. **The bundle builder and launcher** from the spike, hardened: pinned sources (Q5), one launcher per data folder,
   private password file, the newer-data refusal (Q3), the port check (Q10).
2. **Windows:** `NMOS.exe` with the plugin's icon, the tray (Q7), start at login (this `NMOS.exe` in the user's
   `HKCU\...\Run` key; amended in step 3: a Startup-folder shortcut made by `WScript.Shell` stores its paths in the
   ANSI code page and lost a Korean folder name), the short-path launch and its message.
3. **macOS:** the patched `pg_trgm` (finding 2) and the menu-bar app (Q6) in a `.dmg` (Q9): every binary in the app
   signed ad hoc, data in `~/Library/Application Support/NMOS/` (Q3), start at login with `SMAppService` (macOS 13+).
4. **Linux:** the vendored libraries (finding 4); `start.sh`, and a sample systemd user unit in the docs.
5. **The dashboard** (Q8) in the sidecar.
6. **CI and release** (Q9); README install sections per system; an ADR; `ARCHITECTURE.md` §6 names the bundles.

## Out of scope (Phase 23)

- Termux (Q2); Windows ARM, Intel macOS; an installer or `.msi`; code signing.
- Editing settings outside the PocketRisu panel; a PostgreSQL major upgrade in place (Q4).
- Any change to the Docker install, the sidecar's behaviour other than the dashboard, or the plugin.

## Acceptance criteria

- [x] On each of the four targets, in CI: the bundle builds from pinned sources, and the smoke passes from a folder
      with a Korean name and a space (Windows: on the system drive; on a drive without short names, the move message).
      (`native.yml` run 36855596213 on step 6's head: the four builds and smokes from "한글 폴더", Windows under
      `C:/NMOS-CI` and its move message on drive D:.)
- [x] The sidecar test suite passes against the bundle's PostgreSQL on linux-x64, macos-arm64 and win-x64.
      (The same run's suite step on the three targets.)
- [x] Windows: `NMOS.exe` brings up the tray; quit stops the sidecar, the worker and PostgreSQL; a second `NMOS.exe`
      says it is running; start at login works after a sign-out and in.
      (The same run's tray smoke: the tray, start at login on, off and on, quit with the sidecar and PostgreSQL
      stopped, and NMOS started again from the Run entry's command, as a sign-in does. Not run there, accepted by
      the owner 2026-10-02 with the owner's check below: a second `NMOS.exe`'s notice (the launcher's own "already
      running" refusal is in the smoke), the worker checked stopped after a quit (it is after a stopped start), and
      a real sign-out and in.)
- [x] macOS: `NMOS.app` brings up the menu-bar item with the same behaviour; `codesign --verify --deep --strict`
      passes on the app in CI.
      (The same run's app smoke from the `.dmg`: the menu's running state, `codesign` while running, the login item
      on and off, quit with the sidecar and PostgreSQL stopped. Not run there, accepted by the owner 2026-10-02 as for
      Windows: a second app's notice, the worker checked stopped after a quit, and a real login.)
- [x] An update keeps the data: version N's `data/` moved into N+1 starts and migrates; N+1's data refused by N.
      (The same run's smoke on the four targets: the data of the version before migrates with what it held, and data
      with a migration this bundle does not ship is refused as written by a newer NMOS.)
- [x] Every existing test passes; the Docker install, its images and `:edge` are unchanged.
      (`ci.yml` green on `main` after step 6, run 36857825784; steps 2–6 change no Dockerfile, compose file or image
      step: `release.yml` only adds the bundles beside the images.)
- [x] **The owner's check** (evidence boundary, `AGENTS.md` §2): on a Windows PC with PocketRisu's portable package,
      unpack, start, install the plugin from the bundle, chat, and see recall in the panel; on the owner's Mac, the
      same with the app downloaded through a browser and allowed once with Open Anyway, no Terminal (if PostgreSQL or
      Python inside it is still blocked, stop and ask: notarization or `xattr -cr` is the owner's call).

## Steps (one pull request each)

1. This document, approved; AGENTS §2, STATUS and the R7 note in `docs/ROADMAP-1.0.md` name Phase 23.
2. Builder, launcher, pinned sources and the CI smokes for the four targets (from the spike).
3. Windows: `NMOS.exe`, the tray, start at login.
4. macOS: the menu-bar app.
5. The dashboard.
6. Release workflow, README, ADR, `ARCHITECTURE.md`; the owner's check; Phase 23 complete.

A merge reaches `:edge` as usual; the bundles first ship with the next tagged release (`AGENTS.md` §13).

## Owner check (2026-10-02)

The owner reported on Windows and macOS: memory injection works, PostgreSQL shuts down successfully, and the data
remains after restarting. These are the owner's reports, not new agent-run smokes or fixtures; the OS and PocketRisu
versions and bundle builds were not provided. The Windows dashboard lacked a Refresh button (the small addition
above). The owner also explicitly confirmed that the Mac app was downloaded through a browser, allowed with
Open Anyway and run successfully without Terminal. The last owner-check boundary is met: Phase 23 is complete,
not released. The reports do not establish start at login after a sign-out and in, nor a second start's notice;
the owner accepted those on the CI evidence above (acceptance criteria, Windows and macOS).

## Stop conditions

Stop and ask the owner when:

- the sidecar suite fails only against a bundle's PostgreSQL;
- a bundle needs a PostgreSQL change beyond the macOS word-character patch;
- a bundle needs a new runtime package for the sidecar, or an archive passes 150 MB;
- the owner's check finds the plugin cannot reach the bundled sidecar from the portable PocketRisu.
