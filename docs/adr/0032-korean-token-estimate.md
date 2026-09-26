# 0032 — Korean token estimate (`packet-v2`)

Status: accepted, 2026-09-26. Owner decision on K26 (option: lower the non-ASCII rate to 1.2). Amends ADR
0027 (a new packet policy, and the default). D42.

## Context

The packet compiler fills the reserve (600 tokens by default) against an estimate, not a tokenizer:
3.5 ASCII characters a token and 1.5 tokens for every other character. Phase 9 measured three tokenizers
at 0.74–0.98 tokens per Korean character. A Korean packet therefore used 68–75 % of the reserve in real
tokens, and an excerpt, being mostly Korean, cost the most (K26). The owner's response model is of the
Gemini family, the one that counts Korean lowest (0.74).

Three options were put to the owner: lower the rate to 1.2 (margin over the highest measured rate), lower it
to 1.0 (almost none), or raise the default reserve to 800 and leave the rate. Raising the reserve also grows
English packets, and a user who does not lower PocketRisu's max context by the same amount gets a larger
prompt. The owner chose 1.2.

## Decision

1. A new packet policy `packet-v2` is `packet-v1` with non-ASCII characters estimated at 1.2 tokens.
   ASCII stays at 3.5 characters a token. Every cost the compiler computes (frame, state, lines, the
   excerpt reserve and its fitting, the packet total) uses the policy's rate (`packet.NON_ASCII`).
2. `packet-v2` is the default (`NMOS_PACKET_POLICY`, both compose files). `packet-v1` and `packet-v0` keep
   1.5, so a recorded request replays exactly under its own policy, and `tools/replay_packets.py`
   compares the two.
3. The default reserve stays 600.

## Consequences

- A budget-bound Korean packet holds about 1.5 more lines. In real tokens it grows from 68–75 % to
  76–85 % of the reserve; the largest measured was 523 of 600 (`docs/perf/token-estimate.md` §2).
- No whole packet was under-counted on the three tokenizers. A single all-Korean excerpt line can be up to
  3 % under (deepseek-v4.1-flash, 1 of 16). The frame and fact lines carry the margin in a packet.
- A tokenizer not measured that counts Korean above 1.2 a character can make a packet larger than the
  reserve by the difference. The workaround is the same as before: a lower memory budget in the panel,
  or `NMOS_PACKET_POLICY=packet-v1`.
- No schema, extractor or embedding change: nothing is re-extracted. Traces record `packet-v2` from the
  upgrade on; the Inspector shows each request's policy.
- An installation that set `NMOS_PACKET_POLICY=packet-v1` in its `.env` keeps it.
