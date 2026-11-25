import { describe, expect, it } from 'vitest';
import { configBody, connArgs, dirtySections, embedChunkChars, embedWaitTooLong, modelChange, OLLAMA_DOCKER, presetUrl, endpointForKey, fillProject, isVertexEndpoint, presetMatches, serviceAccountProject, trimArgs, VERTEX_URL,
  type FormValues } from '../src/form';
import { risuHost } from '../src/host';
import { STRING_KEYS, langOf, t } from '../src/i18n';

const base: FormValues = {
  conn: { url: 'http://127.0.0.1:8790', route: 'auto', enabled: true, reserved: '800', deadline: '3000', token: '' },
  llm: { url: 'http://llm/v1', model: 'm', key: '' },
  emb: { url: '', model: '', key: '' },
  tune: { threshold: '0.4', minSim: '0.42', embedWait: '300', topK: '5', facts: '8', backfill: '100', summaries: true,
    canonFacts: true },
};

describe('batch save', () => {
  it('saves every changed server section in one body and leaves the rest alone', () => {
    const edited = structuredClone(base);
    edited.llm.model = 'm2';
    edited.tune.topK = '3';
    const dirty = dirtySections(base, edited);
    expect(dirty).toEqual(['llm', 'tune']);
    expect(configBody(dirty, edited)).toEqual({
      llm_url: 'http://llm/v1', llm_model: 'm2',
      recall_threshold: 0.4, vector_min_sim: 0.42, recall_top_k: 3, facts_limit: 8, extract_backfill: 100, summaries: true,
      canon_facts: true, embed_timeout_ms: 300,
    });
  });

  it('sends the embedding wait only when the sidecar reported one (an older sidecar refuses the key)', () => {
    const edited = structuredClone(base);
    edited.tune.embedWait = '1200';
    expect(configBody(['tune'], edited)).toMatchObject({ embed_timeout_ms: 1200 });
    edited.tune.embedWait = '';
    expect(configBody(['tune'], edited)).not.toHaveProperty('embed_timeout_ms');
    // a wait that leaves the request less than 500 ms of its deadline is said, not refused (audit F20)
    expect(embedWaitTooLong('2500', '3000')).toBe(false);
    expect(embedWaitTooLong('2600', '3000')).toBe(true);
    expect(embedWaitTooLong('3000', '')).toBe(true);  // the default deadline, 3000
    expect(embedWaitTooLong('', '1000')).toBe(false);  // an older sidecar: no wait to compare
  });

  it('sends the @name pin setting only when the sidecar reported it (PHASE-60 S8)', () => {
    const edited = structuredClone(base);
    edited.tune = { ...edited.tune, pinAt: true };
    expect(configBody(['tune'], edited, { pinAt: true })).toMatchObject({ pin_at_mentions: true });
    edited.tune.pinAt = false;
    expect(configBody(['tune'], edited, { pinAt: true })).toMatchObject({ pin_at_mentions: false });
    expect(configBody(['tune'], edited, { pinAt: false })).not.toHaveProperty('pin_at_mentions');
    expect(configBody(['tune'], edited)).not.toHaveProperty('pin_at_mentions');  // an older sidecar refuses the key
    expect(configBody(['llm'], edited, { pinAt: true })).not.toHaveProperty('pin_at_mentions');  // only with tune
    const before = { ...structuredClone(base), tune: { ...base.tune, pinAt: false } };
    expect(dirtySections(before, { ...before, tune: { ...before.tune, pinAt: true } })).toEqual(['tune']);
  });

  it('sends reranker settings only when dirty and reported by the sidecar, and the key only when typed (PHASE-60 S5)', () => {
    const before = { ...structuredClone(base), rerank: { url: '', model: '', key: '', timeout: '600' } };
    const edited = structuredClone(before);
    expect(dirtySections(before, edited)).toEqual([]);
    edited.rerank = { url: ' https://rerank.example/v1 ', model: ' rr-1 ', key: '   ', timeout: '800' };
    expect(dirtySections(before, edited)).toEqual(['rerank']);
    expect(configBody(['rerank'], edited, { rerank: true })).toEqual({
      rerank_url: 'https://rerank.example/v1', rerank_model: 'rr-1', rerank_timeout_ms: 800,
    });
    edited.rerank.key = ' rk-secret ';
    expect(configBody(['rerank'], edited, { rerank: true })).toEqual({
      rerank_url: 'https://rerank.example/v1', rerank_model: 'rr-1', rerank_timeout_ms: 800, rerank_api_key: 'rk-secret',
    });
    expect(configBody(['rerank'], edited, { rerank: true })).not.toHaveProperty('rerank_format');
    // bad timeout passes through so the sidecar refuses it with a message
    edited.rerank = { url: '', model: '', key: '', timeout: '' };
    expect(configBody(['rerank'], edited, { rerank: true })).toEqual({
      rerank_url: '', rerank_model: '', rerank_timeout_ms: '',
    });
    edited.rerank.timeout = 'abc';
    expect(configBody(['rerank'], edited, { rerank: true })).toMatchObject({ rerank_timeout_ms: 'abc' });
    // absent on an older sidecar, or not dirty: nothing sent
    expect(configBody(['rerank'], edited, { rerank: false })).toEqual({});
    expect(configBody(['rerank'], edited)).toEqual({});
    expect(configBody(['llm'], edited, { rerank: true })).not.toHaveProperty('rerank_url');
  });

  it('sends an API key only when one was typed and never includes status rules', () => {
    const edited = structuredClone(base);
    edited.emb = { url: 'http://emb/v1', model: 'e', key: ' sk-1 ' };
    expect(configBody(dirtySections(base, edited), edited)).toEqual({
      embed_url: 'http://emb/v1', embed_model: 'e', embed_api_key: 'sk-1' });
    expect(configBody(['llm', 'emb', 'tune'], edited)).not.toHaveProperty('parsers');
  });

  it('passes unparsable numbers through so the sidecar rejects them instead of resetting', () => {
    const edited = structuredClone(base);
    edited.tune.topK = '';
    edited.tune.facts = '3.5';
    expect(configBody(['tune'], edited)).toMatchObject({ recall_top_k: '', facts_limit: 3.5 });
  });

  it('keeps connection settings on the plugin side', () => {
    const edited = structuredClone(base);
    edited.conn = { url: ' http://10.0.0.2:8790 ', route: 'server', enabled: false, reserved: '', deadline: '1200',
      token: ' s3cret ' };
    expect(dirtySections(base, edited)).toEqual(['conn']);
    expect(configBody(['conn'], edited)).toEqual({});
    expect(connArgs(edited.conn)).toEqual({ sidecar_url: 'http://10.0.0.2:8790', route: 'server', disabled: 1,
      reserved_memory_tokens: 4000, deadline_ms: 1200, auth_token: 's3cret' });  // the token, trimmed (audit F27)
  });

  it("picks the PC's own Ollama address on a bundle (audit F18)", () => {
    expect(presetUrl(OLLAMA_DOCKER, 'bundle')).toBe('http://127.0.0.1:11434/v1');
    expect(presetUrl(OLLAMA_DOCKER, null)).toBe(OLLAMA_DOCKER);
    expect(presetUrl('https://api.openai.com/v1', 'bundle')).toBe('https://api.openai.com/v1');
    expect(presetMatches(OLLAMA_DOCKER, 'http://127.0.0.1:11434/v1')).toBe(true);  // shown as the Ollama preset
  });

  it('keeps the memory budget within what the sidecar accepts', () => {
    const reserved = (value: string) => connArgs({ ...base.conn, reserved: value }).reserved_memory_tokens;
    expect([reserved(''), reserved('abc'), reserved('-5'), reserved('1200.6'), reserved('99999')])
      .toEqual([4000, 4000, 4000, 1200, 8000]);  // the panel saves up to 8,000 (ADR 0049)
  });

  it('defaults the deadline to 3 s and keeps it between 200 ms and 30 s', () => {
    const deadline = (value: string) => connArgs({ ...base.conn, deadline: value }).deadline_ms;
    expect([deadline(''), deadline('abc'), deadline('50'), deadline('4500.7'), deadline('99999')])
      .toEqual([3000, 3000, 200, 4500, 30000]);
  });
});

