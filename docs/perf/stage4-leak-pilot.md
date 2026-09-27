# Stage 4 pilot: does the packet make characters leak secrets? — evidence

Date: 2026-09-27. Owner request: before Stage 4 of `docs/ROADMAP-1.0.md` gets a scope, measure how the
memory packet affects secrets between characters. Owner definitions for this pilot: a **leak** is a character
revealing, in words or action, something they should not know or should not say; omniscient narration showing
a character's thoughts is not a leak (answer (가), 2026-09-27). Secret kinds that matter to the owner: between
characters (b) and kept from the user (c).

This is a pilot: few runs per condition, one reader. It shows directions, not rates.

## Setup

- **Chat.** The owner's longest chat (147 messages at the time; a household of a mother, her young
  daughter, an aunt, and the user's persona). The response model for it was Opus 5.5 through the Vercel AI
  Gateway with the 누렁이Claude v7.0 preset, third person with thoughts shown.
- **Opus requests.** Real requests PocketRisu sent, taken from the host's own request log, re-sent unchanged
  except for the NMOS packet (and, for one case, the user's input). Same reasoning setting and temperature.
- **Gemini requests.** No real Gemini request exists for this chat. An isolated PocketRisu (v1.12.0, port 6131,
  scratch save) was seeded with only this character, the chat cut at the case point, the 누렁이Gemini v13.3
  preset, its module and the persona; the model was a local stub that records the prompt. The host rendered
  each prompt in the preset's native Gemini format, third person and **user first person** (the preset's POV
  toggle). The packet was inserted before `# User's input`, where the plugin places it. No API key was copied to
  the test instance, and the owner's instance was not touched.
- **Calls.** The owner ran every paid call from their own terminal with their own keys (the agent did not read
  credentials). Replies were read and judged by the agent; the owner has every reply as a PocketRisu chat file.

### Cases

| Case | Scene | Secret at stake |
|---|---|---|
| C1 | breakfast; mother, daughter, user present (request of turn 16) | the daughter and the user plan to watch the mother's lecture in secret (turns 7–8) |
| C2 | C1 with a probe: the mother asks what the two were whispering about, and the user looks to the daughter | same |
| C3 | a later scene (turn 59) after the mother had found out (turn 21) | the same plan, still marked `hidden_from` the mother (stale) |
| D1 | the mother in bed; the user asks the daughter to go hug her (turn 49) | a promise from turn 9 to hug the mother "next time she is like that", kept from the mother; in the Opus request it exists **only** in the packet |

### Packet conditions

| Condition | What the packet holds |
|---|---|
| current | `packet-v2` as sent |
| A | the same facts; lines whose holders do not include everyone present go under `<Private>`, with a note: non-holders must not mention or act on them; holders may, but keep them from `hidden_from` |
| B | lines with a present character in `hidden_from` are replaced by "something X know and Y does not" |
| B′ | intersection: any line not known to everyone present is replaced that way |
| C | first person: only lines the narrator (the user) knows |
| A′ | A, with `hidden_from="the mother"` added to the D1 promise, which the extraction had marked only `known_by` |

## Results

Leak / near-miss or hint / the holder remembers the secret (when the scene calls for it).

| Model, case | current | A | B | B′ | C | A′ |
|---|---|---|---|---|---|---|
| Opus, C2 ×3 | 0 / 1 / 3 | 0 / 0 / 3 | 0 / 0 / 3 | — | — | — |
| Opus, C1 ×1 | 0 / 1 / 1 | 0 / 0 / 1 | 0 / 0 / 1 | — | — | — |
| Opus, C3 ×1 | 0 / 0 / – | 0 / 0 / – | 0 / 0 / – | — | — | — |
| Opus, D1 ×3 (B′ ×2) | **1** / 1 / 3 | **1** / 1 / 3 | — | 0 / 0 / **0** | — | **0** / 1 / 3 |
| Gemini, C2 3rd ×2 | 0 / 0 / 2 | 0 / 0 / 2 | — | 0 / 0 / – | — | — |
| Gemini, C2 1st ×2 | 0 / 0 / 2 | — | — | — | 0 / 0 / 2 | — |
| Gemini, D1 3rd ×2 | 0 / 0 / 2 | 0 / 0 / 2 | — | 0 / 0 / **0** | — | — |
| Gemini, D1 1st ×2 | 0 / 0 / 1 (+1 broken) | — | — | — | not run | — |

"Broken": one Gemini reply degenerated into a repeated word at the output limit; another first-person reply
was cut by the output limit after long thinking. Not run: Opus C2 under B′ (3) and D1 under B′ (1), and Gemini D1
first person under C (2); the Gemini runner's input-token cap was set from an estimate that was about half the
real prompt size (125–158k tokens per call).

## What it shows

1. **Opus says secrets out loud; Gemini keeps them in narration.** The only leaks (Opus D1) were the daughter
   announcing the promise to her mother. Gemini recalled the same promise every time, in narration only. The
   same packet leads to different behaviour per model.
2. **Withholding (B′) stops leaks by making the holder forget.** Under B′ the daughter never recalled the promise
   (0 of 4, both models). No leak, no memory.
3. **Marking (A) failed in D1 because the data did not say who must not know.** The promise carried `known_by`
   only. A's rule ("keep it from those in `hidden_from`") had nothing to apply. With that one attribute added
   (A′), Opus kept the promise in mind 3 of 3 times and never announced it to the mother; once she learned a
   softened version ("to hug her when she is cold"), not the secret behind it.
4. **The knowledge data is the weak part.** In this chat, of 347 facts, 90 were `limited`, most of them only
   recording who was present; about 15 had `hidden_from`, several of them trivia ("how to fish out eggshell",
   hidden from someone who was simply absent). A secret the mother found out at turn 21 was still marked hidden
   from her at turn 59, next to the fact that she knew. 61 facts held knowledge names as `{'name': …}` strings
   (fixed on read in #103).
5. **With a large context the secret is in the transcript anyway.** The Gemini preset sends up to 150k tokens:
   the C2 plan was in the history itself, so withholding it from the packet changes nothing. The packet decides
   only for secrets older than the host's window (D1).
6. **First person works as a narrator filter.** In user first person, both conditions kept the plan in the
   narrator's thoughts. The cases did not include a secret the narrator does not know, so C removed nothing here.
7. **C3: a stale secret did no harm in that scene.** B's false "secret" line did not make the model invent one.

## Cost

Opus 5.5: 26 calls, $5.39 as reported by the gateway (repeat calls were cached). Gemini 3.1 Pro (Vertex, global):
18 calls, 2,515,858 prompt tokens (1,700,970 cached), 42,485 output and 57,095 thinking tokens.

## Limits

Few runs per condition and one judge; the verdicts are in the viewers given to the owner. The Gemini prompt used
the preset's native format, not the owner's Vertex plugin, which may place the system text differently. The
chat's script variables (affection and so on) were at their current values, not the case turn's. The scripts
read the owner's private request log and stay out of the repository.
