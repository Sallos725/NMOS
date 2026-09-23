# PocketRisu Host Facts

> **Evidence file — do not fill from assumptions.**
>
> Facts already source-verified before the live spike are in `ARCHITECTURE.md §4`.
> This file records what Phase 0A actually observed at runtime. Every claim cites a fixture in
> `fixtures/host/a14c911-2026-09-22/` (abbreviated `F/`) or is explicitly marked as a
> **source reading** (checked in PocketRisu source at `a14c911`, not observed at runtime).

## Environment

- PocketRisu commit/version: `a14c911fd927a2bf63c8665bae202f29643920b4` (v1.12.0), image built from a clean `git archive` of that commit.
- Deployment mode: isolated Node server container (`nmos-spike-pocketrisu`, host network, `PORT=6101`, empty save dir). The owner's production instance was not touched.
- Browser/client: headless Chromium 1223 (Playwright over CDP), origin `http://localhost:6101` (secure context). A second check used `http://192.168.x.x:6101` (plain HTTP LAN, not a secure context).
- Model: `tools/spike_stub_llm.py` configured as PocketRisu "Custom API" (OpenAI-compatible) for main and auxiliary model.
- Spike: `nmos-host-spike.js` v0.2.0, hash format v1.
- Date: 2026-09-22.
- Notes: scenario actions were real UI actions in the running host, scripted with Playwright. See `F/README.md` for the method and scenario index.

## Q1 — `beforeRequest` model-mode values and main-generation gating

Observed values:

| Trigger | `mode` | Evidence |
|---|---|---|
| normal send (S1, warm-up) | `model` | `F/*S1__beforeRequest*`, `F/*warmup__beforeRequest*` |
| reroll (S2) | `model` | `F/*S2__beforeRequest*` |
| continue (S4, S4b) | `model` | `F/*S4__beforeRequest*`, `F/*S4b__beforeRequest*` |
| each retry after a failed request (S12) | `model` | 3× `F/*S12__beforeRequest*` |
| "Auto Suggest" (S11, and automatically after each reply once enabled) | `submodel` | `F/*S11__beforeRequest*`, 4th `F/*S12__beforeRequest*`, 2nd `F/*S14-1000-send__beforeRequest*` |

Not observed at runtime: `memory`, `emotion`, `otherAx`, `translate`. **Source reading:** `ModelModeExtended = 'model' | 'submodel' | 'memory' | 'emotion' | 'otherAx' | 'translate'` (`src/ts/process/request/shared.ts`). Trigger and Lua scripting LLM calls also pass `'model'` (`src/ts/process/triggers.ts`, `src/ts/process/scriptings.ts`), so `mode === 'model'` alone does not guarantee a main chat generation.

Prompt shape observed alongside `mode`:

- Main generations (send, reroll, retry): the last prompt message is `user`, and it equals the host's latest user message after normalization (`latestUserInput.promptLastUserExactMatch = true`).
- Continue (S4, S4b): the last prompt message is `system` (the continue instruction). The host's latest user message is still present and exact-matched as the last `user` message (`promptLastUserIndex = 10` of 12 in S4).
- `submodel` (auto-suggest): 2 messages (`system`, `user`). The `user` message does not equal the host's latest user message (`promptLastUserExactMatch = false`).

Conclusion: `mode` separates main generations from auxiliary requests only coarsely. A stricter main-generation test needs `mode === 'model'` **and** a prompt that contains the host chat's latest user message as its last `user` turn. Whether trigger/Lua `model` calls would also pass that test was not observed.

**O3 decision (owner, 2026-09-22):** `mode === 'model'` and last prompt `user` turn equals the host's latest user message — ARCHITECTURE D13, ADR 0001.

---

## Q2 — Replacer calls per user action / retry / fallback

Normal: 1 call per send, reroll or continue (`callCountForActionKey = 1` in S1, S2, S4, S4b, warm-up).

