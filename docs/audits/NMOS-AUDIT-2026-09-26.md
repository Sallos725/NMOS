# NMOS 감사 보고서 — 2026-09-26

- 기준 커밋: `3fee5a8` (`main`, 태그 `v0.1.0-beta.19`). 요청문은 `v0.1.0-beta.18`을 현재로 적었으나 `main`은 그보다 한 릴리스 앞선 beta.19이며, Phase 9(ADR 0027)까지 병합·릴리스된 상태다 [확인됨: `git describe`, `docs/STATUS.md`].
- 감사 범위: `AGENTS.md`, `ARCHITECTURE.md`, `docs/`, `migrations/`, `apps/sidecar/`, `adapters/pocketrisu-plugin/`, `tools/`, `docker*`, `.github/workflows/`. 외부 유료 API를 부르는 명령은 실행하지 않았다. 실행한 명령과 결과는 부록 C.
- 라벨: `[확인됨]` 코드·실행으로 직접 확인 / `[추론]` 읽은 근거에서의 추론 / `[제안]` 권고.
- 이 문서는 요청문의 라벨·절 체계를 따라 한국어로 쓴다(저장소의 다른 문서는 영어). 쓰기는 이 파일 하나뿐이며 다른 파일은 고치지 않았다.

---

## 0. 요약

### 판정

**베타(후기 베타)가 맞다. production-ready는 아니다.** 근거: 원본 원장은 DB 트리거로 보호되고(마이그레이션 0001/0012), 재구축 가능한 projection·세대(generation) 키·패킷 원장(ledger)·재생(replay)이 실제로 구현돼 있으며, 사이드카 327 · 플러그인 89 테스트가 모두 통과하고 결정적 평가 35케이스에서 stale 주입 0건이다 [확인됨]. 그러나 (1) 한 대화의 기억을 조용히 영구 차단하는 실제 버그 2건(A-01, A-02)을 몇 시간 안에 재현했고, (2) 보안 기본값이 loopback 가정에만 의존하며(A-05), (3) 실모델 증거는 1~2개 모델·3회 반복의 방향성 증거이고(A-17), (4) 릴리스 이틀 만에 문서–코드 불일치가 9건 쌓였다(A-07). 호스트 빌드 1개(`a14c911`/v1.12.0)에서만 검증됐다(K7).

### 가장 중요한 발견 5개

| ID | 심각도 | 확신 | 요지 |
|---|---|---|---|
| A-01 | High | [확인됨] 재현 | 메시지 본문에 lone surrogate(짝 없는 UTF-16 서로게이트)가 있으면 `/v1/sync/bodies`가 500으로 실패한다. 해시는 양쪽이 일치하지만 psycopg가 UTF-8로 인코딩하지 못한다. 그 대화는 매 요청마다 `needs_bodies`→500을 반복해 **영구히 동기화·기억 없이** 진행된다(fail open이라 채팅은 계속됨). |
| A-02 | Medium | [확인됨] 재현 | 모델 응답이 패킷 여는 태그 `<NarrativeMemory version="0" source="nmos">` 문자열을 인용하면 `prompt.ts:hasPacket`이 assistant 메시지에서도 참이 되어, 그 대화는 이후 **동기화·주입 모두 조용히 중단**된다(그 메시지를 수정할 때까지). |
| A-03 | Medium | [확인됨] | 개발용 `docker-compose.yml`은 `NMOS_LLM_JSON_MODE`를 worker에만 넘긴다. `json_mode`는 추출 세대 키의 일부라(`extraction.py:extractor`) 값을 바꾸면 사이드카와 worker의 세대 키가 갈라져 **추출 작업이 영원히 claim되지 않는다**(pending 표시만 남음). 릴리스 compose는 앵커를 공유해 안전하다. 별도로 README가 문서화한 `NMOS_EXTRACT_HINTS`는 두 compose 모두 컨테이너에 전달하지 않는다. |
| A-05 | Medium | [확인됨] 코드 / [추론] 공격 경로 | 토큰이 기본 꺼짐이고 `Host` 헤더 검증이 없다. `/v1/config/models`·`/v1/config/test`는 호출자가 지정한 URL로 **저장된 LLM API 키를 Bearer로 보낸다**. 같은 PC의 다른 프로세스, 또는 DNS rebinding 페이지가 loopback 사이드카에 닿으면 채팅 열람·설정 변경·키 유출이 가능하다. README는 LAN 노출 시나리오만 경고한다. |
| A-07 | Medium | [확인됨] | 문서 표류 9건: README `H1–H14`(실제 H17), README/`guide.ko.md` "unreleased/다음 릴리스 `extract-v10`"(beta.19에 이미 출시), AGENTS "`PHASE-8.md` is the latest", ARCHITECTURE §6 "token auth via `saveSecretHeader`"(ADR 0003과 모순), §7 레이아웃, STATUS `D1–D38`(실제 D39)·`PHASE-0.md`–`PHASE-7.md`, 불변식 9 vs 실제 코드(A-06), D9 `character_pov`(구현 없음). `tools/check_release.py`는 이런 불일치를 잡지 못한다. |

### 먼저 할 작업 (우선순위 순)

1. A-02: `hasPacket`/`injectPacket`을 "`role === 'system'`이고 내용이 태그로 **시작**"으로 좁히고 회귀 테스트 추가 (플러그인 한 줄, 릴리스 필요).
2. A-01: 플러그인 `canonical.ts:normalizeText`와 사이드카 `canonical.py:normalize_text` 양쪽에서 lone surrogate를 U+FFFD로 치환하고 `fixtures/unit/revision-hash-v1.json`의 8번 벡터를 갱신 (해시 계약 변경이라 오너 승인 항목).
3. A-04: `worker.py:run_once`에서 `Exception` 전체를 잡아 job을 실패 처리(스레드 사망 방지).
4. A-03: 개발 compose에 `NMOS_LLM_JSON_MODE`·`NMOS_EXTRACT_HINTS`를 양쪽 서비스에 추가, 릴리스 compose에 `NMOS_EXTRACT_HINTS` 추가; worker가 "활성 세대 ≠ 내 핸들러 세대"를 감지하면 경고 로그.
5. A-07: 문서 9건 일괄 수정 + `check_release.py`에 D/H/K 최대 번호와 phase 파일 목록 교차검사 추가.
6. A-09: K1의 "10k에서 여유 ≈0.25 s"를 추출·임베딩 **켠** 상태로 재측정하거나 문구를 좁힌다.

### 오너 결정이 필요한 항목

| 항목 | 이유 | 선택지 (권장 먼저) |
|---|---|---|
| A-01 해시 정규화 변경 | 교차 언어 해시 계약(`fixtures/unit/revision-hash-v1.json`) 변경 | (a) 양쪽 `normalizeText`에서 U+FFFD 치환, 픽스처 갱신 / (b) 사이드카에서 해당 본문만 명시적 거부(422)로 바꾸고 계약 유지 — 그 대화는 여전히 동기화 불가 |
| A-05 Host 허용 목록 / 토큰 기본값 | 보안 기본값 변경, route=server 사용자에 회귀 위험 | (a) `NMOS_ALLOWED_HOSTS` 도입, 기본 loopback 이름만, 토큰 설정 시 검사 생략 / (b) 문서만 보강 / (c) 토큰 기본 필수화(ADR 0003 개정) |
| A-06 불변식 9 문구 | 불변식은 명시 결정으로만 바뀜 | (a) "저장소는 PostgreSQL 전용이며, 교체 가능성은 목표가 아니다"로 개정 / (b) 유지하고 repository 계층을 실제로 도입(권장하지 않음) |
| A-10 Vertex 지원(ADR 0022) | 실제 Vertex 미검증 기능이 런타임 의존성 `google-auth`(+`cryptography`)를 끌어옴 | (a) 오너 키로 1회 검증 후 유지 / (b) "experimental" 표기 / (c) 제거 |
| A-15 pre-turn 세대용 `window_hash` 호환 경로 | ADR 0008 이전 세대 지원 종료는 결정 사항 | (a) 헤드를 서빙하는 v3 이하 추출이 없음을 쿼리로 확인 후 제거(ADR) / (b) 유지 |
| A-14 `Predicate.epistemic` 필드 | 읽는 코드가 없지만 레지스트리 지문에 포함돼 제거 시 재추출 비용 | (a) 다음 세대 변경 때 함께 제거 / (b) 유지 |
| K26 토큰 추정 | 이미 STATUS의 열린 결정 | 변경 없음(감사 의견: 측정 없이는 바꾸지 말 것) |

---

## 발견 목록