describe('extra request values in the save (PHASE-61 S4)', () => {
  const loaded: FormValues = { ...structuredClone(base), llm: { ...base.llm, extra: '{\n  "a": 1,\n  "b": 2\n}', noTemp: false } };

  it('counts the body by its object: spacing and key order are no change', () => {
    const edited = structuredClone(loaded);
    edited.llm.extra = '{"b":2,"a":1}';
    expect(dirtySections(loaded, edited)).toEqual([]);
    expect(modelChange(loaded, edited)).toBe(false);
    edited.llm.extra = '{"b": 2, "a": 1, "reasoning": {"effort": "low"}}';
    expect(dirtySections(loaded, edited)).toEqual(['llm']);
    expect(modelChange(loaded, edited)).toBe(true);
  });

  it('sends the body and the switch only when they changed, beside the model fields', () => {
    const edited = structuredClone(loaded);
    edited.llm.key = ' sk-new ';  // another llm change: neither new field goes with it
    expect(configBody(['llm'], edited, {}, loaded)).toEqual({ llm_url: 'http://llm/v1', llm_model: 'm', llm_api_key: 'sk-new' });
    edited.llm.key = '';
    edited.llm.extra = '{"a": 1, "b": 2, "reasoning": {"effort": "low"}}';
    expect(configBody(['llm'], edited, {}, loaded)).toEqual({ llm_url: 'http://llm/v1', llm_model: 'm',
      llm_extra_body: { a: 1, b: 2, reasoning: { effort: 'low' } } });
    edited.llm.extra = '';  // emptied: {} is sent
    expect(configBody(['llm'], edited, {}, loaded)).toMatchObject({ llm_extra_body: {} });
    edited.llm.extra = loaded.llm.extra;
    edited.llm.noTemp = true;
    expect(dirtySections(loaded, edited)).toEqual(['llm']);
    expect(modelChange(loaded, edited)).toBe(true);
    expect(configBody(['llm'], edited, {}, loaded)).toEqual({ llm_url: 'http://llm/v1', llm_model: 'm', llm_no_temperature: true });
    expect(configBody(['tune'], edited, {}, loaded)).not.toHaveProperty('llm_no_temperature');  // only with llm
  });

  it('never sends a text that is not a JSON object, nor anything to a sidecar that has no such setting', () => {
    const edited = structuredClone(loaded);
    edited.llm.extra = '{"a": 1';
    expect(dirtySections(loaded, edited)).toEqual(['llm']);
    expect(configBody(['llm'], edited, {}, loaded)).not.toHaveProperty('llm_extra_body');
    const older = structuredClone(base);
    const moved = { ...structuredClone(base), llm: { ...base.llm, model: 'm2' } };
    expect(configBody(['llm'], moved, {}, older)).toEqual({ llm_url: 'http://llm/v1', llm_model: 'm2' });
    expect(modelChange(older, moved)).toBe(true);
    expect(modelChange(older, structuredClone(older))).toBe(false);
  });
});

