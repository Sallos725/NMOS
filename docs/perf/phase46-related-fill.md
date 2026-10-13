# Phase 46 — small talk keeps the configured limits (2026-10-13)

Every measurement here is a zero-call replay. It reads the same test databases and the same extraction under each
policy (`audit.replay`, `tools/eval_rp.py` scoring), three rounds per policy, majority deciding. The probes are the
recall gate's 314 bench probes and 24 exact-quote cases (`AGENTS.md §7.6`). The cases come from the owner's chats
and synthetic chats and stay outside the repository; this page holds numbers only.

## The 1.0 gate's comparison with `0.1.x`

`packet-v1` is the `0.1.x` default (`v0.1.0-beta.21`). It ran on the 1.0 candidate `main` at `bdae2eb`, beside
`packet-v18`, the default since 2026-10-09. The comparison covers recall and the packet only: both policies read
today's extraction.

| category | probes | `packet-v1` | `packet-v18` | `packet-v19` |
|---|---:|---:|---:|---:|
| address | 28 | 28 | 28 | 28 |
| branch-leak | 1 | 1 | 1 | 1 |
| cast | 12 | 12 | 12 | 12 |
| count | 13 | 13 | 13 | 13 |
| delete-rewrite | 2 | 0 | 1 | 1 |
| early | 38 | 25 | 31 | 31 |
| edit | 5 | 3 | 5 | 5 |
| first | 8 | 0 | 5 | 5 |
| goal | 6 | 6 | 6 | 6 |
| **irrelevant** | 20 | 20 | **16** | 20 |
| item | 12 | 12 | 12 | 12 |
| location | 10 | 8 | 10 | 10 |
| newchat-leak | 6 | 6 | 6 | 6 |
| past | 18 | 13 | 13 | 13 |
| planted | 3 | 1 | 3 | 3 |
| promise | 20 | 20 | 20 | 20 |
| question | 2 | 2 | 2 | 2 |
| relationship | 21 | 21 | 21 | 21 |
| reroll-back | 2 | 1 | 2 | 2 |
| reroll-first | 2 | 1 | 2 | 2 |
| reroll-last | 4 | 0 | 4 | 4 |
| secret | 21 | 21 | 21 | 21 |
| speaker | 8 | 0 | 7 | 7 |
| state | 32 | 29 | 31 | 31 |
| story | 15 | 13 | 15 | 15 |
| turn | 8 | 0 | 7 | 7 |
| why | 21 | 17 | 21 | 21 |
| **total** | 338 | 273 | 315 | 319 |

Under `packet-v18`, `irrelevant` is the one category below `0.1.x`. Under `packet-v19` no category is.

## Why `irrelevant` fell

- **Which probes:** two M0 small-talk probes, each in two sets ("오늘 저녁은 뭐 해 먹을까?", "내일 날씨 어떨까?").
- **What filled the packet:** at the default 4,000 tokens the budget fill (`packet-v9`, ADR 0049) took 30 facts and 8
  claims, because the previous reply names the scene's characters. Two of those lines held the probes' forbidden
  words.
- **The budget is the cause:** replayed at 2,000 tokens, where the fill adds nothing, both probes pass; so they do at
  1,200 and 800. The third M0 small-talk probe ("3 더하기 5는?") passes at every budget.

## `packet-v18` against `packet-v19`

| | `packet-v18` | `packet-v19` |
|---|---:|---:|
| bench (314) | 296 | 300 |
| quotes (24) | 19 | 19 |
| lost | | 0 |
| gained | | 4: the two probes above, each in two sets |
| mean packet tokens | 2,082 | 2,040 |

`packet-v18` on this branch and on `main` gave every probe the same majority result.

## The trial install's latest 80 requests

The 6113 database was read read-only, and each of its 80 latest requests with a packet over 300 tokens was replayed
under both policies.

| rule | requests whose packet changed | facts or claims lost |
|---|---:|---|
| the first rule tried: names no one, shares no fact's words | 14 | 1–9 lines in each of the 14 |
| `packet-v19`: the same, and the message is a question | 4 | none |

- In all four `packet-v19` changes the fact and claim counts stayed the same; only the excerpts differed. The lexical
  route varies run to run (`AGENTS.md §7.6`).
- The first rule caught role-play turns written as narration without a name. Limiting the rule to questions left
  them alone.