| ID | 심각도 | 라벨 | 요지 | 근거 | 관련 |
|---|---|---|---|---|---|
| A-01 | High | 확인됨 | lone surrogate 본문 → `/v1/sync/bodies` 500 → 대화 영구 미동기화 | `ledger.py:store_bodies` 내 INSERT에서 `UnicodeEncodeError` 재현(부록 C-6) | 불변식 fail-open, `canonical.py:canonical_json`, 픽스처 벡터 8 |
| A-02 | Medium | 확인됨 | 응답이 패킷 태그를 인용하면 `hasPacket` 오탐 → 동기화·주입 중단 | `prompt.ts:hasPacket`, `core.ts:beforeRequest` 235행; vitest 재현(부록 C-5) | H2, D13 |
| A-03 | Medium | 확인됨 | 개발 compose 환경변수 비대칭(`NMOS_LLM_JSON_MODE`) → 세대 키 불일치 → 추출 정지; `NMOS_EXTRACT_HINTS` 미전달 | `docker-compose.yml`, `deploy/docker-compose.yml`, `extraction.py:extractor`, `worker.py:handlers` | D20, ADR 0006, K19 |
| A-04 | Medium | 확인됨 | worker 루프가 `LLMError/psycopg.Error/ValueError/KeyError`만 잡음; `TypeError` 등은 스레드를 죽이고 프로세스는 살아 있음 | `worker.py:run_once`, `worker.py:loop`; `llm.py:ChatModel.complete_json`의 `message: null` 경로, 삭제 경쟁 시 `normtext.get` None | ADR 0009 §4 |
| A-05 | Medium | 확인됨/추론 | Host 검증 없음 + 토큰 기본 꺼짐 + 설정 API가 저장 키를 임의 URL로 전송 | `api.py:create_app`(`auth`, `test_config`, `config_models`), `runtime.py:list_models` | ADR 0003, K21 |
| A-06 | Low | 확인됨 | 불변식 9("저장소 교체 가능")가 코드와 모순: repository 계층 없음, pg_trgm/pgvector/`set_config` 직접 사용 | `retrieval.py:_lexical`, `vectors.py:vector_candidates`, `facts.py` SQL, ARCHITECTURE §6 | 불변식 9 |
| A-07 | Medium | 확인됨 | 문서 표류 9건, 릴리스 검사 범위 밖 | 표 "문서–코드 불일치" | `tools/check_release.py` |
| A-08 | Low | 확인됨 | 사이드카 시작 작업(정규화 백필·프루닝·턴 갱신·상태 백필·세대 활성화)이 **한 트랜잭션**; 배치 커밋이 savepoint로 격하, 중단 시 전부 재시작 | `api.py:create_app` lifespan, `db.py:make_pool`(autocommit=False), psycopg_pool `with conn:` | D21 |
| A-09 | Medium | 추론 | K1의 10k 여유 0.25 s는 추출·벡터 **끈** 실호스트 측정; 켜면 사실 읽기 ≈101–314 ms + 벡터 ≈104 ms + 질의 임베딩이 더해져 기본 3 s를 넘길 가능성 | `docs/perf/scale.md`, `docs/perf/phase8-extraction.md`, 부록 C-8 벤치 | K1, D24 |
| A-10 | Low | 확인됨 | Vertex 서비스계정 지원이 실서비스 미검증인 채 런타임 의존성 추가 | `vertex.py`, `pyproject.toml`, ADR 0022 | ADR 0022 |
| A-11 | Low | 확인됨 | Inspector 링크의 `?token=`이 uvicorn 접근 로그·브라우저 기록에 남음 | `inspector.py:query`, uvicorn 0.53 `get_path_with_query_string`, `docker/sidecar.Dockerfile` CMD | K21 |
| A-12 | Low | 추론 | 기억 오염(memory poisoning): 서술체로 심긴 지시문이 추출 LLM을 거쳐 사실이 될 수 있음. 방어는 source 분류·"Reference only" Note뿐, 평가 케이스 없음 | `extraction.py:SYSTEM_PROMPT`, `packet.py:PACKET_NOTE`, `docs/proposals/TRACK-B-PHASE-5-PLUS.md` §9 | 불변식 3 |
| A-13 | Low | 추론 | 같은 채팅을 두 탭/기기에서 번갈아 생성하면 헤드가 왕복해 `delete`/`reroll` 커밋과 사실 깜빡임이 생김(손실은 없음, stale 주입도 없음) | `reconcile.py:plan`, `retrieval.py:retrieve`(fresh 검사) | K16 |
| A-14 | Low | 확인됨 | `Predicate.epistemic`("world"/"belief")은 어디서도 읽지 않으나 레지스트리 지문에 포함 | `predicates.py:REGISTRY`, `extraction.py:extractor` | D6, D20 |
| A-15 | Low | 확인됨 | per-message `window_hash` 호환 경로(ADR 0008 이전 세대) 상존 | `ledger.py:_membership_rows`, `facts.py:ACTIVE_ASSERTIONS_TEMPLATE` | ADR 0008, ADR 0014 |
| A-16 | Medium | 확인됨 | 과거 DB에서의 업그레이드 검증이 커밋되지 않은 스크래치 스크립트로만 수행됨; 롤백 절차 미문서화 | `docs/perf/phase6-extraction.md`·`docs/perf/phase7-extraction.md`·`docs/perf/phase8-extraction.md`의 "Upgrade from", `apps/sidecar/tests/test_generations.py:beta3_upgrade`(벡터만) | K19 |
| A-17 | Medium | 확인됨 | 실모델 증거 강도: Phase 5–8 = 모델 1개·장면당 3회; v9/v10/Phase 9 = 모델 2개; 답변 프로브 8건×3회; 오너의 응답 모델은 미사용 | `docs/perf/*extraction*.md`, `docs/perf/phase9-packets.md` §8 | K15, K22 |
| A-18 | Low | 확인됨 | 플러그인이 호스트 "전체 데이터베이스" 권한을 요청하나 페르소나 이름만 읽음(호스트 API 한계) | `host.ts:risuHost.personas`, H17 | ADR 0023 |
| A-19 | Low | 확인됨 | 테스트 카운트·경로 시간에 벽시계 의존(플러그인 deadline 테스트 <300 ms, manifest 캐시 1.8 s) → CI 과부하 시 flaky 가능 | `test/core.test.ts`, `test/manifest-cache.test.ts` | — |
| A-20 | Low | 확인됨 | `state.py:rebuild_state`가 전체 revision을 `fetchall()`로 적재(규칙 변경 시) | `state.py:rebuild_state`, `state.py:sync_rules` | D16 |
| A-21 | Info | 확인됨 | 플러그인 2,516줄 중 UI(패널·HUD·i18n·form) 1,511줄(60 %); 요청 경로 ≈1,000줄. "얇다"는 책임 기준으로 성립, 크기 기준으로는 아님 | `wc -l adapters/pocketrisu-plugin/src` | ARCHITECTURE §3 |
| A-22 | Low | 확인됨 | `retrieval_trace(conversation_id)` 인덱스 없음; 목록 API가 대화당 상관 서브쿼리 3개 | `readmodel.py:list_conversations`, `migrations/0001_source_layer.sql` | 현재 규모 불필요 |

---

## 1. 목적과 실제 구현

**한 문장 정의** [확인됨]: PocketRisu(RisuAI V3 플러그인 API) 롤플레이 사용자가 긴 채팅에서 컨텍스트 밖으로 밀려난 것을, 불변 원본 원장 위에 재구축 가능한 projection(파서 상태·LLM 추출 사실·엔티티·약속 스레드·벡터)을 얹고 매 주 생성 직전에 예산 내 XML 패킷으로 되살려 주는 로컬 사이드카 + 얇은 플러그인.

**약속 vs 실제** (README/ARCHITECTURE ↔ 코드):

| 약속 | 코드 | 판정 |
|---|---|---|
| 편집·삭제·리롤·스와이프·Continue·숨김·Cut·분기·가져오기 추적 | `reconcile.py:plan`, `reconcile.py:turn_layout`, 픽스처 기반 18개 테스트 | 성립 [확인됨] |
| 사이드카 다운/지연 시 채팅 계속 | `core.ts:beforeRequest` try/catch + `DeadlineError`, 30 s miss cache | 성립 [확인됨] |
| 원본 불변 | 트리거 `source_revision_guard`, `source_revision_no_delete`(0001, 0012) | 성립 [확인됨] |
| "Storage is replaceable"(불변식 9) | SQL이 도메인 코드에 직접 있음 | 불성립 (A-06) |
| `character_pov` 모드(D9) | 코드 없음 | 미구현(문서는 "not authorized"로 별도 표기) |
| 환경변수 `NMOS_EXTRACT_HINTS`(README 표) | compose가 컨테이너에 전달하지 않음 | 불성립 (A-03) |

**복잡도 비중** [확인됨, 줄 수 기준]: 사이드카 6,677줄 중 핵심 경로(reconcile 344, ledger 477, canonical 85, retrieval 332, packet 337, facts 513, entities 233, threads 191, predicates 265, extraction 673, vectors 182, state/parsers 206) ≈ 3,840줄(58 %); 부가 기능(inspector 661, audit 201, runtime 184, vertex 111, retention 198, readmodel 95) ≈ 1,450줄(22 %); 나머지는 API·설정·worker. 플러그인은 UI가 60 %(A-21). Vertex(111 + form.ts 일부)와 HUD(349)는 격리돼 있어 요청 경로를 건드리지 않는다.

---

## 2. 구조

### 실행 흐름 (파일 단위)

```text
PocketRisu beforeRequest(formated, mode)
  └ entry.ts → core.ts:beforeRequest
      ├ prompt.ts:hasPacket / userTurnIndex (D13 게이팅)            ← A-02
      ├ host.ts:currentChat (getChatFromIndex)                      ← 호스트 stall(K1)
      ├ manifest.ts:createManifestBuilder (SHA-256, canonical.ts)   ← hash v1
      ├ cache key (chat.id + 모든 (id, hash))                        ← 상태 정확 캐시
      ├ POST /v1/sync/reconcile ──► api.py:do_reconcile
      │     ├ ledger.py:lock_conversation (FOR UPDATE)
      │     ├ api.py:append_reconcile (ADR 0010 증명: prefix hash·중복 id·allBefore·헤드 멤버·load_tail)
      │     │     └ reconcile.py:plan_append → ledger.py:apply_append
      │     └ 실패 시 ledger.py:load_state → reconcile.py:plan → ledger.py:apply_plan
      │           (worldline_commit / worldline_append / active_membership(turn, turn_hash))
      │     └ extraction.py:enqueue_after_apply (job 큐)
      ├ needs_bodies → POST /v1/sync/bodies → ledger.py:store_bodies   ← A-01
      │     └ on_insert: normtext.py:write, state.py:write_state
      ├ POST /v1/retrieve ──► retrieval.py:retrieve
      │     ├ fresh 검사(active_commit, manifest_hash)  → stale면 빈 패킷
      │     ├ retrieval.py:gather: _lexical(pg_trgm) + vectors.py:vector_candidates + fuse(RRF)
      │     │     + state.py:current_state + facts.py:memory_view(→ entities.py:resolve, threads.py:fold)
      │     │     + facts.py:relevant_facts / threads.py:relevant_threads
      │     ├ packet.py:compile_lines (packet-v0/v1, 원장 lines)
      │     └ retrieval_trace INSERT (ledger, 입력, 옵션)
      └ prompt.ts:injectPacket (system 메시지, 사용자 턴 앞)

nmos-worker (별도 프로세스, 스레드 N)
  └ worker.py:loop → extraction.py:claim (SKIP LOCKED, 세대 키 일치만)
      ├ extraction.py:process_extract → llm.py:ChatModel → predicates.py:validate → assertion
      └ vectors.py:process_embed → revision_embedding
  └ worker.py:maintenance (30 s 설정 재적재, 10 min prune: retention.py)
```

### 계층 책임 (ARCHITECTURE §3) 준수 여부 [확인됨]

| 계층 | 코드 | 준수 | 비고 |
|---|---|---|---|
| Host Adapter | `adapters/pocketrisu-plugin/src/*` | 예 | DB·랭킹·추출 없음. 호스트 호출은 `host.ts`에만 있음. UI가 크지만 요청 경로와 분리 |
| Source Layer | `ledger.py`, `reconcile.py`, `canonical.py`, 마이그레이션 0001/0012/0013 | 예 | 내용 해석 없음 |
| Compiler | `extraction.py`, `predicates.py`, `normtext.py`, `parsers.py`, `vectors.py` | 예 | provenance 없는 쓰기 없음 |
| Projection | `facts.py`, `entities.py`, `threads.py`(read-time), `state_observation`, `revision_embedding` | 예, 단 모듈 경계 없음 | "projection layer"가 `facts.py` 내부 fold + SQL로 암묵적 (§5 참고) |
| Retrieval | `retrieval.py`, `packet.py`, `audit.py` | 예 | 정규 쓰기 없음(trace만) |

### 플러그인이 "얇다"는 주장 [확인됨]

- 책임: ID 캡처·manifest·게이팅·주입·출력 알림·설정·패널. 기억 로직(랭킹·추출·임베딩·DB) 없음. `beforeRequest` 안에 재시도 루프 없음(H2 대응은 miss cache).
- 크기: 요청 경로 ≈1,000줄, UI 1,511줄. `ui.ts` 780줄이 가장 큰 파일. "얇다"는 책임 기준으로 성립.
- 한 가지 흠: 플러그인이 사이드카 HTML을 렌더하지만 `inspector.ts:safeFragment`가 태그·속성 allowlist로 걸러 스크립트·외부 로드를 막는다(테스트 `inspector.test.ts` 7건).

