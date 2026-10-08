# Phase 37 — The bundle's data lives outside the bundle

> **Status: approved 2026-10-08 (the owner, as proposed; Q6 amended by the owner before the approval); complete
> 2026-10-08: every acceptance criterion met.** Steps 2–4 on #285, green on all four targets (on Windows: the smoke's
> adoption by rename and across C: → D:, the Q6 console question on a drive without short names, the tray, 1,241
> sidecar tests). Step 5, the owner's Windows check: a real v0.3.0 win-x64 bundle wrote a marker row, its `data/` and
> `.env` were moved into the new bundle as 0.3.0's guide said, `NMOS.exe` adopted them into the per-user folder (the
> log names the move and `data.moved`; `.env` copied), then the new bundle folder was deleted outright and a fresh one
> started on the same data with the row there. Not seen on a device, by choice: the Q6 and Q4 dialogs themselves and
> macOS (its app smoke covers it). A correction phase (AGENTS §7 item 5) found on a user's report, not a
> roadmap stage. It amends PHASE-23 Q3 (ADR 0060) for Windows and Linux; macOS already works this way. Aimed at
> `0.4.0`, so that the update to it is the last one where the data sits inside the folder being replaced. **High risk
> (AGENTS §14): stored data, upgrades.**

## Why now

A user reported that their NMOS database was gone after updating from 0.2.0 to 0.3.0. The cause is not confirmed. What
was checked (2026-10-08):

- **The Docker install could not have dropped it.** Both releases' compose files fix the project name (`name: nmos`), so
  the volume is the same whatever folder the file is run from. PostgreSQL stays 16 (`pgvector/pgvector:pg16`), and the
  two migrations 0.3.0 added only add columns and widen two checks.
- **0.3.0 introduced the portable bundles**, which start their own PostgreSQL in an empty `data/` folder. A Docker user
  who switched to a bundle sees no memory, while the data is still in the Docker volume. Nothing in the docs says that
  a switch does not carry the data over (the NMOS archive does).
- **The bundle keeps its data inside its own folder** on Windows and Linux (PHASE-23 Q3: `data/` beside the launcher, as
  PocketRisu keeps `save/`). The documented update unpacks the new version beside the old and moves `data/` over. The
  natural way to update a folder, deleting the old one and unpacking the new one, deletes the database with it. From
  0.4.0 on this is the likeliest way to lose everything.

This phase removes the last cause. The other two get their own small fixes (Out of scope).

## Questions and proposed answers

| | Question | Proposed answer | Alternative |
|---|---|---|---|
| Q1 | Where does the data live? | **A per-user folder outside the bundle:** Windows `%LOCALAPPDATA%\NMOS`, Linux `$XDG_DATA_HOME/nmos` (`~/.local/share/nmos` when unset), macOS unchanged (`~/Library/Application Support/NMOS`). It holds what `data/` holds now (the cluster, the database password, the logs, the lock). | `%APPDATA%` (Roaming): synced between PCs in a domain; wrong for a database. |
| Q2 | Where is `.env`? | **In the data folder**, as on macOS, so settings survive an update with the data. A `.env` beside the launcher is still read, under the data folder's; on the first start in the new folder it is copied there once if the data folder has none. The process environment wins over both, as now. | Leave `.env` beside the launcher: it is lost with the folder, and with it the token, ports and model settings the user set. |
| Q3 | What happens to data already beside the launcher? | **It is adopted on the first start:** when the per-user folder has no database and `data/` beside the launcher has one, the launcher moves it there. On the same drive this is a rename. Across drives it copies, starts PostgreSQL on the copy, checks it, then renames the old folder `data.moved` and writes a note in it; it never deletes. Any failure leaves the old folder as it was and stops with the reason. | Keep using `data/` beside the launcher when it exists: no move at all, but the trap stays for every current user. |
| Q4 | What if both hold a database? | **Refuse to start**, naming both folders and changing nothing. The user removes or renames one. Never choose silently. | Prefer the per-user one and warn: silently hides the other user's data. |
| Q5 | Can it still be portable on purpose (a USB drive)? | **Yes, with `NMOS_DATA_DIR`**, which keeps the last word. A relative path is resolved against the launcher's folder, so `NMOS_DATA_DIR=data` in the `.env` beside it keeps today's layout. | No portable mode. |
| Q6 | Windows: a user name with Korean letters on a drive without 8.3 short names? | **Amended by the owner: ask, do not refuse.** PostgreSQL on Windows cannot open a non-ASCII data path (`ascii_path`); NMOS itself can. The tray says so and opens a folder picker (Win32 through ctypes, as the tray already does), suggesting `C:\NMOS-data`; `NMOS.bat` asks in its console. The choice is written to a one-line pointer file in the per-user folder, which Python reads whatever its letters, so an update does not ask again. Cancel starts nothing. `NMOS_DATA_DIR` still wins (Q5). Linux and macOS take any path, so they never ask. C: has short names by default, so this is rare. | Refuse and tell the user to set `NMOS_DATA_DIR` in `.env` (the first proposal): it works, but asks the user to edit a file. |
| Q7 | Removing NMOS? | Deleting the bundle no longer deletes the memory. **The guide says where the data is and how to remove it**, and the tray's "open data folder" already follows the new folder (it reads `Services().data`). | An uninstall command: more surface for a portable folder. |

