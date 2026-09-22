# NMOS 사용 안내 (베타)

NMOS는 PocketRisu 롤플레이용 장기 기억 장치입니다. 채팅이 길어져 모델이 예전 내용을 못 보게 되면,
NMOS가 **지금 대화와 관련된 예전 내용**을 골라 답변 생성 직전에 조금만 넣어 줍니다.

- **발췌**: 방금 쓴 말과 관련된 예전 대사 (글자 일치 + 선택 시 의미 검색)
- **상태**: 봇의 상태창(HP, 장소 등)을 규칙으로 읽어 최신 값 유지 (선택, LLM 불필요)
- **사실**: 백그라운드 LLM이 뽑아 둔 "누가 어디 있는지, 무엇을 아는지, 약속, 관계" (선택)

편집·삭제·리롤·스와이프·계속·숨기기·"AI에게서 잘라내기"·분기·가져오기를 모두 따라가므로,
지운 내용이나 바뀐 내용이 기억에 남아 끼어들지 않습니다. NMOS가 꺼져 있거나 느려도 채팅은 그대로 진행됩니다.

## 준비물

- Docker (Compose 포함)
- PocketRisu를 **`http://localhost…` 또는 HTTPS 주소로** 열어야 합니다. `http://192.168.x.x:6001` 같은
  일반 HTTP 내부망 주소에서는 브라우저가 PocketRisu 플러그인을 실행하지 않습니다.
  PocketRisu가 다른 기기(홈서버)에 있으면 SSH 터널을 쓰세요:
  `ssh -L 6001:localhost:6001 -L 8790:localhost:8790 서버` → 브라우저에서 `http://localhost:6001`
- (선택) OpenAI 호환 LLM 주소(Ollama, OpenRouter 등) — 사실 추출용
- (선택) 임베딩 주소(예: Ollama `qwen3-embedding:0.6b`) — 의미 검색용

## 설치

1. [최신 릴리스](https://github.com/Sallos725/NMOS/releases)에서 `nmos-docker-compose.yml`을 받아
   `docker-compose.yml`로 이름을 바꾸고 실행합니다.
   ```bash
   docker compose up -d
   curl http://127.0.0.1:8790/v1/health
   ```
2. PocketRisu → **설정 → 플러그인 → 플러그인 가져오기** → 같은 릴리스의 `nmos-pocketrisu.js`.
   "내용 교체" 권한 요청에 **예**.
3. 플러그인 설정에서 `sidecar_url` = `http://127.0.0.1:8790`.
4. **페이지 새로고침(F5).** 플러그인을 설치·업데이트·끈 뒤에는 꼭 새로고침하세요. 안 하면 다음 메시지에서
   PocketRisu가 멈출 수 있습니다(PocketRisu 쪽 버그).
5. PocketRisu 최대 컨텍스트를 `reserved_memory_tokens`(기본 600)만큼 줄여 두면 기억이 들어갈 자리가 생깁니다.

여기까지만 해도 기본 기억(글자 일치 검색)이 동작합니다. **http://127.0.0.1:8790/inspector** 에서
NMOS가 무엇을 저장했고 무엇을 넣었는지 볼 수 있습니다.

## 더 똑똑하게: LLM·임베딩 켜기

`docker-compose.yml` 옆에 `.env` 파일을 만들고 적은 뒤 `docker compose up -d`:

```bash
# 같은 PC의 Ollama 예시
NMOS_EMBED_URL=http://host.docker.internal:11434/v1
NMOS_EMBED_MODEL=qwen3-embedding:0.6b
NMOS_LLM_URL=http://host.docker.internal:11434/v1
NMOS_LLM_MODEL=원하는-모델-이름
```

- 임베딩을 켜면 "그 반짝이는 물건 어디 숨겼지?"처럼 **다른 말로 물어도** 예전 장면을 찾습니다.
- LLM을 켜면 확정된 메시지마다 백그라운드에서 한 번씩 호출해 사실을 뽑습니다. 유료 API라면
  비용이 들 수 있습니다. 긴 채팅을 처음 연결할 때는 최근 `NMOS_EXTRACT_BACKFILL`(기본 100)개만 처리합니다.
  버린 리롤 답변은 추출하지 않습니다.

## 상태창 읽기

`config/parsers.json`에 규칙을 적고 `.env`에 `NMOS_PARSERS_FILE=/config/parsers.json`을 넣으세요.
예시는 [config/parsers.example.json](../config/parsers.example.json).

- `block`: 시작·끝 패턴 사이의 `키: 값` 줄을 읽습니다 (`:` `：` `=` `|` `｜` 구분자 지원).
- `regex`: 이름 붙은 그룹 `key`/`value`로 뽑습니다.

## 문제 해결

| 증상 | 해결 |
|---|---|
| 메시지를 보냈는데 계속 생성 중 | 플러그인 설치/업데이트 후 새로고침을 안 했습니다. F5 |
| 기억이 전혀 안 들어감 | `http://localhost` 또는 HTTPS로 접속했는지, `curl …/v1/health`, 인스펙터의 "Recent retrievals" 확인 |
| 브라우저 콘솔에 CORS 오류 | `.env`의 `NMOS_CORS_ORIGINS`에 PocketRisu 주소를 넣고 재시작 |
| 엉뚱한 발췌가 들어감 | `NMOS_RECALL_THRESHOLD`(기본 0.4)나 `NMOS_VECTOR_MIN_SIM`(기본 0.42)을 올리세요 |

## 개인정보

모든 데이터는 내 PC의 Postgres 볼륨에만 저장됩니다. 원격 LLM/임베딩 주소를 설정한 경우에만 그쪽으로
채팅 문장이 전송됩니다. `docker compose down -v`로 NMOS 데이터를 전부 지울 수 있습니다.

## 베타 한계

- PocketRisu `a14c911`(v1.12.0)에서 실제 UI로 검증했습니다. 다른 버전은 동작이 다를 수 있습니다.
- 그룹 채팅(해당 PocketRisu 빌드에 없음), 캐릭터별 "아는 것만" 분리는 아직 없습니다.
- 검색 기준값은 제한된 데이터로 맞췄습니다. 이상한 기억/빠진 기억 사례를 이슈로 알려 주세요.
