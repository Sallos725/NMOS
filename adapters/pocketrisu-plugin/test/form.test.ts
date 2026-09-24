import { describe, expect, it } from 'vitest';
import { configBody, connArgs, dirtySections, fillProject, presetMatches, serviceAccountProject, VERTEX_URL,
  type FormValues } from '../src/form';
import { STRING_KEYS, langOf, t } from '../src/i18n';

const base: FormValues = {
  conn: { url: 'http://127.0.0.1:8790', route: 'auto', enabled: true, reserved: '600', deadline: '3000' },
  llm: { url: 'http://llm/v1', model: 'm', key: '' },
  emb: { url: '', model: '', key: '' },
  tune: { threshold: '0.4', minSim: '0.42', topK: '5', facts: '8', backfill: '100' },
  rules: '',
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
      recall_threshold: 0.4, vector_min_sim: 0.42, recall_top_k: 3, facts_limit: 8, extract_backfill: 100,
    });
  });

  it('sends an API key only when one was typed, and clears parser rules with null', () => {
    const edited = structuredClone(base);
    edited.emb = { url: 'http://emb/v1', model: 'e', key: ' sk-1 ' };
    edited.rules = '   ';
    const other = structuredClone(base);
    other.rules = '{"rules": []}';
    expect(configBody(dirtySections(other, edited), edited)).toEqual({
      embed_url: 'http://emb/v1', embed_model: 'e', embed_api_key: 'sk-1', parsers: null });
  });

  it('passes unparsable numbers through so the sidecar rejects them instead of resetting', () => {
    const edited = structuredClone(base);
    edited.tune.topK = '';
    edited.tune.facts = '3.5';
    expect(configBody(['tune'], edited)).toMatchObject({ recall_top_k: '', facts_limit: 3.5 });
  });

  it('keeps connection settings on the plugin side', () => {
    const edited = structuredClone(base);
    edited.conn = { url: ' http://10.0.0.2:8790 ', route: 'server', enabled: false, reserved: '', deadline: '1200' };
    expect(dirtySections(base, edited)).toEqual(['conn']);
    expect(configBody(['conn'], edited)).toEqual({});
    expect(connArgs(edited.conn)).toEqual({ sidecar_url: 'http://10.0.0.2:8790', route: 'server', disabled: 1,
      reserved_memory_tokens: 600, deadline_ms: 1200 });
  });

  it('defaults the deadline to 3 s and keeps it between 200 ms and 30 s', () => {
    const deadline = (value: string) => connArgs({ ...base.conn, deadline: value }).deadline_ms;
    expect([deadline(''), deadline('abc'), deadline('50'), deadline('4500.7'), deadline('99999')])
      .toEqual([3000, 3000, 200, 4500, 30000]);
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
});