---

## 3. 불변식 검증

### 3.1 불변식 10개 + 운영 불변식 3개

| 불변식 | 코드 근거 | 위반 가능 경로(재현 시나리오) | 검증 테스트 | 판정 |
|---|---|---|---|---|
| 1. 원본 비파괴 | `migrations/0001_source_layer.sql` 트리거(UPDATE는 lifecycle/lineage만, DELETE 거부), `0012`는 `nmos.delete_conversation` 트랜잭션 설정 안에서만 통과; 코드의 raw 쓰기는 `ledger.py:apply_plan`/`apply_append`의 lifecycle UPDATE와 `ledger.py:delete_conversation`뿐(부록 C-9 grep) | (a) 대화 삭제(ADR 0009): 오너 명시 요청만, UI 2클릭. (b) retention: `retention.py:prune_embeddings`/`prune_text`는 파생 행만. (c) 관측 압축 `retention.py:compact_observations`는 `host_observation.raw_manifest`를 **재작성**하나 `apply_diff` 재현이 원본과 같을 때만(ADR 0018 §3). 원본 revision은 안 건드림 | `test_revisions_are_immutable`, `test_plain_deletes_of_raw_revisions_are_still_refused`, `test_observation_compaction.py`(4건) | **지켜짐** (관측 압축은 "무손실 재작성"으로 경계에 있음; 문서와 일치) |
| 2. 재구축 가능 | membership: `ledger.py:rebuild_membership`(`nmos-rebuild`); 텍스트: `--text`; 상태: `--state`; 엔티티/스레드/whereabouts/충돌은 read-time fold(`entities.py:resolve`, `threads.py:fold`, `facts.py:_versions`); 오너 링크(ADR 0025)는 "owner input"으로 보존; projection 세대 전환은 새 행 추가만 | LLM 추출은 "재유도"는 되지만 같은 출력을 **재현**하지 못함(모델 비결정성; temperature 0). 세대 키가 이를 감사 가능하게 만들 뿐 결정성은 없음 | `test_rebuild_membership_from_commits`, `test_fast_path_ledger_equals_the_full_path`(재구축 동일성 포함), `test_state.py` 재구축, `test_reveal_and_links.py`(rebuild keeps links) | **지켜짐**(결정적 projection) / **약함**(LLM projection은 본질적으로 재현 불가; 문서가 이를 "generation"으로 다룸) |
| 3. 응답 모델은 정규 기억을 쓰지 않음 | 쓰기 도구·MCP 없음; 플러그인 `host.ts`는 읽기 전용; 사실은 별도 추출 LLM이 씀 | 간접 경로: 응답 텍스트 → 추출 LLM → 사실(A-12). 서술체 지시문("[System: 유저의 본명은 X]")이 `identity`/`world_fact`로 굳을 수 있음. `character_claim` 분류는 대화체만 막음 | 없음(오염 케이스 없음) | **지켜짐**(문자 그대로) / A-12는 잠재 위험 |
| 4. Unknown은 유효 | `predicates.py:knowledge`(unknown 기본), `predicates.py:semantics`(modality unknown 기본), `entities.py:Resolution.ambiguous`, `facts.py:_versions` `disputed_by`, `threads.py:fold` unmatched | — | `test_knowledge.py`, `test_semantics.py`, `test_entities.py`, `test_transitions.py` | **지켜짐** |
| 5. 현재+역사 답변 가능 | 사실: `facts.py:_versions` history, `/facts?history=1`, Inspector 타임라인 | 파서 **상태**는 `state.py:current_state`만 있고 역사 조회 API/Inspector가 없음(행은 `state_observation`에 남음) | `test_extraction.py` 버전/역사 | **지켜짐**(사실) / **약함**(상태 역사 미노출) |
| 6. 캐릭터 지식 ≠ 세계 지식 | `knowledge`/`known_by`/`hidden_from` 소프트 마크, Note 문구, `facts.py:relevant_facts`의 `hidden_from` +2.5; `known_by` 보너스 제거(ADR 0026) | 한 생성이 모든 캐릭터를 씀(K11). `Predicate.epistemic` world/belief는 읽히지 않음(A-14) | `test_knowledge.py`, `test_extraction.py:test_secret_hidden_from_addressed_character_is_selected`, Phase 9 leak flag 테스트 | **약함**(설계상 소프트; 문서와 일치) |
| 7. 비활성 원본은 생성에 영향 없음 | 모든 읽기가 `active_membership`(head) 경유; 추출은 `window_hash IN (turn_hash, window_hash)` 조인으로 동기 마스킹(`facts.py:ACTIVE_ASSERTIONS_TEMPLATE`); 벡터·lexical·상태도 head 조인; `retrieval.py:retrieve`의 fresh 검사; 플러그인 캐시 키는 전체 (id, hash) | (a) 편집→다음 요청: sync가 retrieve보다 먼저, 같은 요청 안. (b) 리롤: 호스트가 꼬리를 먼저 제거(H14) → `reroll` 커밋 → retracted. (c) 두 클라이언트(A-13): 헤드 왕복은 있으나 `active_commit` 불일치면 빈 패킷. (d) worker가 편집 전 문맥으로 LLM 호출 중 편집 → 결과는 옛 turn_hash로 저장 → 매치 안 됨. (e) A-02는 주입 중단(stale 아님) | memeval 35케이스 모든 모드 stale 0(`test_memory_eval.py`), `test_live_reroll_flow_retracts_and_never_recalls`, `test_stale_commit_gets_no_packet`, `test_all_before_cut_is_inactive`, `test_recall_surfaces_out_of_context_excerpt_and_never_inactive`, `test_a_generation_that_never_covered_a_turn_does_not_serve_it` | **지켜짐** |
| 8. 검색 ≠ 활용 | 후보(`candidates`) / 배치(`lines.placed`, `why`) / 사용(echo, `audit.py:audit`) 분리; "visible"은 소프트 마크 | echo는 표면 측정(문서 인정) | `test_packet_ledger.py`(21건) | **지켜짐**(패킷 수준) |
| 9. 저장소 교체 가능 | repository/인덱스 인터페이스 없음. `retrieval.py:_lexical`은 `set_config`로 planner 옵션 조작, `<%` 연산자; `vectors.py:vector_candidates`는 `<=>`; `facts.py`는 window function SQL. §6/AGENTS는 "psycopg 3 with explicit SQL" | — | — | **위반(문서)**: 코드는 의도적으로 Postgres 전용. 불변식 문구를 고쳐야 함(A-06, 오너 결정) |
| 10. 자동 주장의 provenance | `assertion.extraction_id`→`extraction(source_revision_id, members, extractor_key, hints, raw)`; 패킷 라인 `ref`(assertion id / revision id / state key); `retrieval_trace.extractor_key` | — | `test_a_trace_records_every_offered_line_with_provenance` | **지켜짐** |
| 운영-1 Fail open | `core.ts:beforeRequest` 전체 try/catch, `call()` Promise.race 데드라인, 실패 30 s 캐시; `entry.ts`도 이중 try | A-01/A-02는 fail open이 **정상 동작**해서 조용히 기억이 꺼지는 사례 | `core.test.ts` 데드라인/다운/500 | **지켜짐** (단, "조용함"이 관찰성 문제) |
| 운영-2 stale 주입 금지 | fresh 검사 → 빈 패킷(abstain) | — | `test_stale_commit_gets_no_packet` | **지켜짐** |
| 운영-3 플러그인은 호스트 채팅 데이터 불변경 | `host.ts`에 `setChatToIndex` 없음; `setArgument`는 플러그인 인자(`hud`, `language`, 연결 설정)만 | "전체 데이터베이스" 권한을 받지만 `getDatabase(['personas','selectedPersona'])`만 호출(A-18) | 정적 확인(테스트 없음; 실호스트 스모크) | **지켜짐** |

### 3.2 ADR·D 결정과 현재 코드의 표류 (무작위 12건 + 표류 발견 3건)

| 결정 | 코드 위치 | 일치 | 비고 |
|---|---|---|---|
| D2 예산 예약 | `packet.py:compile_lines` `used + cost <= limit` | 일치 | `test_state_respects_budget` |
| D4 / ADR 0010 append는 커밋 없음, `worldline_append` | `reconcile.py:plan` `commit_reason=None`, `ledger.py:_record_append` | 일치 | 4 seed + 추가 16 seed 동치 통과(부록 C-7) |
| D5 지연 컴파일 | `extraction.py:enqueue_after_apply` accepted anchor만 | 일치 | `test_provisional_tail_state_waits_for_acceptance` |
| D13 / ADR 0001 amend 2 | `prompt.ts:userTurnIndex` 64자 앵커, 비-assistant 전부 탐색 | 일치 | `prompt.test.ts` preset 케이스 |
| D15 / ADR 0004 | `retrieval.py` threshold 0.4 `<%`, `AI_TIEBREAK_WEIGHT` 0.2, `BROAD_LIMIT` 200, 연대순 출력 | 일치 | |
| D20 / ADR 0006 | `generations.py:make` 스펙에 자격증명 없음; `test_generation_key_ignores_credentials_and_url_spelling` | 일치 | ADR 0006 §4의 "이전 세대가 덮은 항목 백그라운드 재큐"는 추출에 한해 ADR 0014로 개정됨(임베딩은 유지) |
| D23 / ADR 0009 | `ledger.py:delete_conversation` 17단계 | 일치 | FK 그래프 대조(부록 C-10) |
| D24 | `form.ts:DEFAULT_DEADLINE_MS`=3000, `connArgs` 200–30000 | 일치 | |
| D29 / ADR 0015 | `retention.py:prune_embeddings` 500건 배치, advisory lock, `worker.py:prune` 600 s | 일치 | `test_retention.py` 9건 |
| D32 / ADR 0019 | `threads.py` `MATCH_MIN` 0.6, `MATCH_MARGIN` 0.15, 포함 관계 restate, limit 3 | 일치 | |
| D37 / ADR 0026 | `facts.py` `PRIOR_STANDING` 0.5, `PRIOR_MAJOR_EVENT` 0.3, `known_by` 가산 없음, `lead` 섹션 | 일치 | |
| D39 / ADR 0027 | `packet.py:POLICIES`, `audit.py:replay` as-of(`upto`, `known_at`), `spans.py` echo | 일치 | ADR의 "Other excerpts never cut" → `_fit_excerpt` cut 분기 확인 |
| **D9 principal modes** | `character_pov` 코드 없음 | **표류** | ARCHITECTURE는 두 모드를 결정으로 서술; AGENTS/PHASE-4는 "not authorized". D9 문구에 "미구현" 표기 필요 |
| **§6 Stack "token auth via `saveSecretHeader`"** | `host.ts` 플러그인 인자 `auth_token` | **표류** | ADR 0003·H12와 모순 |
| **불변식 9** | 위 3.1 | **표류** | A-06 |

---

## 4. 잘 설계된 부분 (반증 시도 통과분)

