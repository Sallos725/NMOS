// NMOS settings panel, rendered inside the plugin's own sandboxed iframe (full screen).
// Plugin-side settings are PocketRisu plugin args; model/recall/parser settings live in the sidecar.

export interface PanelDeps {
  api<T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown, timeoutMs?: number): Promise<T>;
  getArg(key: string): Promise<string>;
  setArg(key: string, value: string | number): Promise<void>;
  show(): Promise<void>;
  hide(): Promise<void>;
}

interface ServerConfig {
  llm: { url: string; model: string; api_key_set: boolean; json_mode: boolean };
  embeddings: { url: string; model: string; api_key_set: boolean; query_instruction: string };
  recall: { threshold: number; vector_min_sim: number; top_k: number; facts_limit: number };
  extraction: { backfill: number };
  parsers: { rules: unknown; source: string; active_rules: number; errors: string[] };
  queued_jobs?: number;
}

interface Preset { label: string; url: string; model?: string; key?: boolean }

const LLM_PRESETS: Preset[] = [
  { label: '사용 안 함 / Off', url: '' },
  { label: 'Ollama (이 PC)', url: 'http://host.docker.internal:11434/v1' },
  { label: 'OpenRouter', url: 'https://openrouter.ai/api/v1', key: true },
  { label: 'OpenAI', url: 'https://api.openai.com/v1', model: 'gpt-4o-mini', key: true },
  { label: 'Google Gemini', url: 'https://generativelanguage.googleapis.com/v1beta/openai', model: 'gemini-2.5-flash', key: true },
  { label: '직접 입력 / Custom (OpenAI 호환)', url: 'custom' },
];

const EMBED_PRESETS: Preset[] = [
  { label: '사용 안 함 / Off', url: '' },
  { label: 'Ollama (이 PC)', url: 'http://host.docker.internal:11434/v1', model: 'qwen3-embedding:0.6b' },
  { label: 'OpenAI', url: 'https://api.openai.com/v1', model: 'text-embedding-3-small', key: true },
  { label: '직접 입력 / Custom (OpenAI 호환)', url: 'custom' },
];

const PARSER_EXAMPLE = {
  rules: [
    { id: 'roster', kind: 'block', role: 'char', start: '<status>', end: '</status>', entity_line: '\\[(?P<entity>[^\\]]+)\\]' },
    { id: 'hp', kind: 'regex', pattern: 'HP\\s*[:：]\\s*(?P<value>\\d+\\s*/\\s*\\d+)', key: 'HP' },
  ],
};

const CSS = `
.nmos{position:fixed;inset:0;overflow:auto;background:rgba(12,12,16,.94);font:14px/1.55 system-ui,-apple-system,"Noto Sans KR",sans-serif;color:#e8e8ec}
.nmos *{box-sizing:border-box}
.nmos .wrap{max-width:760px;margin:0 auto;padding:20px 14px 60px}
.nmos header{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.nmos h1{font-size:19px;margin:0;flex:1}
.nmos .card{background:#1d1e24;border:1px solid #30323b;border-radius:10px;padding:16px;margin:12px 0}
.nmos h2{font-size:15px;margin:0 0 2px}
.nmos .sub{color:#9a9ca8;font-size:12.5px;margin:0 0 12px}
.nmos label{display:block;font-size:12.5px;color:#b8bac4;margin:10px 0 4px}
.nmos input,.nmos select,.nmos textarea{width:100%;background:#15161b;color:#e8e8ec;border:1px solid #3a3c46;border-radius:6px;padding:8px 10px;font:inherit}
.nmos textarea{min-height:160px;font-family:ui-monospace,monospace;font-size:12.5px}
.nmos .row{display:flex;gap:10px;flex-wrap:wrap}.nmos .row>*{flex:1;min-width:140px}
.nmos .btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.nmos button{background:#2b2d36;color:#e8e8ec;border:1px solid #444654;border-radius:6px;padding:7px 14px;font:inherit;cursor:pointer}
.nmos button.primary{background:#4c6ef5;border-color:#4c6ef5;color:#fff}
.nmos button:disabled{opacity:.5;cursor:default}
.nmos .msg{margin-top:10px;font-size:13px;white-space:pre-wrap}
.nmos .ok{color:#69db7c}.nmos .err{color:#ff8787}.nmos .muted{color:#9a9ca8}
.nmos .status{white-space:pre-wrap;font-size:13px}
.nmos .check{display:flex;align-items:center;gap:8px;margin-top:10px}.nmos .check input{width:auto}
`;

type Attrs = Record<string, string | number | boolean | undefined>;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {}, ...children: (Node | string)[]): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === false) continue;
    if (k === 'class') node.className = String(v);
    else if (k === 'text') node.textContent = String(v);
    else node.setAttribute(k, v === true ? '' : String(v));
  }
  for (const child of children) node.append(child);
  return node;
}