describe('leaving out old dialogue (PHASE-60 S1)', () => {
  it('stores the switch as 1 or 0 and keeps the recent turns within 4..200, 16 by default', () => {
    const keep = (value: string) => trimArgs({ on: true, keep: value }).keep_recent_turns;
    expect([keep(''), keep('abc'), keep('0'), keep('-5'), keep('0.5'), keep('3'), keep('4'), keep('30.9'), keep(' 40 '),
      keep('200'), keep('500')]).toEqual([16, 16, 16, 16, 16, 4, 4, 30, 40, 200, 200]);
    expect(trimArgs({ on: true, keep: '30' })).toEqual({ trim_old_turns: 1, keep_recent_turns: 30 });
    expect(trimArgs({ on: false, keep: '' })).toEqual({ trim_old_turns: 0, keep_recent_turns: 16 });
  });

  it('is a section of its own that sends nothing to the sidecar', () => {
    const before: FormValues = { ...structuredClone(base), trim: { on: false, keep: '20' } };
    const edited = structuredClone(before);
    expect(dirtySections(before, edited)).toEqual([]);
    edited.trim = { on: true, keep: '30' };
    expect(dirtySections(before, edited)).toEqual(['trim']);
    expect(configBody(['trim'], edited)).toEqual({});
    edited.tune.topK = '3';
    expect(dirtySections(before, edited)).toEqual(['tune', 'trim']);
    expect(configBody(dirtySections(before, edited), edited)).not.toHaveProperty('trim_old_turns');
    expect(configBody(dirtySections(before, edited), edited)).not.toHaveProperty('keep_recent_turns');
  });

  it('stores what the plugin reads back', async () => {
    try {
      for (const v of [{ on: true, keep: '30' }, { on: false, keep: '' }, { on: true, keep: '500' }, { on: true, keep: '2' }]) {
        const args: Record<string, number> = trimArgs(v);
        (globalThis as { risuai?: unknown }).risuai = { getArgument: async (key: string) => args[key.split('::').pop()!] };
        const s = await risuHost.settings();
        expect([s.trimOldTurns ? 1 : 0, s.keepRecentTurns], JSON.stringify(v))
          .toEqual([args.trim_old_turns, args.keep_recent_turns]);
      }
    } finally {
      delete (globalThis as { risuai?: unknown }).risuai;
    }
  });
});

describe('ui language', () => {
  it('defaults to Korean and has both languages for every string', () => {
    expect(langOf(undefined)).toBe('ko');
    expect(langOf('fr')).toBe('ko');
    expect(langOf('en')).toBe('en');
    for (const key of STRING_KEYS) {
      expect(t('ko', key).length, key).toBeGreaterThan(0);
      expect(t('en', key).length, key).toBeGreaterThan(0);
    }
    expect(t('ko', 'outcome.injected', { n: 12 })).toBe('기억 12자를 넣었습니다');
    expect(t('en', 'unsaved', { s: 'Connection' })).toBe('Unsaved changes: Connection');
  });
});

