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

Codex's read-only sandbox is bubblewrap. Started from inside another sandbox (Claude Code's sandboxed
Bash, for one), it fails with `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted` before any
command runs, and Codex reports that it could not read anything. Either run the script from a plain
terminal (or exclude it from the caller's sandbox), or pass `--inline`: the prompt then carries the
`--base` diff, the working-tree diff and every untracked file, plus each `--attach PATH` (for example
`--attach AGENTS.md --attach ARCHITECTURE.md`), up to 400,000 characters. A file outside the checkout,
ignored by git, or with a sensitive name (`.env*`, keys, credentials, `*.db`, `*.bin`) stops the run. An inline review sees only what was attached, so say so when reporting it.

The headless `claude` backend needs a logged-in `claude` CLI in the shell that runs the script; an
expired login fails with `Failed to authenticate`.

## Cost

Each run uses the reviewer CLI's own login, not the NMOS model keys: the CLI gets only the system basics of the
environment and its own login variables (`OPENAI_*`, `CODEX_*`, `ANTHROPIC_*`, `CLAUDE_*`), never `NMOS_*`,
`DATABASE_URL` or `PG*`. It still costs quota or money: one
review per material change, not one per commit.
