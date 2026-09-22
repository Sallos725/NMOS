# Phase 4 — Character Knowledge (soft subset)

> Owner authorization: 2026-09-22, as a subset for the public beta (ARCHITECTURE D19); shipped in
> `v0.1.0-beta.2`. Written after the fact (issue #14) to record what shipped and where it ends.
> Semantics revised by the stabilization work (ADR 0007). Optional: without `NMOS_LLM_URL` there are
> no facts and therefore no annotations. **Hard principal modes (D9 `character_pov`) are not
> authorized.** They need a new owner decision and a revision of this document first.

## Goal

The model knows *who in the story knows a fact*, so it does not leak a secret through a character
who should not have it. Uncertainty stays uncertainty (invariant 4). Character knowledge stays
separate from world knowledge (invariant 6).

## In scope (soft subset)

1. **Knowledge scope per assertion (D19, ADR 0007).** `knowledge = public | limited | unknown`, with
   `known_by` / `hidden_from` name lists for limited facts. Extraction asks for the scope explicitly
   and validation normalizes it. Contradictory names are dropped and noted.
2. **Packet annotations.** `<Fact>` carries `knowledge="public"` or `known_by` / `hidden_from`, or no
   mark. The Note states the semantics exactly: unlisted means unknown, not unaware.
3. **Ranking.** A fact hidden from a character addressed in the current user turn ranks first, so the
   model sees what it must not reveal.
4. **Inspector** shows the knowledge scope of each current fact.

The packet is still built for the omniscient narrator (D9 default). Annotations inform the model;
they do not remove anything from context.

## Out of scope

- **Hard POV isolation** (D9 `character_pov`): per-character packets and withholding hidden values
  from context. A sim bot writes every character in one generation, so a single request cannot be
  split per principal without host orchestration changes (AGENTS §8 stop condition).
- A principal/entity table, alias resolution, or name-to-id identity (path described in ADR 0007).
- Knowledge inference beyond the extraction window, belief revision, or a verifier model.
- Threads, causal links, hierarchy, MCP (Phase 5+).

## Stabilization prerequisites (issues #6–#14), completed before any further Phase 4/5 work

- Extractor generations and worker/generation binding (#6), embedding projections (#7) and
  generation coverage (#8): D20, ADR 0006.
- Normalized-text projection (#9) and long-message coverage (#13): D21.
- Knowledge semantics (#10): D19 revised, ADR 0007.
- CORS for the settings PUT (#11), scale envelope and benchmark (#12, `docs/perf/scale.md`).

## Acceptance criteria

Status 2026-09-22 — met. Evidence: `apps/sidecar/tests/test_knowledge.py`,
`test_extraction.py::test_knowledge_annotations_reach_the_packet`,
`test_extraction.py::test_secret_hidden_from_addressed_character_is_selected`. The soft marks were
first exercised live with a RisuRealm sim bot for beta.2. The extract-v3 prompt was checked against
`deepseek-v4-flash:cloud` (Ollama) on three Korean scenes, calling the sidecar prompt/validation
directly rather than through the host UI. A whispered secret came back as `limited`, with `known_by`
하나 and {{user}} and `hidden_from` 카이토 and 유이; a classroom announcement as `public`; an unexplained
object location as `unknown`. The same run showed a pre-existing prompt weakness: in one scene the
model translated entity names into English despite "keep the chat's language".

- [x] Empty or absent knowledge has one meaning (`unknown`), and unknown is never rendered as "does not
      know".
- [x] Public facts need no `known_by` list; explicit secrecy (`hidden_from`) is preserved.
- [x] The packet Note matches the stored semantics exactly; prompt and validation enforce the same rules.
- [x] Existing `known_by` / `hidden_from` rows have an explicit migration (names → limited, empty →
      unknown).
- [x] Without an LLM configured, behavior is unchanged from Phase 1.
- [x] Documented as guidance to the model, not isolation (README, `docs/guide.ko.md`).
- [x] A real extraction model returns sensible `knowledge` scopes for Korean scenes (sidecar-level run
      above; a full sim-bot run through the host UI is still owner-side).
