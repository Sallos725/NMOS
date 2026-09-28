# NMOS — 최초 구상 대비 구현 감사와 1.0 제안

> 상태: **검토용 제안**. 2026-09-27 감사 결과를 정리한 문서다.
> 기능 구현, 새 phase, ADR 변경, 릴리스 또는 현재 roadmap 변경을 승인하지 않는다.
> 현재 권한과 phase 상태는 `AGENTS.md`, `ARCHITECTURE.md`, `docs/STATUS.md`를 따른다.
> 문서 저장은 owner 요청에 따른다. 아래 테스트와 재현은 저장 직전 새로 실행한 결과가 아니라
> 같은 날 선행 감사에서 실행한 결과다.
> 같은 날 후속 검토(§13)에서 G1–G3를 strict xfail 회귀 테스트로 고정하고, K29 안내·인용 표기·노출 범위를 바로잡았다.
> 이후 owner 승인으로 G1–G3를 수정했다 (§13, ADR 0033 amendment 2). 아래 G1–G3 본문은 수정 전 관찰이다.

## 0. 결론과 기준

NMOS는 원문 원장, 수정·분기 동기화, 세대별 추출, 현재 상태 계산, 하이브리드 검색,
패킷 추적과 업그레이드를 실제로 구현한 베타 제품이다. 전체 Narrative Memory OS와
장기간 신뢰할 수 있는 stable 제품 사이에는 아직 격차가 있다.

우선순위는 새 기억 종류를 늘리는 것보다 **의미적 의존성 무효화 → 추출 검증 → 수리 → 평가·운영 gate**다.
특히 기존 테스트가 모두 통과한 상태에서도 잘못된 비밀 공개와 조용한 추출 누락을 재현했다.
현재 구조는 유지할 가치가 있으며 전면 재작성, 별도 graph DB, 저장소 교체 abstraction은 권하지 않는다.

