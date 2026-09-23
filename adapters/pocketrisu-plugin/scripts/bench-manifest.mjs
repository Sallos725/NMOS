// Plugin-side cost of the full-manifest design for large chats (#12): snapshot copy, manifest
// build with one SHA-256 per message, the incremental builder after a two-message append (Track A,
// A2) with the packet-cache key, and reconcile payload serialization. Node, not a browser:
// numbers are a lower bound for a desktop browser and optimistic for a phone.
//   node scripts/bench-manifest.mjs [1000,5000,10000,25000]
import { build } from 'esbuild';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const out = await build({
  entryPoints: [new URL('../src/manifest.ts', import.meta.url).pathname],
  bundle: true, format: 'esm', platform: 'node', write: false,
});
const file = join(mkdtempSync(join(tmpdir(), 'nmos-bench-')), 'manifest.mjs');
writeFileSync(file, out.outputFiles[0].text);
const { buildManifest, createManifestBuilder } = await import(pathToFileURL(file).href);

const sizes = (process.argv[2] ?? '1000,5000,10000,25000').split(',').map(Number);
const SENTENCE = '하나는 창가에 앉아 등대 쪽을 바라보았다. "오늘은 바람이 차네." ';

function chat(n) {
  // Role-play shaped: short user turns, ~1,200-char replies with a status block, a few swipes.
  const message = [];
  for (let i = 0; i < n; i++) {
    const user = i % 2 === 0;
    const text = user ? `대사 ${i}: 오늘 저녁은 어디서 먹을까?` : SENTENCE.repeat(30) + `\n<status>HP ${i % 100}</status>`;
    message.push({
      role: user ? 'user' : 'char', data: text, chatId: `m-${i}`,
      ...(user ? {} : { saying: 'c', generationInfo: { generationId: `g-${i}` }, swipes: [text, text + ' 다시'], swipeId: 0 }),
    });
  }
  return { id: 'bench', message };
}

const pct = (xs, p) => [...xs].sort((a, b) => a - b)[Math.min(xs.length - 1, Math.floor(p * xs.length))];
console.log('| Messages | snapshot copy p50 | manifest + SHA-256 p50 / p95 | incremental after append p50 / p95 (hashed) | JSON p50 | reconcile payload |');
console.log('|---:|---:|---:|---:|---:|---:|');
async function sha(text) {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(d), (b) => b.toString(16).padStart(2, '0')).join('');
}
for (const n of sizes) {
  const source = chat(n);
  const copy = [], manifest = [], json = [], warm = [];
  let bytes = 0, hashed = 0;
  for (let run = 0; run < 7; run++) {
    let t = performance.now();
    const snap = structuredClone(source); // stands in for getChatFromIndex() returning a copy
    copy.push(performance.now() - t);
    t = performance.now();
    const built = await buildManifest(snap, 'char');
    manifest.push(performance.now() - t);
    t = performance.now();
    bytes = JSON.stringify(built.request).length;
    json.push(performance.now() - t);
  }
  const build = createManifestBuilder();
  const grow = structuredClone(source);
  await build(structuredClone(grow), 'char'); // warm-up: first sight hashes everything
  for (let run = 0; run < 15; run++) {
    grow.message.push({ role: 'user', data: `새 대사 ${run}`, chatId: `n-u-${run}` },
      { role: 'char', data: SENTENCE.repeat(20), chatId: `n-c-${run}`, generationInfo: { generationId: `n-c-${run}` } });
    const snap = structuredClone(grow);
    const t = performance.now();
    const built = await build(snap, 'char');
    await sha(JSON.stringify(['bench', 'model', 3, built.request.messages.map((m) => [m.host_logical_id, m.revision_hash])]));
    warm.push(performance.now() - t);
    hashed = built.hashed;
  }
  const f = (x) => `${x.toFixed(1)} ms`;
  console.log(`| ${n.toLocaleString('en')} | ${f(pct(copy, 0.5))} | ${f(pct(manifest, 0.5))} / ${f(pct(manifest, 0.95))} | ${f(pct(warm, 0.5))} / ${f(pct(warm, 0.95))} (${hashed}) | ${f(pct(json, 0.5))} | ${(bytes / 1024 / 1024).toFixed(2)} MB |`);
}