Retry: S12 forced two HTTP 500 responses, then a success. The replacer ran **3 times** for one user action, 7–8 ms apart (`msSincePreviousCall` 8, 7). All three received an identical prompt (`formatedHash 94f5d11c…`, `callCountForFormatedHash` 1 → 2 → 3). The stub saw 3 main requests (#11–#13). HTTP 500 from Custom API did not trigger the 1 s `failByServerError` back-off.

Fallback: not measured (no fallback model configured). **Source reading:** `formated` is re-cloned from the original per fallback model (`request.ts`, `arg.formated = safeStructuredClone(originalFormated)` at the top of each fallback iteration), so each fallback starts from the unmodified prompt and the replacer runs again.

Additional: once Auto Suggest is on, every completed reply triggers one extra `submodel` replacer call right after `output` (S12, S14-1000-send).

Evidence: `F/*S12__beforeRequest*` (4 files), `F/*S12__output*`, stub log in `F/README.md` context.

Conclusion: H2 confirmed at runtime. Injection must be idempotent, and reconcile/retrieve must be cached per user action.

---

## Q3 — `chatId` behavior S2–S10

| Scenario | Before | After | Same/reissued | Evidence |
|---|---|---|---|---|
| S2 reroll | tail AI `9fc87c88`, no swipes | tail AI `eb2bc3bc`, `swipes = [old, new]`, `swipeId = 1` | **new id** at same position; old reply content moved into the new message's `swipes[0]` | `F/*S2-before*`, `F/*S2-after*`, `F/*S2__output*` |
| S3 swipe | `eb2bc3bc` swipe 1/2 | `eb2bc3bc` swipe 0/2 | same id; `data` switched to the selected swipe | `F/*S3-*` |
| S4 continue (`useSayNothing` default on) | tail AI `eb2bc3bc` | `eb2bc3bc` unchanged + **new** tail `bd4063ab` (role `char`, data starts `*says nothing*`, `generationId f5a7efbe ≠ chatId`) | new message | `F/*S4-*`, `F/*S4__output*` |
| S4b continue (`useSayNothing` off) | `bd4063ab`, gen `f5a7efbe` | `bd4063ab`, gen `3fcd6377`, content extended | same id, **new `generationId`** | `F/*S4b-*` |
| S5 edit user | `f3c47d86` | `f3c47d86` | same id, new content hash | `F/*S5-*` |
| S6 edit AI | `a3f81796` | `a3f81796` | same id, new content hash, `generationId` unchanged | `F/*S6-*` |
| S7 delete | 9 messages | `5e2370a0` removed; later messages shift position by −1 | ids of survivors unchanged | `F/*S7-*` |
| S8 disable | `6fcccbc7` `disabled: null` | `disabled: true` | same id | `F/*S8-*` |
| S8b "Cut Messages for AI" | `f3c47d86` `disabled: null` | `disabled: 'allBefore'` | same id | `F/*S8b-*` |
| S9 branch | chat `26b153b7`, 8 messages | new chat `0455fcdf`, 5 messages | **all reissued**; original `generationId`s kept | `F/*S9-*` |
| S10 reload | chat `26b153b7` | chat `26b153b7` | all same | `F/*S10-before*`, `F/*S10-after*` |
| S10 import | chat `26b153b7` (exported) | new chat `04fcdbc9` | **chat id new, every message `chatId` preserved** | `F/*S10-imported*` |

Conclusion:

- H4 confirmed: reroll yields a new `chatId`, and continue keeps it. Additions:
  - Reroll moves the previous reply into the new message's `swipes` array.
  - Continue replaces `generationInfo.generationId`, so `generationId ≠ chatId` afterwards.
  - With the default `useSayNothing = true`, "Continue Response" on a char tail first appends a `*says nothing*` user message. The continuation is written into that message, which ends up with `role: 'char'`. The user sees a new reply, not an extension.
- H5 confirmed: branching reissues every message id. Addition: branched AI messages keep their origin `generationId`.
- H6 confirmed at import: the synthetic 1,000-message file had no `chatId`s, and all 1,000 had ids after import (`F/*S14-1000-run1*`, 0 null ids).
- New fact: message `chatId`s are unique only **within** a chat. Importing a chat creates a second chat that holds the same message ids. The durable key is `(host chat id, message chatId)`.

---

## Q4 — Exact `branchedfrom` marker

Observed raw marker (S9, branch from index 3 of chat `26b153b7`):

```text
{{specialcomment::branchedfrom::26b153b7-fc92-44da-872e-72499dee0b08::New Chat 2::a3f81796-18cc-42fd-9306-78371f3e68a1::}}
```

Format: `{{specialcomment::branchedfrom::<origin chat.id>::<origin chat name>::<origin chatId of the branch-point message>::}}`.

Placement: appended as the **last** message of the new chat (position 4), with `role: 'char'`, `isComment: true`, `disabled: true`, and no `generationId`. The branch copies origin messages 0..branch point inclusive (4 messages). It keeps their `disabled` flags (`'allBefore'` on index 2) and the AI messages' `generationId`s (`41b095dc`, `a3f81796`). The new chat is named `"<origin name> (Branch)"` and is grouped under "Branches of <origin name>" in the chat list.

Evidence: `F/*S9-after*` (manifest `specialComments`), `F/*S9-before*`.

Conclusion: the marker gives origin chat id + branch-point message id; the copied prefix maps to the origin by position (and by `generationId` for AI messages). The origin chat name inside the marker is user-editable text, not an identifier. Because the marker is a disabled comment, it never reaches the prompt.

**O4 decision (owner, 2026-09-22):** new conversation + recorded origin refs — ARCHITECTURE D14, ADR 0002.

---

## Q5 — `crypto.subtle` and hashing cost

Availability:

- `http://localhost` (secure context): available inside the V3 plugin sandbox iframe (`hashMethod: crypto.subtle` in every fixture's `environment`).
- `http://192.168.x.x:6101` (plain HTTP LAN): the page is not a secure context. `crypto.subtle` and `crypto.randomUUID` are both undefined, and **the V3 plugin never loaded** (no `[NMOS-SPIKE] loaded`, no collector traffic). PocketRisu itself shows "Connected over HTTP — Some features such as plugins may not work. Use the Remote Access feature for an HTTPS connection." **Source reading:** the V3 sandbox host calls `crypto.randomUUID()` (`src/ts/plugins/apiV3/factory.ts:437`), which exists only in secure contexts.

1,000-message hash time (hash payload v1, 413,048 payload bytes; `F/*S14-1000-hash__hashBenchmark*`):

| Method | 100 msgs | 1,000 msgs | Agrees with the other method |
|---|---:|---:|---|
| `crypto.subtle` | 0.8 ms | 6.1 ms | yes |
| JS fallback (in spike) | 4.4 ms | 16.9 ms | yes |

The full manifest build (per-message `contentHash` + `dataHash` + manifest hash, sequential awaits) took 19.3–32.3 ms for 1,000 messages (`F/*S14-1000-run*`).

Environment notes: one run environment (headless Chromium, homelab CPU). No mobile browser was measured.

Conclusion: wherever an NMOS V3 plugin can run at all, `crypto.subtle` is available. That is localhost or HTTPS; the plugin cannot run over plain-HTTP LAN. The sidecar-side hashing fallback in the Phase 0B plan is therefore not needed for the plugin. Deployments must use localhost or HTTPS (PocketRisu Remote Access).

---

## Q6 — `getChatFromIndex()` cost

| Messages | Elapsed ms (3 runs) | Serialized bytes | Evidence |
|---:|---:|---:|---|
| 100 | 3.1 / 2.5 / 3.1 | 30,292 | `F/*S14-100-run*` |
| 1,000 | 13.0 / 11.9 / 15.7 | 307,176 | `F/*S14-1000-run*` |

Inside `beforeRequest` on the 1,000-message chat: 12.6 ms (`F/*S14-1000-send__beforeRequest*` `timings.getChatElapsedMs`). A `submodel` call right after `output` measured 33.7 ms, likely while the host was busy saving.

Messages are synthetic (≈1–4 short sentences each). Real RP messages are longer, so bytes and time scale up accordingly.

Conclusion: a full snapshot per main generation is affordable at 1,000 messages (≈12–16 ms + ≈20–30 ms manifest hashing). The deadline budget should reserve ~50 ms for snapshot + manifest at this size.

---

## Q7 — Lua `request` trigger interaction with injected/system messages

Observed: **not measured at runtime.** No common bot with a Lua `request` trigger was loaded in the isolated instance, and the spike does not inject.

**Source reading:** in `requestChatData` (`src/ts/process/request/request.ts`), each iteration of the retry loop runs every `beforeRequest` replacer and then `runTrigger(currentChar, 'request', { displayData: JSON.stringify(arg.formated) })`. The trigger's returned JSON array **replaces** `arg.formated` wholesale, and a thrown error is swallowed. A request trigger can therefore rewrite, drop, or reorder any message, including an NMOS-injected one. Because the loop does not re-clone between retries, the next retry's replacer receives the trigger's output.

Conclusion: H3 is confirmed by source. **Owner disposition (2026-09-22):** source-based answer accepted; a runtime spot check with a common bot is not required for Phase 0A.

---

## Q8 — Mutations invisible to request-time reconciliation

Observed:

1. **No hook for edits, deletes, disables, swipes, branches, imports or reloads.** S3 and S5–S10 produced no `beforeRequest` or `output` observation. The sidecar learns about these only at the next main generation's snapshot, or never, if the user leaves the chat.
2. **`output` fires before reroll swipes are attached.** In S2 the `output` snapshot shows the new message with `swipeCount 0`. The later snapshot shows `swipes = [old, new]`, `swipeId = 1` (`F/*S2__output*` vs `F/*S2-after*`). The output notification is a provisional hint, not final state.
3. **The current chat index is not identity.** Importing a chat prepends it (`chats.unshift`) while `chatPage` stays numerically the same. After the S10 import, `getCurrentChatIndex()` pointed at a *different* chat ("New Chat 2 (Branch)") (`F/*S10-import-current-index*`). Always key by `chat.id`.
4. **Duplicate message ids across chats** after import (Q3).
5. **Continue with `useSayNothing`** turns a host-created user message into a char message in place (Q3, S4).
6. **Hash-excluded content**: non-selected swipe texts, `time`, and chat-level fields (`note`, `localLore`, `scriptstate`) are outside the revision hash by design, so changes to them are invisible to reconciliation.
7. Test-harness observation, not spike evidence: in the host's lite DB view, chats other than the open one reported 0 messages until opened. This suggests lazily loaded chat content (the host fetches `/api/chat-content/<charId>/<index>` when a chat opens). NMOS must only snapshot the current chat, which the spike already does.
8. UI note (no data effect): after several in-place updates, pencil-edit on older messages silently did nothing until a page reload. A user may reload mid-session; reload itself changes no ids (S10).

Conclusion: request-time reconciliation sees every persisted change to the current chat's selected content, but only lazily. The `output` event must not be treated as final state. Chat index must never be used as identity.

---

## S13 — Group chat

**Not executable on the target build.** PocketRisu `a14c911` has no group-chat type. **Source reading:** `character.type?: "character"` is the only variant (`src/ts/storage/database.svelte.ts:1719`), and `isGroupChat: false` is hard-coded in the main request (`src/ts/process/index.svelte.ts:1582`). The UI's "+" menu offers only RisuRealm / Import / Create from Scratch / Import Package. Multi-character play exists only inside a single character card. **Owner disposition (2026-09-22):** accepted as not applicable on this build.

---

## Phase 0B runtime findings (2026-09-22)

Observed while running the Phase 0B adapter + sidecar against the same isolated `a14c911` instance.
Evidence is in live sidecar/ledger state and the runs described in `docs/perf/phase0.md`, not in
`fixtures/host/`.

1. **Replacer leak on plugin unload (ARCHITECTURE H13).** Toggling the spike plugin off (and, in
   0A setup, re-importing it) left its `beforeRequest` replacer registered. The next generation hung
   with the send button spinning and no model request made. A page reload cleared it every time.
   **Source reading:** V3 `addRisuReplacer` (`src/ts/plugins/apiV3/v3.svelte.ts:894`) adds no
   `addPluginUnloadCallback`, unlike `addRisuChatListener`; `loadPlugins` clears only
   `pluginV2.chatOutput` (`src/ts/plugins/plugins.svelte.ts:916`).
2. **Live reroll order (ARCHITECTURE H14).** The reroll's `beforeRequest` snapshot no longer contains
   the tail reply. This agrees with the recorded S2 `beforeRequest` (`hostMessageCount: 7` vs 8 in
   `S2-before`). The ledger sees "head minus tail", and the regenerated reply arrives with the next
   request. A tail reply is only in the ledger before a reroll if an earlier request synced it,
   e.g. a Continue.
3. **`nativeFetch` fallback.** With the sidecar stopped, the direct browser fetch failed
   (`ERR_CONNECTION_REFUSED`). PocketRisu then retried through its server proxy, which answered
   HTTP 500. With the sidecar delayed, `requestTimeoutMs` aborted the fetch ("signal is aborted
   without reason"). In both cases the plugin failed open, and generation proceeded after ≈800 ms.
4. **Chat UI lazy rendering.** Only recent messages are mounted. Older ones mount when the
   `.default-chat-screen` column-reverse scroller reaches the top. No data effect.


## Plugin frame sandbox (2026-09-23)

Observed on `ghcr.io/pocketrisu/pocketrisu:latest` (v1.12.0, the build the owner runs), isolated
container on `http://localhost:6101` with an empty save dir, headless Chromium 1223, NMOS plugin
0.1.0-beta.5. The owner reported that the panel's "Open inspector" link did nothing.

1. **Sandbox flags (ARCHITECTURE H15).** The plugin iframe carries `sandbox="allow-scripts allow-modals
   allow-downloads"` and `allow="screen-wake-lock"` (read from the live DOM). **Source reading:** the
   bundled V3 factory adds exactly these three tokens (`this.iframe.sandbox.add(...)`).
2. **No new tabs.** Clicking the beta.5 `<a target="_blank">` Inspector link opened no page and left
   the host URL unchanged; Chromium logged *"Blocked opening 'http://127.0.0.1:8790/inspector' in a new
   window because the request was made in a sandboxed frame whose 'allow-popups' permission is not
   set."* Top-level navigation is not allowed either (no `allow-top-navigation`).
3. **Clipboard.** Inside the frame, `navigator.clipboard.writeText` was rejected (*"blocked because of
   a permissions policy"*); `document.execCommand('copy')` on a user click did copy. Not used by NMOS.
4. **No URL-opening API.** The V3 API object exposes no method that opens a URL (its internal
   `window.open` helper is used only for the host's own OAuth flow). `getRootDocument` needs the
   `mainDom` permission and its anchors cannot set `target`.
5. **In-panel inspector works.** With the Inspector rendered in the panel (0.1.0-beta.6), the list →
   conversation → list round trip stayed in the frame: no new page, no frame navigation, no console
   errors; markup in chat text was shown as text.


## Preset-shaped prompts (2026-09-23)

The owner reported that memory was never used over the HTTPS reverse proxy. The owner's PocketRisu
request log (`save/request-logs.db`, read from a copy) showed the plugin's `/v1/output`, `/v1/health`,
`/v1/config` and `/v1/inspector` calls through the server proxy, but **no `/v1/sync/reconcile` and
no `/v1/retrieve` in any request**. The logged model requests show why. The preset (HELENA) sends the
turn as three user messages (`<Current Input>` + fence, the input, the closing fence plus
instructions), then three more user-role instruction blocks. The last block is a system note, which
Gemini conversion turned into `user` with a `system:` prefix. The last user message never carried
the input, so ADR 0001 rule 2 classed every request as auxiliary.

Reproduced on an isolated `ghcr.io/pocketrisu/pocketrisu:latest` (v1.12.0) with an imported JSON
preset of the same shape (chat history → `<Current Input>` wrapper → input → closing wrapper → two
user blocks → system note) and `tools/spike_stub_llm.py` as the model:

- Released 0.1.0-beta.6 plugin: 0 reconcile calls, stub saw `nmos_packets=0`.
- Plugin with ADR 0001 amendment 2, same chat and query: reconcile + retrieve ran, and the stub saw
  one packet with the turn-0 excerpt, placed before the `<Current Input>` run
  (`roles=[system, user, assistant, system(packet), user, user, user, user, user, system]`).

### Bulk deletion and per-turn extraction (2026-09-23, ADR 0008)

On an isolated `ghcr.io/pocketrisu/pocketrisu:latest` (v1.12.0), a message's trash icon asks "Remove
this message?" with **Remove this message only**, **Remove this and following messages (N)** and
Cancel. N counts the message itself and every later one. The plugin sees no event. At the next main
request the manifest simply lacks the removed messages. A reply that was generated but never followed
by a request was never synced, so NMOS counts one deletion fewer than the host: 6 removed in the UI
gave `delete ×5, append ×1`. The message ☰ menu offers Branch, Disable Message and Cut Messages for AI
(S8/S8b), with no bulk delete. Full run: `docs/perf/turn-extraction.md` § Host check.

---

## Main-page HUD (2026-09-24)

Observed on `ghcr.io/pocketrisu/pocketrisu:latest` (v1.12.0, image `13fc7c7f7e06`), isolated container on
`http://localhost:6101` with an empty save dir, headless Chromium 1223 at 1280×800 and 390×844, and two
probe plugins (`hud_spike`, `hud_deny`) that draw a pill from a settings entry. **Source reading:**
`src/ts/plugins/apiV3/v3.svelte.ts` from the image's source map. The owner's instance was not touched.

1. **Permission (ARCHITECTURE H16).** `requestPluginPermission('mainDom')` and `getRootDocument()` exist.
   The first request shows the host confirm *"Plugin hud_spike is requesting to access the main Document,
   which may expose sensitive information. Do you want to allow this?"* (Korean: *"…메인 Document에
   접근하려고 합니다. 민감한 정보가 노출될 수 있습니다. 허용하시겠습니까?"*). Yes → `true`, and the grant
   survived a page reload with no second prompt. No → `false`, and a second request resolved `false`
   with no prompt: a denial is permanent until Settings → Plugin → row menu → "권한 응답 초기화".
   `getRootDocument()` returns `null` without the permission.
2. **Proxy API.** The root document is a `SafeDocument` over `document.documentElement`; every method is
   async over the frame bridge. `createElement`, `appendChild`, `addClass`, `setStyleAttribute`,
   `setStyle`, `setTextContent`, `getBoundingClientRect`, `querySelector` and `remove` worked.
   `setTextContent('🧠 <b>…</b>')` was rendered as text. `setInnerHTML` runs DOMPurify: inline `style`
   was kept, `onclick`/`onerror` were stripped. `setAttribute` accepts only `x-*` names.
3. **Listeners are document-wide.** `SafeElement.addEventListener('click', fn)` calls
   `document.addEventListener`, whatever the element, and passes a trimmed event (`clientX`,
   `clientY`, buttons, modifier keys). A click on the pill logged `hit: true` against its rect; clicks
   elsewhere on the page reached the same listener with `hit: false`. The host removes a plugin's
   listeners when it unloads.
4. **Placement and lifetime.** A `position:fixed` pill appended to `body` (top-right, 8 px + safe-area
   inset, z-index 900) stayed through settings open/close, character creation and the chat view. At
   390×844 it covered only the top of the message list (right of the back arrow); the chat input sat at
   y = 793. Re-importing the plugin without a reload left the old pill in the DOM; a reload cleared it.
5. **Stacking.** The panel frame is `position:fixed; z-index:1000` (`showContainer('fullscreen')`); host
   dialogs use `z-50`, so a permission prompt requested while the panel is open would sit under the
   frame. The plugin hides the frame while it asks.

## Scenario evidence index

| Scenario | Before fixture | After fixture | Other logs | Done |
|---|---|---|---|---|
| S1 | `S1-before` | `S1-after` | `S1__beforeRequest`, `S1__output` | [x] |
| S2 | `S2-before` | `S2-after` | `S2__beforeRequest`, `S2__output` | [x] |
| S3 | `S3-before` | `S3-after` | — | [x] |
| S4 | `S4-before`, `S4b-before` | `S4-after`, `S4b-after` | `S4*__beforeRequest`, `S4*__output` | [x] |
| S5 | `S5-before` | `S5-after` | — | [x] |
| S6 | `S6-before` | `S6-after` | — | [x] |
| S7 | `S7-before` | `S7-after` | — | [x] |
| S8 | `S8-before`, `S8b-before` | `S8-after`, `S8b-after` | — | [x] |
| S9 | `S9-before` | `S9-after` | — | [x] |
| S10 | `S10-before` | `S10-after`, `S10-imported` | `S10-import-current-index` | [x] |
| S11 | `S11-before` | `S11-after` | `S11__beforeRequest` | [x] |
| S12 | `S12-before` | `S12-after` | 4× `S12__beforeRequest`, `S12__output` | [x] |
| S13 | — | — | not executable on this build; owner accepted N/A | [x] |
| S14 | `S14-100-run1..3`, `S14-1000-run1..3` | — | `S14-*-hash`, `S14-1000-send__*` | [x] |

## Phase 0A exit check

- [x] S1–S14 executed. — S1–S12 and S14 executed; S13 not executable on `a14c911`, N/A accepted by owner 2026-09-22.
- [x] Q1–Q8 answered with evidence. — Q7 from source, accepted by owner 2026-09-22.
- [x] S1–S9 fixtures saved.
- [x] ARCHITECTURE §4 reconciled against runtime evidence.
- [x] O3 explicitly decided by owner (2026-09-22, D13).
- [x] O4 explicitly decided by owner (2026-09-22, D14).

Phase 0A exit criteria met on 2026-09-22. Phase 0B unlocked.