1. **순수 reconcile planner + DB 트리거의 이중 방어** [확인됨]. `reconcile.py:plan`은 I/O 없이 `(id, hash)` 키만 다루고, `_ops`는 replay 검증 실패 시 `set`으로 강등한다. 원본 불변은 코드가 아니라 `0001`/`0012` 트리거가 지킨다. 반증: 68개 실호스트 픽스처(S1–S14) 기반 18개 테스트 + 무작위 액션 20 seed 동치 → 통과.
2. **세대(generation) 키와 per-turn 폴백(ADR 0006/0014)** [확인됨]. `generations.py:make`가 프롬프트·레지스트리·정규화기·엔드포인트·모델·설정을 해시하고 자격증명은 뺀다. `facts.py:ACTIVE_ASSERTIONS_TEMPLATE`의 window function이 턴당 정확히 한 세대를 고른다. 반증: 키 변경·API 키만 변경·모델 되돌리기·rebuild·discard 재개 시나리오(`test_generations.py` 23건) 모두 의도대로. 단 A-03처럼 두 프로세스가 다른 키를 계산하면 조용히 멈춘다.
3. **read-time projection(엔티티·스레드·whereabouts)** [확인됨]. 저장하지 않으므로 불변식 2·7이 자동으로 성립하고, 리졸버 변경이 "다음 읽기"로 끝난다. 반증: 편집으로 alias가 사라지면 다음 읽기에서 분리(`test_reveal_and_links.py`), 삭제 후 약속 사라짐(memeval "delete removes the promise"). 비용은 10k에서 ≈100 ms(부록 C-8)로 문서 한계(+50 ms) 안.
4. **패킷 원장 + bitemporal replay(ADR 0027)** [확인됨]. `retrieval.py:retrieve`가 모든 후보 라인의 배치 여부·이유·provenance·입력을 기록하고, `audit.py:replay`가 `upto`/`known_at`으로 당시 상태를 다시 컴파일한다. 반증: 이야기 진행 후·사실/벡터 추가 후·리롤 후 재현 `reproduced: true`, 편집 후 `changed`(`test_packet_ledger.py`). 이 원장이 실제로 오래된 버그(자기 메시지 회상)를 드러냈다는 기록(`docs/perf/phase9-packets.md` §7)도 설득력 있다.
5. **이중 XSS 방어** [확인됨]. 사이드카 `inspector.py`는 모든 값에 `_v()`/`escape()`; 플러그인 `inspector.ts:safeFragment`는 `<template>`에 파싱 후 태그·속성 allowlist(href는 `/inspector/...`·`#s-...`만). 반증: 이름·chat id에 `<script>`·`<img onerror>` 케이스(`test_state.py`, `test_inspector.py`, `inspector.test.ts`) 통과. 패널 상태 탭의 패킷 표시는 `textContent`.
6. **증거 규율** [확인됨]. HOST-FACTS는 픽스처 경로를 인용하고, 각 Phase 문서가 실호스트 스모크·업그레이드 검사·실모델 티어를 남긴다. 결정적 평가(`tests/memeval.py`)가 CI를 게이트한다. 반증: 평가 결과표(`docs/perf/eval-baseline.md`)를 재실행하지 않았으나 같은 코드가 `test_memory_eval.py`로 CI에서 돌고 이번 실행에서 통과했다.

---

## 5. 구조적 문제와 기술 부채

각 항목: **문제 / 원인 / 현재 영향 / 규모 확대 시 영향 / 권장 수정 / 난이도 / 미수정 시 위험**

**5.1 `extraction.py`(673줄)의 책임 집중** [확인됨]
- 문제: 프롬프트 텍스트, 힌트·약속 블록 구성, 정규화, job 큐 SQL(enqueue/claim/fail), 커버리지 SQL(`ELIGIBLE`, `OLDER_SERVES`, `REBUILD_PENDING`), 세대 정의가 한 모듈.
- 원인: 단계별 누적(Phase 2→9). 
- 현재 영향: 읽기 난이도; `vectors.py`·`retention.py`가 `ELIGIBLE`/`REQUEUE`를 import해 순환에 가까운 결합.
- 확대 시: 새 세대·새 술어마다 이 파일이 커짐.
- 권장: `jobs.py`(큐·claim·fail·coverage SQL)와 `prompt.py`(SYSTEM_PROMPT, 힌트 블록)로 분리. 동작 변경 없음.
- 난이도: 낮음(순수 이동). 위험: 방치해도 기능 위험은 없음.

**5.2 projection 계층의 암묵성** [확인됨]
- 문제: ARCHITECTURE §3의 "Projection Layer"가 `facts.py`(SQL+fold+랭킹+XML 렌더 513줄)와 read-side 규칙 4묶음(`predicates.py`의 `HOLDER_PER_ITEM`, `whereabouts`, `PARTICIPANT_PREDICATES`; `facts.py`의 `STANDING`)에 흩어져 있다.
- 원인: "레지스트리 지문을 바꾸지 않으려고" 읽기 규칙을 레지스트리 밖에 둔 결정(ADR 0011 §2)이 반복됨.
- 현재 영향: 술어 하나의 의미를 알려면 4곳을 본다. 
- 확대 시: Track B B2+에서 규칙이 늘면 누락 위험.
- 권장: `predicates.py`에 read-side 정책 표(술어 → 버전 키 규칙·prior·participant 허용·standing)를 한 곳에 모으고 지문 계산은 `REGISTRY`만 유지. `facts.py`에서 XML 렌더(`fact_line` 등)를 `packet.py` 쪽으로.
- 난이도: 중간(테스트 넓음). 위험: 낮음.

**5.3 두 프로세스가 각자 세대 키를 계산** [확인됨] (A-03)
- 문제: 사이드카가 활성화하고 worker가 별도로 계산한 키로 claim한다. 불일치 감지 로직이 없다.
- 원인: 설정을 env+DB에서 각자 읽는 구조.
- 영향: 개발 compose에서 재현 가능; 사용자 환경에서도 env를 한쪽만 바꾸면 발생.
- 권장: worker `maintenance`에서 `generations.active(conn, kind)`와 핸들러 키를 비교해 경고(또는 활성 키의 스펙으로 핸들러를 만들어 따라가기). 
- 난이도: 낮음. 위험: 조용한 추출 정지.

**5.4 pre-turn `window_hash` 호환 경로** [확인됨] (A-15)
- 문제: 모든 membership 행이 per-message 해시를 계속 계산·저장하고, `ACTIVE_ASSERTIONS`가 두 키를 OR 조인한다.
- 원인: ADR 0008 이전 세대(`extract-v3` 이하) 폴백.
- 영향: 소폭 비용·복잡도. 확대 시: 없음(선형).
- 권장: "헤드를 서빙하는 v3 이하 추출이 0인 DB에서 제거" 조건을 정하고 ADR로 종료. 오너 결정.
- 난이도: 낮음(마이그레이션 없이 컬럼 유지 가능). 위험: 없음.

**5.5 문서 다중 진실 원천** [확인됨] (A-07)
- 문제: 한 변경이 STATUS·CHANGELOG·KNOWN-ISSUES·ARCHITECTURE D·README·guide.ko·AGENTS §0 최소 6곳을 건드려야 한다. STATUS는 릴리스 이력을 누적(171줄)해 CHANGELOG와 중복.
- 영향: 릴리스 이틀 뒤 9건 표류. 
- 권장: STATUS를 "현재 단계 + 열린 결정 + 표 한 개"로 줄이고 이력은 CHANGELOG로; `check_release.py`에 교차검사 추가.
- 난이도: 낮음. 위험: 에이전트가 낡은 지시(“PHASE-8이 최신”)를 따를 수 있음.

**5.6 시작 시 단일 트랜잭션** [확인됨] (A-08)
- 문제: lifespan의 `with pool.connection() as conn:` 블록(autocommit=False)이 정규화 백필·텍스트 프루닝·턴 갱신·상태 백필·활성화를 한 트랜잭션으로 묶는다. 내부 `conn.transaction()`은 savepoint가 된다.
- 영향: 정규화기 버전 업(clean-v2류) 직후 큰 DB에서 재시작이 반복되면 진행이 누적되지 않음; advisory lock이 시작 내내 유지.
- 권장: 시작 단계는 `autocommit=True` 연결에서 각 단계별 커밋.
- 난이도: 낮음. 위험: 낮음(현 규모).

**5.7 `Predicate.epistemic` 사문화** [확인됨] (A-14) — 위 결정 표 참조.

**5.8 마이그레이션 체인(0001–0020) 건전성** [확인됨]
- 순서·체크섬·advisory lock·파일별 트랜잭션(`migrate.py:apply_migrations`)은 건전. 0007이 raw 트리그램 인덱스를 삭제, 0008이 PK 변경, 0011이 부분 유니크 인덱스, 0012가 트리거 함수 교체(`CREATE OR REPLACE`)와 인덱스 7개(비동시). 0013부터 전부 가산(additive)이라 최근 버전 간 이미지 롤백이 가능하다[추론]. 다운 마이그레이션 없음, 롤백 절차 미문서(A-16).

**5.9 플러그인–사이드카 프로토콜 결합** [확인됨]
- `hash_version: Literal[1]`로 해시 계약이 고정되고, 요청 모델은 extra 필드를 무시해 구버전 호환이 된다. 버전 협상은 없다(K19). Inspector HTML 계약(태그 allowlist)은 사이드카가 새 태그를 쓰면 플러그인에서 사라지는 암묵 결합 — `safeFragment` allowlist를 사이드카 문서에 명시하면 충분.

**5.10 dead/legacy 후보** [확인됨]: `packet.py:compile_packet`(테스트 전용 래퍼), `packet-v0`(A/B 완료 후 정리 후보), `NMOS_EXTRACT_WINDOW`(per-message 해시 폭만 결정). `tools/spike_*`·`adapters/pocketrisu-spike`(1,087줄)는 AGENTS §6이 재실행용으로 보존한다고 명시.

---

## 6. 버그 가능성 (NMOS 특화)

### 6.1 실제 버그 (재현 경로 있음)

| ID | 재현 | 결과 | 원인 | 수정 |
|---|---|---|---|---|
| A-01 | 본문에 `\ud800` 포함 메시지 → reconcile(200, needs_bodies) → bodies | `UnicodeEncodeError … surrogates not allowed` → 500; 매 요청 반복 | pydantic이 `\ud800` 이스케이프를 lone surrogate str로 디코드; `canonical.py:canonical_json`은 이를 이스케이프해 해시가 플러그인과 일치하지만 `ledger.py:store_bodies`의 INSERT가 UTF-8 인코딩 실패 | 양쪽 `normalizeText`에서 U+FFFD 치환(오너 승인) + 사이드카에서 인코딩 불가 본문을 `rejected`로 명시 |
| A-02 | assistant 메시지에 태그 문자열 포함 → `beforeRequest` | `hasPacket` 참 → 즉시 반환, sync·retrieve 없음 | `prompt.ts:hasPacket`이 역할 무관하게 `includes` | `role === 'system' && startsWith(PACKET_TAG)`; `injectPacket` 동일 |
| A-03 | `.env`에 `NMOS_LLM_JSON_MODE=0`, 개발 compose | worker 핸들러 키 ≠ 활성 키 → job 영구 queued | compose env 비대칭 + 키에 `json_mode` 포함 | compose 수정 + 불일치 경고 |