describe('Vertex AI service-account key (ADR 0021)', () => {
  const key = JSON.stringify({ type: 'service_account', project_id: 'my-proj', private_key: 'x', client_email: 'a@b' }, null, 2);

  it('reads the project from a pasted key only', () => {
    expect(serviceAccountProject(key)).toBe('my-proj');
    expect(serviceAccountProject(key.replace(/\n/g, ''))).toBe('my-proj'); // a password field drops line breaks
    expect(serviceAccountProject('sk-abc')).toBeNull();
    expect(serviceAccountProject('{"type":"authorized_user","project_id":"p"}')).toBeNull();
    expect(serviceAccountProject('{broken')).toBeNull();
  });

  it('fills {project} once and leaves other endpoints alone', () => {
    const filled = fillProject(VERTEX_URL, key);
    expect(filled).toBe('https://aiplatform.googleapis.com/v1/projects/my-proj/locations/global/endpoints/openapi');
    expect(fillProject(filled, key)).toBe(filled);
    expect(fillProject(VERTEX_URL, 'sk-abc')).toBe(VERTEX_URL);
    expect(fillProject('http://llm/v1', key)).toBe('http://llm/v1');
  });

  it('recognizes a saved Vertex endpoint as the Vertex preset', () => {
    expect(presetMatches(VERTEX_URL, fillProject(VERTEX_URL, key))).toBe(true);
    expect(presetMatches(VERTEX_URL, VERTEX_URL.replace('{project}', 'a/b'))).toBe(false);
    expect(presetMatches(VERTEX_URL, 'https://aiplatform.googleapis.com/v1/projects/p/locations/us-central1/endpoints/openapi')).toBe(false);
    expect(presetMatches('http://llm/v1', 'http://llm/v1')).toBe(true);
  });

  it('points the endpoint at the key file\'s project, keeping a custom regional Vertex endpoint', () => {
    const mine = 'https://aiplatform.googleapis.com/v1/projects/my-proj/locations/global/endpoints/openapi';
    expect(endpointForKey('', key)).toBe(mine);
    expect(endpointForKey('https://openrouter.ai/api/v1', key)).toBe(mine);
    expect(endpointForKey(VERTEX_URL, key)).toBe(mine);
    expect(endpointForKey(VERTEX_URL.replace('{project}', 'old-proj'), key)).toBe(mine); // another key's project
    const regional = 'https://us-central1-aiplatform.googleapis.com/v1/projects/p/locations/us-central1/endpoints/openapi';
    expect(endpointForKey(regional, key)).toBe(regional);
    expect(endpointForKey('https://aiplatform.googleapis.com/not-openapi', key)).toBe(mine); // the host alone is not kept
    expect(isVertexEndpoint(regional) && isVertexEndpoint(VERTEX_URL)).toBe(true);
    expect(isVertexEndpoint('https://aiplatform.googleapis.com.evil.example/v1')).toBe(false);
    expect(isVertexEndpoint('https://generativelanguage.googleapis.com/v1beta/openai')).toBe(false);
  });
});

describe('embedding chunks per message (ADR 0062, Tier 4 E8)', () => {
  const tune = (embedChunks: string) => ({ ...structuredClone(base), tune: { ...base.tune, pinAt: false, embedChunks } });

  it('sends embed_max_chunks only when the sidecar reports it and it changed', () => {
    expect(configBody(['tune'], tune('16'), { embedChunks: true }, tune('8'))).toMatchObject({ embed_max_chunks: 16 });
    expect(configBody(['tune'], tune('8'), { embedChunks: true }, tune('8'))).not.toHaveProperty('embed_max_chunks');
    expect(configBody(['tune'], tune('16'), {}, tune('8'))).not.toHaveProperty('embed_max_chunks');
    expect(configBody(['tune'], tune(''), { embedChunks: true }, tune('8'))).not.toHaveProperty('embed_max_chunks');
    expect(configBody(['tune'], tune('abc'), { embedChunks: true }, tune('8'))).toMatchObject({ embed_max_chunks: 'abc' });
    expect(configBody(['llm'], tune('16'), { embedChunks: true }, tune('8'))).not.toHaveProperty('embed_max_chunks');
    expect(dirtySections(tune('8'), tune('16'))).toEqual(['tune']);
  });

  it('says how many characters a cap covers, within 1..64 only', () => {
    expect(embedChunkChars('8')).toBe(5600);
    expect(embedChunkChars(' 64 ')).toBe(44_800);
    for (const bad of ['0', '65', '2.5', '', 'x']) expect(embedChunkChars(bad)).toBeNull();
  });
});