function say(target: HTMLElement, text: string, kind: 'ok' | 'err' | 'muted' = 'muted'): void {
  target.className = `msg ${kind}`;
  target.textContent = text;
}

function field(labelText: string, input: HTMLElement): HTMLElement {
  return el('div', {}, el('label', { text: labelText }), input);
}

function presetIndex(presets: Preset[], url: string): number {
  if (!url) return 0;
  const i = presets.findIndex((p) => p.url === url);
  return i >= 0 ? i : presets.length - 1;
}

function errorText(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return text.replace(/^\/v1\/\S+ -> HTTP 422: /, '입력 오류 / invalid: ').replace(/^\/v1\/\S+ -> /, '사이드카 오류 / sidecar error: ');
}

export async function openSettingsPanel(deps: PanelDeps): Promise<void> {
  document.getElementById('nmos-panel')?.remove();
  if (!document.getElementById('nmos-style')) document.head.append(el('style', { id: 'nmos-style', text: CSS }));
  const root = el('div', { class: 'nmos', id: 'nmos-panel' });
  const wrap = el('div', { class: 'wrap' });
  root.append(wrap);
  const close = el('button', { text: '닫기 / Close' });
  close.addEventListener('click', () => { root.remove(); void deps.hide(); });
  wrap.append(el('header', {}, el('h1', { text: 'NMOS 기억 설정' }), close));

  // --- status -------------------------------------------------------------------------------
  const statusBox = el('div', { class: 'status muted', text: '사이드카 확인 중… / checking sidecar…' });
  wrap.append(el('div', { class: 'card' }, el('h2', { text: '상태 / Status' }), statusBox));

  // --- connection (plugin args) -------------------------------------------------------------
  const url = el('input', { value: (await deps.getArg('sidecar_url')) || 'http://127.0.0.1:8790' });
  const route = el('select', {}, ...['auto', 'direct', 'server'].map((v) => el('option', { value: v, text: v })));
  route.value = (await deps.getArg('route')) || 'auto';
  const enabled = el('input', { type: 'checkbox' });
  enabled.checked = Number(await deps.getArg('disabled')) !== 1;
  const reserved = el('input', { type: 'number', min: 100, max: 8000, value: Number(await deps.getArg('reserved_memory_tokens')) || 600 });
  const deadline = el('input', { type: 'number', min: 200, max: 5000, value: Number(await deps.getArg('deadline_ms')) || 800 });
  const connMsg = el('div', { class: 'msg' });
  const connSave = el('button', { class: 'primary', text: '저장 / Save' });
  connSave.addEventListener('click', async () => {
    await deps.setArg('sidecar_url', url.value.trim());
    await deps.setArg('route', route.value);
    await deps.setArg('disabled', enabled.checked ? 0 : 1);
    await deps.setArg('reserved_memory_tokens', Number(reserved.value) || 600);
    await deps.setArg('deadline_ms', Number(deadline.value) || 800);
    say(connMsg, '저장했습니다. / Saved.', 'ok');
    void refreshServer();
  });
  wrap.append(el('div', { class: 'card' },
    el('h2', { text: '연결 / Connection' }),
    el('p', { class: 'sub', text: '이 브라우저의 PocketRisu 플러그인 설정입니다. 사이드카가 다른 기기에 있으면 route=server가 자동으로 쓰입니다.' }),
    field('사이드카 주소 / Sidecar URL', url),
    el('div', { class: 'row' }, field('경로 / Route', route), field('기억 예산(토큰) / Memory budget', reserved), field('제한 시간(ms) / Deadline', deadline)),
    el('div', { class: 'check' }, enabled, el('span', { text: '기억 넣기 켜기 / Memory on' })),
    el('p', { class: 'sub', text: 'PocketRisu의 최대 컨텍스트를 기억 예산만큼 줄여 두세요.' }),
    el('div', { class: 'btns' }, connSave), connMsg));

  // --- model sections (server config) --------------------------------------------------------
  function modelSection(kind: 'llm' | 'embeddings', title: string, sub: string, presets: Preset[]) {
    const preset = el('select', {}, ...presets.map((p, i) => el('option', { value: String(i), text: p.label })));
    const endpoint = el('input', { placeholder: 'https://…/v1' });
    const model = el('input', { placeholder: kind === 'llm' ? '모델 이름 / model' : '임베딩 모델 / embedding model' });
    const list = el('select', { style: 'display:none' });
    const key = el('input', { type: 'password', placeholder: 'API 키 (필요할 때만) / API key' });
    const msg = el('div', { class: 'msg' });
    const load = el('button', { text: '모델 목록 / Load models' });
    const test = el('button', { text: '연결 테스트 / Test' });
    const save = el('button', { class: 'primary', text: '저장 / Save' });
    preset.addEventListener('change', () => {
      const p = presets[Number(preset.value)] as Preset;
      if (p.url !== 'custom') endpoint.value = p.url;
      if (p.model) model.value = p.model;
      if (!p.url) model.value = '';
    });
    list.addEventListener('change', () => { model.value = list.value; });
    load.addEventListener('click', async () => {
      say(msg, '불러오는 중… / loading…');
      try {
        const r = await deps.api<{ ok: boolean; models: string[]; error?: string }>('POST', '/v1/config/models',
          { kind, url: endpoint.value.trim(), api_key: key.value.trim() || undefined });
        if (!r.ok) return say(msg, `목록을 가져오지 못했습니다: ${r.error}`, 'err');
        list.replaceChildren(el('option', { value: '', text: `— ${r.models.length}개 모델 선택 —` }),
          ...r.models.map((m) => el('option', { value: m, text: m })));
        list.style.display = '';
        say(msg, `${r.models.length}개 모델을 찾았습니다.`, 'ok');
      } catch (error) { say(msg, errorText(error), 'err'); }
    });
    test.addEventListener('click', async () => {
      test.disabled = true;
      say(msg, '실제 호출로 확인 중… / calling the model…');
      try {
        const r = await deps.api<{ ok: boolean; ms: number; dimensions?: number; error?: string }>('POST', '/v1/config/test',
          { kind, url: endpoint.value.trim(), model: model.value.trim(), api_key: key.value.trim() || undefined });
        say(msg, r.ok ? `성공 ${r.ms}ms${r.dimensions ? ` · ${r.dimensions}차원` : ''} / OK` : `실패 / failed: ${r.error}`, r.ok ? 'ok' : 'err');
      } catch (error) { say(msg, errorText(error), 'err'); } finally { test.disabled = false; }
    });
    save.addEventListener('click', async () => {
      const prefix = kind === 'llm' ? 'llm' : 'embed';
      const body: Record<string, unknown> = { [`${prefix}_url`]: endpoint.value.trim(), [`${prefix}_model`]: model.value.trim() };
      if (key.value.trim()) body[`${prefix}_api_key`] = key.value.trim();
      try {
        const r = await deps.api<ServerConfig>('PUT', '/v1/config', body);
        key.value = '';
        fillFields(kind === 'llm' ? r.llm : r.embeddings);
        say(msg, `저장했습니다.${r.queued_jobs ? ` 기존 채팅 ${r.queued_jobs}건을 백그라운드에서 처리합니다.` : ''} / Saved.`, 'ok');
        void refreshStatus();
      } catch (error) { say(msg, errorText(error), 'err'); }
    });
    const card = el('div', { class: 'card' },
      el('h2', { text: title }), el('p', { class: 'sub', text: sub }),
      field('제공자 / Provider', preset), field('주소 / Endpoint (OpenAI 호환 /v1)', endpoint),
      field('모델 / Model', model), list, field('API 키 / API key', key),
      el('div', { class: 'btns' }, load, test, save), msg);
    function fillFields(cfg: { url: string; model: string; api_key_set: boolean }) {
      preset.value = String(presetIndex(presets, cfg.url));
      endpoint.value = cfg.url;
      model.value = cfg.model;
      key.placeholder = cfg.api_key_set ? '저장됨 — 바꿀 때만 입력 / saved' : 'API 키 (필요할 때만) / API key';
    }
    return { card, fill: (c: ServerConfig) => fillFields(kind === 'llm' ? c.llm : c.embeddings) };
  }

  const llm = modelSection('llm', '사실 추출 LLM / Fact extraction',
    '확정된 메시지마다 백그라운드에서 한 번 호출해 인물·장소·약속·관계를 기록합니다. 유료 API는 비용이 듭니다.', LLM_PRESETS);
  const emb = modelSection('embeddings', '의미 검색 임베딩 / Semantic recall',
    '다른 말로 물어도 예전 장면을 찾습니다. Ollama의 qwen3-embedding:0.6b를 추천합니다.', EMBED_PRESETS);
  wrap.append(llm.card, emb.card);

  // --- recall tuning -------------------------------------------------------------------------
  const threshold = el('input', { type: 'number', step: 0.05, min: 0.05, max: 1 });
  const minSim = el('input', { type: 'number', step: 0.01, min: 0, max: 1 });
  const topK = el('input', { type: 'number', min: 0, max: 20 });
  const factsLimit = el('input', { type: 'number', min: 0, max: 30 });
  const backfill = el('input', { type: 'number', min: 0, max: 5000 });
  const tuneMsg = el('div', { class: 'msg' });
  const tuneSave = el('button', { class: 'primary', text: '저장 / Save' });
  tuneSave.addEventListener('click', async () => {
    try {
      const r = await deps.api<ServerConfig>('PUT', '/v1/config', {
        recall_threshold: Number(threshold.value), vector_min_sim: Number(minSim.value), recall_top_k: Number(topK.value),
        facts_limit: Number(factsLimit.value), extract_backfill: Number(backfill.value) });
      fillAll(r);
      say(tuneMsg, '저장했습니다. / Saved.', 'ok');
    } catch (error) { say(tuneMsg, errorText(error), 'err'); }
  });
  wrap.append(el('div', { class: 'card' },
    el('h2', { text: '검색 조정 / Recall tuning' }),
    el('p', { class: 'sub', text: '엉뚱한 발췌가 들어가면 기준값을 올리고, 기억이 너무 안 들어가면 내리세요.' }),
    el('div', { class: 'row' }, field('글자 일치 기준 / Lexical threshold', threshold), field('의미 유사도 기준 / Vector min sim', minSim)),
    el('div', { class: 'row' }, field('발췌 수 / Excerpts', topK), field('사실 수 / Facts', factsLimit), field('처음 연결 시 처리할 메시지 수 / Backfill', backfill)),
    el('div', { class: 'btns' }, tuneSave), tuneMsg));

  // --- parser rules --------------------------------------------------------------------------
  const rules = el('textarea', { spellcheck: 'false' });
  const rulesMsg = el('div', { class: 'msg' });
  const example = el('button', { text: '예시 넣기 / Example' });
  example.addEventListener('click', () => { rules.value = JSON.stringify(PARSER_EXAMPLE, null, 2); });
  const rulesSave = el('button', { class: 'primary', text: '저장 / Save' });
  rulesSave.addEventListener('click', async () => {
    try {
      const r = await deps.api<ServerConfig>('PUT', '/v1/config', { parsers: rules.value.trim() ? rules.value : null });
      fillAll(r);
      say(rulesMsg, `저장했습니다. 규칙 ${r.parsers.active_rules}개 적용, 기존 메시지를 다시 읽었습니다.`, 'ok');
    } catch (error) { say(rulesMsg, errorText(error), 'err'); }
  });
  wrap.append(el('div', { class: 'card' },
    el('h2', { text: '상태창 규칙 / Status-window rules' }),
    el('p', { class: 'sub', text: 'block: 시작~끝 사이의 "키: 값" 줄을 읽습니다. entity_line으로 [인물] 줄마다 인물별로 나눕니다 (시뮬봇). regex: key/value 이름 그룹.' }),
    rules, el('div', { class: 'btns' }, example, rulesSave), rulesMsg));

  function fillAll(cfg: ServerConfig) {
    llm.fill(cfg); emb.fill(cfg);
    threshold.value = String(cfg.recall.threshold);
    minSim.value = String(cfg.recall.vector_min_sim);
    topK.value = String(cfg.recall.top_k);
    factsLimit.value = String(cfg.recall.facts_limit);
    backfill.value = String(cfg.extraction.backfill);
    if (cfg.parsers.source === 'ui') rules.value = JSON.stringify(cfg.parsers.rules, null, 2);
    else if (cfg.parsers.source === 'file') rules.placeholder = `파일에서 규칙 ${cfg.parsers.active_rules}개를 읽는 중 (여기에 저장하면 대체됩니다)`;
    else rules.placeholder = '규칙 없음 — "예시 넣기"로 시작하세요';
  }

  async function refreshStatus() {
    try {
      const h = await deps.api<{ version: string; features: Record<string, boolean> }>('GET', '/v1/health', undefined, 5000);
      const on = (b?: boolean) => (b ? '켜짐' : '꺼짐');
      statusBox.className = 'status ok';
      statusBox.textContent = `연결됨 · NMOS ${h.version}\n상태창 ${on(h.features.state)} · 사실 추출 ${on(h.features.extraction)} · 의미 검색 ${on(h.features.vectors)}\n인스펙터: ${url.value.replace(/\/+$/, '')}/inspector`;
    } catch (error) {
      statusBox.className = 'status err';
      statusBox.textContent = `사이드카에 연결할 수 없습니다: ${errorText(error)}\n확인: docker compose up -d · 주소 · NMOS_CORS_ORIGINS`;
    }
  }

  async function refreshServer() {
    await refreshStatus();
    try { fillAll(await deps.api<ServerConfig>('GET', '/v1/config', undefined, 5000)); } catch { /* status shows the error */ }
  }

  document.body.append(root);
  await deps.show();
  await refreshServer();
}