### 6.2 reconcile 케이스별 확인 [확인됨]

| 호스트 동작 | 코드 경로 | 테스트 | 비고 |
|---|---|---|---|
| 편집(사용자/AI) | `plan` → 같은 id·새 hash → `edit`, 옛 revision `superseded` | `test_edit_old_message` (S5/S6) | 턴 `[t, t+K]` 재큐 `test_edit_inside_window_requeues_following_turns` |
| 삭제(중간) | id 사라짐 → `delete`; accepted 유지 | `test_delete_middle_s7`, `test_deleting_a_middle_accepted_message_does_not_retract_it` | "이 메시지만 삭제"를 **꼬리 AI**에 쓰면 live reroll과 구분 불가 → `reroll`·`retracted`로 기록[추론]. 회상 결과는 같음(둘 다 비활성) |
| 리롤(라이브, H14) | manifest == head[:-1] & 꼬리 char → `reroll`, `retracted` | `test_live_reroll_retracts_tail_before_regeneration`, `test_live_reroll_flow_retracts_and_never_recalls` | 새 응답과의 lineage는 기록 안 됨(문서 일치) |
| 스와이프 | 같은 id·`swipe_id` 변경 → `swipe`; 되돌리면 옛 revision이 `provisional`→acceptance | `test_swipe_switch_s3`, memeval "swipe back" | |
| Continue(useSayNothing 기본) | 새 char 메시지 → append | `test_continue_with_say_nothing_is_an_append_s4` | |
| Continue(끔) | 같은 id·새 generationId → `continue`, lineage | `test_continue_extends_in_place_s4b` | |
| 숨김/Cut | hash에 `disabled` 포함 → `disable`; `turn_layout`·회상 제외 | `test_disable`, `test_all_before_cut_is_inactive` | |
| 분기 | 새 chat id + 마커 → `branch` | `test_branch_is_new_conversation_with_origin_s9`, memeval branch isolation | |
| 가져오기 | 새 chat id → `import`; 같은 message id가 두 대화에 | `test_import_is_new_conversation_s10` | `source_object` UNIQUE(conv, id) |
| append 증명 실패(ADR 0010) | prefix hash 불일치 / 중복 id / `allBefore` / 헤드 멤버 재등장 / `load_tail` None(K 변경, 비accepted 멤버) → 전체 경로 | `test_pure_append_skips_load_state_and_divergence_falls_back`, `test_new_cut_and_repeated_ids_fall_back`, `test_fast_path_survives_a_sidecar_restart` | 추가 16 seed 동치(부록 C-7) |

### 6.3 해시 일치 [확인됨]

- `canonical.ts`/`canonical.py`: NFC·CRLF→LF·키 정렬·undefined 제거·lone surrogate `\udxxx` 소문자 이스케이프. `fixtures/unit/revision-hash-v1.json` 8벡터를 `hash-vectors.test.ts`가 생성·검증하고 `test_canonical.py`가 동일 파일로 검증한다. `manifest-cache.test.ts`가 캐시 경로도 같은 벡터로 검증. `test_manifest_hash_matches_plugin_spike`가 실호스트 스파이크가 기록한 manifest hash 3개와 대조.
- 반증: (a) A-01 — 해시는 일치하나 저장 불가. (b) JS `normalize('NFC')`(ICU)와 Python `unicodedata`(Unicode 15.0)의 버전 차이로 신규 결합 문자에서 이론상 불일치 가능 → 실제 RP 텍스트에서는 무시 가능[추론]. (c) `swipeCount`·`specialComments`는 해시 밖(HOST-FACTS Q8-6과 일치).

### 6.4 동시성

| 상황 | 코드 | 판정 |
|---|---|---|
| worker 동시성 2 | `extraction.py:claim` `FOR UPDATE SKIP LOCKED`, `dedupe_key` UNIQUE, 10분 잠금 회수 | 안전 [확인됨] (`test_skip_locked_claims_are_exclusive`) |
| 같은 대화 sync 동시 | `ledger.py:lock_conversation` `FOR UPDATE`; 요청당 한 트랜잭션(pool `with conn:` 커밋) | 직렬화 [확인됨] |
| 삭제 중 추출 진행 | 삭제가 revision을 지우면 worker의 INSERT가 FK로 실패 → `fail()`; job 행도 삭제됨 | `test_a_job_running_while_its_chat_is_deleted_fails_quietly` [확인됨]. 단 `normtext.get` None → `TypeError` 경로는 A-04 |
| rebuild 중 진행 중 job | `discard`가 obsolete, `REQUEUE`가 되살림; 완료 시 `finish`는 `status='running'`만 갱신, 재실행은 `done` 재확인 | 멱등 [확인됨] |
| 두 클라이언트 | A-13 | 손실 없음, churn 있음 [추론] |
| `put_config` 중 요청 | `rt` dict 교체 | 실질 무해 [추론] |
| job 재시작 | `fail()` 지수 백오프, 5회 후 dead; `retry_failed`로 부활 | [확인됨] |

### 6.5 부분 실패

| 상황 | 판정 |
|---|---|
| 추출 중간 실패 | LLM 호출 후 extraction+assertion 한 트랜잭션 [확인됨] |
| 임베딩 중간 실패 | 청크 전부 임베딩 후 한 트랜잭션 INSERT [확인됨] |
| 세대 전환 중 실패 | 활성화·스케줄이 같은 트랜잭션; 이전 세대 폴백 [확인됨] |
| 마이그레이션 중단 | 파일별 트랜잭션·체크섬 [확인됨] `test_migrations_apply_cleanly_and_are_guarded` |
| bodies + then_reconcile | 한 트랜잭션; `test_failed_append_leaves_the_prior_head` [확인됨] |
| 시작 작업 중단 | A-08: 전부 롤백, 재시작 시 처음부터 |
| worker 스레드 예외 | A-04: 스레드 사망, 프로세스 생존, 재시작 없음 |

### 6.6 삭제·정리

- 대화 삭제 cascade: FK 그래프 전수 대조(부록 C-10) — `observation_base`는 `ON DELETE CASCADE`, `entity_link` 명시 삭제, `projection_generation`/`app_config`는 전역이라 의도적으로 보존. **완전** [확인됨].
- superseded 프루닝(ADR 0015): `missing`(활성 벡터 없고 옛 벡터 있는 헤드 revision)·`busy`(활성 세대 job)가 있는 대화는 제외; dead job은 `missing`으로 남아 차단. 헤드 밖 revision의 옛 벡터는 활성 세대가 임베딩한 경우에만 삭제(ADR 문구와 일치). **필요한 데이터를 지우는 경로 못 찾음** [확인됨]. 
- 관측 압축: 정확 재현 검사 후에만 재작성; base는 압축 안 함 [확인됨].
- trace 30일 보존이 Phase 9 원장을 함께 지움(설계·문서 일치).

### 6.7 업그레이드 경로

- 정방향: 0013 이후 전부 가산; 시작 시 백필(정규화·턴·상태)·활성화가 자동. Phase 6/7/8 문서가 실제 옛 DB에서의 업그레이드를 기록했으나 스크립트는 "scratch code"로 미커밋(A-16). CI에는 `beta3_upgrade`(레거시 벡터) 시나리오만 있다 [확인됨].
- 롤백: 다운 마이그레이션 없음. 최근 릴리스 간(예: beta.19→18)은 추가 컬럼이 nullable이라 구 이미지가 동작할 것[추론]; 구 `migrate.py`는 자기 파일만 순회해 미지 버전을 무시. 문서 없음.
- K19 실제 증상 [확인됨]: 구 사이드카+신 플러그인 → Inspector 탭 404·`links` 부재는 `inspector.ts:linkChoices`가 null 처리; 요청 모델은 extra 필드 무시. 신 사이드카+구 플러그인 → 정상.

---

## 7. 보안

| 항목 | 실제/이론 | 근거 | 판정·권고 |
|---|---|---|---|
| 토큰 선택 사항(ADR 0003) + Host 미검증 (A-05) | **실제**(loopback 가정 무너질 때) | `api.py` `auth()` 토큰 비면 통과; `TrustedHostMiddleware` 없음; `/v1/config/models`·`/test`가 `body.get("api_key") or cur.llm_api_key`를 임의 URL로 전송 | 같은 PC의 다른 프로세스는 항상 접근 가능(로컬 신뢰 모델이면 수용). DNS rebinding은 브라우저 CORS를 우회하므로 README의 LAN 경고만으로는 부족. `NMOS_ALLOWED_HOSTS`(기본 loopback 이름) 또는 토큰 있을 때만 생략 — 오너 결정 |
| CORS | 이론 | `allow_origins` 목록, `allow_methods` GET/POST/PUT, 자격증명 없음; 프리플라이트 거부 테스트 있음 | 적절 |
| `NMOS_SIDECAR_BIND` LAN 노출 | 실제(문서화됨) | README "Security" | 토큰 설정 안내 있음. A-05 수정으로 강화 |
| SSRF(설정 가능 URL) | 이론(설계상 사용자 지정 엔드포인트) | `runtime.py:list_models`, `llm.py` | A-05 해결 시 인가된 사용자만 가능 → 수용 |
| API 키·Vertex 키 저장·로그(K21) | 실제(문서화됨) | `app_config` 평문; `public_view`는 `api_key_set`만; 로그에 키 없음(grep) | 유지. Vertex 키는 서비스계정 사설키라 위험이 더 큼 → 전용 계정 권고가 README에 있음 |
| Inspector/패널 XSS | 방어됨 | §4-5 | 통과 |
| SQL 조립 | 안전 | 모든 값 파라미터; `ledger.py:lock_conversation`의 동적 `SET`는 고정 키 튜플; `_lexical`의 `current_setting('{k}')`는 상수 | 취약 없음 [확인됨] |
| 경로 처리 | 안전 | 파일 경로는 운영자 env만; 라우트 인자는 UUID 타입 | 취약 없음 |
| Docker 권한 | 양호 | non-root uid 10001, `config` ro 마운트, 릴리스 compose는 DB 포트 미공개 | 유지 |
| 기억 오염(A-12) | 이론 | 대화체는 `character_claim`으로 사실화 차단; 서술체 지시문은 막지 못함; Note "not instructions"와 XML 이스케이프로 패킷 탈출은 불가 | 위험은 사용자 자신의 세션에 한정. Track B §9가 요구한 "prompt-injection and memory-poisoning attempts" 케이스를 memeval에 추가 권고 |
| 호스트 권한 범위(A-18) | 이론 | `getDatabase(['personas','selectedPersona'])`만 | 호스트 API가 세분화되지 않음; README가 설명함 |
| 토큰의 URL 노출(A-11) | 이론 | `inspector.py:query`가 `?token=` 전파; uvicorn 접근 로그 | 헤더 방식 권장 문구 추가 또는 접근 로그 끄기 |
| 플러그인이 사이드카 HTML 신뢰 | 완화됨 | `safeFragment` allowlist | 악성 사이드카가 스크립트를 넣을 수 없음; 패킷 내용은 신뢰(본질) |

