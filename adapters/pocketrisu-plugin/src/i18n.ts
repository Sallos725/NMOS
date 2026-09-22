// Plugin UI strings. Korean is the default; the `language` plugin arg (set from the panel) picks English.

export type Lang = 'ko' | 'en';

export function langOf(value: unknown): Lang {
  return value === 'en' ? 'en' : 'ko';
}

const STRINGS = {
  // menus (registered once at load, in the language chosen then)
  'menu.panel': ['NMOS 기억', 'NMOS memory'],
  'menu.settings': ['NMOS 설정', 'NMOS settings'],
  'menu.status': ['NMOS 상태', 'NMOS status'],
  // frame
  'title': ['NMOS 기억', 'NMOS memory'],
  'tab.status': ['상태', 'Status'],
  'tab.settings': ['설정', 'Settings'],
  'close': ['닫기', 'Close'],
  'language': ['언어', 'Language'],
  // status view
  'status.sidecar': ['사이드카', 'Sidecar'],
  'status.checking': ['사이드카 확인 중…', 'Checking the sidecar…'],
  'status.connected': ['연결됨', 'Connected'],
  'status.unreachable': ['연결할 수 없음', 'Cannot reach'],
  'status.fix': ['확인: docker compose up -d · 주소 · NMOS_CORS_ORIGINS에 이 PocketRisu 주소 포함 · localhost 또는 HTTPS로 접속',
    'Check: docker compose up -d · the address · NMOS_CORS_ORIGINS includes this PocketRisu address · open via localhost or HTTPS'],
  'status.memory_off': ['기억 넣기가 꺼져 있습니다. 설정 탭에서 켤 수 있습니다.', 'Memory is switched off. Turn it on in Settings.'],
  'status.features': ['기능', 'Features'],
  'feature.state': ['상태창', 'Status window'],
  'feature.extraction': ['사실 추출', 'Fact extraction'],
  'feature.vectors': ['의미 검색', 'Semantic recall'],
  'on': ['켜짐', 'on'],
  'off': ['꺼짐', 'off'],
  'status.last': ['마지막 요청', 'Last request'],
  'status.none': ['아직 요청이 없습니다. 채팅에서 메시지를 보내 보세요.', 'No request yet. Send a message in a chat.'],
  'status.ago': ['{n}초 전', '{n}s ago'],
  'outcome.injected': ['기억 {n}자를 넣었습니다', 'Injected {n} characters of memory'],
  'outcome.nothing': ['관련된 기억이 없었습니다', 'Nothing relevant to inject'],
  'outcome.failed': ['건너뜀 (원래 요청은 그대로 보냄)', 'Skipped (the request went out unchanged)'],
  'status.inspector': ['인스펙터 열기', 'Open inspector'],
  'status.refresh': ['새로 고침', 'Refresh'],
  // settings: connection
  'conn.title': ['연결', 'Connection'],
  'conn.sub': ['이 브라우저의 PocketRisu 플러그인 설정입니다. 사이드카가 다른 기기에 있으면 route=server가 자동으로 쓰입니다.',
    "This browser's PocketRisu plugin settings. If the sidecar runs on another device, route=server is used automatically."],
  'conn.url': ['사이드카 주소', 'Sidecar URL'],
  'conn.route': ['경로', 'Route'],
  'conn.budget': ['기억 예산(토큰)', 'Memory budget (tokens)'],
  'conn.deadline': ['제한 시간(ms)', 'Deadline (ms)'],
  'conn.enabled': ['기억 넣기 켜기', 'Memory on'],
  'conn.hint': ['PocketRisu의 최대 컨텍스트를 기억 예산만큼 줄여 두세요.', "Lower PocketRisu's max context by the memory budget."],
  // settings: models
  'llm.title': ['사실 추출 LLM', 'Fact extraction LLM'],
  'llm.sub': ['확정된 메시지마다 백그라운드에서 한 번 호출해 인물·장소·약속·관계를 기록합니다. 유료 API는 비용이 듭니다.',
    'Called once per settled message in the background to record people, places, promises and relationships. Paid APIs cost money.'],
  'emb.title': ['의미 검색 임베딩', 'Semantic recall embeddings'],
  'emb.sub': ['다른 말로 물어도 예전 장면을 찾습니다. Ollama의 qwen3-embedding:0.6b를 추천합니다.',
    'Finds earlier scenes even when asked in other words. Ollama qwen3-embedding:0.6b is recommended.'],
  'preset.off': ['사용 안 함', 'Off'],
  'preset.ollama': ['Ollama (이 PC)', 'Ollama (this PC)'],
  'preset.custom': ['직접 입력 (OpenAI 호환)', 'Custom (OpenAI-compatible)'],
  'model.provider': ['제공자', 'Provider'],
  'model.endpoint': ['주소 (OpenAI 호환 /v1)', 'Endpoint (OpenAI-compatible /v1)'],
  'model.model': ['모델', 'Model'],
  'model.llm_placeholder': ['모델 이름', 'model name'],
  'model.emb_placeholder': ['임베딩 모델', 'embedding model'],
  'model.key': ['API 키', 'API key'],
  'model.key_placeholder': ['필요할 때만 입력', 'only if needed'],
  'model.key_saved': ['저장됨 — 바꿀 때만 입력', 'saved — type only to change'],
  'model.load': ['모델 목록', 'Load models'],
  'model.test': ['연결 테스트', 'Test'],
  'model.loading': ['불러오는 중…', 'Loading…'],
  'model.list_failed': ['목록을 가져오지 못했습니다: {e}', 'Could not list models: {e}'],
  'model.pick': ['— 모델 {n}개 중 선택 —', '— pick one of {n} models —'],
  'model.found': ['모델 {n}개를 찾았습니다.', 'Found {n} models.'],
  'model.testing': ['실제 호출로 확인 중…', 'Calling the model…'],
  'model.test_ok': ['성공 {ms}ms', 'OK {ms}ms'],
  'model.dims': [' · {n}차원', ' · {n} dimensions'],
  'model.test_failed': ['실패: {e}', 'Failed: {e}'],
  // settings: tuning
  'tune.title': ['검색 조정', 'Recall tuning'],
  'tune.sub': ['엉뚱한 발췌가 들어가면 기준값을 올리고, 기억이 너무 안 들어가면 내리세요.',
    'Raise the thresholds if unrelated excerpts get in; lower them if too little memory is injected.'],
  'tune.threshold': ['글자 일치 기준', 'Lexical threshold'],
  'tune.min_sim': ['의미 유사도 기준', 'Vector min similarity'],
  'tune.top_k': ['발췌 수', 'Excerpts'],
  'tune.facts': ['사실 수', 'Facts'],
  'tune.backfill': ['처음 연결 시 처리할 메시지 수', 'Messages processed on first sync'],
  // settings: parser rules
  'rules.title': ['상태창 규칙', 'Status-window rules'],
  'rules.sub': ['block: 시작~끝 사이의 "키: 값" 줄을 읽습니다. entity_line으로 [인물] 줄마다 인물별로 나눕니다 (시뮬봇). regex: key/value 이름 그룹.',
    'block: reads "key: value" lines between start and end; entity_line splits them per [character] line (sim bots). regex: named groups key/value.'],
  'rules.example': ['예시 넣기', 'Insert example'],
  'rules.none': ['규칙 없음 — "예시 넣기"로 시작하세요', 'No rules — start with "Insert example"'],
  'rules.from_file': ['파일에서 규칙 {n}개를 읽는 중 (여기에 저장하면 대체됩니다)', 'Reading {n} rules from a file (saving here replaces them)'],
  // save bar
  'save': ['저장', 'Save'],
  'revert': ['되돌리기', 'Revert'],
  'saving': ['저장 중…', 'Saving…'],
  'saved': ['저장했습니다.', 'Saved.'],
  'saved_queued': ['저장했습니다. 기존 채팅 {n}건을 백그라운드에서 처리합니다.', 'Saved. {n} existing items are processed in the background.'],
  'saved_rules': ['규칙 {n}개를 적용하고 기존 메시지를 다시 읽었습니다.', '{n} rules applied; existing messages were re-read.'],
  'no_changes': ['바뀐 내용이 없습니다.', 'No changes.'],
  'unsaved': ['저장하지 않은 변경: {s}', 'Unsaved changes: {s}'],
  'close_unsaved': ['저장하지 않은 변경이 있습니다.', 'You have unsaved changes.'],
  'save_and_close': ['저장하고 닫기', 'Save and close'],
  'discard_and_close': ['버리고 닫기', 'Discard and close'],
  'cancel': ['취소', 'Cancel'],
  'lang_unsaved': ['언어를 바꾸기 전에 변경을 저장하거나 되돌리세요.', 'Save or revert your changes before switching the language.'],
  'conn_saved_server_failed': ['연결 설정은 저장했지만 서버 설정은 저장하지 못했습니다: {e}', 'Connection saved, but the server settings were not: {e}'],
  'invalid': ['입력 오류: ', 'Invalid: '],
  'sidecar_error': ['사이드카 오류: ', 'Sidecar error: '],
} as const satisfies Record<string, readonly [string, string]>;

export type StringKey = keyof typeof STRINGS;

export function t(lang: Lang, key: StringKey, vars: Record<string, string | number> = {}): string {
  const text: string = STRINGS[key][lang === 'en' ? 1 : 0];
  return text.replace(/\{(\w+)\}/g, (m, name: string) => (name in vars ? String(vars[name]) : m));
}

export const STRING_KEYS = Object.keys(STRINGS) as StringKey[];