## In scope

- `tools/native/launcher/nmos_launcher.py`: the data folder per Q1, `.env` per Q2, the adoption per Q3, the refusal per
  Q4, `NMOS_DATA_DIR` per Q5, the Windows path per Q6 (the pointer file and the console question). The ACL step (`restrict_to_this_user`) and the lock run on the
  new folder as before.
- `tools/native/windows/nmos_tray.py`: the folder picker (Q6); it and `start.sh`/`NMOS.bat` otherwise only where they
  name `data/`.
- Tests and the bundle smoke (`tools/native/smoke.py`, `.github/workflows/native.yml`): a fresh start makes the per-user
  folder; data written beside the launcher by the version before is adopted and migrated with what it held (same drive,
  and a second temporary drive or mount where CI has one); both present is refused with nothing changed; a relative
  `NMOS_DATA_DIR` is honoured; a failed copy leaves the old folder untouched.
- `README.md`, `docs/guide.ko.md` (update, backup, rollback, removal), `CHANGELOG.md` (the 0.4.0 entry says, first,
  that the update moves the data and where), ADR 0060 amended.

## Out of scope

- The Docker install (its data never lived in the folder).
- Moving a Docker install's data into a bundle. The archive does it; the guide gets a line saying so (a docs fix in
  its own PR, with the next item).
- The rollback block in the guide that starts with `dropdb`: made so it cannot be pasted by mistake during an update
  (its own PR).
- CI upgrade tests from databases written by 0.2.0 and 0.3.0 (`tests/test_upgrade.py` covers 0.1.0-beta.7, .16 and
  .21 only): their own PR.
- PocketRisu's own `save/` folder, which stays where PocketRisu keeps it.

## Steps

1. This spec, with the owner's answers.
2. The launcher, the tray and their tests (Q1–Q7).
3. The bundle smoke on the four targets with an adoption from the previous release's data layout.
4. Docs, CHANGELOG, ADR 0060 amendment.
5. **The owner's check** on Windows (a real update from a 0.3.0 bundle folder) and a look on macOS that nothing moved.

## Acceptance criteria

1. A fresh bundle start on each target creates the database in the Q1 folder, and nothing in the bundle folder.
2. A bundle folder holding 0.3.0's `data/` starts, adopts it, migrates, and every row it held is there (smoke, the
   same marker check as PHASE-23's update). After that, deleting the bundle folder and unpacking the next version
   starts on the same data.
3. Both locations holding a database: the start is refused and neither folder changes (smoke).
4. An adoption that fails at any point leaves the old `data/` byte-identical and the per-user folder without a
   database (test with an injected failure).
5. `NMOS_DATA_DIR`, absolute or relative, wins (test). macOS is unchanged (its app sets it).
6. Q6: a non-ASCII per-user path without a short name asks once; the pointer file brings the next start (and the next
   version) to the chosen folder; cancel starts nothing (tests with the short-name lookup stubbed).
7. The owner's check passes on Windows.

## Stop conditions

- PostgreSQL refuses a moved cluster on any target (the cluster's configuration holds no absolute path today; if a
  target writes one, stop and report).
- A target where the per-user folder cannot be made private to the user.
- Adoption needs anything beyond a rename or a copy that is checked before the old folder is renamed.

## Risk

**High (AGENTS §14).** The guarantee at risk: the user's memory survives every start and every update. The change
moves stored data on the first start after the update, so it is built to fail closed: one folder or the other is
whole at every step, nothing is deleted, and two databases stop the start instead of hiding one.