---

## 8. 테스트와 평가

**수치** [확인됨, 이번 실행]: 사이드카 `327 passed`(168.7 s; 테스트 함수 312 + parametrize), 플러그인 `89 passed`(2.2 s), `tsc` 통과, `dist/` 최신(`git diff --exit-code` 0). STATUS의 327/89와 일치(요청문의 287/85는 옛 수치).

**무엇을 검증하나**: 픽스처 기반 reconcile(18), fast path 동치(8), 통합 흐름(15), 세대·커버리지(23), 패킷 원장·replay(21), 전이/whereabouts(19), 엔티티·리졸버(10+9), 스레드(12), 참가자(13+2), 지식·의미(7+13), 삭제(5), retention(9), Inspector(17), 설정 API(11), 상태 파서(12), 결정적 평가(5, 35케이스×5모드), Vertex 토큰 교환(8, mock). 플러그인: 게이팅·주입·in-context(16), 어댑터 흐름(26), HUD(25), manifest 캐시(4), Inspector 도우미(7), 폼(9), 해시 벡터(2).

**mock 과다 여부**: LLM·임베더는 모든 테스트에서 결정적 스텁(`fake_complete`, `stub_extractor`, `FakeEmbedder`). `httpx` 실호출은 닫힌 포트 실패 케이스뿐이라 `llm.py`의 응답 형태 처리(`message: null` 등)는 미검증 → A-04. `monkeypatch`는 6파일에서 카운터·컴파일러 버전·env에 한정. 실호스트(`host.ts`)는 단위 테스트가 없고 Phase별 스모크로 대체(문서 일치).

**검증되지 않은 핵심 경로**: (1) lone surrogate 저장(A-01), (2) `hasPacket` 역할 무관 매치(A-02), (3) worker 예외 클래스(A-04), (4) 옛 DB 스냅샷 업그레이드(A-16), (5) 두 클라이언트 동시 sync(A-13), (6) 기억 오염(A-12), (7) 사이드카·worker 세대 키 불일치(A-03).

**flaky 가능성** (A-19): `core.test.ts` "gives up at the deadline" 벽시계 `<300 ms`; `manifest-cache.test.ts` 10k 메시지 1.8 s; `test_skip_locked_claims_are_exclusive` 스레드 4개; memeval 모듈 픽스처가 DB 5개를 만들어 2–3분 — CI 총 168 s는 수용 범위.

**CI가 막는 것** [확인됨]: PR/main에서 pg16+pgvector 서비스로 전체 pytest, 플러그인 typecheck/test/build, `dist/` 동기. 태그 릴리스는 CI 통과 + `check_release.py`(버전·CHANGELOG 절·Known limitations·STATUS 버전·마이그레이션 번호) 후 GHCR 다중 아키텍처 push. **막지 못하는 것**: 린트/타입 검사(Python: ruff·mypy 없음, "type hints everywhere" 규칙은 검사 안 됨), 문서 교차 일관성(A-07), 커버리지 측정, 업그레이드.

**증거 강도** [확인됨]:
- 결정적 평가(memeval): 35케이스, 5모드, stale 0, `full` 35/35, `full-v0` 33/35. 스텁 추출기라 **정확성(무효화·격리·예산)** 증거로 강함. 추출 품질 증거는 아님(문서가 명시).
- 실모델 티어: Phase 5–8은 `deepseek-v4.1-flash` 1개, 장면당 3회(총 54–66콜). v9/v10는 2개 모델. 결론 대부분 "3/3"이지만 n=3이라 rate가 아니라 방향. Phase 8의 "chores 1/3→10회 재실행 3/10 vs 4/10"이 분산의 크기를 보여준다(문서가 정직하게 기록). Phase 9 답변 프로브 8건×3회×2모델, 오너의 응답 모델 미사용(문서 §8 인정). **표본이 문서의 "메커니즘이 작동한다"는 결론은 뒷받침하지만 "정확률"류 주장은 뒷받침하지 못한다**; 문서 대부분이 그렇게 쓰여 있다(A-17은 경고이지 결함이 아님).
- 성능: `docs/perf/scale.md` 수치를 이번 벤치가 재현(§9).

**[제안] 우선순위 높은 추가 테스트 5개**
1. `test_sidecar_integration.py`: 본문에 `\ud800`·이모지 분할 문자열이 든 메시지가 저장·회상되는지(A-01 회귀).
2. `prompt.test.ts`: assistant/user 메시지에 태그가 인용돼도 `hasPacket`이 거짓이고, system 주입은 여전히 멱등인지(A-02).
3. `test_extraction.py`: `complete`가 `TypeError`/`RuntimeError`를 던져도 `run_once`가 job을 `queued`/`dead`로 남기고 다음 job을 처리하는지(A-04).
4. 세대 키 불일치: 사이드카 설정과 다른 `Settings`로 만든 핸들러가 활성 키 job을 claim하지 못할 때 worker가 경고를 남기는지(A-03).
5. 업그레이드: 마이그레이션을 0013까지 적용 → 대표 행 삽입 → 0020까지 적용 → 읽기 API·replay가 500 없이 동작(스키마 전이 회귀, A-16). 추가로 memeval에 "서술체 지시문이 사실이 되지 않음" 케이스(A-12)를 스텁 규칙으로 표현.

---

## 9. 성능과 확장성

**이번 벤치**(부록 C-8, 같은 기계, load avg ≈1.4) vs 문서(`docs/perf/scale.md`) [확인됨]:

| 항목 | 1k 문서 / 측정 | 10k 문서 / 측정 |
|---|---|---|
| warm append p50 (fast path) | 28 / 31 ms | 156 / 172 ms |
| edit near head p50 | 87 / 94 ms | 917 / 917 ms |
| lexical retrieve p50 | 5–8 / 8 ms | 9–12 / 12 ms |
| vector search p50 | 10 / 12 ms | 102 / 104 ms |
| fact read p50 (5,014 assertions) | 10 / 10 ms | 96 / 101 ms |
| DB 크기 | 21 / 22 MB | 120 / 124 MB |

문서 수치는 **성립**한다. K1의 "사이드카 처리 ≈135–165 ms at 10k"는 sync 두 호출의 합으로, 재현된 append 172 ms(하니스 JSON 인코딩 ≈39 ms 포함)와 부합.

**A-09 [추론]**: 실호스트 10k 측정(2.69–2.77 s, 여유 ≈0.25 s)은 stub 모델·추출/임베딩 없이 이뤄졌다(`docs/perf/scale.md` "Real-host check"). 추출·벡터를 켜면 요청 경로에 사실 읽기 ≈101 ms(단언 5k) ~ ≈314 ms(단언 15.6k, `docs/perf/phase8-extraction.md`)와 벡터 ≈104 ms, 질의 임베딩(로컬 Ollama ≈20 ms, cold 300 ms 초과 가능)이 더해진다. 합산하면 기본 3 s를 넘길 가능성이 크다. README·K1 문구를 "추출·임베딩 꺼진 상태 기준"으로 좁히거나 재측정해야 한다.

**N+1·대용량 적재** [확인됨]: 전체 경로 `ledger.py:load_state`는 대화의 모든 revision을 적재(K3, 문서화됨). `state.py:rebuild_state`는 DB 전체 revision `fetchall`(A-20; 25k×~1 KB면 수십 MB, 지금은 문제 아님). `readmodel.py:list_conversations`는 대화당 상관 서브쿼리 3개(LIMIT 200; 무시 가능). 추출 job당 `served_assertions` 전체 읽기(힌트) — 10k에서 ≈100 ms/job, worker 측이라 무해.

**인덱스** [확인됨]: 삭제·membership·trace(commit)·revision 참조 인덱스는 0012에 있음. `retrieval_trace(conversation_id, created_at)`·`job(conversation_id)` 인덱스는 없으나 30일 보존·수천 행 규모라 **지금 고칠 필요 없음**(A-22). 벡터 검색은 exact scan으로 10k에서 ≈100 ms, 25k에서 ≈277 ms(문서) — HNSW는 25k 이상에서만 검토(문서와 같은 판단; premature optimization 권하지 않음).

**저장소 증가(K17)** [확인됨]: 10k 벤치 124 MB 중 벡터 55 MB(청크 1개 기준; 실제 최대 8배). 관측 압축·벡터 프루닝이 있어 성장은 "버려진 브랜치+추출"로 한정. 수용 가능.

**결론**: 현재 규모(≤10k)에서 고쳐야 할 성능 문제는 없다. 문서 정확성(A-09)만 고칠 것.

---

## 10. 개발자 경험과 운영

- **설치** [확인됨, 문서 기준]: README 5단계와 릴리스 compose(`deploy/docker-compose.yml`)로 충분하다. 실제 신규 설치는 이 감사에서 시도하지 않았다(GHCR pull은 부작용 없지만 오너 환경의 compose 이름 `nmos`와 충돌 위험). `guide.ko.md`가 같은 내용을 한국어로 제공.
- **업그레이드**: CHANGELOG 릴리스마다 절차 서술(25회 언급). 마이그레이션은 시작 시 자동. 
- **롤백**: 어디에도 없음(A-16). "docker compose down -v"만 데이터 삭제로 언급. 백업 절차도 없음 → `pg_dump` 한 줄 안내 권고.
- **릴리스 절차**: `check_release.py v0.1.0-beta.19` 통과(부록 C-3). 검사 범위가 좁아 A-07을 놓친다.
- **문서 간 일관성**: STATUS↔CHANGELOG↔KNOWN-ISSUES↔ADR 목록은 대체로 일치(ADR 28개 모두 STATUS 결정 행에 나열). 표류 9건은 "문서–코드 불일치" 표.
- **문서량** [확인됨]: 규범·증거 문서 9,323줄 + 참고 6,031줄 vs 소스 9,193줄. 비율 ≈1:1. 에이전트 운영 계약(AGENTS)이 잘 짜여 있으나 §0가 STATUS를 복제해 표류 지점이 됨.
- **운영 관측성**: `/v1/health`가 활성 세대를 보여주고 Inspector가 큐 상태를 보여주지만, worker 쪽 이상(A-03·A-04)은 "pending이 안 줄어듦"으로만 드러난다. compose에 사이드카 healthcheck 없음(worker도).

---

## 11. 목적 대비 복잡도

**규모** [확인됨]: ADR 28, D 39, H 17, K 26, 마이그레이션 20, Phase 10(0A/0B~9), 술어 17, 추출 세대 v10, 리졸버 v4, 패킷 정책 2, 정규화기 v2, 청커 v1.

