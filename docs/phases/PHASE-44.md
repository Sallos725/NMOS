# Phase 44 — A recall tool the response model can call (read-only MCP)

Status: **draft**, 2026-10-12. Not approved. Written at the owner's request after a read-only survey of a recently
published memory plugin ("plugin D"). It reopens a recorded decision: **R5** (`docs/ROADMAP-1.0.md`, 2026-10-01)
took read-only MCP out of the 1.0 scope, and **R7** says a new phase before 1.0 is a Stage 7 item unless the owner
pulls it in by name. Q0 is that decision. Nothing here is built. `docs/STATUS.md` and `AGENTS.md` §0/§2 are not
changed by this draft. Linear: AGE-TBD.

## Why

1. **The packet is decided before the model reads the question.** Recall chooses what to place from the latest
   messages and the budget. When it misses, the response model cannot ask for more. The latest replay
   (`packet-v18`, `docs/STATUS.md`) still misses 23 of 314 recall probes and 3 of 24 exact quotes.
2. **The forensic path already exists.** Stage 7 gave NMOS a quote route, excerpt anchors and source-turn pages, but
   only the panel reaches them. The response model could reach them as well.
3. **Plugin D shows the host path works.** It registers two read-only tools with the host (`recall` by question,
   `expand` by a ref placed in its packet). It offers them only on turns where its archive has something the packet
   did not carry. Its tool descriptions tell the model the packet comes first. A ref from an earlier version of the
   chat is refused. Its tool path also calls an auxiliary model to write the answer; this draft does not adopt that
   part (Q2).
4. **The costs are real, and the host sets them, not NMOS.** Each tool call is one more full main-model request with
   the whole prompt. A preset with tools on loses streaming. ARCHITECTURE D12 already says MCP is optional deep
   recall and never the correctness mechanism; this phase keeps it that way.

## Host facts (PocketRisu v1.14.0; source reading only, nothing run)

Production runs v1.14.0 (`package.json` in the running container, 2026-10-12). The sources below were read from the
`:latest` image's source map. Live evidence is step 2's job, and its result goes into `docs/HOST-FACTS.md`.

- **H-a Registration.** `registerMCP({identifier, name, version, description}, getToolList, callTool)`. The
  identifier must start with `plugin:` (`process/mcp/pluginmcp.ts`).
- **H-b Activation is the user's step.**
  - The host lists tools only from modules whose `mcp.url` is set (`getModuleMcps`, `process/modules.ts`).
  - The user imports the module through "import MCP module" with the URL `plugin:<id>`, then enables it.
  - The import also adds an always-active lorebook entry, "MCP Info", which carries the description. It costs
    prompt tokens on every turn.
- **H-c Three gates on the preset.** The preset path uses tools only when all three hold:
  - `preset.toolUse` is on (off by default);
  - the adapter kind is `openai-compatible`, `anthropic-messages` or `google-gemini`;
  - the profile declares the `tools` capability (`process/request/request.ts`, `preset/types.ts`).

  The older OpenAI path has its own recursive tool call (`process/request/openAI/requests.ts`).
- **H-d Tools cost streaming.**
  - Tool runs are non-streaming.
  - They skip the server-side job transport (the tool loop stays in the browser).
  - The preset path allows at most 8 tool steps per request.
- **H-e `beforeRequest` runs once per request attempt, not once per tool round.** Both tool paths re-send the
  conversation without re-running replacers. So the packet placed in round 1 stays, and `/v1/retrieve` runs once per
  turn as today.
- **H-f `getToolList` is called often.** It runs inside `getMCPTools` on every request. `callMCPTool` also calls it
  for every MCP to find the tool's owner. It must not touch the network.
- **H-g Tool use can be written into the reply.** With `rememberToolUsage` on, the host appends
  `<tool_call>{id}{name}</tool_call>` to the assistant text and keeps the call in its persistent storage.
  NMOS's normalizer does not handle this form today.

## Proposal

S1. **One read-only tool, `nmos_recall(question)`**, registered as `plugin:nmos`.
- Its schema has a single string field (at most 300 characters). It has no conversation, chat, character or
  principal argument the model could write.
- The plugin takes the scope from the current host snapshot and the turn's retrieve: `chat_id`, `active_commit`
  (the worldline head) and `manifest_hash`, the same fields `RetrieveRequest` sends today. The sidecar resolves the
  conversation and the principal from them, as it does for `/v1/retrieve`, and refuses a scope whose head is no
  longer current (D12).
- The tool description says that the packet comes first, that this is a lookup for a specific missing record, and
  that an unchanged query that already failed should not be repeated.

S2. **A sidecar recall endpoint on the forensic path.**
- It runs the existing quote route, excerpt anchors and fact recall for the question inside the bound scope.
- It returns facts, claims and excerpts with their turn refs and holders, within a small budget (Q5).
- It calls no model. The query embedding uses the configured embedder and falls back to lexical recall as today.

S3. **Offered only when it can help.**
- `getToolList` returns an empty list unless the panel toggle is on (Q4) and NMOS is on for the chat.
- It also needs the turn's `/v1/retrieve` response to show that the archive holds more than the packet placed.
  `RetrieveResponse.memory.cut` (memory lines left out for the budget, ADR 0036) already says so for memory lines.
  Whether excerpts and quote candidates need a flag of their own is decided in step 1. The plugin keeps the signal
  locally (H-f).