| 기준 | 확인 결과 |
|---|---|
| 감사 대상 | `main`, `69800f08dc4d2bf618266d8458adafdb95bcb5fe` |
| 최신 공개 릴리스 | `v0.1.0-beta.21`, commit `7bfe01e40c417b80ffd558bc27199bfd2f0f35f5` |
| 최초 Git 기준 | `791dcb69e46630896371652a10f105212da9f60f`, 2026-09-22 |
| Phase 10 | main 병합, 미릴리스 |
| 사이드카 실행 | `uv run --frozen pytest -q -p no:cacheprovider` — **421 passed**, 2 deprecation warnings, 216.46 s |
| 플러그인 실행 | `npm test` — **104 passed**; `npm run typecheck` — exit 0 |
| main CI | [36320119494](https://github.com/Sallos725/NMOS/actions/runs/36320119494): sidecar, plugin, edge 성공 |
| release 검증 | GitHub asset digest와 beta.21 태그의 plugin/Compose 파일 SHA-256 일치; GHCR amd64/arm64 manifest 확인 |
| 추가 재현 | 임시 PostgreSQL DB, 실제 API·worker·조회·packet 경로, 결정적 모델 대역 |
| 미실행 | 새 실모델 호출, 실호스트 재시험, 운영 DB 변경, 장기 운영 시험, release image의 신규 설치·실행 |

공개 artifact 확인값:

- Plugin: `eddd4f90613c2f0a8116a94fda2867fbdfaeea1332244018e906cbe758090860`
- Compose: `fe074c6a2d06e5c20055febebfe0233962268926e2e685d019c859513c12ae3b`
- GHCR beta.21 index: `sha256:4fe1e8068f5ad4842df7cec7612b1e1d0b72b061a55786bda34c10b95f3c860c`

[공개 릴리스](https://github.com/Sallos725/NMOS/releases/tag/v0.1.0-beta.21),
[Phase 10 종료 PR #118](https://github.com/Sallos725/NMOS/pull/118).
CI 통과, artifact 존재, 실호스트 동작, 장기 신뢰성은 서로 다른 증거다.

## 1. Original Vision Baseline

[초기 PNME 계획](../reference/initial_narrative_memory_plan.md)과
[Ultimate NMOS 설계](../reference/ultimate_narrative_memory_architecture.md)는 최초 커밋부터 존재하며,
감사 대상의 두 파일은 최초 커밋과 바이트 단위로 동일했다. 현재 roadmap을 과거 설계로 간주하지 않았다.
이 문서의 `Ultimate §N`은 모두 Ultimate 설계의 절 번호다. 초기 PNME 계획의 절 번호가 아니다.
최초 커밋은 이미 Phase 0 구현을 포함하므로 그 이전 구상 과정은 Git만으로 복원할 수 없다.

초기 의도는 다음과 같다.

| 영역 | 최초 의도 |
|---|---|
| 통합 | 얇은 plugin과 sidecar, 응답 직전 자동 주입, 선택적 MCP 깊은 회상 |
| 원천 | 메시지·canon·수정·swipe·분기를 불변 원장으로 보존 |
| 컴파일 | entity/event/assertion, provenance, polarity, modality, authority 분리 |
| 시간 | 기록 시간·대화 순서·서사 유효 시간·지식 획득 시간 구분 |
| 지식 | 세계의 진실과 캐릭터의 앎·믿음·의심·오해 분리 |
| 서사 | 인과관계, 여러 종류의 open thread, scene/episode/arc, 동적 인물 상태 |
| 검색·선택 | SQL·lexical·vector·graph·시간·계층 검색, 정밀 인용, 예산·위험·반복 사용 제어 |
| 수리·운영 | Inspector, correction/retraction/merge/split/canon lock, migration, backup, portable archive |
| 확장 | style/procedural memory, multimodal 준비 |

현재 구현의 Phase 번호와 Ultimate §84의 단계 번호는 일치하지 않는다. §84는 단계를 `Phase 0–8`로 부르며,
[ROADMAP-1.0](../ROADMAP-1.0.md)이 혼동을 피하려고 이를 Stage로 부른다.
Ultimate §84의 `Phase 8 — Optional PocketRisu Bridge`는 **optional**이며 Ultimate §93은 v1에 필수가 아니라고 명시한다.
현재 roadmap의 bridge 필수화는 후대 owner 결정이다.
단일 호출이 여러 인물을 생성할 때의 완전한 비밀 격리 한계는 Ultimate §30에서도 인정했다.

## 2. 설계 발전과 재설계

- 호스트 가정을 [실제 관찰과 fixture](../HOST-FACTS.md)로 교체했다.
- 메시지별 추출을 턴별 추출로 바꾸어 사용자 행동과 응답을 함께 해석한다 (ADR 0008).
- prompt·registry·normalizer·endpoint·설정을 generation key에 포함한다 (ADR 0006).
- 최근 구간 재추출과 이전 세대 fallback으로 비용과 가용성을 조정한다 (ADR 0014).
- read-time entity resolution, persona 통합, owner merge를 도입했다 (ADRs 0012, 0023, 0025).
- item의 소유·위치·소멸을 함께 계산하고 소멸 후 재등장을 충돌로 표시한다 (ADRs 0016–0017).
- packet ledger·replay·echo로 선택 결과를 감사할 수 있게 했다 (ADR 0027).
- 실사용에서 드러난 관계·말투 누락을 standing ranking과 `addresses`로 다뤘다 (ADRs 0026, 0028).
- 지식 경계를 Private·strict·narrator로 좁혀 구현했다 (ADRs 0033–0035). 전체 epistemic engine은 아니다.
- 저장소 교체 가능성을 PostgreSQL 전용 계약으로 바꿨다. 실제 코드에 맞는 합리적 범위 축소다.
- owner의 명시적 대화 전체 삭제를 허용했다 (ADR 0009). 자동 원문 삭제와는 구분된다.

원래 계획보다 구체화된 강점은 host evidence, generation coverage, 패킷 설명 가능성,
이전 릴리스가 작성한 DB의 upgrade test, 실제 RP의 말투·persona 처리다.
기록된 10k 측정의 append 715→156 ms, plugin manifest 175→17 ms 개선은
[기존 성능 보고](../perf/scale.md)의 결과이며 이번 감사의 재측정값은 아니다.

## 3. Capability별 현재 상태

- **R**: Implemented + tested + released. 각 행의 좁은 범위에 대한 판정이며 무결함을 뜻하지 않는다.
- **T**: Implemented + tested, main에 있으나 미릴리스.
- **P**: Partial. **N**: Not started. **S**: Superseded / intentionally redesigned.
- **D**: Deferred beyond 1.0. 미승인 미래 기능의 존재를 승인으로 해석하지 않는다.

| Capability | 상태 | 구현·테스트·릴리스 근거 | 남은 격차 |
|---|---|---|---|
| 불변 메시지 원장 | R | `ledger`, migrations 0001/0012, `test_sidecar_integration`, beta.21 | canon 전체 원천까지 구현된 것은 아님 |
| reconcile/worldline | R | `reconcile`, `test_reconcile_fixtures`, host fixtures | 다른 host build·다중 기기 한계 |
| 결정적 상태 | R | `state`, `parsers`, `test_state`, Phase 1 | bot별 규칙 필요 |
| 비동기 추출·queue | R | `worker`, `process_extract`, `test_extraction` | G3 출력 구조 검증 |
| generation·coverage | R | `generations`, `test_generations`, beta.4 이후 | 이전 세대 오류가 fallback으로 남을 수 있음 |
| entity identity | P | `entities`, `test_entities`, owner links, beta.12/17 | 동명이인·동명 물건·잘못된 alias split |
| assertion semantics | R, 좁은 범위 | `predicates.semantics`, `test_semantics`, beta.12 | belief/suspicion/authority 전체 모델 없음 |
| 시간 모델 | P | turn/position, extraction 시각, as-of replay | 상대 서사 시간·flashback 유효 시간 없음 |
| item transition | R, item 범위 | `facts._versions`, `test_transitions`, beta.13 | 일반 verifier 아님 |
| 관계 일관성 | P | `facts.version_key`, K24 | 방향·predicate를 넘는 상태 전환 미해결 |
| soft knowledge | R | Phase 4, knowledge tests | 추출 marks 정확성에 의존 |
| 비밀 공개 생명주기 | P, main | `secrets`, `test_secrets`, Phase 10 | G1/G2, K29 |
| Private/strict/narrator | T, 제한된 계약 | `scene`, `retrieval._moded`, migration 0021 | hard ACL 아님; host text 제외·unknown 허용 |
| false belief/suspicion | N | Phase 10 out-of-scope, registry | character claim은 belief projection이 아님 |
| promise threads | R | `threads`, `test_threads`, beta.14 | 매칭·모델 오류, owner repair 없음 |
| 일반 open threads | P | goal assertion 등 존재 | 목표·빚·위협·수수께끼의 lifecycle 없음 |
| 사건 중요도·참여자 | R | salience/participant tests, beta.14/15 | observer·인과 graph까지는 아님 |
| 인과 graph | N | Ultimate §25, Stage 5 계획 | 명시적 cause/resolves 등 경로 없음 |
| scene/episode/arc | N | Ultimate §36–37 | `scene.py`는 cast 계산이지 계층 요약이 아님 |
| style/procedural memory | N | Ultimate §33/35 | 1.0 범위 배정 불명확 |
| canon/authority/lock | N, subsystem 기준 | source-kind 확장 여지는 존재 | ingest→conflict→lock 실행 경로 없음 |
| lexical/vector/RRF | R | `retrieval`, `vectors`, fallback tests | 광범위 query·장문 truncation·규모 한계 |
| 패킷 예산·원장 | R + T | beta.19 packet-v1/ledger, main packet-v4 | 실제 tokenizer 보장·overuse 제어 미완성 |
| forensic/exact quote | P | excerpt·Inspector·provenance·replay | 전용 원문 인용·깊은 탐색 없음 |
| MCP deep recall | N | roadmap R5 조건부 | host tool 실행 증거 필요 |
| Inspector·진단 | R + T | inspector API/tests | secrets/build 표시는 main |
| owner repair | P | merge·rebuild·delete | 세밀한 correction/retraction/split/resolve 없음 |
| migration·DB 복구 | R + T | beta.7/16/21 dump upgrade tests | portable archive·장기 지원 계약 미완성 |
| bridge | N | Stage 8 초안, host 성능 측정 | host 변경 승인·구현·검증 필요 |
| 저장소 abstraction | S | invariant 9 개정 | PostgreSQL 전용으로 의도적 변경 |
| 일반 LLM memory | D | roadmap After 1.0 | 현 1.0 blocker 아님 |

실행 경로를 추적한 핵심 파일:
[plugin core](../../adapters/pocketrisu-plugin/src/core.ts),
[API](../../apps/sidecar/src/nmos_sidecar/api.py),
[extraction](../../apps/sidecar/src/nmos_sidecar/extraction.py),
[facts](../../apps/sidecar/src/nmos_sidecar/facts.py),
[retrieval](../../apps/sidecar/src/nmos_sidecar/retrieval.py),
[packet](../../apps/sidecar/src/nmos_sidecar/packet.py),
[upgrade tests](../../apps/sidecar/tests/test_upgrade.py).

## 4. 재현한 정확성 문제

이 절은 합성 입력과 저장소의 `SimChat`, `SecretRecorder`, `make_client`, `sync`, `drain`, `facts`,
`recall` 도우미로 실제 API·worker·DB 재조회·packet까지 실행한 감사 기록이다.
운영 데이터나 실제 모델의 오류율에 대한 측정은 아니다. 임시 DB는 실행 후 삭제했다.
감사 당시 실행 코드는 shell heredoc에만 있었다. 후속 검토(§13)에서 G1–G3를 저장소의 strict xfail 테스트로 옮겼다.
각 테스트는 현재 목표 assertion에서 실패하며, 수정되면 XPASS로 실행이 실패해 marker 제거를 강제한다.

### G1 — P0: 이전 공개가 수정된 다른 비밀에 적용됨

**Problem:** turn 0의 비밀 내용이 바뀌어도 turn 5의 공개 기록이 새 비밀을 공개한 것으로 연결된다.

**재현:** 기본 `extract_turns=3`, 매 턴 worker 처리.

1. turn 0: `Luca secretly plans to watch the lecture, hidden from Noel.`
2. turn 1–4: 비밀과 무관한 장면.
3. turn 5: `Noel found out: Luca goal: watch the lecture.`
4. 다음 턴으로 진행해 공개가 반영됐음을 확인.
5. turn 0을 `Luca secretly plans to steal the diamond, hidden from Noel.`로 edit.
6. sync·worker 처리 후 facts와 `What does Noel know about Luca?`의 packet 조회.

**관찰:** 새 goal의 `known_by`에 Noel이 들어가고 `hidden_from`은 사라졌다.
공개 evidence는 여전히 강의를 알게 됐다는 문장이었다.

```xml
<Fact kind="goal" turn="0" known_by="Luca, {{user}}, Noel">Luca goal: steal the diamond</Fact>
```

**Impact:** 공개되지 않은 새 비밀이 알려진 것으로 취급되고 narrator/strict 판단에도 전파된다.

**Evidence:** [secrets._hits](../../apps/sidecar/src/nmos_sidecar/secrets.py)는 같은 turn·head의 후보 중
내용 유사도가 최대인 것을 최소 기준 없이 연결한다. turn 5는 수정된 turn 0의 bounded context 밖이라
기존 `learned`가 남는다. [ADR 0033](../adr/0033-secrets.md)의 재추출 재문구화 대응이
원문 자체의 내용 변경까지 같은 방식으로 취급하는 문제다.

**Recommended solution:** 동일 원문 revision의 재추출과 원문 변경을 구별하고 공개의 원천 의존성을 보존한다.
연결 근거가 바뀌면 무효화 또는 pending; 낮은 유사도·동률은 임의 확정하지 않는다.
**Scope:** Medium. **Priority:** P0, Phase 10 포함 다음 milestone의 release blocker.
**Dependencies:** ADR 0033 연결·무효화 계약 검토, 원천 수정/삭제/재추출 회귀 테스트.
이 기능이 없는 beta.21에 같은 결함이 배포됐다는 판정은 아니다.
다만 Phase 10은 `main` 병합 시 `:edge` image로 게시되며, owner의 운영 시험이 이 image를 쓴다.
따라서 태그 릴리스와 별개로 **현재 운영 시험에는 노출되어 있다**. 오래된 비밀 turn을 수정하면 재현될 수 있다.
**Regression:** `test_secrets.py::test_a_reveal_does_not_carry_over_to_a_different_secret_after_its_turn_is_edited` (수정됨).

### G2 — P1: K29의 안내된 복구가 같은 세대에서 작동하지 않음

**Problem:** 기존 채팅을 처음 일괄 추출할 때 공개 턴이 먼저 처리되면 비밀 목록이 없어 공개를 놓친다.
K29는 이후 `Extract all history`를 실행하라고 안내한다.

**재현:** 네 개의 완성된 턴을 한 번에 sync한 뒤 worker 처리:
비밀 생성 → Noel의 일상 → Noel의 공개 → 후속 장면. 그다음 history/rebuild API를 각각 실행했다.

| 단계 | 관찰 |
|---|---|
| 첫 추출 | 공개됐어야 할 비밀이 `hidden_from=Noel` |
| Extract all history | `queued.extract=0`, worker 처리 0개, 상태 불변 |
| Rebuild + 순차 worker | discarded 4, queued 4; Noel이 known_by에 추가되고 hidden_from 제거 |

**Impact:** 사용자에게 제시한 복구 방법이 정상 처리로 기록된 의미적 누락을 고치지 못한다.
공개를 놓친 turn은 그 시점에 이미 추출된 상태이므로, 이 우회책은 검증되지 않은 것이 아니라 구조적으로 효과가 없다.
**Evidence:** [schedule_generation](../../apps/sidecar/src/nmos_sidecar/extraction.py)의 `NOT EXISTS`는
같은 generation·turn hash의 extraction을 건너뛴다. [K29](../KNOWN-ISSUES.md)와 실제 경로가 다르다.
첫 sync의 job은 priority 200으로 `claim()`에서 최신 turn부터 처리된다. Rebuild의 job은 priority 250 이상이라
오래된 turn부터 처리되어 공개 turn이 앞선 비밀을 본다. 이 차이가 두 결과를 가른다.
**Follow-up:** K29 안내를 먼저 Rebuild로 정정했고, 수정 후 Extract all history로 되돌렸다.
`test_extract_all_history_recovers_a_reveal_missed_on_first_import`와 `test_rebuild_recovers_a_reveal_missed_on_first_import` 모두 통과(단일 worker).
**Recommended solution:** 누락 구간 채우기와 이미 처리된 구간 재처리를 구분하고,
비밀·공개의 의존성에 따른 재처리를 제공한다. 먼저 복구 안내를 실제 검증된 범위로 바로잡는다.
**Scope:** Medium. **Priority:** P1. **Dependencies:** G1, queue 순서·동시성 검증.
Rebuild의 이번 성공은 순차 worker 사례이며 기본 동시 worker·모든 긴 채팅에서의 보장은 아니다.

### G3 — P1: 잘못된 JSON 구조가 정상 추출 완료가 됨

**Problem:** 모델 대역이 `{"assertions":"invalid schema"}`를 반환해도 worker는 빈 목록으로 바꾸고
성공한 extraction을 저장한다.
**Impact:** provider 출력 변화나 모델 오류가 조용한 기억 누락으로 남는다. 정상적인 빈 추출과 구별되지 않는다.
**Evidence:** `process_extract`의 `if not isinstance(items, list): items = []`.
worker 실행 후 coverage는 `eligible=1, compiled=1, failed=0, percent=100, complete=true`였다.
이 줄은 Phase 2 커밋 `e21e9cd`(2026-09-22)부터 있어 **`v0.1.0-beta.1` 이후 모든 공개 릴리스에 포함**된다.
과거 실모델 fixture에서 이런 출력이 실제로 나온 빈도는 아직 세지 않았다.
**Regression:** `test_extraction.py::test_a_malformed_assertions_field_is_not_a_compiled_turn` (수정됨).
`isinstance` 분기를 예외로 바꾸는 임시 변이에서 이 테스트가 XPASS(strict)로 실패해 수정을 감지함을 확인했다.
**Recommended solution:** envelope/schema 검증으로 정상 `[]`와 invalid output을 분리하고
실패·재시도·진단 경로에 연결한다.
**Scope:** Small. **Priority:** P1. **Dependencies:** 기존 validation/worker 경로; 신규 runtime dependency 불필요.

### G4 — P1: provenance와 grounding은 다름

**Problem:** 원문은 `Hana walks beside the river.`인데 모델 대역이 identity `queen of the moon`,
evidence `Hana is the queen of the moon.`을 반환하면 fact와 packet에 들어간다.
**Impact:** source revision을 가리킨다는 사실이 해당 주장·인용을 원문이 뒷받침한다는 뜻은 아니다.
**Evidence:** [predicates.validate](../../apps/sidecar/src/nmos_sidecar/predicates.py),
[extraction.normalize](../../apps/sidecar/src/nmos_sidecar/extraction.py). API 재조회와 packet에서 확인했다.

이는 단순히 숨겨진 누락이라고 판정하지 않는다. [Phase 9 §3](../perf/phase9-packets.md)은
기존 valid assertion 3,169개를 조사한 뒤 단순 quote 일치 검사의 효용이 작다고 판단해 도입하지 않았다.
잘못된 의미 해석은 실제 인용을 달고도 발생한다. 이번 probe는 허용 경계를 확인했으며 실모델 환각률이 아니다.

**Recommended solution:** 고위험 assertion부터 grounding 상태와 pending 처리를 도입하고,
근거 불일치와 근거의 오해를 따로 평가한다. 정상 paraphrase까지 막는 단순 일치 강제는 피한다.
**Scope:** Medium. **Priority:** P2 (후속 검토에서 P1→P2). Phase 9 §3이 단순 인용 검사의 효용을 낮게 판단했으므로,
gold set으로 실제 오류율을 먼저 측정하고 그 결과로 P1 승격을 판단한다. **Dependencies:** G3, 정상·오인용·의미 오해 gold set.

## 5. 나머지 격차와 해결안

P0는 다음 해당 릴리스의 blocker, P1은 1.0 blocker, P2는 개선 권고, P3는 이후 개선이다.
P1은 두 종류로 나눠 읽는다. **정확성 P1**(G5–G10, G14)은 어떤 1.0 범위를 택하든 필요한 gate다.
**범위 P1**(G11–G13)은 현 owner roadmap의 Stages 5–7을 유지할 때만 blocker이며, 범위 결정에 따라 연기될 수 있다.

| ID / Priority | Problem → Impact | Evidence | Recommended solution | Scope / Dependencies |
|---|---|---|---|---|
| G5 / P1 | fact 수리·alias split·thread 수리 없음 → 발견한 오류도 원문 수정·전체 재추출에 의존 | K8/K23, owner links, Stage 6 | 감사 가능한 owner correction/retraction/split/resolve 입력을 fold에 반영 | Large / Stage 6 승인·우선순위 계약 |
| G6 / P1 | 관계 방향·predicate별 분리 → 화해·관계 전환 후 과거 상태가 남음 | K24, `facts.version_key`, Phase 8 2/9 관찰 | 관계 종류별 방향·대칭·감정 전환을 좁은 fixture부터 정의 | Medium / G5·관계 gold set |
| G7 / P1 | marks·근사 cast에 의존 → 누락이 필터로 전파 | `scene`, ADR 0035 | unknown 허용·host text 제외 명시; cast 누락·alias·paraphrased excerpt 평가 | Medium / G1/G2 |
| G8 / P1 | 모델·실채팅 평가 범위 제한 → 작은 성공을 일반 신뢰도로 확대할 위험 | K15/K22, v11/v12, secrets-eval | 최종 generation/policy의 held-out 평가; packet와 응답 평가 분리 | Medium / G1–G7 핵심 수정 |
| G9 / P1 | 운영·장애·지원 범위 계약 미완성 → 실제 보장 범위 불명확 | host 한 빌드, 모바일 미측정, roadmap 2주 | 지원 환경 고정, 종료·재시작·provider 장애·restore drill | Medium / 후보 artifact 고정 |
| G10 / P1 | facts/vectors를 켠 10k가 기본 deadline 초과 → 기억 없이 응답 | K1, scale.md의 3.14–3.29 s 10회 | host snapshot과 fold 비용 분리; end-to-end SLO 후 최적화 | Medium–Large / 실제 규모 측정·bridge 결정 |
| G11 / 범위 P1 | 인과·일반 thread·계층 서사 부족 → 장기적인 왜/미완료 과제 회상 한계 | Ultimate §24–37, Stage 5 | 명확한 lifecycle → 명시적 event link → 계층 요약 순서 | Large / G5/G6·phase 승인 |
| G12 / 범위 P1 | canon/authority/lock 없음 → 설정과 진행 서사 충돌 처리 부재 | Ultimate §19/66, Stage 6 | host 증거 있는 source 한 종류부터 conflict·owner override까지 완결 | Large / G5·source별 host evidence |
| G13 / 범위 P1 | exact quote/forensic 미완성 → 정확한 과거 발언·근거 연결 불확실 | excerpt·audit·Stage 7 | raw revision/범위 반환 경로부터 구현; MCP는 host 확인 후 | Medium–Large / visibility 계약·승인 |
| G14 / P1 | 버전 조합·장기 migration 정책 미완성 → build 표시가 호환 보장은 아님 | ADR 0037, release workflow | plugin/image/schema 조합·채널·rollback·지원 종료 계약 | Medium / release·복구 검증 |
| G15 / P2 | 단일 사용자·비공개 배포 가정 → LAN 오설정·평문 키/백업/기록 위험 | README Security, K21 | 지원 배포 범위 명시; 인증·로그·설정 API·백업 취급 시험 | Small–Medium / 배포 범위 |
| G16 / P2 | 문서 표류 → 완료·복구 판단 오류 | STATUS 419 vs 실행 421 (후속 검토에서 정정), Phase 10 draft 잔존, K29 (정정) | 기능 상태·evidence 상태 분리; summary drift 검사 보완 | Small / 없음 |
| G17 / P3, 권고 | style/procedural·multimodal 확장 미구현 → 초기 궁극 설계와 차이 | Ultimate 설계·After 1.0 | 1.0 포함/재설계/연기를 명시적으로 결정 | Small, 범위 결정 / owner |

G17의 전부가 이미 승인된 post-1.0 연기 사항은 아니다. 일반 LLM memory 방향만 roadmap이 명시적으로 이후에 둔다.

## 6. Architecture와 기술 부채

유지할 것: 불변 원장·파생 데이터 분리, generative worker 분리, PostgreSQL transaction과 명시적 SQL,
순수한 entity/fact/thread fold, host adapter 경계, generation coverage, packet ledger.

주요 부채:

1. **의미적 의존성이 K턴을 넘어섰다.** OPEN PROMISES/SECRETS와 entity hints는 오래된 파생 기억을
   새 추출의 입력으로 쓴다. 특히 secret reveal은 목록의 존재에 따라 생성 여부가 달라진다.
   bounded context만으로 의존성 무효화를 설명할 수 없다.
2. **read-time fold가 assertion 수에 따라 비싸진다.** cache/checkpoint가 필요하면
   head·generation·resolver·owner repair 버전과 무효화 계약을 먼저 정해야 한다.
3. **재구축과 동일 결과 재현은 다르다.** 저장된 assertion의 fold는 결정적이지만 외부 모델 재추출은
   결과가 달라질 수 있다. replay도 원문 prefix 변경·이전 vector 부재·read-side 규칙 변경의 제한이 있다.
4. **provenance가 있는 잘못된 주장도 가능하다.** 원문 추적성, 인용의 실제 존재, 의미적 지지 여부를
   별도의 검증 수준으로 다뤄야 한다.

2026-09-26 감사의 이미 해결된 문제를 현재 결함으로 다시 세지 않았다.
[후속 기록](../audits/NMOS-AUDIT-2026-09-26-REVIEW.md), 현재 코드와 이번 회귀 실행을 교차 확인했다.

## 7. Roadmap 감사와 권장 순서

[현재 roadmap](../ROADMAP-1.0.md)은 evidence와 upgrade·운영 기간을 포함한 점이 좋다.
다만 다음은 정리해야 한다.

- 승인된 Phase 10 완료와 초기 Stage 4 전체 완료를 구분한다. observer model·principal ACL·false beliefs 전체는 없다.
- Stage 0–3 완료도 원래 문서의 MCP·넓은 temporal/compiler 범위 전체 완료로 읽히지 않게 한다.
- 초기 optional bridge의 현 필수화는 owner의 후대 결정으로 기록한다.
- Stage 6의 DB backup/restore는 이미 존재한다. 없는 portable archive·수리 데이터 계약과 구별한다.
- `No category may get worse`에 표본·동일 조건·허용차·예외 승인 기준을 붙인다.
- `2주 동안 heavy change 없음`을 실제 요청·mutation·복원·미해결 결함 기준으로 보완한다.
- correctness 결함을 단순 accepted trade-off로 분류해 gate를 우회하지 않게 한다.

권장 순서: **G1–G3 → 평가 기준 → 수리·검증 → 관계·명시적 인과·thread → 계층 서사 → forensic → 필요한 host 개선 → 안정화**.
이 순서는 Stage 6(수리)의 일부를 Stage 5보다 앞에 둔다. ROADMAP-1.0의 "stage당 한 release, R1 순서" 원칙과 충돌하므로
적용하려면 roadmap 변경 결정이 필요하다 (§12의 6).
현재 owner의 Stages 4–8 조건을 유지하면 bridge도 필수다. bridge를 지원 규모에 따라 선택적으로 만들거나
이후로 미루려면 별도 owner 결정이 필요하다. 이 문서는 그 결정을 대신하지 않는다.

## 8. Release Readiness

| 판정 | 이미 있는 것 | 미충족 / blocker | 권장 gate |
|---|---|---|---|
| 기능적 beta 탈피 | 실제 memory pipeline, 상태·검색·추적, deterministic suite, 제한된 실호스트·모델 증거 | G1–G3, 의미 오류 수리, 관계·entity 일관성, 품질 계약 | 명시한 기능 범위가 edit/rebuild/upgrade 후에도 일관되고 오류를 발견·수리할 수 있음 |
| GitHub prerelease 해제 | 공개 artifact, lockfile/CI, 실제 데이터 upgrade, 설치·복구 문서 | 최종 후보 설치·복원·지원 환경·성능·운영 evidence | 일반 사용자가 지원 환경에서 설치·업데이트·복구 가능; 현 정책상 1.0 전 해제 안 함 |
| 1.0 stable | 유지 가능한 핵심 구조 | 승인된 milestone 범위, 호환성·지원 정책, 수리, 정확성·운영 gate | 아래 checklist와 승인된 범위를 모두 충족 |

`0.2.0`처럼 버전 문자열에서 beta가 없어져도 기능적 안정성이나 GitHub prerelease 해제를 뜻하지 않는다.
현재 정책은 모든 1.0 이전 릴리스를 GitHub prerelease로 게시한다.

## 9. Proposed Path to 1.0

| 순서 | 목적 | 규모 | Blocker | Acceptance criteria |
|---|---|---|---|---|
| 1 | G1–G3 수정·Phase 10 재검증 | Medium | 다음 milestone | 비밀 원천 변경 후 잘못된 지식 없음; first-import 공개 처리; invalid JSON 성공 처리 없음 |
| 2 | 최종 모델·패킷 평가 기준 | Medium | 1.0 | held-out 질문·정답·금지 기억·평가 방식·artifact 고정 |
| 3 | owner repair·의미 검증 | Large | 1.0 | correction/retraction/split/resolve가 rebuild·generation 변경 후 유지 |
| 4 | 관계와 명시적 narrative link | Medium–Large | 현 roadmap | 방향 전환·화해·thread 해결·삭제 후 복원 통과 |
| 5 | 남은 narrative 범위 | Large | 현 roadmap | 선택된 thread·scene/episode 요약이 최장 채팅의 budget 내 정답 근거 제공 |
| 6 | canon·forensic | Large | 현 roadmap | source별 host evidence, canon 충돌, 정확 인용 범위, MCP 여부 결정 |
| 7 | 지원 규모 성능·host 개선 | Medium–Large | 범위에 따름 | facts/vectors를 켠 warm/cold/edit 지연과 memory 제공률 기준 통과 |
| 8 | 후보 동결·운영·복구 | Medium + 관찰 기간 | 1.0 | 동일 artifact의 upgrade/restore/장애 시험·최소 14일 실제 운영 통과 |

**출시 시점은 조건으로 판단한다.** 정확성 결함과 수리가 해결되고 승인된 범위를 충족한 동일 후보가
모델·호스트·업그레이드·복구·성능 검증을 통과한 뒤, 최소 14일의 의미 있는 운영에서
release-blocking regression이 없으면 stable candidate로 판단할 수 있다.
14일은 현 roadmap의 2주 조건을 유지한 것이며 idle 상태의 경과 시간만으로 충족하지 않는다.
Git에서 관찰되는 약 6일의 개발 이력만으로 낙관/현실/보수 출시 날짜를 추정할 근거는 부족하다.

## 10. Final Stable Release Gate — 제안

### 범위와 계약

- [ ] 초기 capability를 구현 / 재설계 / 이후 연기로 분류했다.
- [ ] Phase 완료와 원래 Stage 전체 완료를 구분했다.
- [ ] 지원 host build·브라우저·배포·모델 설정·대화 규모를 명시했다.
- [ ] soft privacy·strict·narrator의 보장과 제외 범위가 일관된다.

### 정확성과 수리

- [ ] G1–G3를 회귀 테스트로 고정하고 통과했다.
- [ ] edit/delete/reroll/swipe/branch/disable 후 금지된 기억이 패킷에 나타나지 않는다.
- [ ] 비밀 원천과 공개 턴을 각각 수정·삭제해도 지식 상태가 올바르다.
- [ ] first import·generation 변경·rebuild·복수 worker의 의존성 처리를 검증했다.
- [ ] malformed output·근거 없는 assertion·모호한 연결이 정상 완료나 fact로 위장되지 않는다.
- [ ] owner 수리가 rebuild·upgrade·generation 변경 후 보존된다.

### 평가

- [ ] 최종 extractor generation·packet policy로 전체 평가를 실행했다.
- [ ] 기존 421/104개 테스트와 이후 추가한 회귀 테스트가 통과하며 필수 skip이 없다.
- [ ] 결정적 packet 평가와 실제 모델 응답 평가를 구분했다.
- [ ] 공개 scene과 별도의 held-out 실제 채팅 사례를 사용했다.
- [ ] 현재/과거 상태·관계·약속·비밀·irrelevant query·exact quote를 각각 채점했다.
- [ ] leak·holder recall·slip/near miss를 별도 기록했다.
- [ ] 확률적 회귀의 표본·판정 기준·예외 승인 방식을 실행 전에 정했다.
- [ ] gate 도구가 필수 조건 미달을 실패로 반환한다. 표 출력만으로 통과시키지 않는다.

### 운영과 출하

- [ ] beta.21 및 지원하는 각 중간 milestone DB의 upgrade를 통과했다.
- [ ] backup을 새 설치에 restore해 원문·수리·설정·핵심 packet 결과를 비교했다.
- [ ] worker 중단·DB 재시작·provider timeout/rate limit/잘못된 응답 후 복구를 검증했다.
- [ ] facts/vectors를 켠 지원 규모에서 warm/cold/deep-edit SLO와 memory 제공률을 충족했다.
- [ ] plugin·image·schema·문서가 같은 후보를 가리킨다.
- [ ] release asset checksum·실제 설치·지원 플랫폼 실행을 확인했다.
- [ ] 인증·설정 API·로그·백업의 비밀정보 취급이 지원 배포 정책과 일치한다.
- [ ] 최종 후보의 최소 14일 실제 사용 기록이 있고 미해결 release blocker가 없다.
- [ ] 중대한 기능·schema·prompt·packet 변경 시 영향받는 검증을 다시 수행했다.

## 11. Risks / Unknowns

- 실모델 결과는 제한된 모델·대화·반복의 증거다. 일반 RP 정확도를 확정할 수 없다.
- secrets 평가의 48회는 모델·정책·strict 조건·수정 전후를 합친 수치다.
  최종 packet-v4 하나가 독립적인 48개 사례를 통과했다는 뜻이 아니다.
- 실제 사용자 scene과 응답 일부는 저장소 밖에 있어 이번 감사에서 독립 재채점하지 않았다.
- 같은 endpoint/model 이름 아래 provider 모델이 바뀌면 generation key만으로 감지되지 않을 수 있다.
- 배타적 queue claim은 의미적으로 의존하는 작업의 완료 순서 보장이 아니다.
- 한 PocketRisu 빌드의 증거를 upstream RisuAI·모바일·group chat으로 확대할 수 없다.
- 여러 주·여러 사용자·매우 긴 실제 대화에서 누적 오류율과 성능은 확인되지 않았다.
- 이번 감사에서 새로운 raw-data loss는 재현하지 않았다. 그것이 모든 장애에서의 무손실 증명은 아니다.

## 12. 검토가 필요한 결정

1. G1을 다음 Phase 10 milestone의 release blocker로 반영할지.
2. G2/G3와 수리·검증을 다음 기능 확장보다 먼저 처리할지.
3. 초기 Stage 4의 미구현 범위를 1.0 포함 / 의도적 재설계 / 이후 연기로 어떻게 정리할지.
4. Stage 8 필수 조건을 유지할지, 지원 대화 규모의 SLO에 연결할지.
5. 최종 모델 평가·운영 gate의 표본과 성능 기준을 무엇으로 승인할지.
6. §9처럼 수리(Stage 6 일부)를 Stage 5보다 앞에 둘지, 아니면 G1–G3만 먼저 고치고 roadmap 순서를 유지할지.
7. G1·G2가 있는 `:edge`로 운영 시험을 계속할지. 수정 전까지 오래된 비밀 turn의 수정은 피하고,
   기존 채팅 연결 후에는 Extract all history가 아니라 Rebuild를 쓴다.

이 결정과 필요한 phase/ADR 승인 전에는 제안 문서만으로 미래 기능을 구현하지 않는다.

## 13. 후속 검토 (2026-09-27)

같은 날 이 문서를 `69800f0` 기준으로 다시 검토했다. 코드 대조로 G1–G3의 원인 위치를 확인했다
(`secrets.py`의 `_hits`, `extraction.py`의 `schedule_generation`·`process_extract`).
테스트 수는 `pytest --collect-only`로 421개를 확인했다.

| 변경 | 내용 |
|---|---|
| 회귀 테스트 | G1–G3 strict xfail 3개와 Rebuild 복구 테스트 1개. `--runxfail`로 각 xfail이 목표 assertion에서 실패함을 확인했다 |
| K29 | 우회책을 Extract all history → Rebuild memory로 정정 (`docs/KNOWN-ISSUES.md`) |
| STATUS | 테스트 수 419 → 425, 노출 범위(G1/G2는 `:edge`, G3은 beta.1부터) 기록 |
| 이 문서 | `Ultimate §N` 인용 표기, G1 운영 노출, G2 구조적 원인, G3 출시 이력, P1 두 종류 분리, G4 P2 조정, 결정 항목 6–7 |

외부 artifact(CI run, release digest, GHCR manifest)는 후속 검토에서 다시 확인하지 않았다.

### G1–G3 수정 (2026-09-27, owner 승인)

| ID | 수정 | 남은 한계 |
|---|---|---|
| G1 | worker가 OPEN SECRETS와 함께 각 비밀 turn의 hash를 `extraction.hints`에 저장한다(모델에는 보이지 않음). 읽을 때 공개의 `listed_hash`와 그 turn의 현재 hash가 다른 비밀에는 turn 연결(규칙 1)을 쓰지 않는다. 내용 일치(규칙 2)만 남고, 맞지 않으면 unmatched로 보고되어 비밀이 유지된다 | 수정 전에 추출된 공개는 hash가 없어 기존 연결을 유지한다 |
| G2 | Extract all history가 앞선 turn의 현재 비밀이 어떤 세대로든 추출되기 전에 추출된 turn을 discard하고 오래된 순서로 다시 추출한다. 이전 문구의 비밀을 본 turn은 건너뛴다 | 재추출 대기 중에는 그 turn의 fact가 이전 세대에서 오거나 비어 있다. worker 2개가 이웃 turn을 동시에 처리하면 한 번 더 실행해야 할 수 있다 |
| G3 | `assertions` 리스트가 없는 응답은 `LLMError`로 job을 실패시킨다(backoff 재시도 후 failed) | 기록된 실모델 응답 1,922건은 모두 리스트였다 |

extractor generation은 바뀌지 않는다: prompt·registry·normalizer가 같고, hash는 hints에만 저장된다.
성능: 10,000 메시지(5,000 turn, 공개 99개)의 사실 읽기는 main과 같은 p50 ≈57 ms이다. G2 판정은 모든 turn이 대상인
최악 조건에서 ≈104 ms이다. 비교를 SQL에서 하던 첫 구현은 CTE가 두 번 참조되어 사실 읽기를 ≈129 ms로 늘렸으므로 폐기했다.