**복잡도가 몰린 곳**: (1) 세대·커버리지·폴백 기계(`generations.py`, `extraction.py`의 SQL 3묶음, `ACTIVE_ASSERTIONS` window function) — LLM 비용(K18)과 감사 가능성을 위해 존재하며 목적에 비례한다고 본다. (2) `facts.py:_versions`의 3슬롯 whereabouts fold + 분쟁 마킹. (3) `entities.py:Resolution`(union-find + 모호성 + 페르소나 + 오너 링크). (4) `packet.py:compile_lines`에 두 정책이 교차. (5) bitemporal 파라미터(`upto`, `known_at`)가 6개 함수에 관통.

**더 단순하게 풀 수 있는 곳** [제안]: read-side 규칙 4묶음의 한 표 통합(§5.2); STATUS 슬림화(§5.5); pre-turn 호환 경로 종료(§5.4); `packet-v0`는 첫 실데이터 A/B 뒤 제거 결정; `compile_packet` 래퍼 삭제.

**현재 구조를 유지하는 것이 합리적인 곳**: 불변 원장 + read-time projection(재구축·무효화가 공짜), 세대 키(모델 교체 비용·감사), 패킷 원장·replay(선택 정책의 오프라인 평가), 순수 reconcile planner, 이중 이스케이프, 결정적 평가 게이트. 이 다섯은 "긴 롤플레이에서 잊은 것을 되살린다"에 직접 복무한다. 반대로 Vertex(A-10)와 HUD는 목적과 무관한 편의 기능이나 격리돼 있어 유지 비용이 낮다.

---

## 12. 개선안

### 12.1 지금 수정해야 하는 것

| ID | 무엇 | 왜 | 기대 효과 | 난이도 | 변경 범위 | regression 위험 | 의존성 |
|---|---|---|---|---|---|---|---|
| A-02 | `hasPacket`/`injectPacket` 역할·접두 검사 | 대화 하나가 조용히 기억을 잃음 | 오탐 제거 | 낮음 | `prompt.ts` 2줄, 테스트 1건, 플러그인 릴리스 | 낮음(H2 재시도는 system 역할 유지) | 없음 |
| A-01 | lone surrogate 정규화(양쪽) + 사이드카 명시 거부 | 영구 미동기화 | 그 메시지가 저장됨 | 낮음–중간 | `canonical.ts`, `canonical.py`, 픽스처 벡터 8, `ledger.py:store_bodies` | 중간(해시 계약) | 오너 승인 |
| A-04 | `run_once`에서 `Exception` 포괄 처리 | 스레드 사망 → 조용한 정지 | 복원력 | 낮음 | `worker.py` | 낮음 | 없음 |
| A-03 | compose env 대칭화 + worker 불일치 경고 | 조용한 추출 정지 | 진단 가능 | 낮음 | `docker-compose.yml`, `deploy/docker-compose.yml`, `worker.py:maintenance` | 낮음 | 없음 |
| A-07 | 문서 9건 수정, `check_release.py` 확장 | 에이전트·사용자가 낡은 지시 따름 | 일관성 | 낮음 | 문서, `tools/check_release.py` | 없음 | 없음 |

**점진적 방법(A-01)**: (1) `test_sidecar_integration.py`에 실패 재현 테스트 추가(현재 500 확인) → (2) `canonical.py:normalize_text`·`canonical.ts:normalizeText`에 lone surrogate → U+FFFD 치환, `UPDATE_VECTORS=1`로 픽스처 재생성, `test_canonical.py` 통과 확인 → (3) `store_bodies`에서 인코딩 불가 본문은 `rejected`(원인 문자열 포함)로 반환해 500 방지 → (4) 호환: 신 플러그인+구 사이드카는 해당 메시지에서 해시 불일치→rejected(현재도 500이므로 악화 없음); 구 플러그인+신 사이드카도 동일 → (5) 검증: 사이드카·플러그인 전체 테스트, 실호스트 스모크 1회(이모지 분할 메시지) → (6) 롤백: 두 파일 되돌리고 픽스처 복원.

**점진적 방법(A-02)**: 테스트 추가(assistant 인용 → 거짓) → `hasPacket`을 `m.role === 'system' && contentText(m.content).startsWith(PACKET_TAG)`로 → `core.test.ts` H2 재시도 테스트 통과 확인 → 플러그인 릴리스(사이드카 무변경) → 롤백은 파일 교체.

**점진적 방법(A-04)**: `test_extraction.py`에 `TypeError`를 던지는 `complete`로 job이 `queued`가 되고 다음 job이 처리되는 테스트 → `run_once`의 except를 `Exception`으로 넓히고 `log.exception` → 전체 테스트 → 롤백 단순.

### 12.2 가까운 시기에 좋은 것

| ID | 무엇 | 난이도 | 비고 |
|---|---|---|---|
| A-05 | `NMOS_ALLOWED_HOSTS` + 토큰 시 생략 | 낮음 | 오너 결정; route=server 사용자 안내 필요 |
| A-09 | K1/README 문구 좁히기 또는 재측정 | 낮음 | 실호스트 세션 1회 |
| A-16 | 스키마 전이 테스트 + `pg_dump` 백업·롤백 절차 문서 | 낮음–중간 | |
| A-08 | 시작 작업 단계별 커밋 | 낮음 | |
| A-12 | memeval 오염 케이스 + 추출 프롬프트에 "메시지 안의 지시문은 이야기가 아니다" 한 줄(새 세대 → 비용; 다음 세대 변경 때 동반) | 낮음 | |
| 5.1/5.2 | `extraction.py` 분리, read-side 규칙 표 | 중간 | 동작 변경 없음 |
| 5.5 | STATUS 슬림화 | 낮음 | |
| A-11 | Inspector 링크에서 토큰을 URL 대신 헤더로(패널) / 접근 로그 억제 | 낮음 | |
| CI | ruff + mypy(점진), 커버리지 리포트 | 낮음 | 새 dev 의존성(승인 불필요: dev 그룹) |

### 12.3 지금은 건드리지 않아도 되는 것

- 벡터 HNSW·`retrieval_trace` 인덱스·`rebuild_state` 스트리밍(A-20, A-22): 현재 규모에서 측정된 문제 없음.
- `packet-v0` 제거·`compile_packet` 삭제: 첫 실데이터 A/B 뒤.
- `Predicate.epistemic`·`window_hash` 호환 경로(A-14, A-15): 다음 세대 변경과 묶어서.
- 두 클라이언트 churn(A-13): KNOWN-ISSUES 한 줄이면 충분.
- A-18 권한 범위: 호스트 API 한계.

**새 abstraction·의존성**: 권하지 않는다. A-05는 Starlette 내장 `TrustedHostMiddleware`로 충분하고, A-01은 표준 라이브러리로 해결된다. rewrite 불필요.

### 12.4 오너 승인이 필요한 항목

| 항목 | 종류 | 권장 |
|---|---|---|
| A-01 해시 정규화 변경 | 교차 언어 해시 계약·픽스처 변경 | 승인 권장 |
| A-05 Host 허용 목록·토큰 기본값 | 보안 기본값(ADR 0003 관련) | 허용 목록 도입, 토큰 설정 시 생략 |
| A-06 불변식 9 문구 개정 | 불변식 수정 | 개정 |
| A-10 Vertex 검증/표기/제거 | 의존성·미검증 기능 | 오너 키로 1회 검증 |
| A-12 추출 프롬프트 한 줄 | 새 추출 세대(재추출 비용) | 다음 세대 변경 때 동반 |
| A-14, A-15 | 세대·ADR | 다음 세대 변경 때 동반 |
| K26 | 열린 결정 | 측정 전 변경 금지 |
| Track B 잔여·하드 POV | 미승인 단계 | 이 감사는 권고하지 않음 |

---

## 13. 최종 평가

**상태: beta(후기).** prototype·experimental을 넘어선 근거: 원장·무효화·재구축·provenance가 코드와 DB 제약으로 구현되고, 416개 테스트와 결정적 평가가 CI를 게이트하며, 각 Phase가 실호스트 스모크와 업그레이드 검사를 남겼다. production-ready가 아닌 근거: 호스트 빌드 1개, 조용한 실패 모드 2건 발견(A-01, A-02), loopback 의존 보안 기본값(A-05), 소표본 실모델 증거(A-17), 문서 표류(A-07), 롤백·백업 절차 부재(A-16).

**가장 잘 된 부분**: (1) 순수 planner + DB 트리거의 원본 보호, (2) 세대 키와 per-turn 폴백, (3) read-time projection, (4) 패킷 원장·bitemporal replay, (5) 증거 규율(픽스처·스모크·결정적 평가).

**가장 중요한 문제**: (1) A-01 lone surrogate로 대화 영구 미동기화, (2) A-02 태그 인용으로 기억 중단, (3) A-03/A-04 worker의 조용한 정지 경로, (4) A-05 Host 미검증·토큰 기본 꺼짐, (5) A-07/A-09 문서 정확성.

**먼저 할 작업(순서)**: A-02 → A-01 → A-04 → A-03 → A-07(+check_release 확장) → A-09 → A-05(오너 결정) → A-16.

---

## 반증 시도

| 주장 | 시도한 반증 | 결과 |
|---|---|---|
| 불변식 7: 비활성 원본이 패킷에 들어가지 않는다 | (a) 응답이 패킷 태그를 인용하는 경우(A-02): 주입이 **중단**될 뿐 stale은 없음. (b) 두 클라이언트 왕복: `active_commit` 불일치 → 빈 패킷. (c) 편집 직전 문맥으로 LLM 호출 중인 worker: 결과가 옛 `turn_hash`로 저장돼 조인에서 제외. (d) 플러그인 캐시: 키가 전체 (id, hash)라 편집 시 miss. (e) memeval 35케이스 stale 0 재실행 | **유지** (A-02는 별도 가용성 버그로 기록) |
| 플러그인·사이드카 해시가 같은 입력에 같은 결과 | (a) lone surrogate 본문: 해시는 일치하지만 저장 단계에서 500(부록 C-6). (b) NFC 유니코드 버전 차이: 이론상 가능, 실사용 무시 가능 | **수정**: "해시는 일치, 저장 파이프라인은 실패" → A-01 |
| fast path == full path(ADR 0010) | 추가 16 seed(5–12 × 두 K/window 조합) 무작위 70단계 동치 실행; 헤드 밖 revision의 같은 id 재등장·K 변경·재시작·비accepted 멤버 코드 경로 검토 | **유지** (부록 C-7 16 passed) |
| K1: 10k에서 사이드카 ≈135–165 ms, 3 s 기본에 ≈0.25 s 여유 | 벤치 재현(append 172 ms)은 sync 경로에 부합. 그러나 실호스트 측정이 추출·벡터 꺼진 조건이라 켠 경우 사실 읽기 101–314 ms + 벡터 104 ms + 임베딩이 누락 | **수정**: sync 수치는 성립, 여유 주장은 조건부 → A-09 |
| ADR 0009 삭제가 완전하다 | 마이그레이션 20개의 FK를 전수 대조: `observation_base`(CASCADE), `entity_link`(명시), `worldline_append`(명시), `retrieval_trace`(명시), 전역 테이블(`projection_generation`, `app_config`)은 제외가 맞음. `test_conversation_delete.py`의 14테이블 0행 검증 | **유지** |
| 문서가 코드와 일치하고 릴리스 검사가 이를 보장한다 | `check_release.py` 통과 후 grep으로 9건 발견(README H1–H14, unreleased v10, AGENTS PHASE-8 최신, §6 saveSecretHeader, §7 레이아웃, STATUS D38/PHASE-7, 불변식 9, D9, README 플러그인 인자) | **수정** → A-07 |
| 테스트 327/89 | 실행 | **유지** |