S4. **Fail open, bounded.**
- A recall error or timeout returns a short fixed text ("NMOS has no record for this" / "NMOS memory is
  unavailable") inside the retrieve deadline. It never throws into the host loop.
- A tool call never blocks the reply.

S5. **Recorded like the packet.**
- Each delivery is a ledger entry tied to the turn's trace (ADR 0027): the question, what was placed, its token
  count and refs.
- As-of replay, echo and the overuse measurement then see it, and the Inspector shows it under the turn.

S6. **Tool markers never become story text.** The normalizer strips the H-g marker before ingest and extraction. A
test pins that extraction input is the same with and without the marker.

S7. **Setup in the panel.**
- One card explains the three host steps: import `plugin:nmos` as an MCP module, enable it, and turn on tool use in
  the preset.
- It states the costs plainly: no streaming for that preset, and one more main-model request per call.
- The plugin itself stays light: registration, the local flag and the HTTP call only (owner rule: the logic stays in
  the sidecar).

## Questions (recommended answer first)

- **Q0 — when.**
  - (a) **Build after 1.0. Only step 1 (zero-call evidence, no product change, no paid call) runs now**, so the
    decision is made on data.
  - (b) Pull it in by name now. It is a heavy change: it resets the two quiet weeks of the 1.0 gate.
  - (c) Record only, as R5 says today.
- **Q1 — tools.**
  - (a) **One tool, `nmos_recall`.**
  - (b) Add `nmos_expand(ref)`, which returns the source turn of a ref placed in the packet. This needs refs in the
    packet: a packet-policy change and a new `packet-v*` key.
- **Q2 — who writes the answer.**
  - (a) **No model. The tool returns recalled facts and excerpts with refs.**
  - (b) An auxiliary model writes a prose answer from them, as plugin D does. This adds a paid call and latency to the
    reply path, which Phase 34 kept out (C8).
- **Q3 — exposure.**
  - (a) **Only when the retrieve flag says there is more (S3).**
  - (b) Every turn while the toggle is on.
- **Q4 — default.**
  - (a) **Off. The user turns it on in the panel**, beside the host steps, which are off by default anyway.
  - (b) On whenever the host has it enabled.
- **Q5 — result budget.** (a) **1,200 tokens.** (b) 800. (c) 2,000.
- **Q6 — live budget.** Step 3 needs a tool-capable main model and real calls. The owner sets the model and a dollar
  cap before any live call.

## Steps

1. **Zero-call evidence (allowed under Q0 a).**
   - Prototype the S2 recall as an evaluation script, not product code.
   - Run it on the latest replay databases, with each missed probe's question as the tool query.
   - Count how many misses would place the gold. Record the result in `docs/perf/phase44-zero-call.md`.
   - Go or no-go: fewer than half of the 26 misses answered stops the phase and is reported.
2. **Host spike on an isolated v1.14.0.**
   - Use a stub plugin MCP and a stub tool-capable model.
   - Confirm H-b to H-g live, and how many requests a call adds.
   - Record the result in `docs/HOST-FACTS.md`. This step needs no provider cost.
3. **Implementation (only after Q0 b, or after 1.0).** S1–S7, with the tests below.
4. **Reduced live run (Q6).**
   - Run the miss set with tools on and off.
   - Run also turns where the packet already holds the answer, to measure overuse.

## Acceptance

- A1. Step 1: the tool path places the gold for at least 13 of the 26 probes the default packet misses.
- A2. With the toggle off, the packet is byte-identical to `main` for every replay probe, and no tool is listed.
- A3. Scope: tests show that a call cannot reach these, whatever the question says:
  - another conversation;
  - another worldline (a rerolled or edited-away branch);
  - facts hidden from the principal.
- A4. Fail open: with the sidecar down or slow, the tool returns its fixed text inside the deadline plus 1 s, and the
  reply completes.
- A5. Every delivery is in the turn's trace, and as-of replay reproduces it.
- A6. The H-g marker is stripped, and extraction input is unchanged by it.
- A7. `getToolList` makes no network request (test).
- A8. Step 4, reduced live run:
  - recall on the miss set is better than with tools off;
  - the call rate on turns that need no lookup is at most 10 %;
  - added p95 latency per turn with a call is reported next to the tools-off p95.

## Measurement gate (AGENTS.md §7 item 6)

Neither "recall only" nor "extraction": it adds a reply-path tool. It follows the recall-only order:
1. a zero-call replay first (step 1), where a miss is understood before any live call;
2. then one reduced live run of the sets it is for (step 4), at the corrected harness pacing.

## Out of scope

- Write tools, or any tool that changes memory (invariant 3).
- A model call on the tool path (Q2 b, unless chosen).
- Retrieval in the plugin.
- Any change to the default packet policy, extraction, or the worker.
- Group-chat principals beyond what `/v1/retrieve` resolves today.
- Stage 8.

## Risk

**High risk** (AGENTS.md §14):
- retrieval and injection semantics (a second path that places memory in the prompt);
- the security boundary of scope binding (S1, A3);
- fail-open on the reply path (S4, A4).
