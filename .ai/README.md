# Cross-model review (Codex ⇄ Claude)

One agent leads a change; the other model gives one read-only second opinion. The rule itself is
`AGENTS.md §14`; this file is the how-to.

```text
.ai/scripts/peer-review   runs the reviewer CLI read-only and prints its final answer
.ai/prompts/review.md     bugs, regressions, missing tests, phase scope (the default)
.ai/prompts/architecture.md   data flow, invariants, provenance, phase scope
.ai/prompts/security.md   tokens, logging, injection, leakage, isolation, fail-open
```

## Protocol

1. The lead reads the authority files (`AGENTS.md §1`), `docs/STATUS.md` and `git status`, and records the
   task scope and the phase it belongs to.
2. The lead implements in its own checkout. One writer per checkout; parallel work uses separate Git
   worktrees and is integrated deliberately.
3. For a material change (`AGENTS.md §14`), the lead runs one focused review with the other model:

   ```bash
   python3 .ai/scripts/peer-review codex review --base origin/main "reroll and swipe invalidation in the fold"
   python3 .ai/scripts/peer-review claude security --base origin/main
   ```

   The first argument is the **reviewer**: Claude leading calls `codex`, Codex leading calls `claude`.
   `--base` adds the branch diff; without it the scope is the working tree (untracked files included). The
   free text narrows the question. A review takes minutes: run it in the background (default timeout 900 s).
4. The lead classifies each finding as confirmed, partial or unsupported, citing code, a test or a fixture.
   Decisions listed in `ARCHITECTURE.md §9` go to the owner; a reviewer cannot settle them.
5. The lead fixes confirmed defects, runs the repository's real commands (`AGENTS.md §11`), and reports
   changes, test results, what the review found and what it rejected, and the remaining risk.

A good focus line names the path and the property: "Review the changed reconciliation path, especially
reroll and swipe invalidation. Check immutable source history, membership, fixture coverage and
fail-open behavior."

## What the script does

- Builds the prompt from the role file, the scope (`--base` diff file list, `git status`, the focus text)
  and fixed rules: read the authority files, stay read-only, no `.env`, no services or model APIs, no chat
  content in the answer, findings with severity and `path:line`.
- Codex runs as `codex exec --sandbox read-only`. Claude runs as `claude -p --permission-mode dontAsk`
  with only `Read`, `Grep` and `Glob`, no MCP servers and no shell (even `git diff --output=` writes a
  file), so the script puts the diff in Claude's prompt.
- Prints the reviewer's final answer on stdout; the full progress goes to a log file (`--log`, or a temp
  file named on stderr). A non-zero exit is the reviewer's own exit code; 124 means it timed out.
- Sets `NMOS_PEER_REVIEW_ACTIVE=1` for the reviewer and refuses to run when it is already set. That stops
  an accidental Codex → Claude → Codex chain; it is a guard, not a security boundary. The reviewer's
  instructions also forbid delegation.

## When the reviewer cannot read the tree

Codex's read-only sandbox is bubblewrap, which needs unprivileged user namespaces. Where they are
restricted it fails with `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted` before any command
runs, and Codex reports that it could not read anything. The owner's host is one: Ubuntu 24.04 sets
`kernel.apparmor_restrict_unprivileged_userns = 1`, so it fails from a plain terminal too, not only inside
Claude Code's Bash (checked 2026-09-28 with `codex sandbox -- head -2 AGENTS.md`). Allowing it is a host
security setting and the owner's call. Until then pass `--inline`: the prompt then carries the
`--base` diff, the working-tree diff and every untracked file, plus each `--attach PATH` (for example
`--attach AGENTS.md --attach ARCHITECTURE.md`), up to 400,000 characters. A file outside the checkout,
ignored by git, or with a sensitive name (`.env*`, keys, credentials, `*.db`, `*.bin`) stops the run; changes to
tracked files with such names are left out of every diff the script sends. An inline review sees only what was attached, so say so when reporting it.

The headless `claude` backend needs a logged-in `claude` CLI in the shell that runs the script (`claude auth
status`); an expired login fails with `Failed to authenticate`. When Codex leads on the owner's host, its own
sandbox cannot start either, and `claude -p` needs the network: Codex runs the script as a command the owner
approves outside its sandbox.

The Claude Code `codex` plugin (`/codex:rescue`) is not this review: it hands Codex the task, and Codex may
edit. A §14 review goes through this script, read-only.

## Cost

Each run uses the reviewer CLI's own login, not the NMOS model keys: the CLI gets only the system basics of the
environment and its own login variables (Codex: `OPENAI_*`, `CODEX_*`; Claude: `ANTHROPIC_*`, `CLAUDE_*`), never
the other CLI's, `NMOS_*`, `DATABASE_URL` or `PG*`. It still costs quota or money: one
review per material change, not one per commit.