---

## 문서–코드 불일치

| # | 문서 | 문구 | 실제 | 조치 [제안] |
|---|---|---|---|---|
| 1 | `README.md` §Develop | "host facts H1–H14" | H17까지 | H1–H17 |
| 2 | `README.md` §What gets injected, `docs/guide.ko.md` 236행 | `extract-v10` "(unreleased)" / "(다음 릴리스)" | beta.19에 출시 | "since 0.1.0-beta.19" |
| 3 | `AGENTS.md` §1 | "`PHASE-8.md` is the latest" | `PHASE-9.md` 존재 | 갱신 |
| 4 | `ARCHITECTURE.md` §6 Stack | "token auth via `saveSecretHeader`" | 플러그인 인자(ADR 0003, H12) | "plugin arg `auth_token` (ADR 0003)" |
| 5 | `ARCHITECTURE.md` §7 | "phases/PHASE-0.md … PHASE-4.md", "perf/phase0.md, perf/scale.md" | PHASE-9, perf 11개 | 갱신 |
| 6 | `docs/STATUS.md` "What exists" | "D1–D38", "`PHASE-0.md`–`PHASE-7.md` … 5, 6 and 7 met" | D39, PHASE-9 | 갱신 |
| 7 | `ARCHITECTURE.md` §2 불변식 9 | "Storage is replaceable … repository/index interfaces" | 명시 SQL 전용(§6, AGENTS §10) | 오너 결정으로 개정(A-06) |
| 8 | `ARCHITECTURE.md` D9 | `character_pov` 하드 ACL을 결정으로 서술 | 코드 없음 | "not implemented; not authorized" 명기 |
| 9 | `README.md` §Configuration | 플러그인 인자 목록에 `route`, `language`, `hud` 없음 | `scripts/build.mjs` 헤더에 9개 | 추가 |
| 10 | `README.md` env 표, `.env.example` | `NMOS_EXTRACT_HINTS` | 두 compose 모두 컨테이너에 미전달 | compose 추가(A-03) |
| 11 | `docker-compose.yml`(dev) | `NMOS_LLM_JSON_MODE` worker만 | 세대 키 불일치 가능 | sidecar에도 추가(A-03) |
| 12 | `docs/KNOWN-ISSUES.md` K1, `README.md` Status | 10k 여유 ≈0.25 s | 추출·벡터 끈 조건 | 조건 명기 또는 재측정(A-09) |
| 13 | `AGENTS.md` §0 | "As of 2026-09-24 … Phase 8 … complete" 뒤에 Phase 9 문장 덧붙임 | 두 시점이 섞임 | STATUS를 유일 원천으로 |

---

## 부록 A. 읽은 파일

- 규범·상태: `AGENTS.md`, `ARCHITECTURE.md`, `CLAUDE.md`, `README.md`, `CHANGELOG.md`, `docs/STATUS.md`, `docs/KNOWN-ISSUES.md`, `docs/HOST-FACTS.md`, `docs/adr/0001-main-generation-gating.md`–`docs/adr/0028-addresses.md` 전문, `docs/adr/README.md`, `docs/phases/PHASE-0.md`–`docs/phases/PHASE-4.md`, `docs/phases/PHASE-0-RETRO.md`, `docs/phases/PHASE-9.md` 전문, `docs/phases/PHASE-5.md`–`docs/phases/PHASE-8.md` 제목·수용 기준 훑음, `docs/proposals/*` 5편(PR64 리뷰 2편 제외), `docs/perf/*` 11편 전문, `docs/PHASE-0A-RUNBOOK.md`·`fixtures/host/README.md` 앞부분, `docs/guide.ko.md` 목차·grep.
- 사이드카 소스 32파일 전부(`apps/sidecar/src/nmos_sidecar/*.py`), `pyproject.toml`, `uv.lock` 미열람.
- 사이드카 테스트: `conftest.py`, `hostfixtures.py`, `simchat.py`, `memeval.py`, `test_memory_eval.py`, `test_reconcile_fixtures.py`, `test_append_fast_path.py`, `test_conversation_delete.py`, `test_sidecar_integration.py`, `test_generations.py`, `test_packet_ledger.py`, `test_retention.py`, `test_extraction.py`, `test_inspector.py`, `test_config_api.py`, `test_chat_actions.py`, `test_state.py`, `test_canonical.py`.
- 플러그인 소스 15파일 전부(`i18n.ts`는 앞 40줄), `scripts/build.mjs`, `tsconfig.json`, `package.json`, `dist/` 헤더; 테스트 9파일 전부.
- `migrations/0001_source_layer.sql`–`migrations/0020_packet_ledger.sql` 전문; `docker-compose.yml`, `deploy/docker-compose.yml`, `docker/sidecar.Dockerfile`, `.env.example`, `.gitignore`; `.github/workflows/ci.yml`, `release.yml`.
- 도구: `tools/check_release.py`, `eval_memory.py`, `replay_packets.py`, `bench_scale.py`, `check_phase8_scope_audit.py`(앞부분), `eval_extraction_model.py`·`eval_packet_answers.py` 앞부분.
- `fixtures/unit/revision-hash-v1.json` 전문; `fixtures/host`·`fixtures/model`은 목록·크기만.

## 부록 B. 읽지 않은 영역 (여기에 기대는 결론은 `[추론]`뿐)

- 사이드카 테스트 20파일 본문(`test_addresses.py`, `test_entities.py`, `test_fact_ranking.py`, `test_hints.py`, `test_knowledge.py`, `test_limits.py`, `test_long_messages.py`, `test_normalized_text.py`, `test_observation_compaction.py`, `test_participant_scope.py`, `test_participants.py`, `test_persona_name.py`, `test_reveal_and_links.py`, `test_semantics.py`, `test_threads.py`, `test_transitions.py`, `test_turn_extraction.py`, `test_turns.py`, `test_type_fill.py`, `test_vectors.py`, `test_vertex.py`) — 이름·건수·실행 결과만 사용.
- `tools/eval_phase6_model.py`, `tools/eval_phase7_model.py`, `tools/eval_phase8_model.py`, `tools/eval_v9_model.py`, `tools/eval_v10_model.py`, `tools/eval_phase8_minor_repeat.py`, `tools/bench_facts.py`, `tools/bench_observations.py`, `tools/bench_prune.py`, `tools/spike_collector.py`, `tools/spike_report.py`, `tools/spike_stub_llm.py`, `tools/make_synthetic_chat.py`, `adapters/pocketrisu-spike/nmos-host-spike.js`, `scripts/bench-manifest.mjs`.
- `fixtures/host/a14c911-2026-09-22/*.json` 68개와 `fixtures/model/**` 내용, `docs/reference/*`(비규범), `docs/images`, `docs/proposals/PHASE-8-PR64-*`, `docs/guide.ko.md` 본문 대부분, `i18n.ts` 나머지, `uv.lock`, `package-lock.json`.
- 실호스트(PocketRisu) 동작: 이번 감사에서 실행하지 않음. 실제 LLM·임베딩·Vertex 호출: 실행하지 않음. 오너의 운영 DB: 접근하지 않음.

## 부록 C. 실행한 명령과 결과

| # | 명령 | 결과 |
|---|---|---|
| C-1 | `cd adapters/pocketrisu-plugin && npm run typecheck && npm test && npm run build && git diff --exit-code -- dist/` | typecheck 통과; **89 passed**(8 files, 2.2 s); build 성공; dist 변경 없음 |
| C-2 | `cd apps/sidecar && uv run pytest -q` (compose Postgres 127.0.0.1:5436, 임시 DB 생성/삭제) | **327 passed**, 2 warnings, 168.7 s |
| C-3 | `python3 tools/check_release.py v0.1.0-beta.19` / `v0.1.0-beta.18` | beta.19 exit 0; beta.18은 버전 불일치 2건으로 exit 1(정상) |
| C-4 | `git status --porcelain` (감사 전·후) | clean(이 문서 외 변경 없음) |
| C-5 | vitest 임시 테스트: assistant 메시지가 `PACKET_TAG`를 포함 → `hasPacket` | `true`, `injectPacket`이 원본 반환(주입 없음). 임시 파일 삭제함 |
| C-6 | 임시 스크립트: 본문 `"lone surrogate \ud800 here"`를 브라우저처럼 JSON 이스케이프로 전송 | reconcile 200 `needs_bodies`; bodies에서 `UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800' … surrogates not allowed` |
| C-7 | 임시 pytest: `test_fast_path_ledger_equals_the_full_path`를 seed 5–12 × (K=3,w=6),(K=1,w=2)로 16회 | **16 passed**, 95.6 s. 임시 파일 삭제함 |
| C-8 | `uv run python ../../tools/bench_scale.py 1000,10000` | 1k: append p50 31 ms, edit 94/99, lexical 8, vector 12, fact 10, DB 22 MB. 10k: append 172 ms(p95 209), edit 917/968, lexical 12, vector 104, fact 101(p95 123), DB 124 MB. load avg ≈1.4 |
| C-9 | `grep`: `DELETE FROM source_revision`/`UPDATE source_revision`/`host_observation` 쓰기 | `ledger.py` lifecycle·lineage UPDATE, `delete_conversation`, `retention.py:compact_observations`의 raw_manifest UPDATE만 |
| C-10 | 마이그레이션 FK 전수 대조 vs `ledger.py:delete_conversation` 단계 | 누락 없음 |
| C-11 | `grep` `Predicate.epistemic` 사용처 / `TrustedHost` / uvicorn `get_path_with_query_string` | 사용처 없음 / 없음 / 쿼리 문자열 포함(uvicorn 0.53.0) |
| C-12 | README 환경변수 ↔ compose 파일 대조 | `NMOS_EXTRACT_HINTS` 두 compose 모두 미전달; 릴리스 compose에 `NMOS_FACTS_LIMIT`·`EVENTS_LIMIT`·`THREADS_LIMIT`·`RECALL_TOP_K`·`LLM_TIMEOUT_S`·`APPEND_FAST_PATH` 없음(패널에서 편집 가능한 것은 무해) |
| — | 미실행: 실 LLM/임베딩/Vertex 평가 도구, 신규 설치·업그레이드 실제 시도, 실호스트 스모크 | 사유: 유료 API·오너 환경 충돌 위험·호스트 인스턴스 필요 |

## 부록 D. 기준

- 커밋 `3fee5a8` (Merge pull request #83 from Sallos725/release-beta19), 태그 `v0.1.0-beta.19`, 브랜치 `main`, 작업 트리 clean.
- 환경: Python 3.12 + uv 0.10.10, Node 22.23.2, PostgreSQL 16 + pgvector(compose `nmos-postgres-1`), Linux 6.8.
