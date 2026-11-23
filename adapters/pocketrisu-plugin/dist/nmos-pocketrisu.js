//@name nmos_memory
//@display-name NMOS Narrative Memory
//@api 3.0
//@version 0.6.0
//@link https://github.com/Sallos725/NMOS Documentation
//@update-url https://raw.githubusercontent.com/Sallos725/NMOS/main/adapters/pocketrisu-plugin/dist/nmos-pocketrisu.js
//@arg sidecar_url string NMOS sidecar URL (empty = http://127.0.0.1:8790)
//@arg auth_token string Optional; only if the sidecar sets NMOS_AUTH_TOKEN
//@arg disabled int 1 = pass every request through untouched
//@arg reserved_memory_tokens int Max packet tokens; lower the host max context by this much (0 = 4000)
//@arg deadline_ms int Hard request-path deadline in ms (0 = 3000)
//@arg inject_position string before_last_user (default) or end
//@arg trim_old_turns int 1 = leave old dialogue out in steps once memory and summaries cover it (needs summaries on)
//@arg keep_recent_turns int Recent turns always sent when trimming; the cut moves in steps of this many (0 = 20, 4-200)
//@arg route string auto (default) / direct / server — how to reach the sidecar
//@arg language string Panel language: ko (default) or en
//@arg hud int 1 = progress display on the chat screen (turn it on from the NMOS panel)
//@arg disabled_chats string Chat ids NMOS is off for (switched from the NMOS panel or the chat menu)
"use strict";
(() => {
  // src/build.ts
  var PLUGIN_BUILD = true ? "nmos-build:870d9e00b6f7".replace("nmos-build:", "") : "dev";

  // src/canonical.ts
  function normalizeText(value) {
    return String(value ?? "").normalize("NFC").replace(/\r\n/g, "\n");
  }
  function canonicalize(value) {
    if (value === null || typeof value !== "object") {
      return typeof value === "string" ? normalizeText(value) : value;
    }
    if (Array.isArray(value)) return value.map(canonicalize);
    const out = {};
    for (const key of Object.keys(value).sort()) {
      const v = value[key];
      if (v !== void 0) out[key] = canonicalize(v);
    }
    return out;
  }
  function canonicalJson(value) {
    return JSON.stringify(canonicalize(value));
  }

  // src/hash.ts
  async function sha256Hex(text2) {
    return sha256HexOf(new TextEncoder().encode(text2));
  }
  async function sha256HexOf(bytes) {
    const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  }

  // src/notes.ts
  var BLOCK = /\[NMOS note(?: · t(\d+))?(?: · [^\]\n]*)?\]\n?[\s\S]*?\[\/NMOS note\]\n?/g;
  var PROMPT_MAX = 4e3;
  function stripNoteBlocks(text2) {
    const blocks = [...text2.matchAll(BLOCK)].map((m) => ({ turn: m[1] ?? "" }));
    if (!blocks.length) return { text: text2, blocks };
    return { text: text2.replace(BLOCK, "\n\n").replace(/\n{3,}/g, "\n\n").trim(), blocks };
  }
  async function copyText(box, clipboard) {
    try {
      if (!clipboard) throw new Error("no clipboard");
      await clipboard.writeText(box.value);
      return true;
    } catch {
      box.focus();
      box.select();
      box.setSelectionRange(0, box.value.length);
      return false;
    }
  }

  // src/canon.ts
  var ID = /^[A-Za-z0-9_.:-]{1,110}$/;
  var MAX_CANON_CHARS = 19e5;
  function fnv(text2) {
    let h = 2166136261;
    for (let i = 0; i < text2.length; i++) {
      h ^= text2.charCodeAt(i);
      h = Math.imul(h, 16777619) >>> 0;
    }
    return h.toString(16).padStart(8, "0");
  }
  function loreKey(entry) {
    if (typeof entry.id === "string" && ID.test(entry.id)) return `lore:${entry.id}`;
    return `lore:f${fnv([entry.comment ?? "", entry.key ?? "", entry.secondkey ?? "", entry.mode ?? ""].join("\0"))}`;
  }
  function keysOf(entry) {
    return `${entry.key ?? ""},${entry.secondkey ?? ""}`.split(/[,\n]/).map((k) => k.trim()).filter(Boolean);
  }
  var text = (value) => typeof value === "string" ? value.trim() : "";
  function same(a, b) {
    return a === b || !!a.id && a.id === b.id || a.content === b.content && a.key === b.key && a.comment === b.comment;
  }
  function canonTexts(card, chat, lore, persona) {
    const out = [];
    const add = (key, value, metadata = {}) => {
      if (typeof value === "string" && value.trim() && value.length <= MAX_CANON_CHARS) out.push({ key, text: value, metadata });
    };
    if (card) {
      for (const field2 of ["name", "desc", "personality", "scenario"]) add(`card:${field2}`, card[field2], { field: field2 });
      const index = Number.isInteger(chat.fmIndex) ? Number(chat.fmIndex) : -1;
      add("card:greeting", index < 0 ? card.firstMessage : card.alternateGreetings?.[index], { field: "greeting", index });
    }
    if (typeof chat.note === "string") {
      const note = stripNoteBlocks(chat.note);
      add("note", note.text, note.blocks.length ? { nmos_blocks: note.blocks } : {});
    }
    if (persona) add("persona", persona.personaPrompt, { name: text(persona.name) || void 0, persona_id: persona.id });
    const local = Array.isArray(chat.localLore) ? chat.localLore : [];
    const global = Array.isArray(card?.globalLore) ? card.globalLore : [];
    const seen = /* @__PURE__ */ new Map();
    for (const entry of lore) {
      if (!entry || entry.mode === "folder") continue;
      let key = loreKey(entry);
      const n = seen.get(key) ?? 0;
      seen.set(key, n + 1);
      if (n) key = `${key}~${n}`;
      const scope = local.some((e) => same(e, entry)) ? "chat" : global.some((e) => same(e, entry)) ? "character" : card ? "module" : null;
      add(key, entry.content, {
        scope: scope ?? void 0,
        mode: entry.mode,
        always_active: !!entry.alwaysActive,
        keys: keysOf(entry),
        comment: text(entry.comment) || void 0
      });
    }
    return out;
  }
  var NAME_MACRO = /\{\{\s*(char|bot|user)\s*\}\}/gi;
  var HELD_MIN_LINE = 12;
  var HELD_SHARE = 0.8;
  function heldKeys(canon, prompt) {
    const all = normalizeText(prompt.map((m) => typeof m?.content === "string" ? m.content : "").join("\n"));
    const character = canon.find((c) => c.key === "card:name")?.text.trim();
    const persona = canon.find((c) => c.key === "persona")?.metadata.name;
    const user = typeof persona === "string" && persona.trim() ? persona.trim() : void 0;
    const named = (value) => value.replace(NAME_MACRO, (m, which) => (which.toLowerCase() === "user" ? user : character) ?? m);
    return canon.filter((c) => {
      if (c.key === "card:name") return false;
      const whole = normalizeText(named(c.text)).trim();
      if (all.includes(whole)) return true;
      const lines = whole.split("\n").map((l) => l.trim()).filter((l) => l.length >= HELD_MIN_LINE && !l.includes("{{"));
      return lines.length >= 2 && lines.filter((l) => all.includes(l)).length >= HELD_SHARE * lines.length;
    }).map((c) => c.key);
  }
  function canonHash(text2) {
    return sha256Hex(normalizeText(text2));
  }
  function canonManifestId(entries) {
    const rows = entries.map((e) => ({ key: e.key, hash: e.hash, metadata: e.metadata ?? {} })).sort((a, b) => a.key < b.key ? -1 : a.key > b.key ? 1 : 0);
    return sha256Hex(canonicalJson(rows));
  }

  // src/extrabody.ts
  var EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"];
  var isObj = (v) => typeof v === "object" && v !== null && !Array.isArray(v);
  function bodyOf(text2) {
    if (!text2.trim()) return {};
    try {
      const v = JSON.parse(text2);
      return isObj(v) ? v : null;
    } catch {
      return null;
    }
  }
  function showBody(body) {
    return Object.keys(body).length ? JSON.stringify(body, null, 2) : "";
  }
  function bodyKey(text2) {
    const body = bodyOf(text2);
    return body ? canonicalJson(body) : `!${text2}`;
  }
  function effortOf(text2) {
    const body = bodyOf(text2);
    if (!body) return { state: "invalid" };
    if (!("reasoning" in body)) return { state: "none" };
    const r = body.reasoning;
    if (!isObj(r)) return { state: "custom" };
    if (!("effort" in r)) return { state: "none" };
    return typeof r.effort === "string" && EFFORTS.includes(r.effort) ? { state: "value", effort: r.effort } : { state: "custom" };
  }
  function withEffort(text2, effort) {
    const body = bodyOf(text2);
    if (!body) return text2;
    const r = body.reasoning;
    if (effort !== null) body.reasoning = isObj(r) ? Object.assign(r, { effort }) : { effort };
    else if (isObj(r) && "effort" in r) {
      delete r.effort;
      if (!Object.keys(r).length) delete body.reasoning;
    }
    return showBody(body);
  }
  function isOpenRouter(url) {
    try {
      const host = new URL(url.trim()).hostname.toLowerCase();
      return host === "openrouter.ai" || host.endsWith(".openrouter.ai");
    } catch {
      return false;
    }
  }

  // src/form.ts
  var DEFAULT_DEADLINE_MS = 3e3;
  var MAX_DEADLINE_MS = 3e4;
  var DEFAULT_RESERVED_TOKENS = 4e3;
  var MAX_RESERVED_TOKENS = 2e4;
  var PANEL_MAX_RESERVED_TOKENS = 8e3;
  var DEFAULT_KEEP_RECENT_TURNS = 20;
  var MIN_KEEP_RECENT_TURNS = 4;
  var MAX_KEEP_RECENT_TURNS = 200;
  var MIN_RERANK_TIMEOUT_MS = 50;
  var MAX_RERANK_TIMEOUT_MS = 5e3;
  var SECTIONS = ["conn", "llm", "emb", "rerank", "tune", "trim"];
  var VERTEX_URL = "https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/endpoints/openapi";
  function serviceAccountProject(key) {
    const text2 = key.trim();
    if (!text2.startsWith("{")) return null;
    try {
      const info = JSON.parse(text2);
      return info.type === "service_account" && typeof info.project_id === "string" && info.project_id ? info.project_id : null;
    } catch {
      return null;
    }
  }
  function fillProject(url, key) {
    const project = serviceAccountProject(key);
    return project && url.includes("{project}") ? url.replace("{project}", encodeURIComponent(project)) : url;
  }
  function isVertexEndpoint(url) {
    return /^https:\/\/(?:[a-z0-9-]+-)?aiplatform\.googleapis\.com\//.test(url.trim());
  }
  var VERTEX_OPENAPI = /^https:\/\/(?:[a-z0-9-]+-)?aiplatform\.googleapis\.com\/v1(?:beta1)?\/projects\/[^/]+\/locations\/[^/]+\/endpoints\/openapi\/?$/;
  function endpointForKey(url, key) {
    const u = url.trim();
    return VERTEX_OPENAPI.test(u) && !u.includes("{project}") && !presetMatches(VERTEX_URL, u) ? u : fillProject(VERTEX_URL, key);
  }
  var OLLAMA_DOCKER = "http://host.docker.internal:11434/v1";
  var OLLAMA_LOCAL = "http://127.0.0.1:11434/v1";
  function presetUrl(url, install) {
    return url === OLLAMA_DOCKER && install === "bundle" ? OLLAMA_LOCAL : url;
  }
  function presetMatches(presetUrl2, url) {
    if (presetUrl2 === OLLAMA_DOCKER && url === OLLAMA_LOCAL) return true;
    if (!presetUrl2.includes("{project}")) return presetUrl2 === url;
    const [head, tail] = presetUrl2.split("{project}");
    return url.startsWith(head) && url.endsWith(tail) && url.length > head.length + tail.length && !url.slice(head.length, url.length - tail.length).includes("/");
  }
  function dirtySections(baseline, current2) {
    const view2 = (v, s) => s === "llm" && v.llm.extra !== void 0 ? { ...v.llm, extra: bodyKey(v.llm.extra) } : v[s];
    return SECTIONS.filter((s) => JSON.stringify(view2(baseline, s)) !== JSON.stringify(view2(current2, s)));
  }
  function modelChange(baseline, current2) {
    const [b, c] = [baseline.llm, current2.llm];
    return c.url.trim() !== b.url.trim() || c.model.trim() !== b.model.trim() || bodyKey(c.extra ?? "") !== bodyKey(b.extra ?? "") || Boolean(c.noTemp) !== Boolean(b.noTemp);
  }
  function num(value) {
    const n = Number(value.trim());
    return value.trim() !== "" && Number.isFinite(n) ? n : value;
  }
  function configBody(dirty, v, known = {}, base) {
    const body = {};
    for (const [section, prefix] of [["llm", "llm"], ["emb", "embed"]]) {
      if (!dirty.includes(section)) continue;
      body[`${prefix}_url`] = v[section].url.trim();
      body[`${prefix}_model`] = v[section].model.trim();
      if (v[section].key.trim()) body[`${prefix}_api_key`] = v[section].key.trim();
    }
    if (dirty.includes("llm") && base) {
      const extra = v.llm.extra === void 0 ? null : bodyOf(v.llm.extra);
      if (extra && bodyKey(v.llm.extra) !== bodyKey(base.llm.extra ?? "")) body.llm_extra_body = extra;
      if (v.llm.noTemp !== void 0 && v.llm.noTemp !== Boolean(base.llm.noTemp)) body.llm_no_temperature = v.llm.noTemp;
    }
    if (dirty.includes("rerank") && known.rerank) {
      body.rerank_url = v.rerank.url.trim();
      body.rerank_model = v.rerank.model.trim();
      body.rerank_timeout_ms = num(v.rerank.timeout);
      if (v.rerank.key.trim()) body.rerank_api_key = v.rerank.key.trim();
    }
    if (dirty.includes("tune")) {
      Object.assign(body, {
        recall_threshold: num(v.tune.threshold),
        vector_min_sim: num(v.tune.minSim),
        recall_top_k: num(v.tune.topK),
        facts_limit: num(v.tune.facts),
        extract_backfill: num(v.tune.backfill),
        summaries: v.tune.summaries,
        canon_facts: v.tune.canonFacts
      });
      if (v.tune.embedWait.trim() !== "") body.embed_timeout_ms = num(v.tune.embedWait);
      if (known.pinAt) body.pin_at_mentions = v.tune.pinAt;
    }
    return body;
  }
  var EMBED_WAIT_MARGIN_MS = 500;
  function embedWaitTooLong(wait, deadline) {
    const w = Number(wait.trim());
    const d = Number(deadline.trim()) || DEFAULT_DEADLINE_MS;
    return wait.trim() !== "" && Number.isFinite(w) && w > d - EMBED_WAIT_MARGIN_MS;
  }
  function connArgs(v) {
    return {
      sidecar_url: v.url.trim(),
      route: v.route,
      disabled: v.enabled ? 0 : 1,
      reserved_memory_tokens: Math.min(PANEL_MAX_RESERVED_TOKENS, Math.floor(Number(v.reserved)) > 0 ? Math.floor(Number(v.reserved)) : DEFAULT_RESERVED_TOKENS),
      deadline_ms: Math.min(MAX_DEADLINE_MS, Math.max(200, Math.floor(Number(v.deadline)) || DEFAULT_DEADLINE_MS)),
      auth_token: v.token.trim()
    };
  }
  function trimArgs(v) {
    const n = Math.floor(Number(v.keep.trim()));
    const keep = Number.isFinite(n) && n > 0 ? n : DEFAULT_KEEP_RECENT_TURNS;
    return {
      trim_old_turns: v.on ? 1 : 0,
      keep_recent_turns: Math.min(MAX_KEEP_RECENT_TURNS, Math.max(MIN_KEEP_RECENT_TURNS, keep))
    };
  }

  // src/deadline.ts
  var NEAR_FRACTION = 0.8;
  function deadlineAdvice(r) {
    if (!r || !(r.deadlineMs > 0)) return null;
    let level;
    let tookMs;
    if (r.outcome === "failed") {
      if (!r.error?.startsWith("deadline")) return null;
      level = "over";
      tookMs = r.neededMs ?? null;
    } else {
      if (r.ms < NEAR_FRACTION * r.deadlineMs) return null;
      level = "near";
      tookMs = r.ms;
    }
    const base = level === "over" ? Math.max(tookMs ?? 0, r.deadlineMs) : r.ms;
    const suggestMs = Math.min(MAX_DEADLINE_MS, Math.max(r.deadlineMs + 500, Math.ceil(base * 1.25 / 500) * 500));
    return { level, deadlineMs: r.deadlineMs, tookMs, suggestMs };
  }
  function formatMs(ms) {
    return Math.round(ms).toLocaleString("en-US");
  }

  // src/i18n.ts
  function langOf(value) {
    return value === "en" ? "en" : "ko";
  }
  var STRINGS = {
    // menus (registered once at load, in the language chosen then)
    "menu.panel": ["NMOS \uAE30\uC5B5", "NMOS memory"],
    "menu.chat_switch": ["NMOS: \uC774 \uCC44\uD305 \uB044\uAE30/\uCF1C\uAE30", "NMOS: this chat off/on"],
    // frame
    "title": ["NMOS \uAE30\uC5B5", "NMOS memory"],
    "tab.status": ["\uC0C1\uD0DC", "Status"],
    "tab.inspector": ["\uC778\uC2A4\uD399\uD130", "Inspector"],
    "tab.settings": ["\uC124\uC815", "Settings"],
    "close": ["\uB2EB\uAE30", "Close"],
    "refresh": ["\uC0C8\uB85C \uACE0\uCE68", "Refresh"],
    "language": ["\uC5B8\uC5B4", "Language"],
    // status view
    "status.sidecar": ["\uC0AC\uC774\uB4DC\uCE74", "Sidecar"],
    "status.checking": ["\uC0AC\uC774\uB4DC\uCE74 \uD655\uC778 \uC911\u2026", "Checking the sidecar\u2026"],
    "status.connected": ["\uC5F0\uACB0\uB428", "Connected"],
    "status.unreachable": ["\uC5F0\uACB0\uD560 \uC218 \uC5C6\uC74C", "Cannot reach"],
    "status.fix": [
      "\uD655\uC778: NMOS\uAC00 \uCF1C\uC838 \uC788\uB294\uC9C0(Docker: docker compose up -d \xB7 \uC124\uCE58\uD310: \uD2B8\uB808\uC774\uB098 \uBA54\uB274 \uB9C9\uB300\uC758 NMOS) \xB7 \uC8FC\uC18C \xB7 NMOS_CORS_ORIGINS\uC5D0 \uC774 PocketRisu \uC8FC\uC18C \uD3EC\uD568 \xB7 localhost \uB610\uB294 HTTPS\uB85C \uC811\uC18D",
      "Check: NMOS is running (Docker: docker compose up -d \xB7 bundle: NMOS in the tray or menu bar) \xB7 the address \xB7 NMOS_CORS_ORIGINS includes this PocketRisu address \xB7 open via localhost or HTTPS"
    ],
    // why a request could not reach NMOS (pre-0.4.0 audit F24, F27)
    "status.fix_token": [
      "\uD1A0\uD070\uC774 \uB9DE\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4. \uC124\uC815 \uD0ED \u2192 \uC5F0\uACB0\uC758 \uD1A0\uD070\uC744 \uC0AC\uC774\uB4DC\uCE74\uC758 NMOS_AUTH_TOKEN\uACFC \uAC19\uAC8C \uB123\uC5B4 \uC8FC\uC138\uC694.",
      "The token does not match. Set Settings \u2192 Connection \u2192 token to the sidecar's NMOS_AUTH_TOKEN."
    ],
    "status.fix_host": [
      "\uC0AC\uC774\uB4DC\uCE74\uAC00 \uC774 \uC8FC\uC18C\uB97C \uD1A0\uD070 \uC5C6\uC774 \uBC1B\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4. \uC0AC\uC774\uB4DC\uCE74\uC758 NMOS_ALLOWED_HOSTS\uC5D0 \uC774 \uC8FC\uC18C\uB97C \uB123\uAC70\uB098, NMOS_AUTH_TOKEN\uC744 \uC815\uD558\uACE0 \uAC19\uC740 \uD1A0\uD070\uC744 \uC5F0\uACB0 \uC124\uC815\uC5D0 \uB123\uC5B4 \uC8FC\uC138\uC694.",
      "The sidecar refuses this address without a token. Add it to the sidecar's NMOS_ALLOWED_HOSTS, or set NMOS_AUTH_TOKEN and the same token in Settings \u2192 Connection."
    ],
    "status.insecure": [
      "\uC774 \uD398\uC774\uC9C0\uB294 \uBCF4\uC548 \uC5F0\uACB0\uC774 \uC544\uB2C8\uB77C\uC11C NMOS\uAC00 \uAE30\uC5B5\uC744 \uC900\uBE44\uD560 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4(\uBAA8\uB4E0 \uCC44\uD305\uC774 \uAE30\uC5B5 \uC5C6\uC774 \uAC11\uB2C8\uB2E4). PocketRisu\uB97C HTTPS \uC8FC\uC18C\uB098 localhost\uB85C \uC5F4\uC5B4 \uC8FC\uC138\uC694.",
      "This page is not a secure context, so NMOS cannot prepare memory (every chat goes without it). Open PocketRisu over HTTPS or on localhost."
    ],
    "status.plugin_file": ["\uB9DE\uB294 \uD50C\uB7EC\uADF8\uC778 \uD30C\uC77C \uBC1B\uAE30", "Get the matching plugin file"],
    "status.plugin_saved": [
      "{name}\uC744(\uB97C) \uBC1B\uC558\uC2B5\uB2C8\uB2E4. PocketRisu \uC124\uC815 \u2192 \uD50C\uB7EC\uADF8\uC778\uC5D0\uC11C \uC774 \uD30C\uC77C\uB85C \uAD50\uCCB4\uD558\uACE0 \uC0C8\uB85C \uACE0\uCE68\uD558\uC138\uC694.",
      "Saved {name}. Replace the plugin with it in PocketRisu Settings \u2192 Plugin, then reload."
    ],
    // once per page, after a reply that went without memory (pre-0.4.0 audit F25)
    "reach.unreachable": [
      "NMOS: \uC774\uBC88 \uB2F5\uC7A5\uC740 \uAE30\uC5B5 \uC5C6\uC774 \uBCF4\uB0C8\uC2B5\uB2C8\uB2E4. \uC0AC\uC774\uB4DC\uCE74({url})\uC5D0 \uC5F0\uACB0\uD560 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4. NMOS\uAC00 \uCF1C\uC838 \uC788\uB294\uC9C0(Docker: docker compose up -d, \uC124\uCE58\uD310: \uD2B8\uB808\uC774\uB098 \uBA54\uB274 \uB9C9\uB300\uC758 NMOS)\uC640 NMOS \uD328\uB110 \u2192 \uC124\uC815\uC758 \uC0AC\uC774\uB4DC\uCE74 \uC8FC\uC18C\uB97C \uD655\uC778\uD574 \uC8FC\uC138\uC694. (\uC774 \uC54C\uB9BC\uC740 \uD398\uC774\uC9C0\uB97C \uC0C8\uB85C \uC5F4 \uB54C\uAE4C\uC9C0 \uB2E4\uC2DC \uB728\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.)",
      "NMOS: this reply went without memory. The sidecar ({url}) cannot be reached. Check that NMOS is running (Docker: docker compose up -d; bundle: NMOS in the tray or menu bar) and the sidecar address in the NMOS panel \u2192 Settings. (This notice does not come back until the page is reloaded.)"
    ],
    "reach.unauthorized": [
      "NMOS: \uC774\uBC88 \uB2F5\uC7A5\uC740 \uAE30\uC5B5 \uC5C6\uC774 \uBCF4\uB0C8\uC2B5\uB2C8\uB2E4. \uC0AC\uC774\uB4DC\uCE74\uAC00 \uD1A0\uD070\uC744 \uBC1B\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4. NMOS \uD328\uB110 \u2192 \uC124\uC815 \u2192 \uC5F0\uACB0\uC758 \uD1A0\uD070\uC744 \uC0AC\uC774\uB4DC\uCE74\uC758 NMOS_AUTH_TOKEN\uACFC \uAC19\uAC8C \uB123\uC5B4 \uC8FC\uC138\uC694. (\uC774 \uC54C\uB9BC\uC740 \uD398\uC774\uC9C0\uB97C \uC0C8\uB85C \uC5F4 \uB54C\uAE4C\uC9C0 \uB2E4\uC2DC \uB728\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.)",
      "NMOS: this reply went without memory. The sidecar refused the token. Set the NMOS panel \u2192 Settings \u2192 Connection \u2192 token to the sidecar's NMOS_AUTH_TOKEN. (This notice does not come back until the page is reloaded.)"
    ],
    "reach.host_refused": [
      "NMOS: \uC774\uBC88 \uB2F5\uC7A5\uC740 \uAE30\uC5B5 \uC5C6\uC774 \uBCF4\uB0C8\uC2B5\uB2C8\uB2E4. \uC0AC\uC774\uB4DC\uCE74\uAC00 \uC774 \uC8FC\uC18C\uB97C \uD1A0\uD070 \uC5C6\uC774 \uBC1B\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4(NMOS_ALLOWED_HOSTS). NMOS \uD328\uB110 \u2192 \uC0C1\uD0DC \uD0ED\uC5D0\uC11C \uACE0\uCE58\uB294 \uBC95\uC744 \uBCFC \uC218 \uC788\uC2B5\uB2C8\uB2E4. (\uC774 \uC54C\uB9BC\uC740 \uD398\uC774\uC9C0\uB97C \uC0C8\uB85C \uC5F4 \uB54C\uAE4C\uC9C0 \uB2E4\uC2DC \uB728\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.)",
      "NMOS: this reply went without memory. The sidecar refuses this address without a token (NMOS_ALLOWED_HOSTS). The NMOS panel \u2192 Status tab shows the fix. (This notice does not come back until the page is reloaded.)"
    ],
    "reach.insecure": [
      "NMOS: \uC774\uBC88 \uB2F5\uC7A5\uC740 \uAE30\uC5B5 \uC5C6\uC774 \uBCF4\uB0C8\uC2B5\uB2C8\uB2E4. \uC774 \uD398\uC774\uC9C0\uAC00 \uBCF4\uC548 \uC5F0\uACB0\uC774 \uC544\uB2C8\uB77C\uC11C(HTTP\uB85C \uC5F0 LAN \uC8FC\uC18C) \uAE30\uC5B5\uC744 \uC900\uBE44\uD560 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4. PocketRisu\uB97C HTTPS \uC8FC\uC18C\uB098 localhost\uB85C \uC5F4\uC5B4 \uC8FC\uC138\uC694. (\uC774 \uC54C\uB9BC\uC740 \uD398\uC774\uC9C0\uB97C \uC0C8\uB85C \uC5F4 \uB54C\uAE4C\uC9C0 \uB2E4\uC2DC \uB728\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.)",
      "NMOS: this reply went without memory. This page is not a secure context (a LAN address over HTTP), so memory cannot be prepared. Open PocketRisu over HTTPS or on localhost. (This notice does not come back until the page is reloaded.)"
    ],
    "status.memory_off": ["\uAE30\uC5B5 \uB123\uAE30\uAC00 \uAEBC\uC838 \uC788\uC2B5\uB2C8\uB2E4. \uC124\uC815 \uD0ED\uC5D0\uC11C \uCF24 \uC218 \uC788\uC2B5\uB2C8\uB2E4.", "Memory is switched off. Turn it on in Settings."],
    "status.features": ["\uAE30\uB2A5", "Features"],
    // this chat (ADR 0048)
    "chat.title": ["\uC774 \uCC44\uD305", "This chat"],
    "chat.none": ["\uC5F4\uB9B0 \uCC44\uD305\uC774 \uC5C6\uC2B5\uB2C8\uB2E4. \uCC44\uD305\uC744 \uC5F0 \uB4A4 \uB2E4\uC2DC \uC2DC\uB3C4\uD558\uC138\uC694.", "No chat is open. Open one and try again."],
    "chat.dropped": [
      '\uB2E4\uC2DC \uCD94\uCD9C\uD558\uBA74\uC11C \uC0AC\uB77C\uC9C4 \uC0AC\uC2E4 {n}\uAC1C: \uC778\uC2A4\uD399\uD130\uC758 "\uD655\uC778 \uD544\uC694"\uC5D0\uC11C \uBCF5\uC6D0\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.',
      '{n} facts dropped by a re-extraction: restore them under "Needs attention" in the Inspector.'
    ],
    // PHASE-22 Q6
    "chat.on": ["NMOS \uCF1C\uC9D0", "NMOS on"],
    "chat.off": ["NMOS \uAEBC\uC9D0", "NMOS off"],
    "chat.on_sub": [
      "\uC774 \uCC44\uD305\uC758 \uB300\uD654\uB97C \uAE30\uC5B5\uD558\uACE0 \uC0DD\uC131\uD560 \uB54C \uAE30\uC5B5\uC744 \uB123\uC2B5\uB2C8\uB2E4. \uB044\uBA74 \uC774 \uCC44\uD305\uC740 \uC0AC\uC774\uB4DC\uCE74\uB85C \uBCF4\uB0B4\uC9C0 \uC54A\uACE0 \uAE30\uC5B5\uB3C4 \uB123\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4. \uC774\uBBF8 \uC313\uC778 \uAE30\uC5B5\uC740 \uC9C0\uC6B0\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
      "This chat is remembered and gets memory when you generate. Off: nothing of it goes to the sidecar and no memory goes in. What is already remembered is kept."
    ],
    "chat.off_sub": [
      "\uC774 \uCC44\uD305\uC740 \uC0AC\uC774\uB4DC\uCE74\uB85C \uBCF4\uB0B4\uC9C0 \uC54A\uACE0 \uAE30\uC5B5\uB3C4 \uB123\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4. \uC774\uBBF8 \uC313\uC778 \uAE30\uC5B5\uC740 \uADF8\uB300\uB85C\uC774\uBA70, \uB2E4\uC2DC \uCF1C\uBA74 \uB2E4\uC74C \uC0DD\uC131 \uB54C \uADF8\uB3D9\uC548\uC758 \uB300\uD654\uB97C \uB530\uB77C\uC7A1\uC2B5\uB2C8\uB2E4.",
      "Nothing of this chat goes to the sidecar and no memory goes in. What is already remembered is kept; turned back on, the next generation catches up."
    ],
    "chat.all_off": [
      "NMOS\uAC00 \uBAA8\uB4E0 \uCC44\uD305\uC5D0\uC11C \uAEBC\uC838 \uC788\uC2B5\uB2C8\uB2E4(\uC124\uC815 \uD0ED). \uC774 \uCC44\uD305\uB3C4 \uCF1C\uAE30 \uC804\uAE4C\uC9C0\uB294 \uC4F0\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
      "NMOS is off for every chat (Settings tab), so this chat is not used either until it is back on."
    ],
    "chat.turn_off": ["\uC774 \uCC44\uD305\uC5D0\uC11C \uB044\uAE30", "Turn off for this chat"],
    // what this chat's memory cost in NMOS's own model calls (PHASE-17 Q4)
    "usage.line": ["NMOS \uBAA8\uB378 \uC0AC\uC6A9: \uD638\uCD9C {calls}\uD68C \xB7 {sides} \uD1A0\uD070{cached}", "NMOS model use: {calls} \xB7 {sides} tokens{cached}"],
    "usage.calls": ["NMOS \uBAA8\uB378 \uC0AC\uC6A9: \uD638\uCD9C {calls}\uD68C", "NMOS model use: {calls}"],
    "usage.cached_side": ["\uCE90\uC2DC \uC785\uB825 {n} \uD1A0\uD070", "{n} cached input tokens"],
    "usage.input": ["\uC785\uB825 {n}", "{n} input"],
    "usage.output": ["\uCD9C\uB825 {n}", "{n} output"],
    "usage.cached": [" (\uC785\uB825 \uC911 \uCE90\uC2DC {n})", " ({n} of the input cached)"],
    "usage.partial": [" \xB7 {calls}\uD68C \uC911 {r}\uD68C\uB9CC \uBCF4\uACE0\uB428", " \xB7 {r} of {calls} reported"],
    "usage.unreported": [
      "NMOS \uBAA8\uB378 \uC0AC\uC6A9: \uD638\uCD9C {calls}\uD68C (\uC81C\uACF5\uC790\uAC00 \uD1A0\uD070\uC744 \uBCF4\uACE0\uD558\uC9C0 \uC54A\uC74C)",
      "NMOS model use: {calls} (the provider reported no tokens)"
    ],
    "usage.none": ["NMOS \uBAA8\uB378 \uC0AC\uC6A9: \uC544\uC9C1 \uAE30\uB85D \uC5C6\uC74C", "NMOS model use: none recorded yet"],
    "usage.older_only": [
      "NMOS \uBAA8\uB378 \uC0AC\uC6A9: \uC774\uC804 \uBC84\uC804\uC5D0\uC11C \uB9CC\uB4E0 \uAE30\uC5B5\uC774\uB77C \uC0AC\uC6A9\uB7C9\uC774 \uAE30\uB85D\uB418\uC9C0 \uC54A\uC558\uC74C",
      "NMOS model use: not recorded (this memory was made by an older version)"
    ],
    "usage.older": [" \xB7 \uC774\uC804 \uBC84\uC804 \uACB0\uACFC {n}\uAC1C\uB294 \uAE30\uB85D \uC5C6\uC74C", " \xB7 {n} results from an older version not recorded"],
    "chat.turn_on": ["\uC774 \uCC44\uD305\uC5D0\uC11C \uB2E4\uC2DC \uCF1C\uAE30", "Turn back on for this chat"],
    "chat.switched_off": [
      "\uC774 \uCC44\uD305\uC5D0\uC11C NMOS\uB97C \uAED0\uC2B5\uB2C8\uB2E4. \uC0AC\uC774\uB4DC\uCE74\uB85C \uBCF4\uB0B4\uC9C0 \uC54A\uACE0 \uAE30\uC5B5\uB3C4 \uB123\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4. \uC774\uBBF8 \uC313\uC778 \uAE30\uC5B5\uC740 \uADF8\uB300\uB85C\uC785\uB2C8\uB2E4.",
      "NMOS is off for this chat: nothing of it goes to the sidecar and no memory goes in. What is already remembered is kept."
    ],
    "chat.switched_on": [
      "\uC774 \uCC44\uD305\uC5D0\uC11C NMOS\uB97C \uB2E4\uC2DC \uCF30\uC2B5\uB2C8\uB2E4. \uB2E4\uC74C \uC0DD\uC131\uBD80\uD130 \uAE30\uC5B5\uC744 \uB123\uC2B5\uB2C8\uB2E4.",
      "NMOS is back on for this chat. Memory goes in from the next generation."
    ],
    "chat.switched_on_all_off": [
      "\uC774 \uCC44\uD305\uC5D0\uC11C NMOS\uB97C \uB2E4\uC2DC \uCF30\uC9C0\uB9CC, NMOS\uAC00 \uBAA8\uB4E0 \uCC44\uD305\uC5D0\uC11C \uAEBC\uC838 \uC788\uC5B4(\uC124\uC815 \uD0ED) \uAE30\uC5B5\uC744 \uB123\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
      "NMOS is back on for this chat, but it is off for every chat (Settings tab), so no memory goes in."
    ],
    "feature.state": ["\uC0C1\uD0DC\uCC3D", "Status window"],
    "feature.extraction": ["\uC0AC\uC2E4 \uCD94\uCD9C", "Fact extraction"],
    "feature.vectors": ["\uC758\uBBF8 \uAC80\uC0C9", "Semantic recall"],
    "on": ["\uCF1C\uC9D0", "on"],
    "off": ["\uAEBC\uC9D0", "off"],
    "status.last": ["\uB9C8\uC9C0\uB9C9 \uC694\uCCAD", "Last request"],
    "status.none": ["\uC544\uC9C1 \uC694\uCCAD\uC774 \uC5C6\uC2B5\uB2C8\uB2E4. \uCC44\uD305\uC5D0\uC11C \uBA54\uC2DC\uC9C0\uB97C \uBCF4\uB0B4 \uBCF4\uC138\uC694.", "No request yet. Send a message in a chat."],
    "status.ago": ["{n}\uCD08 \uC804", "{n}s ago"],
    "status.packet": ["\uB123\uC740 \uAE30\uC5B5 \uBCF4\uAE30", "Show the injected memory"],
    "deadline.over.title": ["\u26A0 \uAE30\uC5B5\uC774 \uC81C\uD55C \uC2DC\uAC04\uC5D0 \uAC78\uB838\uC2B5\uB2C8\uB2E4", "\u26A0 Memory missed the deadline"],
    "deadline.over": [
      "\uB9C8\uC9C0\uB9C9 \uC694\uCCAD\uC740 \uAE30\uC5B5\uC744 \uC900\uBE44\uD558\uB294 \uB370 \uC81C\uD55C \uC2DC\uAC04 {d}ms\uB97C \uB118\uACA8{took} \uAE30\uC5B5 \uC5C6\uC774 \uBCF4\uB0C8\uC2B5\uB2C8\uB2E4. \uC124\uC815 \uD0ED\uC5D0\uC11C \uC81C\uD55C \uC2DC\uAC04(ms)\uC744 {s} \uC815\uB3C4\uB85C \uC62C\uB824 \uBCF4\uC138\uC694. \uB298\uB9B0 \uB9CC\uD07C \uB2F5\uC7A5 \uC2DC\uC791\uC774 \uB2A6\uC5B4\uC9C8 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
      "The last request needed more than its {d} ms deadline to prepare memory{took} and went without it. Raise Deadline (ms) in the Settings tab to about {s}. Replies may start that much later."
    ],
    "deadline.near.title": ["\uC81C\uD55C \uC2DC\uAC04\uC5D0 \uAC00\uAE5D\uC2B5\uB2C8\uB2E4", "Close to the deadline"],
    "deadline.near": [
      "\uB9C8\uC9C0\uB9C9 \uC694\uCCAD\uC740 \uC81C\uD55C \uC2DC\uAC04 {d}ms \uC911 {n}ms\uB97C \uC37C\uC2B5\uB2C8\uB2E4. \uCC44\uD305\uC774 \uB354 \uAE38\uC5B4\uC9C0\uBA74 \uAE30\uC5B5\uC774 \uBE60\uC9C8 \uC218 \uC788\uC73C\uB2C8, \uC124\uC815 \uD0ED\uC5D0\uC11C \uC81C\uD55C \uC2DC\uAC04(ms)\uC744 {s} \uC815\uB3C4\uB85C \uC62C\uB824 \uB450\uC138\uC694.",
      "The last request used {n} ms of its {d} ms deadline. As the chat grows, memory may start to miss it: raise Deadline (ms) in the Settings tab to about {s}."
    ],
    "vectors.title": ["\uAE30\uC5B5\uC744 \uC758\uBBF8 \uAC80\uC0C9 \uC5C6\uC774 \uCC3E\uC558\uC2B5\uB2C8\uB2E4", "Memory was recalled without semantic search"],
    "vectors.text": [
      "\uB9C8\uC9C0\uB9C9 \uC694\uCCAD\uC5D0\uC11C \uC784\uBCA0\uB529 \uBAA8\uB378\uC774 \uC81C\uB54C \uB2F5\uD558\uC9C0 \uC54A\uC558\uAC70\uB098 \uC624\uB958\uB97C \uB0B4\uC11C, \uAE30\uC5B5\uC744 \uB2E8\uC5B4\uAC00 \uACB9\uCE58\uB294 \uAC83\uC73C\uB85C\uB9CC \uCC3E\uC558\uC2B5\uB2C8\uB2E4. \uB9D0\uC744 \uBC14\uAFD4 \uC4F4 \uC61B \uC7A5\uBA74\uC740 \uC774\uB54C \uBE60\uC9C8 \uC218 \uC788\uC2B5\uB2C8\uB2E4. \uBA3C\uC800 \uC124\uC815 \uD0ED\uC758 \uC758\uBBF8 \uAC80\uC0C9 \uC784\uBCA0\uB529 \uC5F0\uACB0 \uD14C\uC2A4\uD2B8\uB85C \uC8FC\uC18C\uC640 \uD0A4\uB97C \uD655\uC778\uD558\uC138\uC694. \uBAA8\uB378\uC774 \uC26C\uB2E4\uAC00 \uB2E4\uC2DC \uC62C\uB77C\uC624\uB294 \uC911\uC774\uC5C8\uB2E4\uBA74(Ollama\uB294 5\uBD84 \uC26C\uBA74 \uB0B4\uB9BC) \uB2E4\uC74C \uC694\uCCAD\uC740 \uAD1C\uCC2E\uC2B5\uB2C8\uB2E4. \uC5F0\uACB0\uC740 \uB418\uB294\uB370 \uC790\uC8FC \uB728\uBA74 \uC784\uBCA0\uB529 \uBAA8\uB378\uC744 \uACC4\uC18D \uC62C\uB824 \uB450\uAC70\uB098(Ollama keep_alive) \uC124\uC815 \uD0ED \uAC80\uC0C9 \uC870\uC815\uC758 \uC758\uBBF8 \uAC80\uC0C9 \uB300\uAE30(ms)\uB97C 1000 \uC815\uB3C4\uB85C \uB298\uB824 \uC8FC\uC138\uC694.",
      "On the last request the embedding model did not answer in time or answered with an error, so memory was found by shared words only; an earlier scene in other words can be missed then. First check the address and key with the embedding connection test in the Settings tab. If the model was loading after a pause (Ollama unloads it after 5 minutes idle), the next request is fine. If it connects and this still shows often, keep the embedding model loaded (Ollama keep_alive) or raise Embedding wait (ms) under Recall tuning in the Settings tab to about 1000."
    ],
    "deadline.took": [" (\uC2E4\uC81C\uB85C\uB294 \uC57D {n}ms \uAC78\uB9BC)", " (it took about {n} ms)"],
    "status.plugin_mismatch": [
      "\uC774 \uD50C\uB7EC\uADF8\uC778(\uBE4C\uB4DC {mine})\uC774 \uC0AC\uC774\uB4DC\uCE74\uC758 \uD50C\uB7EC\uADF8\uC778(\uBE4C\uB4DC {theirs})\uACFC \uB2E4\uB985\uB2C8\uB2E4. \uC544\uB798 \uBC84\uD2BC\uC73C\uB85C \uC0AC\uC774\uB4DC\uCE74\uC640 \uAC19\uC740 \uBC84\uC804\uC758 \uD30C\uC77C\uC744 \uBC1B\uC544 \uAD50\uCCB4\uD558\uACE0 \uC0C8\uB85C \uACE0\uCE68\uD558\uC138\uC694.",
      "This plugin (build {mine}) differs from the sidecar's (build {theirs}). Get the file of the sidecar's version with the button below, replace the plugin with it and reload."
    ],
    "status.plugin_ok": ["\uD50C\uB7EC\uADF8\uC778 \uBE4C\uB4DC {b} \xB7 \uC0AC\uC774\uB4DC\uCE74\uC640 \uAC19\uC74C", "Plugin build {b} \xB7 matches the sidecar"],
    // The host registers the request hook only with the "replace content" permission and remembers a denial silently.
    "status.no_requests": [
      '\uC774 \uD398\uC774\uC9C0\uB97C \uC5F0 \uB4A4 NMOS\uAC00 \uBC1B\uC740 \uCC44\uD305 \uC694\uCCAD\uC774 \uC544\uC9C1 \uC5C6\uC2B5\uB2C8\uB2E4. \uCC44\uD305\uC744 \uBCF4\uB0C8\uB294\uB370\uB3C4 \uC774\uB300\uB85C\uB77C\uBA74 PocketRisu\uAC00 "\uB0B4\uC6A9 \uAD50\uCCB4" \uAD8C\uD55C \uAC70\uC808\uC744 \uAE30\uC5B5\uD558\uACE0 \uC788\uC744 \uC218 \uC788\uC2B5\uB2C8\uB2E4: \uC124\uC815 \u2192 \uD50C\uB7EC\uADF8\uC778 \u2192 NMOS \uC904 \uBA54\uB274 \u2192 \uAD8C\uD55C \uC751\uB2F5 \uCD08\uAE30\uD654, \uC0C8\uB85C \uACE0\uCE68 \uD6C4 \uC608.',
      'No chat request has reached NMOS since this page opened. If you have sent one, PocketRisu may remember a denied "replace content" permission: Settings \u2192 Plugin \u2192 the NMOS row menu \u2192 reset permission responses, reload, and answer Yes.'
    ],
    "budget.title": ["\uAE30\uC5B5 {c}\uC904\uC774 \uC790\uB9AC\uAC00 \uC5C6\uC5B4 \uBE60\uC84C\uC2B5\uB2C8\uB2E4", "{c} memory lines did not fit"],
    "budget.text": [
      "\uB9C8\uC9C0\uB9C9 \uC751\uB2F5\uC5D0\uC11C \uCC3E\uC740 \uAE30\uC5B5 {m}\uC904 \uC911 {c}\uC904\uC774 \uAE30\uC5B5 \uC608\uC0B0({b}\uD1A0\uD070)\uC5D0 \uB4E4\uC5B4\uAC00\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4. \uC608\uC0B0\uC744 {s}\uC73C\uB85C \uC62C\uB9AC\uBA74 \uBAA8\uB450 \uB4E4\uC5B4\uAC11\uB2C8\uB2E4. \uC62C\uB9B0 \uB9CC\uD07C({d}\uD1A0\uD070) PocketRisu\uC758 \uCD5C\uB300 \uCEE8\uD14D\uC2A4\uD2B8\uB3C4 \uC904\uC5EC \uC8FC\uC138\uC694.",
      "The last reply found {m} memory lines and {c} did not fit the memory budget ({b} tokens). A budget of {s} holds them all. Lower PocketRisu's max context by the same amount ({d} tokens)."
    ],
    "budget.text_more": [
      "\uB9C8\uC9C0\uB9C9 \uC751\uB2F5\uC5D0\uC11C \uCC3E\uC740 \uAE30\uC5B5 {m}\uC904 \uC911 {c}\uC904\uC774 \uAE30\uC5B5 \uC608\uC0B0({b}\uD1A0\uD070)\uC5D0 \uB4E4\uC5B4\uAC00\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4. {s}\uC73C\uB85C \uC62C\uB9AC\uBA74 \uB354 \uB4E4\uC5B4\uAC00\uC9C0\uB9CC \uC804\uBD80\uB294 \uC544\uB2D9\uB2C8\uB2E4. \uC62C\uB9B0 \uB9CC\uD07C({d}\uD1A0\uD070) PocketRisu\uC758 \uCD5C\uB300 \uCEE8\uD14D\uC2A4\uD2B8\uB3C4 \uC904\uC5EC \uC8FC\uC138\uC694.",
      "The last reply found {m} memory lines and {c} did not fit the memory budget ({b} tokens). {s} holds more of them, not all. Lower PocketRisu's max context by the same amount ({d} tokens)."
    ],
    "budget.apply": ["\uC608\uC0B0\uC744 {n}\uC73C\uB85C \uC62C\uB9AC\uAE30", "Raise the budget to {n}"],
    "budget.applied": [
      "\uAE30\uC5B5 \uC608\uC0B0\uC744 {n}\uC73C\uB85C \uBC14\uAFE8\uC2B5\uB2C8\uB2E4. \uB2E4\uC74C \uC751\uB2F5\uBD80\uD130 \uC801\uC6A9\uB429\uB2C8\uB2E4. PocketRisu \uC124\uC815\uC5D0\uC11C \uCD5C\uB300 \uCEE8\uD14D\uC2A4\uD2B8\uB97C {d}\uB9CC\uD07C \uC904\uC5EC \uC8FC\uC138\uC694.",
      "The memory budget is now {n}, from the next reply. Lower the max context in PocketRisu's settings by {d}."
    ],
    "deadline.open_settings": ["\uC124\uC815 \uD0ED \uC5F4\uAE30", "Open Settings"],
    "deadline.alert": [
      "NMOS: \uC774\uBC88 \uB2F5\uC7A5\uC740 \uAE30\uC5B5 \uC5C6\uC774 \uBCF4\uB0C8\uC2B5\uB2C8\uB2E4. \uAE30\uC5B5 \uC900\uBE44\uAC00 \uC81C\uD55C \uC2DC\uAC04 {d}ms\uB97C \uB118\uACBC\uC2B5\uB2C8\uB2E4{took}. NMOS \uD328\uB110 \u2192 \uC124\uC815 \uD0ED \u2192 \uC81C\uD55C \uC2DC\uAC04(ms)\uC744 {s} \uC815\uB3C4\uB85C \uC62C\uB824 \uBCF4\uC138\uC694. (\uC774 \uC54C\uB9BC\uC740 \uD398\uC774\uC9C0\uB97C \uC0C8\uB85C \uC5F4 \uB54C\uAE4C\uC9C0 \uB2E4\uC2DC \uB728\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.)",
      "NMOS: this reply went without memory: preparing it took longer than the {d} ms deadline{took}. In the NMOS panel, Settings tab, raise Deadline (ms) to about {s}. (This notice does not show again until the page is reloaded.)"
    ],
    "outcome.injected": ["\uAE30\uC5B5 {n}\uC790\uB97C \uB123\uC5C8\uC2B5\uB2C8\uB2E4", "Injected {n} characters of memory"],
    "outcome.nothing": ["\uAD00\uB828\uB41C \uAE30\uC5B5\uC774 \uC5C6\uC5C8\uC2B5\uB2C8\uB2E4", "Nothing relevant to inject"],
    "outcome.failed": ["\uAC74\uB108\uB700 (\uC6D0\uB798 \uC694\uCCAD\uC740 \uADF8\uB300\uB85C \uBCF4\uB0C4)", "Skipped (the request went out unchanged)"],
    "outcome.skipped": [
      "\uAC74\uB108\uB700: \uC774\uBC88 \uBA54\uC2DC\uC9C0\uB97C \uD504\uB86C\uD504\uD2B8\uC5D0\uC11C \uCC3E\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4 (\uC6D0\uB798 \uC694\uCCAD\uC740 \uADF8\uB300\uB85C \uBCF4\uB0C4)",
      "Skipped: this message was not found in the prompt (the request went out unchanged)"
    ],
    // inspector view
    "insp.loading": ["\uC778\uC2A4\uD399\uD130\uB97C \uBD88\uB7EC\uC624\uB294 \uC911\u2026", "Loading the inspector\u2026"],
    "insp.back": ["\u2190 \uB4A4\uB85C", "\u2190 Back"],
    "tl.canon": ["\uC124\uC815(canon)\uC5D0\uC11C \uC2DC\uC791\uD55C \uAC12\uC774\uC5D0\uC694. \uC774\uC57C\uAE30\uAC00 \uBC14\uAFB8\uBA74 \uADF8\uCABD\uC774 \uC774\uACA8\uC694.", "Starts from the setting (canon); the story wins when it says otherwise."],
    "tl.owner": ["\uC624\uB108\uAC00 \uACE0\uCE5C \uAC12\uC774\uC5D0\uC694.", "The owner's version."],
    "insp.browser": ["\uBE0C\uB77C\uC6B0\uC800\uC5D0\uC11C \uC9C1\uC811 \uC5F4 \uC218\uB3C4 \uC788\uC2B5\uB2C8\uB2E4: {url}", "Also available in a browser: {url}"],
    "act.history": ["\uACFC\uAC70 \uC804\uCCB4 \uCD94\uCD9C", "Extract all history"],
    "act.retry": ["\uC2E4\uD328\uD55C \uC791\uC5C5 \uB2E4\uC2DC \uC2DC\uB3C4", "Retry failed"],
    "act.retry_done": ["\uC2E4\uD328\uD55C \uC791\uC5C5 {n}\uAC1C\uB97C \uB2E4\uC2DC \uB3CC\uB9BD\uB2C8\uB2E4.", "Running {n} failed jobs again."],
    "act.retry_none": ["\uB2E4\uC2DC \uB3CC\uB9B4 \uC2E4\uD328\uD55C \uC791\uC5C5\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.", "No failed job to retry."],
    "act.rebuild": ["\uAE30\uC5B5 \uC7AC\uAD6C\uCD95", "Rebuild memory"],
    "act.rebuild_confirm": ["\uD55C \uBC88 \uB354 \uB204\uB974\uBA74 \uC7AC\uAD6C\uCD95\uD569\uB2C8\uB2E4", "Click again to rebuild"],
    "act.delete": ["\uB300\uD654 \uC0AD\uC81C", "Delete conversation"],
    "act.delete_confirm": ["\uD55C \uBC88 \uB354 \uB204\uB974\uBA74 \uC601\uAD6C \uC0AD\uC81C\uD569\uB2C8\uB2E4", "Click again to delete for good"],
    "act.sub": [
      "\uC2E4\uD328\uD55C \uC791\uC5C5 \uB2E4\uC2DC \uC2DC\uB3C4: \uC774 \uCC44\uD305\uC5D0\uC11C \uC2E4\uD328\uB85C \uB05D\uB09C \uC791\uC5C5\uB9CC \uB2E4\uC2DC \uB3CC\uB9BD\uB2C8\uB2E4(\uADF8\uB9CC\uD07C \uBAA8\uB378\uC744 \uD638\uCD9C\uD569\uB2C8\uB2E4). \uC2E4\uD328\uAC00 \uC788\uC744 \uB54C\uB9CC \uBCF4\uC785\uB2C8\uB2E4. \uACFC\uAC70 \uC804\uCCB4 \uCD94\uCD9C: \uCC98\uC74C \uC5F0\uACB0\uD560 \uB54C \uAC74\uB108\uB6F4 \uC774 \uCC44\uD305\uC758 \uC774\uC804 \uD134\uAE4C\uC9C0 \uC0AC\uC2E4\uC744 \uCD94\uCD9C\uD558\uACE0 \uC784\uBCA0\uB529\uD569\uB2C8\uB2E4. \uAE30\uC5B5 \uC7AC\uAD6C\uCD95: \uC774 \uCC44\uD305\uC758 \uC0AC\uC2E4\uC744 \uBC84\uB9AC\uACE0 \uBAA8\uB4E0 \uD134\uC744 \uB2E4\uC2DC \uCD94\uCD9C\uD569\uB2C8\uB2E4(\uC6D0\uBB38\uC740 \uADF8\uB300\uB85C). \uC720\uB8CC API\uB294 \uD134\uB9C8\uB2E4 \uBE44\uC6A9\uC774 \uB4ED\uB2C8\uB2E4. \uB300\uD654 \uC0AD\uC81C: NMOS\uC5D0 \uC800\uC7A5\uB41C \uC774 \uCC44\uD305\uC758 \uBAA8\uB4E0 \uAE30\uB85D(\uC6D0\uBB38 \uD3EC\uD568)\uC744 \uC9C0\uC6C1\uB2C8\uB2E4. \uB418\uB3CC\uB9B4 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4. PocketRisu\uC758 \uCC44\uD305\uC740 \uADF8\uB300\uB85C\uC774\uACE0, \uADF8 \uCC44\uD305\uC5D0\uC11C \uB2E4\uC2DC \uC0DD\uC131\uD558\uBA74 \uC0C8 \uB300\uD654\uB85C \uCC98\uC74C\uBD80\uD130 \uAE30\uB85D\uB429\uB2C8\uB2E4.",
      "Retry failed: run only this chat's jobs that failed for good again (as many model calls). Shown only when something failed. Extract all history: extract facts and embeddings for the older turns of this chat that the first sync skipped. Rebuild memory: discard this chat's facts and extract every turn again (raw messages stay). Paid APIs cost money per turn. Delete conversation: delete everything NMOS stored for this chat, raw messages included. This cannot be undone. The chat in PocketRisu stays; generating in it again records it as a new conversation from scratch."
    ],
    "act.help": ["\uC774 \uBC84\uD2BC\uB4E4\uC740?", "What do these do?"],
    "act.working": ["\uC694\uCCAD \uC911\u2026", "Requesting\u2026"],
    "act.history_done": ["\uD134 {t}\uAC1C \uCD94\uCD9C\uACFC \uBA54\uC2DC\uC9C0 {m}\uAC1C \uC784\uBCA0\uB529\uC744 \uBC31\uADF8\uB77C\uC6B4\uB4DC\uC5D0 \uB123\uC5C8\uC2B5\uB2C8\uB2E4.", "Queued {t} turns for extraction and {m} messages for embedding."],
    "act.history_none": ["\uC774\uBBF8 \uC804\uBD80 \uCC98\uB9AC\uB418\uC5C8\uAC70\uB098 \uCC98\uB9AC \uC911\uC785\uB2C8\uB2E4.", "Everything is already processed or queued."],
    "act.rebuild_done": [
      "\uCD94\uCD9C {d}\uAC74\uC744 \uBC84\uB9AC\uACE0 \uD134 {t}\uAC1C\uB97C \uB2E4\uC2DC \uCD94\uCD9C\uD569\uB2C8\uB2E4. \uB05D\uB0A0 \uB54C\uAE4C\uC9C0 \uC774 \uCC44\uD305\uC758 \uC0AC\uC2E4\uC774 \uBE44\uC5B4 \uC788\uC744 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
      "Discarded {d} extractions; {t} turns are extracted again. Facts of this chat may be missing until then."
    ],
    // export (ADR 0050)
    "exp.chat": ["\uC774 \uB300\uD654 \uB0B4\uBCF4\uB0B4\uAE30", "Export this chat"],
    // notes for the author's note (PHASE-50)
    "notes.open": ["\uC791\uAC00\uC758 \uB178\uD2B8\uC6A9 \uC815\uB9AC", "For the author's note"],
    "chats.search": ["\uC774\uB984\uC774\uB098 \uCE90\uB9AD\uD130\uB85C \uCC3E\uAE30", "Search by name or character"],
    // the panel's shell (PHASE-52): home and the settings groups
    "home": ["\u2190 NMOS", "\u2190 NMOS"],
    "grp.back": ["\u2190 \uC124\uC815", "\u2190 Settings"],
    "grp.connection": ["\uC5F0\uACB0", "Connection"],
    "grp.connection_sub": ["\uC0AC\uC774\uB4DC\uCE74 \uC8FC\uC18C \xB7 \uD1A0\uD070 \xB7 \uC5F0\uACB0 \uC0C1\uD0DC \xB7 \uC774 \uCC44\uD305 \uCF1C\uAE30/\uB044\uAE30", "Sidecar address \xB7 token \xB7 status \xB7 this chat on or off"],
    "grp.models": ["\uBAA8\uB378", "Models"],
    "grp.models_sub": ["\uC0AC\uC2E4 \uCD94\uCD9C \uBAA8\uB378 \xB7 \uAC80\uC0C9\uC6A9 \uC784\uBCA0\uB529", "Fact extraction \xB7 search embeddings"],
    "grp.memory": ["\uAE30\uC5B5 \uB3D9\uC791", "How memory works"],
    "grp.memory_sub": ["\uAC80\uC0C9 \uAE30\uC900 \xB7 \uB123\uB294 \uC591", "Recall thresholds \xB7 how much goes in"],
    "grp.chat": ["\uC774 \uCC44\uD305", "This chat"],
    "grp.chat_sub": ["\uAE30\uC5B5 \uBAA8\uB4DC \xB7 \uC774 \uCC44\uD305\uC758 \uC0C1\uD0DC\uCC3D \xB7 \uACFC\uAC70 \uCD94\uCD9C \xB7 \uC7AC\uAD6C\uCD95 \xB7 \uB0B4\uBCF4\uB0B4\uAE30 \xB7 \uC0AD\uC81C", "Memory mode \xB7 status windows \xB7 history \xB7 rebuild \xB7 export \xB7 delete"],
    "grp.chat_none": ["NMOS\uAC00 \uC544\uC9C1 \uC774 \uCC44\uD305\uC744 \uBAB0\uB77C\uC694. \uCC44\uD305\uC5D0\uC11C \uD55C \uBC88 \uB2F5\uC7A5\uC744 \uBC1B\uC73C\uBA74 \uC0DD\uACA8\uC694.", "NMOS does not know this chat yet; it does after one reply."],
    "grp.rules": ["\uC0C1\uD0DC\uCC3D \uADDC\uCE59", "Status window rules"],
    "grp.rules_sub": ["\uCE74\uB4DC\uBCC4 \uADDC\uCE59 \xB7 \uC9C1\uC811 \uC4F4 \uADDC\uCE59", "Rules per card \xB7 hand-written rules"],
    "grp.display": ["\uD654\uBA74", "Display"],
    "grp.display_sub": ["\uCC44\uD305 \uD654\uBA74\uC758 \uC9C4\uD589 \uD45C\uC2DC", "The progress display on the chat screen"],
    "grp.backup": ["\uBC31\uC5C5", "Backup"],
    "grp.backup_sub": ["\uC804\uCCB4 \uB0B4\uBCF4\uB0B4\uAE30 \xB7 \uBCF5\uC6D0", "Export everything \xB7 restore"],
    "notes.title": ["\uC791\uAC00\uC758 \uB178\uD2B8\uC6A9 \uC815\uB9AC", "For the author's note"],
    "notes.part.diverged": ["\uC124\uC815\uACFC \uB2EC\uB77C\uC9C4 \uAC83", "diverged from the setting"],
    "notes.part.chronicle": ["\uC5F0\uB300\uAE30", "chronicle"],
    "notes.part.changed": ["\uC124\uC815 \uBCC0\uACBD\uC810", "changed from the setting"],
    "notes.part.address": ["\uD638\uCE6D\xB7\uAD00\uACC4", "address and standing"],
    "notes.part.custom": ["\uCEE4\uC2A4\uD140", "custom"],
    "notes.sub": [
      "\uC774 \uCC44\uD305\uC758 \uAE30\uC5B5\uC73C\uB85C \uC791\uAC00\uC758 \uB178\uD2B8\uC5D0 \uBD99\uC5EC\uB123\uC744 \uAE00 \uD558\uB098\uB97C \uB9CC\uB4ED\uB2C8\uB2E4. \uBAA8\uB378\uC774 \uC77D\uAE30 \uC88B\uAC8C \uC601\uC5B4 \uB9C8\uD06C\uB2E4\uC6B4\uC73C\uB85C \uC4F0\uACE0, \uC774\uB984\uACFC \uD638\uCE6D\uC740 \uCC44\uD305\uC5D0 \uC801\uD78C \uADF8\uB300\uB85C \uB461\uB2C8\uB2E4. \uACB0\uACFC\uB97C [NMOS note \u2026] \uC904\uBD80\uD130 [/NMOS note] \uC904\uAE4C\uC9C0 \uD1B5\uC9F8\uB85C \uBCF5\uC0AC\uD574 \uC791\uAC00\uC758 \uB178\uD2B8\uC5D0 \uBD99\uC5EC\uB123\uC73C\uC138\uC694(\uC804\uC5D0 \uBD99\uC778 \uAC83\uC774 \uC788\uC73C\uBA74 \uADF8 \uBE14\uB85D\uC744 \uC9C0\uC6B0\uACE0 \uC0C8\uB85C \uBD99\uC774\uBA74 \uB429\uB2C8\uB2E4). \uADF8\uB798\uC57C NMOS\uAC00 \uADF8 \uBD80\uBD84\uC744 \uC6D0\uC804(\uC124\uC815)\uC73C\uB85C \uC77D\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4. \uC791\uAC00\uC758 \uB178\uD2B8\uB294 \uB9E4 \uC694\uCCAD\uC5D0 \uD568\uAED8 \uAC00\uBBC0\uB85C, \uBD99\uC5EC\uB123\uC740 \uAE38\uC774\uB9CC\uD07C \uB9E4 \uD134 \uD1A0\uD070\uC774 \uB4ED\uB2C8\uB2E4. \uC124\uC815\uACFC \uB2EC\uB77C\uC9C4 \uAC83, \uC5F0\uB300\uAE30, \uCEE4\uC2A4\uD140\uC740 \uB9CC\uB4E4 \uB54C\uB9C8\uB2E4 \uBAA8\uB378\uC744 \uD55C \uBC88\uC529 \uBD80\uB985\uB2C8\uB2E4.",
      "Makes one text from this chat's memory to paste into its author's note: English Markdown, which the model reads well, with names and forms of address as the chat writes them. Copy it whole, from the [NMOS note \u2026] line to the [/NMOS note] line, into the author's note (replace the block you pasted before, if any), so NMOS does not read it as the setting. The note goes with every request, so what you paste is paid on every turn. Diverged from the setting, the chronicle and the custom part each call the model once when made."
    ],
    "notes.diverged": ["\uC124\uC815\uACFC \uB2EC\uB77C\uC9C4 \uAC83: \uCE74\uB4DC\xB7\uB85C\uC5B4\uBD81\uACFC \uC9C0\uAE08 \uC774\uC57C\uAE30\uAC00 \uC5B4\uAE0B\uB09C \uACF3 (\uBAA8\uB378 1\uD68C \uD638\uCD9C)", "Diverged from the setting: where the story no longer fits the card or lorebook (one model call)"],
    "notes.entries": ["\uB85C\uC5B4\uBD81 {n}\uAC1C \uD56D\uBAA9\uACFC \uBE44\uAD50, {m}\uAC1C\uB294 \uAE38\uC774 \uC0C1\uD55C\uC73C\uB85C \uC81C\uC678", "{n} lorebook entries compared, {m} left out for length"],
    "notes.chronicle": ["\uC5F0\uB300\uAE30: \uC9C0\uAE08\uAE4C\uC9C0\uC758 \uC0AC\uAC74\uACFC \uACB0\uACFC (\uBAA8\uB378 1\uD68C \uD638\uCD9C)", "Chronicle: the events so far and how they ended (one model call)"],
    "notes.address": ["\uD638\uCE6D\xB7\uAD00\uACC4: \uC11C\uB85C \uBB50\uB77C\uACE0 \uBD80\uB974\uACE0 \uC5B4\uB5A4 \uC0AC\uC774\uC778\uC9C0", "Address and standing: what they call each other and how they stand"],
    // PHASE-56: a part the owner words
    "notes.custom": ["\uCEE4\uC2A4\uD140: \uB0B4\uAC00 \uC4F4 \uD504\uB86C\uD504\uD2B8\uB300\uB85C (\uBAA8\uB378 1\uD68C \uD638\uCD9C)", "Custom: written as your prompt asks (one model call)"],
    "notes.custom_prompt": ["\uCEE4\uC2A4\uD140 \uD504\uB86C\uD504\uD2B8", "Custom prompt"],
    "notes.custom_placeholder": [
      "\uC608: \uC9C0\uAE08 \uC7A5\uBA74\uC5D0 \uC788\uB294 \uC778\uBB3C\uB4E4\uC758 \uC637\uCC28\uB9BC\uACFC \uC18C\uC9C0\uD488\uC744 \uC778\uBB3C\uBCC4\uB85C \uC815\uB9AC\uD574 \uC918.",
      "e.g. List what each character in the current scene is wearing and carrying."
    ],
    "notes.custom_count": ["{n} / {max}\uC790 \xB7 \uBAA8\uB4E0 \uCC44\uD305\uC5D0 \uAC19\uC740 \uD504\uB86C\uD504\uD2B8\uAC00 \uC800\uC7A5\uB429\uB2C8\uB2E4", "{n} / {max} characters \xB7 one prompt, saved for every chat"],
    "notes.custom_setting": ["\uC124\uC815(\uCE74\uB4DC\xB7\uB85C\uC5B4\uBD81)\uB3C4 \uB123\uAE30", "Include the setting (card, lorebook)"],
    "notes.custom_setting_sub": [
      "\uCF1C\uBA74 \uCE74\uB4DC\xB7\uD398\uB974\uC18C\uB098\xB7\uAD00\uB828 \uB85C\uC5B4\uBD81 \uD56D\uBAA9\uC774 \uD568\uAED8 \uB4E4\uC5B4\uAC00 \uC785\uB825\uC774 \uCD5C\uB300 60,000\uC790 \uB298\uC5B4\uB0A9\uB2C8\uB2E4.",
      "With it on, the card, the persona and the related lorebook entries go in too: up to 60,000 more characters."
    ],
    "notes.custom_unchecked": [
      "\uCEE4\uC2A4\uD140 \uD30C\uD2B8\uB294 \uD504\uB86C\uD504\uD2B8\uB300\uB85C \uC790\uC720\uB86D\uAC8C \uC4F0\uC5EC\uC11C NMOS\uAC00 \uC774\uC57C\uAE30\uC640 \uD55C \uC904\uC529 \uB300\uC870\uD558\uC9C0 \uBABB\uD569\uB2C8\uB2E4. \uBD99\uC5EC\uB123\uAE30 \uC804\uC5D0 \uAF2D \uC77D\uC5B4 \uBCF4\uC138\uC694.",
      "The custom part is written freely from your prompt, so NMOS cannot check it line by line against the story. Read it before you paste it."
    ],
    "notes.custom_empty": ["\uCEE4\uC2A4\uD140 \uD504\uB86C\uD504\uD2B8\uB97C \uC801\uC5B4 \uC8FC\uC138\uC694.", "Write a custom prompt."],
    "notes.custom_unsaved": ["(\uD504\uB86C\uD504\uD2B8\uB294 \uC800\uC7A5\uD558\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4. \uB2E4\uC74C\uC5D0 \uB2E4\uC2DC \uC801\uC5B4\uC57C \uD560 \uC218 \uC788\uC5B4\uC694.)", "(The prompt could not be saved; you may need to write it again next time.)"],
    "notes.unchecked": ["NMOS\uAC00 \uAC80\uC99D\uD558\uC9C0 \uC54A\uC74C, \uC77D\uACE0 \uBD99\uC5EC\uB123\uC73C\uC138\uC694", "not checked by NMOS, read it before pasting"],
    "notes.part_no_model": ["{part}: \uCD94\uCD9C \uBAA8\uB378\uC774 \uC124\uC815\uB418\uC9C0 \uC54A\uC544 \uB9CC\uB4E4\uC9C0 \uBABB\uD568", "{part}: not made, no extraction model is configured"],
    "notes.part_failed": ["{part}: \uBAA8\uB378 \uB2F5\uC744 \uC4F8 \uC218 \uC5C6\uC5B4 \uBE90\uC74C (\uB2E4\uC2DC \uB9CC\uB4E4\uBA74 \uB2E4\uC2DC \uBD80\uB985\uB2C8\uB2E4)", "{part}: left out, the model's reply could not be used (Make calls it again)"],
    "notes.part_held": ["{part}: \uBE44\uBC00\uC774 \uB4E4\uC5B4\uAC00\uC11C \uBE90\uC74C (\uB2E4\uC2DC \uB9CC\uB4E4\uBA74 \uB2E4\uC2DC \uBD80\uB985\uB2C8\uB2E4)", "{part}: left out, it told a secret (Make calls it again)"],
    "notes.length": ["\uC5F0\uB300\uAE30\xB7\uCEE4\uC2A4\uD140 \uAE38\uC774", "Chronicle and custom length"],
    "notes.short": ["\uC9E7\uAC8C (3,000\uC790)", "Short (3,000 characters)"],
    "notes.long": ["\uAE38\uAC8C (6,000\uC790)", "Long (6,000 characters)"],
    "notes.secrets": ["\uBE44\uBC00 \uD3EC\uD568 (\uB204\uAC00 \uBAA8\uB974\uB294\uC9C0 \uD45C\uC2DC)", "Include secrets (marked with who does not know)"],
    "notes.secrets_warn": [
      "\uC791\uAC00\uC758 \uB178\uD2B8\uB294 \uBAA8\uB4E0 \uC7A5\uBA74\uC5D0 \uB4E4\uC5B4\uAC11\uB2C8\uB2E4. \uBE44\uBC00\uC744 \uB123\uC73C\uBA74 \uBAA8\uB974\uB294 \uCE90\uB9AD\uD130 \uC55E\uC5D0\uC11C \uBAA8\uB378\uC774 \uD758\uB9B4 \uC218 \uC788\uC5B4\uC694.",
      "The author's note reaches every scene. With secrets in it, the model can let one slip in front of a character it is kept from."
    ],
    "notes.make": ["\uB9CC\uB4E4\uAE30", "Make"],
    "notes.pick": ["\uD558\uB098 \uC774\uC0C1 \uACE0\uB974\uC138\uC694.", "Pick at least one."],
    "notes.done": ["\uB9CC\uB4E4\uC5C8\uC2B5\uB2C8\uB2E4. \uC544\uB798 \uC0C1\uC790\uB97C \uD1B5\uC9F8\uB85C \uBCF5\uC0AC\uD574 \uC791\uAC00\uC758 \uB178\uD2B8\uC5D0 \uBD99\uC5EC\uB123\uC73C\uC138\uC694.", "Done. Copy the box below, whole, into the author's note."],
    "notes.result": ["\uC791\uAC00\uC758 \uB178\uD2B8\uC5D0 \uBD99\uC5EC\uB123\uC744 \uAE00", "To paste into the author's note"],
    "notes.part_none": ["{part}: \uC801\uC744 \uAC83\uC774 \uC5C6\uC74C", "{part}: nothing to write"],
    "notes.part_no_scenes": ["{part}: \uC544\uC9C1 \uC7A5\uBA74 \uC694\uC57D\uC774 \uC5C6\uC74C (8\uD134\uB9C8\uB2E4 \uD558\uB098, \uADF8 \uB4A4 4\uD134\uC774 \uC9C0\uB098\uBA74 \uB9CC\uB4E4\uC5B4\uC9D0)", "{part}: no scene summary yet (one per 8 turns, made 4 turns later)"],
    "notes.part_made": ["{part}: {how}", "{part}: {how}"],
    "notes.stale": [
      '30\uD134 \uB118\uAC8C \uB2E4\uC2DC \uC5B8\uAE09\uB418\uC9C0 \uC54A\uC740 \uC5F4\uB9B0 \uC77C {n}\uAC1C\uB294 \uB123\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4. \uB05D\uB09C \uC77C\uC778\uC9C0\uB294 \uC778\uC2A4\uD399\uD130\uC758 "\uD655\uC778 \uD544\uC694"\uC5D0\uC11C \uD655\uC778\uD558\uACE0 \uB2EB\uC744 \uC218 \uC788\uC5B4\uC694.',
      'Left out {n} open threads not mentioned again for more than 30 turns. Check or close them under "Needs a look" in the Inspector.'
    ],
    "notes.copy": ["\uBCF5\uC0AC", "Copy"],
    "notes.copied": ["\uBCF5\uC0AC\uD588\uC2B5\uB2C8\uB2E4.", "Copied."],
    "notes.copy_hint": ["\uC5EC\uAE30\uC11C\uB294 \uC790\uB3D9 \uBCF5\uC0AC\uAC00 \uB9C9\uD600 \uC788\uC5B4\uC11C \uB0B4\uC6A9\uC744 \uC120\uD0DD\uD574 \uB450\uC5C8\uC2B5\uB2C8\uB2E4. \uC9C1\uC811 \uBCF5\uC0AC\uD574 \uC8FC\uC138\uC694.", "Copying is blocked here, so the text is selected: copy it yourself."],
    "notes.made_model": ["\uBAA8\uB378\uC774 \uC500", "written by the model"],
    "notes.made_assembled": ["\uBAA8\uB378 \uC5C6\uC774 \uC870\uB9BD (\uBAA8\uB378\uC774 \uC5C6\uAC70\uB098 \uB2F5\uC774 \uC4F8 \uC218 \uC5C6\uC5C8\uC74C)", "assembled without a model (no model, or its reply could not be used)"],
    "notes.made_facts": ["\uAE30\uC5B5\uC5D0\uC11C \uBC14\uB85C (\uD638\uCD9C \uC5C6\uC74C)", "straight from memory (no call)"],
    "notes.cached": ["\uC774\uC804\uACFC \uAC19\uC544\uC11C \uB2E4\uC2DC \uBD80\uB974\uC9C0 \uC54A\uC74C", "unchanged, not asked again"],
    "notes.held": ["\uBE44\uBC00 \uB54C\uBB38\uC5D0 \uBE80 \uC694\uC57D {n}\uAC1C", "{n} summaries left out for secrets"],
    "notes.chars": ["\uC804\uCCB4 {n}\uC790", "{n} characters in all"],
    "exp.title": ["\uB0B4\uBCF4\uB0B4\uAE30", "Export"],
    "exp.sub": [
      "NMOS\uAC00 \uAE30\uC5B5\uD558\uB294 \uBAA8\uB4E0 \uB300\uD654\uC640 \uC124\uC815(API \uD0A4\uB294 \uBE7C\uACE0)\uC744 .nmos.zip \uD30C\uC77C \uD558\uB098\uB85C \uC800\uC7A5\uD569\uB2C8\uB2E4. \uCC44\uD305 \uC6D0\uBB38\uC774 \uB4E4\uC5B4 \uC788\uC73C\uB2C8 \uCC44\uD305\uCC98\uB7FC \uBCF4\uAD00\uD558\uC138\uC694.",
      "Saves every conversation NMOS keeps and its settings (never an API key) as one .nmos.zip file. It holds the chat text: keep it as you keep the chat."
    ],
    "exp.embeddings": ["\uC784\uBCA0\uB529\uB3C4 \uB123\uAE30 (\uD30C\uC77C\uC774 \uCEE4\uC9C0\uC9C0\uB9CC \uBCF5\uC6D0 \uB4A4 \uB2E4\uC2DC \uACC4\uC0B0\uD558\uC9C0 \uC54A\uC74C)", "Include embeddings (a larger file, not recomputed after a restore)"],
    "exp.all": ["\uC804\uBD80 \uB0B4\uBCF4\uB0B4\uAE30", "Export everything"],
    "exp.working": ["\uD30C\uC77C\uC744 \uC900\uBE44\uD558\uB294 \uC911\u2026", "Preparing the file\u2026"],
    "exp.saved": ["{mb} MB\uB97C \uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4. \uBE0C\uB77C\uC6B0\uC800\uC758 \uB2E4\uC6B4\uB85C\uB4DC\uB97C \uD655\uC778\uD558\uC138\uC694.", "Saved {mb} MB. Check the browser's downloads."],
    // restore from the panel (PHASE-38)
    "rst.title": ["\uC544\uCE74\uC774\uBE0C\uC5D0\uC11C \uBCF5\uC6D0", "Restore from an archive"],
    "rst.sub": [
      "\uB0B4\uBCF4\uB0B8 .nmos.zip\uC744 \uC774 NMOS\uC5D0 \uB123\uC2B5\uB2C8\uB2E4. \uC774\uBBF8 \uC788\uB294 \uB300\uD654\uC640\uB294 \uD569\uCE58\uC9C0 \uC54A\uC544\uC694: \uADF8 \uB300\uD654\uAC00 \uC5EC\uAE30 \uC788\uC73C\uBA74 \uBCF5\uC6D0 \uC804\uCCB4\uB97C \uAC70\uBD80\uD569\uB2C8\uB2E4(\uBA3C\uC800 \uC778\uC2A4\uD399\uD130\uC5D0\uC11C \uC9C0\uC6B0\uC138\uC694). \uBCF5\uC6D0\uD558\uB294 \uB3D9\uC548\uC5D0\uB3C4 \uD68C\uC0C1\uC740 \uB418\uACE0, \uAE30\uC5B5 \uC800\uC7A5\uB9CC \uC7A0\uAE50 \uAE30\uB2E4\uB9BD\uB2C8\uB2E4.",
      "Puts an exported .nmos.zip into this NMOS. It never merges into a chat that is here: one of its chats here refuses the whole restore (delete it in the Inspector first). While it runs, recall goes on; saving memory waits briefly."
    ],
    "rst.pick": ["\uD30C\uC77C \uACE0\uB974\uAE30\u2026", "Choose a file\u2026"],
    "rst.insecure": [
      "\uC774 \uD398\uC774\uC9C0\uB294 \uBCF4\uC548 \uC5F0\uACB0\uC774 \uC544\uB2C8\uB77C\uC11C \uD30C\uC77C\uC744 \uD655\uC778\uD560 \uC218 \uC5C6\uC5B4\uC694. PocketRisu\uB97C HTTPS \uC8FC\uC18C\uB098 localhost\uB85C \uC5F4\uC5B4 \uC8FC\uC138\uC694.",
      "This page is not a secure context, so the file cannot be checked. Open PocketRisu over HTTPS or on localhost."
    ],
    "rst.uploading": ["\uC62C\uB9AC\uB294 \uC911\u2026 {pct}% ({sent} / {total} MB)", "Uploading\u2026 {pct}% ({sent} of {total} MB)"],
    "rst.checking": ["\uD30C\uC77C\uC744 \uAC80\uC0AC\uD558\uB294 \uC911\u2026", "Checking the file\u2026"],
    "rst.summary": ["{scope} \xB7 \uB300\uD654 {n}\uAC1C \xB7 NMOS {version} \xB7 {date}", "{scope} \xB7 {n} chats \xB7 NMOS {version} \xB7 {date}"],
    "rst.scope_install": ["\uC124\uCE58 \uC804\uCCB4", "The whole install"],
    "rst.scope_chats": ["\uACE0\uB978 \uB300\uD654", "Chosen chats"],
    "rst.here": ["\uC774\uBBF8 \uC788\uC74C", "already here"],
    "rst.no_character": ["\uCE90\uB9AD\uD130 \uC774\uB984 \uC5C6\uC74C", "no character name"],
    "rst.no_chat": ["\uC774\uB984 \uC5C6\uB294 \uB300\uD654", "untitled chat"],
    "rst.blocked": [
      "\uC774\uBBF8 \uC788\uB294 \uB300\uD654\uAC00 \uC788\uC5B4\uC11C \uBCF5\uC6D0\uD560 \uC218 \uC5C6\uC5B4\uC694. \uC778\uC2A4\uD399\uD130\uC5D0\uC11C \uADF8 \uB300\uD654\uB97C \uC9C0\uC6B4 \uB4A4 \uB2E4\uC2DC \uC62C\uB824 \uC8FC\uC138\uC694.",
      "Chats already here block the restore. Delete them in the Inspector, then upload the file again."
    ],
    "rst.settings": ["\uC0C8\uB85C \uB4E4\uC5B4\uC62C \uC124\uC815: {keys}", "Settings it adds: {keys}"],
    "rst.migrations": ["\uC61B NMOS\uC758 \uD30C\uC77C\uC774\uB77C \uBCF5\uC6D0\uD558\uBA70 \uC62C\uB9BD\uB2C8\uB2E4: {list}", "Made by an older NMOS; upgraded as it is restored: {list}"],
    "rst.restore": ["\uBCF5\uC6D0", "Restore"],
    "rst.cancel": ["\uCDE8\uC18C", "Cancel"],
    "rst.restoring": ["\uBCF5\uC6D0\uD558\uB294 \uC911\u2026", "Restoring\u2026"],
    "rst.done": ["\uBCF5\uC6D0\uD588\uC5B4\uC694: \uB300\uD654 {n}\uAC1C, \uC0C8\uB85C \uCC98\uB9AC\uD560 \uC791\uC5C5 {jobs}\uAC1C.", "Restored: {n} chats; {jobs} jobs queued."],
    "rst.refused": ["\uC774 \uD30C\uC77C\uC740 \uBCF5\uC6D0\uD560 \uC218 \uC5C6\uC5B4\uC694: {why}", "This file cannot be restored: {why}"],
    "rst.failed": ["\uBCF5\uC6D0\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694. \uC544\uBB34\uAC83\uB3C4 \uBC14\uB00C\uC9C0 \uC54A\uC558\uC5B4\uC694: {why}", "Not restored; nothing changed: {why}"],
    "act.delete_done": ["\uB300\uD654\uB97C \uC0AD\uC81C\uD588\uC2B5\uB2C8\uB2E4 (\uBA54\uC2DC\uC9C0 {m}\uAC1C\uC758 \uAE30\uB85D).", "Conversation deleted (records of {m} messages)."],
    "link.title": ["\uAC19\uC740 \uB300\uC0C1\uC73C\uB85C \uD569\uCE58\uAE30", "Same as another entity"],
    "link.sub": [
      "\uC774\uC57C\uAE30\uAC00 \uC2A4\uC2A4\uB85C \uC787\uC9C0 \uBABB\uD55C \uC774\uB984\uC744 \uC9C1\uC811 \uD569\uCE69\uB2C8\uB2E4(\uC608: \uC774\uB984 \uC5C6\uC774 \uBA3C\uC800 \uB098\uC628 \uC778\uBB3C\uACFC \uB098\uC911\uC5D0 \uC774\uB984\uC774 \uBC1D\uD600\uC9C4 \uC778\uBB3C). \uAE30\uC5B5 \uC7AC\uAD6C\uCD95\uC744 \uD574\uB3C4 \uC720\uC9C0\uB418\uACE0, \uC5B8\uC81C\uB4E0 \uD574\uC81C\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
      "Join names the story did not link on its own (e.g. someone shown without a name and named later). Kept across rebuilds; you can undo it at any time."
    ],
    "link.pick": ["\uAC19\uC740 \uB300\uC0C1", "Same as"],
    "link.join": ["\uD569\uCE58\uAE30", "Join"],
    "link.remove": ["\uD574\uC81C", "Undo"],
    "link.none": ["\uD569\uCE60 \uC218 \uC788\uB294 \uAC19\uC740 \uC885\uB958\uC758 \uB300\uC0C1\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.", "No other entity of this type."],
    "link.done": ['"{a}"\uC640(\uACFC) "{b}"\uB97C \uD569\uCCE4\uC2B5\uB2C8\uB2E4.', 'Joined "{a}" and "{b}".'],
    "link.removed": ["\uC5F0\uACB0\uC744 \uD574\uC81C\uD588\uC2B5\uB2C8\uB2E4.", "Link undone."],
    // owner repair (ADR 0044): buttons the panel puts on the inspector's lines
    "rp.thread_close": ["\uB2EB\uAE30", "Close"],
    "rp.thread_reopen": ["\uB2E4\uC2DC \uC5F4\uAE30", "Reopen"],
    "rp.secret_found_out": ["{n}: \uC54C\uAC8C \uB428", "{n}: found out"],
    "rp.secret_keep": ["{n}: \uC544\uC9C1 \uBAA8\uB984", "{n}: still kept"],
    "rp.fact_retract": ["\uCCA0\uD68C", "Retract"],
    "rp.fact_correct": ["\uC815\uC815({n})", "Correct {n}"],
    "rp.fact_lock": ["\uACE0\uC815", "Lock"],
    // a canon fact or a correction stays current against the story (ADR 0047)
    "rp.alias_join": ["\uD55C \uC0AC\uB78C\uC73C\uB85C \uC5F0\uACB0", "Link as one person"],
    // a held alias, linked by the owner (PHASE-29 Q5)
    "rp.fact_restore": ["\uBCF5\uC6D0", "Restore"],
    // a fact a re-extraction dropped, remembered at its turn again (PHASE-22 Q7)
    "rp.state_dismiss": ["\uAD1C\uCC2E\uC74C", "Dismiss"],
    // a status flag the owner looked at (PHASE-39 Q4)
    "rp.undo": ["\uB418\uB3CC\uB9AC\uAE30", "Undo"],
    "rp.undo_batch": ["\uC804\uBD80 \uB418\uB3CC\uB9AC\uAE30", "Undo all"],
    "rp.fact_correct_lock": ["\uC6D0\uC804 \uC815\uC815({n})", "Correct the setting {n}"],
    "bk.select": ["\uC77C\uAD04 \uCC98\uB9AC\uC5D0 \uB123\uAE30", "Select"],
    "bk.all": ["{k} \uC804\uBD80 \uC120\uD0DD ({n})", "Select all {k} ({n})"],
    "bk.apply": ["\uC120\uD0DD \uC801\uC6A9 ({n})", "Apply selected ({n})"],
    "bk.retract": ["\uC120\uD0DD \uCCA0\uD68C ({n})", "Retract selected ({n})"],
    "bk.again": ["\uD55C \uBC88 \uB354 \uB204\uB974\uBA74 \uC2E4\uD589\uD569\uB2C8\uB2E4", "Click again to do it"],
    "bk.none": ["\uACE0\uB978 \uD589\uC5D0\uB294 \uC774 \uC870\uCE58\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4 ({n}\uAC74 \uAC74\uB108\uB700).", "None of the selected rows has this action ({n} skipped)."],
    "bk.confirm": ["{what} \xB7 \uAC74\uB108\uB700 {n}\uAC74. \uD55C \uBC88 \uB354 \uB204\uB974\uBA74 \uD55C\uAEBC\uBC88\uC5D0 \uC800\uC7A5\uD569\uB2C8\uB2E4.", "{what} \xB7 {n} skipped. Click again to save them at once."],
    "bk.refused": ["{n}\uAC74\uC740 \uCC98\uB9AC\uD560 \uC218 \uC5C6\uC5B4 \uC544\uBB34\uAC83\uB3C4 \uC800\uC7A5\uD558\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4: {e}", "{n} cannot be done, so nothing was saved: {e}"],
    "bk.done": ["{n}\uAC74\uC744 \uD55C\uAEBC\uBC88\uC5D0 \uCC98\uB9AC\uD588\uC2B5\uB2C8\uB2E4. \uC218\uB9AC \uCE78\uC5D0\uC11C \uC804\uBD80 \uB418\uB3CC\uB9B4 \uC218 \uC788\uC2B5\uB2C8\uB2E4.", "Done for {n} at once. The repairs section undoes them all."],
    "rp.entity_exclude": ["{n}: \uCE90\uB9AD\uD130 \uC544\uB2D8", "{n}: not a character"],
    "ro.title": ["AI \uB2F5\uC7A5\uB9CC \uAE30\uC5B5", "Remember AI replies only"],
    "ro.sub": [
      "AI\uAC00 \uB0B4 \uCE90\uB9AD\uD130\uC758 \uB9D0\uACFC \uD589\uB3D9\uAE4C\uC9C0 \uC4F0\uB294 \uCC44\uD305(\uD480\uC0AC\uCE6D)\uC6A9\uC774\uC5D0\uC694. \uCF1C\uBA74 \uB0B4\uAC00 \uBCF4\uB0B8 \uBA54\uC2DC\uC9C0\uB294 \uAE30\uC5B5\uC744 \uCC3E\uC744 \uB54C \uC4F0\uC774\uC9C0 \uC54A\uC544\uC694. \uC9C0\uAE08\uC740 \uD68C\uC0C1\uC5D0\uB9CC \uC801\uC6A9\uB3FC\uC694.",
      "For chats where the AI writes your character too (full impersonation). When on, your own messages are not used to recall memory. For now it applies to recall only."
    ],
    "ro.on": ["\uCF30\uC5B4\uC694. \uC774 \uCC44\uD305\uC740 \uC774\uC81C AI \uB2F5\uC7A5\uC5D0\uC11C\uB9CC \uAE30\uC5B5\uC744 \uCC3E\uC544\uC694.", "On. This chat now recalls from the AI's replies only."],
    "ro.off": ["\uAED0\uC5B4\uC694. \uC774 \uCC44\uD305\uC758 \uAE30\uC5B5\uC740 \uC6D0\uB798\uB300\uB85C \uB3CC\uC544\uC654\uC5B4\uC694.", "Off. This chat recalls as before."],
    "ex.cast": [
      "\uC778\uBB3C \uBAA9\uB85D\uACFC \uAD00\uACC4\uC5D0\uC11C \uBE60\uC838\uC694 (\uAD00\uACC4 {p}\uAC1C). \uC0AC\uC2E4\uC740 \uADF8\uB300\uB85C \uB0A8\uC544\uC694.",
      "It leaves the cast and the relationships ({p}). Every fact stays."
    ],
    "ex.also": ["\uAE30\uC5B5\uC5D0\uC11C\uB3C4 \uC81C\uC678: \uC774 \uC774\uB984\uC774 \uC8FC\uC778\uACF5\uC778 \uC0AC\uC2E4 {f}\uAC1C\uB3C4 \uAC00\uB824\uC694", "Also leave it out of memory: hides {f} facts about it"],
    "ex.confirm": ["\uCE90\uB9AD\uD130 \uC544\uB2D8\uC73C\uB85C \uD45C\uC2DC", "Mark not a character"],
    "ex.done": ["\uCE90\uB9AD\uD130 \uC544\uB2D8\uC73C\uB85C \uD45C\uC2DC\uD588\uC5B4\uC694.", "Marked not a character."],
    "rp.select": ["\uC77C\uAD04 \uB2EB\uAE30\uC5D0 \uB123\uAE30", "Select to close"],
    "rp.outcome": ["\uB2EB\uB294 \uACB0\uACFC", "Outcome"],
    "oc.kept": ["\uC9C0\uCF1C\uC9D0", "kept"],
    "oc.broken": ["\uAE68\uC9D0", "broken"],
    "oc.achieved": ["\uC774\uB904\uC9D0", "achieved"],
    "oc.abandoned": ["\uADF8\uB9CC\uB460", "abandoned"],
    "oc.failed": ["\uC2E4\uD328", "failed"],
    "oc.answered": ["\uB2F5\uC774 \uB098\uC634", "answered"],
    "oc.averted": ["\uD53C\uD568", "averted"],
    "oc.paid": ["\uAC1A\uC74C", "paid"],
    "rp.how_ended": ["\uC5B4\uB5BB\uAC8C \uB05D\uB0AC\uB098\uC694?", "How did it end?"],
    "rp.bulk": ["\uACE0\uB978 \uC2A4\uB808\uB4DC {n}\uAC1C \uB2EB\uAE30", "Close {n} selected threads"],
    "rp.bulk_done": ["\uC2A4\uB808\uB4DC {n}\uAC1C\uB97C \uB2EB\uC558\uC2B5\uB2C8\uB2E4.", "Closed {n} threads."],
    "rp.bulk_failed": ["{n}\uAC1C\uB294 \uB2EB\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4:", "{n} could not be closed:"],
    "rp.done": [
      "\uACE0\uCCE4\uC2B5\uB2C8\uB2E4. \uC7AC\uAD6C\uCD95\uACFC \uC0C8 \uCD94\uCD9C \uC138\uB300\uC5D0\uB3C4 \uB0A8\uACE0, \uC218\uB9AC \uCE78\uC5D0\uC11C \uB418\uB3CC\uB9B4 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
      "Fixed. It survives rebuilds and new extractor generations; undo it in Repairs."
    ],
    "rp.undone": ["\uB418\uB3CC\uB838\uC2B5\uB2C8\uB2E4.", "Undone."],
    "rp.correct_prompt": ["\uC0C8 {f}", "New {f}"],
    "rp.turn": ["\uC801\uC6A9 \uD134", "From turn"],
    "rp.turn_hint": ["\uD134 (\uBE44\uC6B0\uBA74 \uADF8 \uC0AC\uC2E4\uC758 \uD134)", "turn (empty: the fact's)"],
    "rp.bad_turn": ["\uD134\uC740 0 \uC774\uC0C1\uC758 \uC815\uC218\uC785\uB2C8\uB2E4.", "A turn is a whole number, 0 or more."],
    "rp.field_object": ["\uB300\uC0C1", "object"],
    "rp.field_value": ["\uAC12", "value"],
    "split.title": ["\uC798\uBABB \uD569\uCCD0\uC9C4 \uC774\uB984 \uB098\uB204\uAE30", "Split names joined by mistake"],
    "split.sub": [
      "\uC774\uC57C\uAE30\uAC00 \uAC19\uC740 \uC778\uBB3C\uB85C \uBB36\uC740 \uB450 \uC774\uB984\uC744 \uB098\uB215\uB2C8\uB2E4(K8). \uC624\uB108\uAC00 \uD569\uCE5C \uAC83\uC740 \uC704\uC758 \uD574\uC81C\uB97C \uC4F0\uC138\uC694.",
      "Separates two names the story joined as one (K8). For a join you made, use Undo above."
    ],
    "split.do": ["\uBD84\uB9AC", "Split"],
    "split.done": ['"{a}"\uC640(\uACFC) "{b}"\uB97C \uB098\uB234\uC2B5\uB2C8\uB2E4.', 'Split "{a}" and "{b}".'],
    "pv.title": ["\uBC14\uB00C\uB294 \uAC83", "What changes"],
    "pv.nothing": [
      "\uAE30\uC5B5\uC740 \uADF8\uB300\uB85C\uC785\uB2C8\uB2E4. \uB450 \uC774\uB984\uC740 \uC774\uBBF8 \uAC19\uC740 \uB300\uC0C1\uC774\uAC70\uB098, \uC774 \uCC44\uD305\uC5D0 \uB458 \uB2E4 \uB098\uC624\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
      "Memory stays as it is: the two names are one entity already, or not both mentioned in this chat."
    ],
    "pv.entities": ["{a} \u2192 {b}", "{a} \u2192 {b}"],
    "pv.more": ["\uC678 {n}\uAC74", "{n} more"],
    "pv.changed": ["\uBBF8\uB9AC\uBCF4\uAE30 \uB4A4\uC5D0 \uAE30\uC5B5\uC774 \uBC14\uB00C\uC5C8\uC2B5\uB2C8\uB2E4. \uC0C8\uB85C \uBCF8 \uB0B4\uC6A9\uC785\uB2C8\uB2E4.", "Memory changed since the preview. Here is the new one."],
    "pv.confirm_join": ["\uC774\uB300\uB85C \uD569\uCE58\uAE30", "Join as shown"],
    "pv.confirm_split": ["\uC774\uB300\uB85C \uB098\uB204\uAE30", "Split as shown"],
    "pv.confirm_undo": ["\uC774\uB300\uB85C \uB418\uB3CC\uB9AC\uAE30", "Undo as shown"],
    "pv.fact_replaced": ['"{a}" \uB300\uC2E0 "{b}"\uAC00 \uD604\uC7AC \uC0AC\uC2E4\uC774 \uB429\uB2C8\uB2E4', '"{b}" replaces "{a}"'],
    "pv.turn": [" ({t}\uD134)", " (turn {t})"],
    "pv.names": ['"{a}"\uC758 \uB2E4\uB978 \uC774\uB984: {n}', '"{a}" also goes by: {n}'],
    "pv.kept": ['"{a}"\uC758 \uC778\uC2A4\uD399\uD130 \uD398\uC774\uC9C0\uAC00 \uB0A8\uACE0, \uB2E4\uB978 \uCABD \uD398\uC774\uC9C0\uB294 \uC0AC\uB77C\uC9D1\uB2C8\uB2E4', `"{a}"'s Inspector page stays; the other one goes`],
    "pv.reextract_failed": ["\uC5F0\uACB0\uC740 \uD574\uC81C\uD588\uC9C0\uB9CC \uB2E4\uC2DC \uCD94\uCD9C\uC740 \uD558\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4: {e}", "The join was undone, but the re-extraction failed: {e}"],
    "pv.retry": ["\uB2E4\uC2DC \uCD94\uCD9C \uC7AC\uC2DC\uB3C4", "Retry the re-extraction"],
    "pv.fact_merged": ['"{a}"\uAC00 \uAC19\uC740 \uC0AC\uC2E4 "{b}"\uB85C \uD569\uCCD0\uC9D1\uB2C8\uB2E4', '"{a}" merges into the same fact "{b}"'],
    "pv.fact_ended": ['"{a}"\uAC00 \uB354\uB294 \uD604\uC7AC \uC0AC\uC2E4\uC774 \uC544\uB2D9\uB2C8\uB2E4', '"{a}" is no longer current'],
    "pv.fact_back": ['"{a}"\uAC00 \uB2E4\uC2DC \uD604\uC7AC \uC0AC\uC2E4\uC774 \uB429\uB2C8\uB2E4', '"{a}" is current again'],
    "pv.fact_back_instead": ['"{b}" \uB300\uC2E0 "{a}"\uAC00 \uB2E4\uC2DC \uD604\uC7AC \uC0AC\uC2E4\uC774 \uB429\uB2C8\uB2E4', '"{a}" is current again instead of "{b}"'],
    "pv.self_relation": ['\uC8FC\uC758: \uAD00\uACC4 "{a}"\uAC00 \uD55C \uC778\uBB3C\uACFC \uADF8 \uC790\uC2E0\uC758 \uAD00\uACC4\uAC00 \uB429\uB2C8\uB2E4', 'Note: the relationship "{a}" becomes one with itself'],
    "pv.self_relation_gone": ['\uAD00\uACC4 "{a}"\uAC00 \uB2E4\uC2DC \uB450 \uC778\uBB3C \uC0AC\uC774\uC758 \uAD00\uACC4\uAC00 \uB429\uB2C8\uB2E4', 'The relationship "{a}" is between two again'],
    "pv.self_thread": ['\uC8FC\uC758: {w}\uC758 \uC57D\uC18D "{a}"\uAC00 \uC790\uAE30 \uC790\uC2E0\uACFC\uC758 \uC57D\uC18D\uC774 \uB429\uB2C8\uB2E4', `Note: {w}'s promise "{a}" becomes one to themselves`],
    "pv.self_thread_gone": ['{w}\uC758 \uC57D\uC18D "{a}"\uAC00 \uB2E4\uC2DC \uB450 \uC778\uBB3C \uC0AC\uC774\uC758 \uC57D\uC18D\uC774 \uB429\uB2C8\uB2E4', `{w}'s promise "{a}" is between two again`],
    "pv.thread_status": ['"{a}": {s}', '"{a}": {s}'],
    "pv.thread_merged": ['"{a}"\uAC00 \uB2E4\uB978 \uD560 \uC77C\uC758 \uBC18\uBCF5\uC73C\uB85C \uD569\uCCD0\uC9D1\uB2C8\uB2E4', '"{a}" becomes a restatement of another thread'],
    "pv.thread_back": ['"{a}"\uAC00 \uB2E4\uC2DC \uB530\uB85C \uBCF4\uC785\uB2C8\uB2E4', '"{a}" is its own thread again'],
    "pv.secret": ['\uBE44\uBC00 "{a}"\uB97C \uC544\uB294 \uC0AC\uB78C\xB7\uBAA8\uB974\uB294 \uC0AC\uB78C\uC774 \uBC14\uB01D\uB2C8\uB2E4', 'Who holds or is kept from the secret "{a}" changes'],
    "pv.secret_holder": ['\uC8FC\uC758: \uBE44\uBC00 "{a}"\uAC00 \uADF8\uAC83\uC744 \uC544\uB294 \uC778\uBB3C\uC5D0\uAC8C\uC11C \uC228\uACA8\uC9D1\uB2C8\uB2E4', 'Note: the secret "{a}" is kept from someone who holds it'],
    "pv.secret_holder_gone": ['\uBE44\uBC00 "{a}"\uAC00 \uB354\uB294 \uC544\uB294 \uC778\uBB3C\uC5D0\uAC8C\uC11C \uC228\uACA8\uC9C0\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4', 'The secret "{a}" is no longer kept from someone who holds it'],
    "pv.secret_merged": ['\uBE44\uBC00 "{a}"\uAC00 \uB2E4\uB978 \uBE44\uBC00\uACFC \uD569\uCCD0\uC9D1\uB2C8\uB2E4', 'The secret "{a}" merges with another'],
    "pv.secret_back": ['\uBE44\uBC00 "{a}"\uAC00 \uB2E4\uC2DC \uB530\uB85C \uBCF4\uC785\uB2C8\uB2E4', 'The secret "{a}" is its own again'],
    "pv.repair_stops": ["\uC218\uB9AC \uD558\uB098({k})\uAC00 \uB354\uB294 \uC801\uC6A9\uB418\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4", "A repair ({k}) stops applying"],
    "pv.repair_starts": ["\uC218\uB9AC \uD558\uB098({k})\uAC00 \uB2E4\uC2DC \uC801\uC6A9\uB429\uB2C8\uB2E4", "A repair ({k}) applies again"],
    "pv.repair_moves": ["\uC218\uB9AC \uD558\uB098({k})\uAC00 \uB2E4\uB978 \uD56D\uBAA9\uC5D0 \uC801\uC6A9\uB429\uB2C8\uB2E4", "A repair ({k}) applies to another item"],
    "pv.conflict_new": ['\uC0C8 \uCDA9\uB3CC: "{a}"', 'New conflict: "{a}"'],
    "pv.conflict_gone": ['\uCDA9\uB3CC\uC774 \uC0AC\uB77C\uC9D1\uB2C8\uB2E4: "{a}"', 'Conflict gone: "{a}"'],
    "pv.persona": ["\uC8FC\uC758: \uD398\uB974\uC18C\uB098(\uC720\uC800)\uC640 \uD569\uCCD0\uC9D1\uB2C8\uB2E4", "Note: joins the persona (the user)"],
    "pv.persona_gone": ["\uD398\uB974\uC18C\uB098(\uC720\uC800)\uC640 \uB2E4\uC2DC \uB098\uB269\uB2C8\uB2E4", "Parts from the persona (the user) again"],
    "pv.canon_alias": ['\uCE90\uB17C\uC758 "{b}"\uB3C4 "{a}"\uC758 \uB2E4\uB978 \uC774\uB984\uC774 \uB429\uB2C8\uB2E4', `Canon's "{b}" also becomes a name of "{a}"`],
    "pv.canon_alias_gone": ['\uCE90\uB17C\uC758 "{b}"\uAC00 \uB354\uB294 "{a}"\uC758 \uB2E4\uB978 \uC774\uB984\uC774 \uC544\uB2D9\uB2C8\uB2E4', `Canon's "{b}" is no longer a name of "{a}"`],
    "pv.reextract": [
      "\uD569\uCCD0\uC838 \uC788\uB358 \uB3D9\uC548 \uCD94\uCD9C\uB41C {n}\uAC1C \uD134\uC744 \uC774\uB984\uC744 \uB098\uB220 \uB2E4\uC2DC \uCD94\uCD9C (\uCD94\uCD9C \uBAA8\uB378 \uD638\uCD9C {n}\uD68C)",
      "Re-extract the {n} turns extracted while joined, with the names apart ({n} extraction calls)"
    ],
    "pv.reextracted": ["{n}\uAC1C \uD134\uC744 \uB2E4\uC2DC \uCD94\uCD9C\uD558\uB3C4\uB85D \uB123\uC5C8\uC2B5\uB2C8\uB2E4.", "Queued {n} turns for re-extraction."],
    "mode.title": ["\uAE30\uC5B5 \uBAA8\uB4DC (\uC774 \uCC44\uD305)", "Memory mode (this chat)"],
    "mode.sub": [
      '\uBE44\uBC00\uCC98\uB7FC \uC77C\uBD80 \uC778\uBB3C\uB9CC \uC544\uB294 \uAE30\uC5B5\uC744 \uC5B4\uB5BB\uAC8C \uB123\uC744\uC9C0 \uC815\uD569\uB2C8\uB2E4. \uAE30\uBCF8\uAC12\uC740 "\uC544\uB294 \uC778\uBB3C\uB9CC \uC548\uB2E4"\uB294 \uADDC\uCE59\uACFC \uD568\uAED8 \uB123\uB294 \uAC83\uC785\uB2C8\uB2E4.',
      "How memory that only some characters know, such as a secret, is given to the model. By default it is given with a rule that only its holders know it."
    ],
    "mode.strict": ["\uC5C4\uACA9 \uBAA8\uB4DC: \uC7A5\uBA74\uC758 \uBAA8\uB450\uAC00 \uC544\uB294 \uAC83\uB9CC \uB123\uAE30", "Strict: give only what everyone in the scene knows"],
    "mode.strict_sub": [
      '\uC7A5\uBA74\uC5D0 \uBAA8\uB974\uB294 \uC778\uBB3C\uC774 \uC788\uC73C\uBA74 \uBE44\uBC00\uC758 \uB0B4\uC6A9 \uB300\uC2E0 "\uB204\uAC00 \uBB34\uC5B8\uAC00\uB97C \uC228\uAE30\uACE0 \uC788\uB2E4"\uB9CC \uB123\uC2B5\uB2C8\uB2E4. \uC0C8\uC5B4 \uB098\uAC08 \uC77C\uC740 \uC904\uC9C0\uB9CC, \uBE44\uBC00\uC744 \uAC00\uC9C4 \uC778\uBB3C\uB3C4 \uB0B4\uC6A9\uC744 \uB5A0\uC62C\uB9AC\uC9C0 \uBABB\uD569\uB2C8\uB2E4.',
      'When someone in the scene does not know it, only "someone keeps something" is given, not the content. Leaks become rarer, but the holders cannot recall the content either.'
    ],
    "mode.narrator": ["1\uC778\uCE6D \uD654\uC790", "First-person narrator"],
    "mode.narrator_sub": [
      "\uC774 \uCC44\uD305\uC744 \uD55C \uC778\uBB3C\uC758 1\uC778\uCE6D\uC73C\uB85C \uC4F4\uB2E4\uBA74 \uACE0\uB974\uC138\uC694. \uADF8 \uC778\uBB3C\uC774 \uBAA8\uB974\uB294 \uAE30\uC5B5\uC740 \uB123\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
      "Pick one if this chat is told in one character's first person: memory that character does not know is left out."
    ],
    "mode.narrator_none": ["\uC5C6\uC74C (3\uC778\uCE6D\xB7\uC804\uC9C0\uC801 \uC2DC\uC810)", "None (third person or omniscient)"],
    "mode.narrator_user": ["\uC720\uC800 \uCE90\uB9AD\uD130 (\uB098)", "The user's character (me)"],
    "mode.save": ["\uC800\uC7A5", "Save"],
    "mode.on": ["\uCF2C", "on"],
    "mode.off": ["\uB054", "off"],
    "mode.saved": ["\uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4. \uC5C4\uACA9 \uBAA8\uB4DC: {s}, 1\uC778\uCE6D \uD654\uC790: {n}. \uB2E4\uC74C \uC0DD\uC131\uBD80\uD130 \uC801\uC6A9\uB429\uB2C8\uB2E4.", "Saved. Strict: {s}, narrator: {n}. Applies from the next generation."],
    "act.off": ["\uC0AC\uC2E4 \uCD94\uCD9C(\uB610\uB294 \uC784\uBCA0\uB529)\uC774 \uAEBC\uC838 \uC788\uC2B5\uB2C8\uB2E4. \uC124\uC815 \uD0ED\uC5D0\uC11C \uCF1C\uC138\uC694.", "Fact extraction (or embeddings) is off. Turn it on in Settings."],
    // settings: connection
    "conn.title": ["\uC5F0\uACB0", "Connection"],
    "conn.sub": [
      "\uC774 \uBE0C\uB77C\uC6B0\uC800\uC758 PocketRisu \uD50C\uB7EC\uADF8\uC778 \uC124\uC815\uC785\uB2C8\uB2E4. \uC0AC\uC774\uB4DC\uCE74\uAC00 \uB2E4\uB978 \uAE30\uAE30\uC5D0 \uC788\uC73C\uBA74 route=server\uAC00 \uC790\uB3D9\uC73C\uB85C \uC4F0\uC785\uB2C8\uB2E4.",
      "This browser's PocketRisu plugin settings. If the sidecar runs on another device, route=server is used automatically."
    ],
    "conn.url": ["\uC0AC\uC774\uB4DC\uCE74 \uC8FC\uC18C", "Sidecar URL"],
    "conn.route": ["\uACBD\uB85C", "Route"],
    "conn.budget": ["\uAE30\uC5B5 \uC608\uC0B0(\uD1A0\uD070)", "Memory budget (tokens)"],
    "conn.deadline": ["\uC81C\uD55C \uC2DC\uAC04(ms)", "Deadline (ms)"],
    "conn.enabled": ["\uAE30\uC5B5 \uB123\uAE30 \uCF1C\uAE30", "Memory on"],
    "conn.token": ["\uD1A0\uD070", "Token"],
    // the sidecar's NMOS_AUTH_TOKEN, when it has one (audit F27)
    "conn.token_placeholder": ["\uC0AC\uC774\uB4DC\uCE74\uC5D0 \uD1A0\uD070\uC774 \uC5C6\uC73C\uBA74 \uBE44\uC6CC \uB450\uC138\uC694", "Leave empty when the sidecar has no token"],
    "conn.hint": ["PocketRisu\uC758 \uCD5C\uB300 \uCEE8\uD14D\uC2A4\uD2B8\uB97C \uAE30\uC5B5 \uC608\uC0B0\uB9CC\uD07C \uC904\uC5EC \uB450\uC138\uC694.", "Lower PocketRisu's max context by the memory budget."],
    "conn.deadline_hint": [
      "\uC81C\uD55C \uC2DC\uAC04 \uC548\uC5D0 \uAE30\uC5B5\uC744 \uC900\uBE44\uD558\uC9C0 \uBABB\uD558\uBA74 \uADF8 \uC694\uCCAD\uC740 \uAE30\uC5B5 \uC5C6\uC774 \uBCF4\uB0C5\uB2C8\uB2E4. \uAE30\uBCF8 3000ms. \uC544\uC8FC \uAE34 \uCC44\uD305(1\uB9CC \uAC1C \uC774\uC0C1)\uC5D0\uC11C \uAE30\uC5B5\uC774 \uC790\uC8FC \uBE60\uC9C0\uBA74 \uB298\uB9AC\uC138\uC694. \uB298\uB9B0 \uB9CC\uD07C \uB2F5\uC7A5 \uC2DC\uC791\uC774 \uB2A6\uC5B4\uC9C8 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
      "If memory is not ready within the deadline, that request goes without memory. Default 3000 ms. Raise it if very long chats (10,000+ messages) often miss memory; replies may start that much later."
    ],
    // settings: models
    "llm.title": ["\uC0AC\uC2E4 \uCD94\uCD9C LLM", "Fact extraction LLM"],
    "llm.sub": [
      "\uD655\uC815\uB41C \uD134(\uC785\uB825\uACFC \uC751\uB2F5)\uB9C8\uB2E4 \uBC31\uADF8\uB77C\uC6B4\uB4DC\uC5D0\uC11C \uD55C \uBC88 \uD638\uCD9C\uD574 \uC778\uBB3C\xB7\uC7A5\uC18C\xB7\uC57D\uC18D\xB7\uAD00\uACC4\uB97C \uAE30\uB85D\uD569\uB2C8\uB2E4. \uC720\uB8CC API\uB294 \uBE44\uC6A9\uC774 \uB4ED\uB2C8\uB2E4.",
      "Called once per settled turn (input and reply) in the background to record people, places, promises and relationships. Paid APIs cost money."
    ],
    // settings: what the extraction model's requests carry (PHASE-61 S4)
    "extra.body": ["\uCD94\uAC00 \uC694\uCCAD \uAC12 (JSON)", "Extra request values (JSON)"],
    "extra.body_sub": [
      "\uC774 \uBAA8\uB378\uB85C \uBCF4\uB0B4\uB294 \uBAA8\uB4E0 \uC694\uCCAD\uC5D0 \uB354\uD574\uC9D1\uB2C8\uB2E4. API \uD0A4\uB098 \uC694\uCCAD \uC790\uCCB4\uC758 \uD56D\uBAA9(model, messages, temperature \uB4F1)\uC740 \uB123\uC744 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.",
      "Added to every request made with this model. It may not hold an API key or the request's own fields (model, messages, temperature\u2026)."
    ],
    "extra.invalid": ["JSON \uAC1D\uCCB4\uAC00 \uC544\uB2D9\uB2C8\uB2E4", "Not a JSON object"],
    "extra.effort": ["\uCD94\uB860 \uAC15\uB3C4", "Reasoning effort"],
    "extra.effort_sub": ["\uACE0\uB974\uBA74 \uC704 JSON\uC758 reasoning.effort\uC5D0 \uC801\uD799\uB2C8\uB2E4.", "Writes reasoning.effort into the JSON above."],
    "extra.custom": ["\uC9C1\uC811 \uC785\uB825", "custom"],
    "extra.no_temp": ["temperature \uBCF4\uB0B4\uC9C0 \uC54A\uAE30", "Do not send a temperature"],
    "extra.no_temp_sub": ["temperature\uB97C \uBC1B\uC9C0 \uC54A\uB294 \uBAA8\uB378\uC6A9\uC785\uB2C8\uB2E4. \uB044\uBA74 0\uC744 \uBCF4\uB0C5\uB2C8\uB2E4.", "For models that reject a temperature; otherwise 0 is sent."],
    "emb.title": ["\uC758\uBBF8 \uAC80\uC0C9 \uC784\uBCA0\uB529", "Semantic recall embeddings"],
    "emb.sub": [
      "\uB2E4\uB978 \uB9D0\uB85C \uBB3C\uC5B4\uB3C4 \uC608\uC804 \uC7A5\uBA74\uC744 \uCC3E\uC2B5\uB2C8\uB2E4. Ollama\uC758 qwen3-embedding:0.6b\uB97C \uCD94\uCC9C\uD569\uB2C8\uB2E4.",
      "Finds earlier scenes even when asked in other words. Ollama qwen3-embedding:0.6b is recommended."
    ],
    "emb.voyage_hint": [
      "\uC758\uBBF8 \uC720\uC0AC\uB3C4 \uAE30\uC900\uC744 voyage-4-large\uC5D0\uC11C \uC7B0 \uAC12 0.3\uC73C\uB85C \uB9DE\uCDC4\uC2B5\uB2C8\uB2E4. \uACB0\uC81C \uC218\uB2E8\uC744 \uB4F1\uB85D\uD558\uC9C0 \uC54A\uC740 Voyage \uACC4\uC815\uC740 \uBD84\uB2F9 3\uD68C\uB85C \uC81C\uD55C\uB418\uC5B4, \uB300\uD654\uB97C \uC784\uBCA0\uB529\uD558\uAE30\uC5D0 \uBD80\uC871\uD569\uB2C8\uB2E4. Voyage\uB294 \uBAA8\uB378 \uBAA9\uB85D\uC744 \uC8FC\uC9C0 \uC54A\uC73C\uB2C8 \uB2E4\uB978 \uBAA8\uB378\uC740 \uC774\uB984\uC744 \uC9C1\uC811 \uC801\uC73C\uC138\uC694.",
      "The vector min similarity is set to 0.3, the value measured for voyage-4-large. A Voyage account with no payment method is limited to 3 requests a minute, too few to embed a chat. Voyage lists no models, so type the name of another model yourself."
    ],
    // settings: optional reranker (PHASE-60 S5)
    "rerank.title": ["\uC7AC\uC815\uB82C \uBAA8\uB378 (\uC120\uD0DD)", "Reranker (optional)"],
    "rerank.sub": [
      "\uC8FC\uC18C\uC640 \uBAA8\uB378\uC744 \uBAA8\uB450 \uB123\uC73C\uBA74, \uB9E4 \uC694\uCCAD\uB9C8\uB2E4 \uC0AC\uC6A9\uC790 \uBA54\uC2DC\uC9C0\uC640 \uCC3E\uC740 \uAE30\uC5B5 \uD6C4\uBCF4 \uCD5C\uB300 30\uAC1C\uC758 \uAE00\uC744 \uADF8 \uC8FC\uC18C\uB85C \uBCF4\uB0B4 \uB354 \uC54C\uB9DE\uC740 \uC21C\uC11C\uB85C \uB2E4\uC2DC \uB9E4\uAE41\uB2C8\uB2E4(\uC784\uBCA0\uB529 \uBAA8\uB378\uC5D0 \uB300\uD654 \uAE00\uC744 \uBCF4\uB0B4\uB294 \uAC83\uACFC \uAC19\uC2B5\uB2C8\uB2E4). \uC720\uB8CC \uC11C\uBE44\uC2A4\uB294 \uC694\uCCAD\uB9C8\uB2E4 \uBE44\uC6A9\uC774 \uB4E4 \uC218 \uC788\uC2B5\uB2C8\uB2E4. \uC751\uB2F5\uC774 \uB2A6\uAC70\uB098 \uC624\uB958\uAC00 \uB098\uBA74 \uAE30\uC5B5\uC740 \uC6D0\uB798 \uC21C\uC11C \uADF8\uB300\uB85C \uB4E4\uC5B4\uAC11\uB2C8\uB2E4. \uC784\uBCA0\uB529 \uB300\uAE30\uC640 \uC7AC\uC815\uB82C \uB300\uAE30\uB97C \uD569\uCCD0 \uD50C\uB7EC\uADF8\uC778\uC758 \uC694\uCCAD \uC81C\uD55C \uC2DC\uAC04(\uAE30\uBCF8 3\uCD08)\uBCF4\uB2E4 \uB109\uB109\uD788 \uC9E7\uAC8C \uB450\uC138\uC694. \uB044\uB824\uBA74 \uC8FC\uC18C\uB098 \uBAA8\uB378\uC744 \uBE44\uC6CC \uB450\uC138\uC694.",
      "With both an address and a model set, each request sends your message and the text of up to 30 recalled memory candidates to that address to put them in a better order, just as chat text goes to the embedder. Paid services may charge for each request. If it is slow or fails, memory goes out in its usual order. Keep the embedding wait plus the reranker wait well under the plugin request deadline (3 s by default). Leave the address or model empty to turn it off."
    ],
    "rerank.on": ["\uCF1C\uC9D0: \uC694\uCCAD\uB9C8\uB2E4 \uC21C\uC11C\uB97C \uB2E4\uC2DC \uB9E4\uAE41\uB2C8\uB2E4", "On: reorders memory candidates on every request"],
    "rerank.off": ["\uAEBC\uC9D0: \uC8FC\uC18C\uC640 \uBAA8\uB378\uC774 \uBE44\uC5B4 \uC788\uC2B5\uB2C8\uB2E4", "Off: address and model are empty"],
    "rerank.url": ["\uC8FC\uC18C", "Endpoint URL"],
    "rerank.model_placeholder": ["\uC7AC\uC815\uB82C \uBAA8\uB378 \uC774\uB984", "reranker model name"],
    "rerank.timeout": ["\uC7AC\uC815\uB82C \uB300\uAE30(ms)", "Reranker wait (ms)"],
    "preset.off": ["\uC0AC\uC6A9 \uC548 \uD568", "Off"],
    "preset.ollama": ["Ollama (\uC774 PC)", "Ollama (this PC)"],
    "preset.custom": ["\uC9C1\uC811 \uC785\uB825 (OpenAI \uD638\uD658)", "Custom (OpenAI-compatible)"],
    "model.provider": ["\uC81C\uACF5\uC790", "Provider"],
    "model.endpoint": ["\uC8FC\uC18C (OpenAI \uD638\uD658 /v1)", "Endpoint (OpenAI-compatible /v1)"],
    "model.model": ["\uBAA8\uB378", "Model"],
    "model.llm_placeholder": ["\uBAA8\uB378 \uC774\uB984", "model name"],
    "model.emb_placeholder": ["\uC784\uBCA0\uB529 \uBAA8\uB378", "embedding model"],
    "model.key": ["API \uD0A4", "API key"],
    "model.key_placeholder": ["\uD544\uC694\uD560 \uB54C\uB9CC \uC785\uB825", "only if needed"],
    "model.key_saved": ["\uC800\uC7A5\uB428 \u2014 \uBC14\uAFC0 \uB54C\uB9CC \uC785\uB825", "saved \u2014 type only to change"],
    "model.vertex_hint": [
      "\u2018\uD0A4 \uD30C\uC77C \uBD88\uB7EC\uC624\uAE30\u2019\uB85C \uC11C\uBE44\uC2A4 \uACC4\uC815 JSON \uD0A4 \uD30C\uC77C\uC744 \uACE0\uB974\uC138\uC694(\uB0B4\uC6A9\uC744 API \uD0A4 \uCE78\uC5D0 \uD1B5\uC9F8\uB85C \uBD99\uC5EC \uB123\uC5B4\uB3C4 \uB429\uB2C8\uB2E4). \uC8FC\uC18C\uC758 \uD504\uB85C\uC81D\uD2B8\uB294 \uD0A4\uC5D0\uC11C \uCC44\uC6CC\uC9C0\uACE0, \uBAA8\uB378 \uBAA9\uB85D\uC744 \uBC14\uB85C \uBD88\uB7EC\uC624\uBA70, \uD1A0\uD070\uC740 \uC0AC\uC774\uB4DC\uCE74\uAC00 1\uC2DC\uAC04\uB9C8\uB2E4 \uAC31\uC2E0\uD569\uB2C8\uB2E4. Vertex AI User \uC5ED\uD560\uB9CC \uC900 \uC804\uC6A9 \uC11C\uBE44\uC2A4 \uACC4\uC815\uC744 \uC4F0\uC138\uC694.",
      "Pick the service-account JSON key file with \u2018Load key file\u2019 (or paste its whole content into the API key field). The project in the endpoint is filled from the key, the model list loads right away, and the sidecar renews the token every hour. Use a dedicated service account with only the Vertex AI User role."
    ],
    "model.key_file": ["\uD0A4 \uD30C\uC77C \uBD88\uB7EC\uC624\uAE30", "Load key file"],
    "model.key_file_ok": ["\uD0A4 \uD30C\uC77C\uC744 \uC77D\uC5C8\uC2B5\uB2C8\uB2E4 (\uD504\uB85C\uC81D\uD2B8 {project}). \uC800\uC7A5\uD574\uC57C \uC801\uC6A9\uB429\uB2C8\uB2E4.", "Key file read (project {project}). Save to apply it."],
    "model.key_file_bad": [
      'Google \uC11C\uBE44\uC2A4 \uACC4\uC815 JSON \uD0A4 \uD30C\uC77C\uC774 \uC544\uB2D9\uB2C8\uB2E4 ("type": "service_account"\uC640 project_id\uAC00 \uC788\uC5B4\uC57C \uD569\uB2C8\uB2E4).',
      'Not a Google service-account JSON key file (it needs "type": "service_account" and a project_id).'
    ],
    "model.load": ["\uBAA8\uB378 \uBAA9\uB85D", "Load models"],
    "model.test": ["\uC5F0\uACB0 \uD14C\uC2A4\uD2B8", "Test"],
    "model.loading": ["\uBD88\uB7EC\uC624\uB294 \uC911\u2026", "Loading\u2026"],
    "model.list_failed": ["\uBAA9\uB85D\uC744 \uAC00\uC838\uC624\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4: {e}", "Could not list models: {e}"],
    "model.pick": ["\u2014 \uBAA8\uB378 {n}\uAC1C \uC911 \uC120\uD0DD \u2014", "\u2014 pick one of {n} models \u2014"],
    "model.found": ["\uBAA8\uB378 {n}\uAC1C\uB97C \uCC3E\uC558\uC2B5\uB2C8\uB2E4.", "Found {n} models."],
    "model.testing": ["\uC2E4\uC81C \uD638\uCD9C\uB85C \uD655\uC778 \uC911\u2026", "Calling the model\u2026"],
    "model.test_ok": ["\uC131\uACF5 {ms}ms", "OK {ms}ms"],
    "model.dims": [" \xB7 {n}\uCC28\uC6D0", " \xB7 {n} dimensions"],
    "model.test_failed": ["\uC2E4\uD328: {e}", "Failed: {e}"],
    // settings: tuning
    "tune.title": ["\uAC80\uC0C9 \uC870\uC815", "Recall tuning"],
    "tune.sub": [
      "\uC5C9\uB6B1\uD55C \uBC1C\uCDCC\uAC00 \uB4E4\uC5B4\uAC00\uBA74 \uAE30\uC900\uAC12\uC744 \uC62C\uB9AC\uACE0, \uAE30\uC5B5\uC774 \uB108\uBB34 \uC548 \uB4E4\uC5B4\uAC00\uBA74 \uB0B4\uB9AC\uC138\uC694.",
      "Raise the thresholds if unrelated excerpts get in; lower them if too little memory is injected."
    ],
    "tune.threshold": ["\uAE00\uC790 \uC77C\uCE58 \uAE30\uC900", "Lexical threshold"],
    "tune.min_sim": ["\uC758\uBBF8 \uC720\uC0AC\uB3C4 \uAE30\uC900", "Vector min similarity"],
    "tune.embed_wait": ["\uC758\uBBF8 \uAC80\uC0C9 \uB300\uAE30(ms)", "Embedding wait (ms)"],
    "tune.embed_wait_hint": [
      "\uC784\uBCA0\uB529 \uB2F5\uC744 \uAE30\uB2E4\uB9AC\uB294 \uC2DC\uAC04\uC785\uB2C8\uB2E4. \uB118\uC73C\uBA74 \uADF8 \uC694\uCCAD\uC740 \uC758\uBBF8 \uAC80\uC0C9 \uC5C6\uC774 \uB2E8\uC5B4\uAC00 \uACB9\uCE58\uB294 \uAE30\uC5B5\uB9CC \uCC3E\uC2B5\uB2C8\uB2E4. \uAE30\uBCF8 300ms. \uC0C1\uD0DC \uD0ED\uC5D0 \uC758\uBBF8 \uAC80\uC0C9 \uC5C6\uC774 \uCC3E\uC558\uB2E4\uB294 \uC54C\uB9BC\uC774 \uC790\uC8FC \uB728\uBA74(\uC6D0\uACA9 \uC784\uBCA0\uB529, \uB290\uB9B0 PC) 1000 \uC815\uB3C4\uB85C \uB298\uB9AC\uC138\uC694. \uB298\uB9B0 \uB9CC\uD07C \uB2F5\uC7A5 \uC2DC\uC791\uC774 \uB2A6\uC5B4\uC9C8 \uC218 \uC788\uACE0, \uC704\uC758 \uC81C\uD55C \uC2DC\uAC04\uBCF4\uB2E4 \uC9E7\uC544\uC57C \uD569\uB2C8\uB2E4.",
      "How long a request waits for the embedding. Past it, that request recalls by shared words only. Default 300 ms. If the Status tab often warns that semantic search was skipped (a remote embedder, a slow PC), raise it to about 1000. Replies may start that much later, and it must stay below the deadline above."
    ],
    "tune.embed_wait_tight": [
      "\uB2E4\uB9CC \uC784\uBCA0\uB529 \uB300\uAE30({w}ms)\uAC00 \uC81C\uD55C \uC2DC\uAC04({d}ms)\uC5D0\uC11C 500ms\uB97C \uBE80 \uAC83\uBCF4\uB2E4 \uAE38\uC5B4\uC11C, \uC784\uBCA0\uB529\uC774 \uB2A6\uC73C\uBA74 \uADF8 \uC694\uCCAD\uC740 \uAE30\uC5B5 \uC5C6\uC774 \uAC11\uB2C8\uB2E4. \uB300\uAE30\uB97C \uC904\uC774\uAC70\uB098 \uC81C\uD55C \uC2DC\uAC04\uC744 \uB298\uB9AC\uC138\uC694.",
      "But the embedding wait ({w} ms) is longer than the deadline ({d} ms) minus 500 ms: a slow embedding then sends the request without memory. Lower the wait or raise the deadline."
    ],
    "tune.top_k": ["\uBC1C\uCDCC \uC218", "Excerpts"],
    "tune.facts": ["\uC0AC\uC2E4 \uC218", "Facts"],
    "tune.backfill": ["\uCC98\uC74C \uC5F0\uACB0 \uC2DC \uCD94\uCD9C\uD560 \uD134 \uC218", "Turns extracted on first sync"],
    "tune.summaries": ["\uC7A5\uBA74 \uC694\uC57D \uB9CC\uB4E4\uAE30", "Scene summaries"],
    "tune.summaries_hint": [
      "\uCD94\uCD9C \uBAA8\uB378\uC774 8\uD134\uB9C8\uB2E4 \uC7A5\uBA74\uACFC \uC9C0\uAE08\uAE4C\uC9C0\uC758 \uC774\uC57C\uAE30\uB97C \uC694\uC57D\uD574 \uAE30\uC5B5\uC5D0 \uB123\uC2B5\uB2C8\uB2E4. \uB044\uBA74 \uC694\uC57D\uC744 \uB9CC\uB4E4\uC9C0\uB3C4, \uB123\uC9C0\uB3C4 \uC54A\uC2B5\uB2C8\uB2E4.",
      "The extraction model summarizes every 8 turns and the story so far for memory. Off: none are written or used."
    ],
    "tune.canon_facts": ["\uC6D0\uC804\uC5D0\uC11C \uC0AC\uC2E4 \uC77D\uAE30", "Facts from canon"],
    "tune.canon_facts_hint": [
      "\uCD94\uCD9C \uBAA8\uB378\uC774 \uCE74\uB4DC\xB7\uD398\uB974\uC18C\uB098\xB7\uC791\uAC00 \uB178\uD2B8\uC640, \uD504\uB86C\uD504\uD2B8\uC5D0 \uD55C \uBC88\uC774\uB77C\uB3C4 \uB4E4\uC5B4\uAC04 \uB85C\uC5B4\uBD81 \uD56D\uBAA9\uC744 \uC77D\uC5B4 \uAE30\uC5B5\uC5D0 \uB123\uC2B5\uB2C8\uB2E4. \uC774\uC57C\uAE30\uAC00 \uC0C8\uB85C \uB9D0\uD558\uBA74 \uADF8 \uD134\uBD80\uD130 \uC774\uC57C\uAE30\uB97C \uB530\uB985\uB2C8\uB2E4. \uB044\uBA74 \uC77D\uC9C0\uB3C4, \uC4F0\uC9C0\uB3C4 \uC54A\uC2B5\uB2C8\uB2E4.",
      "The extraction model reads the card, the persona, the author's note and each lorebook entry a prompt has held, for memory. The story supersedes them. Off: none are read or used."
    ],
    // settings: parser rules
    "rules.title": ["\uC0C1\uD0DC\uCC3D \uADDC\uCE59", "Status-window rules"],
    "rules.where": [
      "\uCC44\uD305\uC758 \uC0C1\uD0DC\uCC3D\uC740 \uC778\uC2A4\uD399\uD130\uC758 \uADF8 \uCC44\uD305 \uD398\uC774\uC9C0\uC5D0\uC11C \uCC3E\uC544 \uCF2D\uB2C8\uB2E4. \uC544\uB798\uB294 \uBAA8\uB4E0 \uCE74\uB4DC\uC758 \uADDC\uCE59\uACFC \uC9C1\uC811 \uC4F0\uB294 \uADDC\uCE59\uC785\uB2C8\uB2E4.",
      "A chat's status window is found and turned on from that chat's Inspector page. Below: every card's rules, and rules written by hand."
    ],
    "rules.all_cards": ["\uBAA8\uB4E0 \uCE74\uB4DC\uC758 \uC0C1\uD0DC\uCC3D \uADDC\uCE59", "Every card's status rules"],
    "rules.advanced": ["\uACE0\uAE09: \uADDC\uCE59 \uC9C1\uC811 \uC4F0\uAE30 (JSON)", "Advanced: write rules by hand (JSON)"],
    "sw.title": ["\uC0C1\uD0DC\uCC3D (\uC774 \uCC44\uD305)", "Status window (this chat)"],
    "sw.sub": [
      '\uB2F5\uC7A5 \uB05D\uC758 [\uD0A4=\uAC12 | \uD0A4: \uAC12 \u2026] \uBAA8\uC591\uC744 \uCC3E\uC2B5\uB2C8\uB2E4. \uCF1C\uBA74 \uCE74\uB4DC "{card}"\uC758 \uB2E4\uB978 \uCC44\uD305\uC5D0\uC11C\uB3C4 \uAC19\uC740 \uBAA8\uC591\uC744 \uC77D\uC2B5\uB2C8\uB2E4.',
      'Looks for [key=value | key: value \u2026] at the end of replies. Once on, other chats of the card "{card}" with the same window are read too.'
    ],
    "sw.no_card": [
      "\uC774 \uCC44\uD305\uC758 \uCE90\uB9AD\uD130 \uC774\uB984\uC744 \uC544\uC9C1 \uBAB0\uB77C\uC11C \uCF24 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4. \uD55C \uBC88 \uB300\uD654\uD55C \uB4A4 \uB2E4\uC2DC \uC5EC\uC138\uC694.",
      "This chat's character name is not known yet; send a message, then open this page again."
    ],
    "sw.none": ["\uC0C1\uD0DC\uCC3D \uBAA8\uC591\uC774 \uBCF4\uC774\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4 (\uAC19\uC740 \uBAA8\uC591\uC774 \uB2F5\uC7A5 2\uBC88 \uC774\uC0C1 \uD544\uC694).", "No status window found (the same shape in at least two replies)."],
    "sw.found": ["\uD0A4 {n}\uAC1C\uC9DC\uB9AC \uC0C1\uD0DC\uCC3D \xB7 \uB2F5\uC7A5 {c}\uBC88", "A {n}-key status window \xB7 in {c} replies"],
    "sw.tracked": ["\uCD94\uC801 \uC911 \xB7 \uD0A4 {n}\uAC1C \xB7 \uB2F5\uC7A5 {c}\uBC88", "Tracked \xB7 {n} keys \xB7 in {c} replies"],
    "sw.track": ["\uCD94\uC801", "Track"],
    "sw.tracked_now": ['\uCD94\uC801\uD569\uB2C8\uB2E4. \uCE74\uB4DC "{card}"\uC758 \uCC44\uD305\uC5D0\uC11C \uC774 \uC0C1\uD0DC\uCC3D\uC744 \uC77D\uC2B5\uB2C8\uB2E4.', 'Tracking: chats of "{card}" read this window.'],
    "sw.untrack": ["\uCD94\uC801 \uD574\uC81C", "Stop tracking"],
    "sw.untracked": ["\uCD94\uC801\uC744 \uD574\uC81C\uD588\uC2B5\uB2C8\uB2E4.", "No longer tracked."],
    "sw.by_rule": ["\uCE74\uB4DC\uC5D0 \uC9C1\uC811 \uC4F4 \uADDC\uCE59\uC73C\uB85C \uC77D\uACE0 \uC788\uC2B5\uB2C8\uB2E4 (\uC124\uC815 \u2192 \uACE0\uAE09).", "Read by a rule written for the card (Settings \u2192 advanced)."],
    "sw.pins_sub": [
      "\u{1F4CC} \uACE0\uC815\uD55C \uD0A4\uB294 \uBC14\uB00C\uC9C0 \uC54A\uC544\uB3C4 \uB9E4\uBC88 \uAE30\uC5B5\uC5D0 \uB123\uC2B5\uB2C8\uB2E4. \uB0A0\uC9DC\xB7\uC2DC\uAC04\xB7\uC7A5\uC18C\uB294 \uB298 \uB123\uC2B5\uB2C8\uB2E4.",
      "Pinned keys are told every time, changed or not. Date, time and place always are."
    ],
    "sw.save_pins": ["\uACE0\uC815 \uC800\uC7A5", "Save pins"],
    "sw.pins_saved": ["\uACE0\uC815\uD55C \uD0A4\uB97C \uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4.", "Pins saved."],
    "rules.sub": [
      'block: \uC2DC\uC791~\uB05D \uC0AC\uC774\uC758 "\uD0A4: \uAC12" \uC904\uC744 \uC77D\uC2B5\uB2C8\uB2E4. entity_line\uC73C\uB85C [\uC778\uBB3C] \uC904\uB9C8\uB2E4 \uC778\uBB3C\uBCC4\uB85C \uB098\uB215\uB2C8\uB2E4 (\uC2DC\uBBAC\uBD07). regex: key/value \uC774\uB984 \uADF8\uB8F9.',
      'block: reads "key: value" lines between start and end; entity_line splits them per [character] line (sim bots). regex: named groups key/value.'
    ],
    "rules.example": ["\uC608\uC2DC \uB123\uAE30", "Insert example"],
    "rules.none": [
      "JSON \uD30C\uC77C\uC774\uB098 \uD504\uB9AC\uC14B\uC744 \uC120\uD0DD\uD558\uC138\uC694. \uC801\uC6A9 \uC804\uAE4C\uC9C0 \uD65C\uC131 \uADDC\uCE59\uC740 \uBC14\uB00C\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
      "Choose a JSON file or preset. Active rules stay unchanged until Apply."
    ],
    "rules.scope": [
      "\uCE90\uB9AD\uD130\uC758 \uD45C\uC2DC \uC774\uB984\uC5D0 \uC815\uD655\uD788 \uC5F0\uACB0\uD569\uB2C8\uB2E4. \uC774\uB984\uC774 \uAC19\uC740 \uCE74\uB4DC\uB294 \uADDC\uCE59\uC744 \uACF5\uC720\uD558\uC9C0\uB9CC \uB300\uD654\uBCC4 \uC0C1\uD0DC\uAC12\uC740 \uB530\uB85C \uC720\uC9C0\uD569\uB2C8\uB2E4.",
      "Rules match the character display name exactly. Same-name cards share rules; each chat keeps its own state."
    ],
    "rules.target": ["\uC801\uC6A9\uD560 \uCE90\uB9AD\uD130 \uC774\uB984", "Target character name"],
    "rules.choose_target": ["\uC801\uC6A9\uD560 \uCE90\uB9AD\uD130 \uC774\uB984\uC744 \uC9C1\uC811 \uC120\uD0DD\uD558\uAC70\uB098 \uC785\uB825\uD558\uC138\uC694.", "Choose or enter the target character name."],
    "rules.draft": ["\uADDC\uCE59 JSON \uCD08\uC548", "Rules JSON draft"],
    "rules.apply": ["\uC774 \uCE90\uB9AD\uD130\uC5D0 \uC801\uC6A9", "Apply to this character"],
    "rules.disable": ["\uC774 \uCE90\uB9AD\uD130\uC758 \uC0C1\uD0DC\uCC3D \uADDC\uCE59 \uD574\uC81C", "Disable rules for this character"],
    "rules.prepare_disable": ["\uD574\uC81C\uD560 \uBE48 \uADDC\uCE59 \uC900\uBE44", "Prepare empty rules to disable"],
    "rules.import": ["JSON \uD30C\uC77C \uC120\uD0DD", "Choose JSON file"],
    "rules.preset": ["\uC800\uC7A5\uB41C \uD504\uB9AC\uC14B", "Saved preset"],
    "rules.choose_preset": ["\uD504\uB9AC\uC14B \uC120\uD0DD\u2026", "Choose a preset\u2026"],
    "rules.preset_name": ["\uD504\uB9AC\uC14B \uC774\uB984", "Preset name"],
    "rules.save_preset": ["\uD504\uB9AC\uC14B \uC800\uC7A5\xB7\uC5C5\uB370\uC774\uD2B8", "Save or update preset"],
    "rules.remove_preset": ["\uC120\uD0DD\uD55C \uD504\uB9AC\uC14B \uC0AD\uC81C", "Remove selected preset"],
    "rules.preview": [
      "\uB300\uC0C1: {card} \xB7 \uADDC\uCE59 {n}\uAC1C. \uC801\uC6A9\uD558\uBA74 \uC774 \uCE90\uB9AD\uD130\uC758 \uADDC\uCE59\uB9CC \uAD50\uCCB4\uD569\uB2C8\uB2E4.",
      "Target: {card} \xB7 {n} rules. Apply replaces only this character\u2019s rules."
    ],
    "rules.binding": ["{card}: \uC5F0\uACB0\uB41C \uADDC\uCE59 {n}\uAC1C", "{card}: {n} bound rules"],
    "rules.unbound": [
      "\uBBF8\uC5F0\uACB0 \uADDC\uCE59 {n}\uAC1C\uB294 \uBE44\uD65C\uC131 \uC0C1\uD0DC\uC785\uB2C8\uB2E4. JSON\uC744 \uD655\uC778\uD558\uACE0 \uCE90\uB9AD\uD130\uC5D0 \uB2E4\uC2DC \uC5F0\uACB0\uD558\uC138\uC694.",
      "{n} unbound rules are inactive. Review their JSON and bind them to a character."
    ],
    "rules.no_active": ["\uC5F0\uACB0\uB41C \uC0C1\uD0DC\uCC3D \uADDC\uCE59\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.", "No bound status rules."],
    "rules.upgrade": [
      "\uC774 \uAE30\uB2A5\uC744 \uC4F0\uB824\uBA74 NMOS\uB97C \uC5C5\uB370\uC774\uD2B8\uD558\uC138\uC694. \uAE30\uC874 \uC804\uC5ED \uC800\uC7A5\uC73C\uB85C \uC801\uC6A9\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
      "Update NMOS to use this feature. The old global save will not be used."
    ],
    "rules.stored": ["\uC800\uC7A5\uB41C \uADDC\uCE59 JSON \uBCF4\uAE30", "View stored rules JSON"],
    "rules.blank": [
      "\uCD08\uC548\uC774 \uBE44\uC5B4 \uC788\uC2B5\uB2C8\uB2E4. \uBE48\uCE78\uC740 \uD65C\uC131 \uADDC\uCE59\uC744 \uBCC0\uACBD\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
      "The draft is blank. A blank draft does not change active rules."
    ],
    "rules.invalid_json": ["\uC62C\uBC14\uB978 JSON\uC744 \uC785\uB825\uD558\uC138\uC694.", "Enter valid JSON."],
    "rules.invalid_shape": [
      "rules \uBC30\uC5F4\uC5D0 \uADDC\uCE59 \uAC1D\uCCB4\uB97C \uB2F4\uC740 JSON\uC774 \uD544\uC694\uD569\uB2C8\uB2E4.",
      "Use a JSON object with a rules array containing rule objects."
    ],
    "rules.loaded": ["\uD30C\uC77C\uC744 \uCD08\uC548\uC73C\uB85C \uBD88\uB7EC\uC654\uC2B5\uB2C8\uB2E4. \uC544\uC9C1 \uC801\uC6A9\uD558\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4.", "File loaded into the draft; not applied."],
    "rules.applied": ["{card}\uC5D0 \uADDC\uCE59 {n}\uAC1C\uB97C \uC801\uC6A9\uD588\uC2B5\uB2C8\uB2E4.", "Applied {n} rules to {card}."],
    "rules.preset_saved": ["\uD504\uB9AC\uC14B \uBAA9\uB85D\uC744 \uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4. \uD65C\uC131 \uADDC\uCE59\uC740 \uADF8\uB300\uB85C\uC785\uB2C8\uB2E4.", "Preset library saved. Active rules are unchanged."],
    "rules.close_draft": [
      "\uC544\uC9C1 \uC801\uC6A9\uD558\uC9C0 \uC54A\uC740 \uC0C1\uD0DC\uCC3D \uCD08\uC548\uC774 \uC788\uC2B5\uB2C8\uB2E4. \uC801\uC6A9\uD558\uB824\uBA74 \uCDE8\uC18C \uD6C4 \uC0C1\uD0DC\uCC3D\uC758 \uC801\uC6A9 \uBC84\uD2BC\uC744 \uB204\uB974\uC138\uC694.",
      "There is an unapplied status draft. Cancel and use its Apply button to activate it."
    ],
    "rules.from_file": ["\uD30C\uC77C\uC5D0\uC11C \uADDC\uCE59 {n}\uAC1C\uB97C \uC77D\uB294 \uC911 (\uC5EC\uAE30\uC5D0 \uC800\uC7A5\uD558\uBA74 \uB300\uCCB4\uB429\uB2C8\uB2E4)", "Reading {n} rules from a file (saving here replaces them)"],
    // save bar
    "save": ["\uC800\uC7A5", "Save"],
    "revert": ["\uB418\uB3CC\uB9AC\uAE30", "Revert"],
    "saving": ["\uC800\uC7A5 \uC911\u2026", "Saving\u2026"],
    "saved": ["\uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4.", "Saved."],
    "saved_queued": ["\uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4. \uAE30\uC874 \uCC44\uD305 {n}\uAC74\uC744 \uBC31\uADF8\uB77C\uC6B4\uB4DC\uC5D0\uC11C \uCC98\uB9AC\uD569\uB2C8\uB2E4.", "Saved. {n} existing items are processed in the background."],
    "saved_rules": ["\uADDC\uCE59 {n}\uAC1C\uB97C \uC801\uC6A9\uD558\uACE0 \uAE30\uC874 \uBA54\uC2DC\uC9C0\uB97C \uB2E4\uC2DC \uC77D\uC5C8\uC2B5\uB2C8\uB2E4.", "{n} rules applied; existing messages were re-read."],
    "no_changes": ["\uBC14\uB010 \uB0B4\uC6A9\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.", "No changes."],
    "unsaved": ["\uC800\uC7A5\uD558\uC9C0 \uC54A\uC740 \uBCC0\uACBD: {s}", "Unsaved changes: {s}"],
    "close_unsaved": ["\uC800\uC7A5\uD558\uC9C0 \uC54A\uC740 \uBCC0\uACBD\uC774 \uC788\uC2B5\uB2C8\uB2E4.", "You have unsaved changes."],
    "save_and_close": ["\uC800\uC7A5\uD558\uACE0 \uB2EB\uAE30", "Save and close"],
    "discard_and_close": ["\uBC84\uB9AC\uACE0 \uB2EB\uAE30", "Discard and close"],
    "cancel": ["\uCDE8\uC18C", "Cancel"],
    "mc.title": ["\uCD94\uCD9C \uBAA8\uB378\uC774 \uBC14\uB01D\uB2C8\uB2E4. \uC774\uBBF8 \uCC98\uB9AC\uD55C \uCC44\uD305\uC740 \uC5B4\uB5BB\uAC8C \uD560\uAE4C\uC694?", "The extraction model changes. What about the chats already processed?"],
    "mc.continue": ["\uC774\uC5B4\uC4F0\uAE30: \uB2E4\uC2DC \uCC98\uB9AC\uD558\uC9C0 \uC54A\uACE0, \uC0C8 \uD134\uBD80\uD130 \uC0C8 \uBAA8\uB378\uC774 \uC77D\uC2B5\uB2C8\uB2E4 ({n}\uAC74)", "Carry on: nothing is redone; the new model reads from the next turn ({n} jobs)"],
    "mc.recent": ["\uCD5C\uADFC {t}\uD134 \uB2E4\uC2DC: \uCC44\uD305\uB9C8\uB2E4 \uCD5C\uADFC \uD134\uACFC \uADF8 \uC694\uC57D\uC744 \uC0C8 \uBAA8\uB378\uB85C \uB2E4\uC2DC \uB9CC\uB4ED\uB2C8\uB2E4 ({n}\uAC74)", "Redo the latest {t} turns: each chat's latest turns and their summaries, with the new model ({n} jobs)"],
    "mc.canon": ["\uC6D0\uC804(\uCE74\uB4DC\xB7\uB85C\uC5B4\uBD81)\uB3C4 \uC0C8 \uBAA8\uB378\uB85C \uB2E4\uC2DC \uC77D\uAE30 (+{n}\uAC74)", "Read the setting (card, lorebook) again with the new model (+{n} jobs)"],
    "mc.cancelled": ["\uC800\uC7A5\uD558\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4.", "Not saved."],
    "lang_unsaved": ["\uC5B8\uC5B4\uB97C \uBC14\uAFB8\uAE30 \uC804\uC5D0 \uBCC0\uACBD\uC744 \uC800\uC7A5\uD558\uAC70\uB098 \uB418\uB3CC\uB9AC\uC138\uC694.", "Save or revert your changes before switching the language."],
    "conn_saved_server_failed": ["\uC5F0\uACB0 \uC124\uC815\uC740 \uC800\uC7A5\uD588\uC9C0\uB9CC \uC11C\uBC84 \uC124\uC815\uC740 \uC800\uC7A5\uD558\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4: {e}", "Connection saved, but the server settings were not: {e}"],
    "conn_save_failed": [
      "\uC5F0\uACB0 \uC124\uC815 \uC800\uC7A5\uC744 \uB9C8\uCE58\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4({n}/{total}\uAC1C \uC800\uC7A5 \uD655\uC778). \uC11C\uBC84 \uC124\uC815\uC740 \uBCF4\uB0B4\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4. \uC800\uC7A5\uB41C \uC5F0\uACB0\uC744 \uD655\uC778\uD558\uAC70\uB098 \uB2E4\uC2DC \uC800\uC7A5\uD558\uC138\uC694: {e}",
      "Could not finish saving the connection ({n}/{total} settings confirmed saved). Server settings were not sent. Check the saved connection or retry: {e}"
    ],
    // progress display (HUD) on the chat screen
    "hud.recalling": ["\uAE30\uC5B5 \uBD88\uB7EC\uC624\uB294 \uC911\u2026", "Recalling memory\u2026"],
    "hud.injected": ["\u2713 \uAE30\uC5B5 \uC8FC\uC785 ({n}\uC790)", "\u2713 Memory injected ({n} chars)"],
    "hud.nothing": ["\u2013 \uAD00\uB828 \uAE30\uC5B5 \uC5C6\uC74C", "\u2013 Nothing relevant"],
    "hud.chat_off": ["\u23FB \uC774 \uCC44\uD305\uC740 NMOS \uAEBC\uC9D0", "\u23FB NMOS is off for this chat"],
    "hud.skipped": ["\u26A0 \uAC74\uB108\uB700: {r}", "\u26A0 Skipped: {r}"],
    "hud.reason.deadline": ["\uC81C\uD55C \uC2DC\uAC04 {s}\uCD08 \uCD08\uACFC \xB7 \uB20C\uB7EC\uC11C \uB298\uB9AC\uAE30", "over the {s} s deadline \xB7 tap to raise"],
    "hud.reason.error": ["\uC0AC\uC774\uB4DC\uCE74 \uC624\uB958", "sidecar error"],
    "hud.reason.no_turn": ["\uC774\uBC88 \uBA54\uC2DC\uC9C0\uB97C \uD504\uB86C\uD504\uD2B8\uC5D0\uC11C \uBABB \uCC3E\uC74C", "this message is not in the prompt"],
    "hud.extract": ["\uCD94\uCD9C {d}/{n}", "Facts {d}/{n}"],
    "hud.embed": ["\uC784\uBCA0\uB529 {d}/{n}", "Embeddings {d}/{n}"],
    "hud.summarize": ["\uC694\uC57D {n}\uAC1C \uB0A8\uC74C", "summaries to write: {n}"],
    "hud.failed": ["\u26A0 \uC2E4\uD328 {n}", "\u26A0 {n} failed"],
    "hud.done": ["\u2713 \uCC98\uB9AC \uC644\uB8CC", "\u2713 Processing done"],
    "hud.reused": [" \xB7 \uC7AC\uC0AC\uC6A9", " \xB7 reused"],
    "hud.lexical": [" \xB7 \uC5B4\uD718 \uAC80\uC0C9\uB9CC", " \xB7 lexical only"],
    "hud.rewritten": [" \xB7 \uC2A4\uD06C\uB9BD\uD2B8 \uC218\uC815 {n}\uAC1C \uBC18\uC601", " \xB7 {n} script-edited replies picked up"],
    "hud.made.facts": ["\uC0AC\uC2E4 {n}\uAC1C \uCD94\uAC00", "facts +{n}"],
    "hud.made.summaries": ["\uC694\uC57D {n}\uAC1C \uCD94\uAC00", "summaries +{n}"],
    // progress display: panel
    "hud.title": ["\uC9C4\uD589 \uD45C\uC2DC", "Progress display"],
    "hud.sub": [
      '\uCC44\uD305 \uD654\uBA74 \uC624\uB978\uCABD \uC704\uC5D0 \uAE30\uC5B5\uC774 \uB4E4\uC5B4\uAC14\uB294\uC9C0\uC640 \uBC31\uADF8\uB77C\uC6B4\uB4DC \uCC98\uB9AC \uC9C4\uD589\uC744 \uC791\uAC8C \uB744\uC6C1\uB2C8\uB2E4. \uCF1C\uBA74 PocketRisu\uAC00 "\uBA54\uC778 Document \uC811\uADFC" \uAD8C\uD55C\uC744 \uBB3B\uC2B5\uB2C8\uB2E4. NMOS\uB294 \uC774 \uAD8C\uD55C\uC73C\uB85C \uD45C\uC2DC \uD558\uB098\uB9CC \uADF8\uB9AC\uACE0 \uD654\uBA74 \uB0B4\uC6A9\uC740 \uC77D\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4. \uB204\uB974\uBA74 \uC774 \uD328\uB110\uC774 \uC5F4\uB9BD\uB2C8\uB2E4.',
      'Shows a small pill at the top right of the chat screen: whether memory went in, and background processing progress. Turning it on makes PocketRisu ask for "main Document" access. NMOS only draws the pill with it and reads nothing on the page. Tap the pill to open this panel.'
    ],
    "hud.toggle": ["\uCC44\uD305 \uD654\uBA74\uC5D0 \uC9C4\uD589 \uD45C\uC2DC \uB744\uC6B0\uAE30", "Show the progress display on the chat screen"],
    "hud.enable": ["\uC9C4\uD589 \uD45C\uC2DC \uCF1C\uAE30", "Turn on progress display"],
    "hud.hint": [
      "\uC9C4\uD589 \uD45C\uC2DC\uAC00 \uAEBC\uC838 \uC788\uC2B5\uB2C8\uB2E4. \uCF1C\uBA74 \uAE30\uC5B5\uC774 \uB4E4\uC5B4\uAC14\uB294\uC9C0 \uCC44\uD305 \uD654\uBA74\uC5D0\uC11C \uBC14\uB85C \uBCF4\uC785\uB2C8\uB2E4.",
      "The progress display is off. Turn it on to see on the chat screen whether memory went in."
    ],
    "hud.on": ["\uCF30\uC2B5\uB2C8\uB2E4. \uB2E4\uC74C \uBA54\uC2DC\uC9C0\uBD80\uD130 \uD45C\uC2DC\uB429\uB2C8\uB2E4.", "On. It shows from the next message."],
    "hud.off": ["\uAED0\uC2B5\uB2C8\uB2E4.", "Off."],
    "hud.denied": [
      '\uAD8C\uD55C\uC774 \uAC70\uBD80\uB418\uC5B4 \uCF1C\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4. PocketRisu\uB294 \uAC70\uBD80\uB97C \uAE30\uC5B5\uD569\uB2C8\uB2E4. \uC124\uC815 \u2192 \uD50C\uB7EC\uADF8\uC778 \u2192 NMOS \uC904\uC758 \uBA54\uB274 \u2192 "\uAD8C\uD55C \uC751\uB2F5 \uCD08\uAE30\uD654" \uD6C4 \uB2E4\uC2DC \uCF1C\uC138\uC694.',
      "Permission was denied, so it stays off. PocketRisu remembers a denial: Settings \u2192 Plugin \u2192 the NMOS row menu \u2192 reset permission responses, then turn it on again."
    ],
    "hud.unsupported": [
      "\uC774 PocketRisu \uBC84\uC804\uC740 \uD50C\uB7EC\uADF8\uC778\uC774 \uCC44\uD305 \uD654\uBA74\uC5D0 \uD45C\uC2DC\uB97C \uADF8\uB9AC\uB294 \uAE30\uB2A5\uC744 \uC9C0\uC6D0\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
      "This PocketRisu version does not let plugins draw on the chat screen."
    ],
    "hud.broken": ["\uC9C4\uD589 \uD45C\uC2DC\uB97C \uADF8\uB9AC\uC9C0 \uBABB\uD574 \uC774\uBC88 \uC138\uC158\uC5D0\uC11C\uB294 \uBA48\uCDC4\uC2B5\uB2C8\uB2E4: {e}", "The progress display stopped for this session: {e}"],
    "invalid": ["\uC785\uB825 \uC624\uB958: ", "Invalid: "],
    "sidecar_error": ["\uC0AC\uC774\uB4DC\uCE74 \uC624\uB958: ", "Sidecar error: "],
    // PHASE-59: unified navigation, chat switcher, memory sub-tabs, Author's Note studio, 2-column settings
    "nav.home": ["\uD648", "Home"],
    "nav.memory": ["\uAE30\uC5B5", "Memory"],
    "nav.notes": ["\uC791\uAC00\uC758 \uB178\uD2B8", "Author's Note"],
    "nav.settings": ["\uC124\uC815", "Settings"],
    "shell.switch_chat": ["\uCC44\uD305 \uC804\uD658", "Switch chat"],
    "shell.no_chat": ["\uC120\uD0DD\uB41C \uCC44\uD305 \uC5C6\uC74C", "No chat selected"],
    "shell.search_chat": ["\uCE90\uB9AD\uD130 \uB610\uB294 \uCC44\uD305 \uAC80\uC0C9\u2026", "Search character or chat\u2026"],
    "shell.chats_empty": ["\uAE30\uB85D\uB41C \uCC44\uD305\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.", "No recorded chats yet."],
    "shell.chats_all": ["\uBAA8\uB4E0 \uCC44\uD305 \uBCF4\uAE30", "View all chats"],
    "shell.status_ok": ["\uC815\uC0C1 \uC791\uB3D9", "Healthy"],
    "shell.status_working": ["\uCC98\uB9AC \uC911", "Working"],
    "shell.status_warn": ["\uD655\uC778 \uD544\uC694", "Attention"],
    "shell.status_off": ["\uAEBC\uC9D0", "Off"],
    "shell.status_err": ["\uC5F0\uACB0 \uB04A\uAE40", "Offline"],
    "home.chat_on_badge": ["\uC774 \uCC44\uD305 \uAE30\uC5B5 ON", "Memory ON"],
    "home.chat_off_badge": ["\uC774 \uCC44\uD305 \uAE30\uC5B5 OFF", "Memory OFF"],
    "home.all_off_badge": ["\uC804\uCCB4 \uAE30\uC5B5 \uAEBC\uC9D0", "All memory OFF"],
    "mem.story": ["\uC2A4\uD1A0\uB9AC \uBB38\uC11C", "Story document"],
    "mem.story_sub": [
      "\uD604\uC7AC \uC7A5\uBA74, \uC9C4\uD589 \uC911\uC778 \uB5A1\uBC25, \uC124\uC815 \uBCC0\uACBD\uACFC \uC778\uBB3C \uC694\uC57D\uC744 \uBB38\uC11C\uCC98\uB7FC \uC77D\uACE0 \uBC14\uB85C \uC218\uC815\uD569\uB2C8\uB2E4.",
      "Read the current scene, open threads, setting changes and cast like a document, and fix lines inline."
    ],
    "mem.map": ["\uC778\uBB3C \xB7 \uAD00\uACC4\uB3C4", "Cast & Map"],
    "mem.map_sub": [
      "\uB4F1\uC7A5\uC778\uBB3C \uAC04\uC758 \uAD00\uACC4\uC640 \uC0AC\uAC74\uC758 \uCD9C\uCC98(\uC124\uC815 vs \uC774\uC57C\uAE30)\uB97C \uD55C\uB208\uC5D0 \uD0D0\uC0C9\uD569\uB2C8\uB2E4.",
      "Explore character ties, places, and what came from the setting versus the story."
    ],
    "mem.attention": ["\uD655\uC778 \uD544\uC694", "Needs attention"],
    "mem.attention_sub": [
      "\uC124\uC815\uC774 \uCDA9\uB3CC\uD558\uAC70\uB098 \uC624\uB798\uB41C \uB5A1\uBC25, \uBCF4\uB958\uB41C \uBCC4\uCE6D\uC744 \uAC80\uD1A0\uD558\uACE0 \uC77C\uAD04 \uC815\uB9AC\uD569\uB2C8\uB2E4.",
      "Review conflicts, stale threads, and held aliases, and settle them in bulk."
    ],
    "mem.diag": ["\uC6D0\uBCF8 \xB7 \uC9C4\uB2E8", "Working & Raw"],
    "mem.diag_sub": [
      "\uBC31\uADF8\uB77C\uC6B4\uB4DC \uCD94\uCD9C\xB7\uC784\uBCA0\uB529 \uC9C4\uD589 \uC0C1\uD0DC, \uC2E4\uD328\uD55C \uC791\uC5C5 \uC7AC\uC2DC\uB3C4, \uC6D0\uBCF8 \uC778\uC2A4\uD399\uD130\uB97C \uD655\uC778\uD569\uB2C8\uB2E4.",
      "Check extraction and embedding progress, retry failed jobs, or inspect raw memory records."
    ],
    "mem.diag_working": ["\uCC98\uB9AC \uC0C1\uD0DC", "Working status"],
    "mem.diag_raw": ["\uC6D0\uBCF8 \uC778\uC2A4\uD399\uD130", "Raw inspector"],
    "mem.no_chat": ["\uBA3C\uC800 \uC0C1\uB2E8\uC5D0\uC11C \uCC44\uD305\uC744 \uC120\uD0DD\uD558\uAC70\uB098 \uD648\uC5D0\uC11C \uB300\uD654\uB97C \uC5F4\uC5B4 \uC8FC\uC138\uC694.", "Select a chat from the top switcher or open one from Home."],
    "notes.studio_sub": [
      "\uD604\uC7AC \uCC44\uD305\uC758 \uAE30\uC5B5\uC744 \uBC14\uD0D5\uC73C\uB85C \uC791\uAC00\uC758 \uB178\uD2B8\uC5D0 \uBD99\uC5EC\uB123\uC744 \uC694\uC57D\uC744 \uB9CC\uB4ED\uB2C8\uB2E4. \uCCB4\uD06C\uD55C \uD56D\uBAA9\uB9CC \uC0DD\uC131\uB429\uB2C8\uB2E4.",
      "Generate a ready-to-paste summary for the Author's Note from this chat's memory. Only checked parts run."
    ],
    "notes.config_head": ["\uD3EC\uD568\uD560 \uD56D\uBAA9 \uC120\uD0DD", "Sections to include"],
    "notes.preview_head": ["\uC0DD\uC131 \uACB0\uACFC \uBBF8\uB9AC\uBCF4\uAE30", "Generated preview"],
    "notes.badge_llm": ["\uBAA8\uB378 1\uD68C \uD638\uCD9C", "1 model call"],
    "notes.badge_free": ["\uBB34\uB8CC \xB7 \uC989\uC2DC", "Free \xB7 instant"],
    "notes.badge_unchecked": ["\uBBF8\uAC80\uC99D \xB7 \uBAA8\uB378 1\uD68C", "Unchecked \xB7 1 call"],
    "notes.desc_diverged": [
      "\uCE90\uB9AD\uD130 \uCE74\uB4DC\xB7\uB85C\uC5B4\uBD81 \uC6D0\uC804\uACFC \uB2EC\uB77C\uC9C4 \uAD00\uACC4\xB7\uC0C1\uD0DC\xB7\uBCC0\uD654\uB97C \uC815\uB9AC\uD569\uB2C8\uB2E4.",
      "Summarizes what changed from the character card and lorebook setting."
    ],
    "notes.desc_chronicle": [
      "\uC7A5\uBA74 \uC694\uC57D\uB4E4\uC744 \uC5EE\uC5B4 \uC9C0\uAE08\uAE4C\uC9C0\uC758 \uC904\uAC70\uB9AC\uB97C \uC5F0\uB300\uAE30\uB85C \uC501\uB2C8\uB2E4.",
      "Weaves scene summaries into a chronicle of the story so far."
    ],
    "notes.desc_address": [
      "\uC778\uBB3C \uAC04 \uD638\uCE6D, \uB9D0\uD22C, \uC785\uC7A5 \uAD00\uACC4\uB97C \uAE30\uC5B5\uC5D0\uC11C \uADF8\uB300\uB85C \uC870\uB9BD\uD569\uB2C8\uB2E4.",
      "Assembles forms of address and standings directly from memory."
    ],
    "notes.desc_custom": [
      "\uC9C1\uC811 \uC4F4 \uC9C0\uC2DC\uBB38\uC73C\uB85C \uAE30\uC5B5\uC744 \uC694\uC57D\uD569\uB2C8\uB2E4. \uC6D0\uC804 \uB300\uC870 \uAC80\uC99D\uC740 \uAC70\uCE58\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
      "Summarizes memory using your own prompt, without canon verification."
    ],
    "notes.calls_est": ["\uC608\uC0C1 \uD638\uCD9C: \uBAA8\uB378 {n}\uD68C", "Estimated: {n} model call(s)"],
    "notes.calls_free": ["\uC608\uC0C1 \uD638\uCD9C: \uBAA8\uB378 \uD638\uCD9C \uC5C6\uC74C (\uC989\uC2DC \uC0DD\uC131)", "Estimated: no model calls (instant)"],
    "notes.empty_hint": [
      "\uC67C\uCABD\uC5D0\uC11C \uD3EC\uD568\uD560 \uD56D\uBAA9\uC744 \uACE0\uB978 \uB4A4 [\uC791\uAC00\uC758 \uB178\uD2B8 \uB9CC\uB4E4\uAE30]\uB97C \uB204\uB974\uBA74 \uACB0\uACFC\uAC00 \uC5EC\uAE30\uC5D0 \uD45C\uC2DC\uB429\uB2C8\uB2E4.",
      "Choose sections on the left and press Make author's note \u2014 your result appears here."
    ],
    "notes.no_chat": [
      "\uC791\uAC00\uC758 \uB178\uD2B8\uB97C \uB9CC\uB4E4 \uCC44\uD305\uC774 \uC544\uC9C1 \uC120\uD0DD\uB418\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4. \uC0C1\uB2E8\uC5D0\uC11C \uCC44\uD305\uC744 \uC120\uD0DD\uD574 \uC8FC\uC138\uC694.",
      "No chat is selected yet. Pick a chat from the top switcher first."
    ],
    "set.scope_chat": ["\uC774 \uCC44\uD305 \uC804\uC6A9", "This chat"],
    "set.scope_global": ["\uC804\uCCB4 \uC2DC\uC2A4\uD15C \uC124\uC815", "Global settings"],
    "set.maint_title": ["\uB370\uC774\uD130 \uC720\uC9C0\uBCF4\uC218", "Chat maintenance"],
    "set.maint_sub": [
      "\uC774 \uCC44\uD305\uC5D0 \uC800\uC7A5\uB41C \uAE30\uC5B5\uC744 \uCD94\uCD9C\xB7\uC7AC\uAD6C\uCD95\xB7\uBC31\uC5C5\uD558\uAC70\uB098 \uC0AD\uC81C\uD569\uB2C8\uB2E4. \uBE44\uC6A9\uACFC \uC704\uD5D8\uB3C4\uB97C \uBA3C\uC800 \uD655\uC778\uD558\uC138\uC694.",
      "Extract, rebuild, export, or delete memory stored for this chat. Check cost and risk first."
    ],
    "set.badge_llm": ["\uBAA8\uB378 \uD638\uCD9C", "LLM calls"],
    "set.badge_local": ["\uB85C\uCEEC \xB7 \uC548\uC804", "Local \xB7 safe"],
    "set.badge_warn": ["\uAE30\uC874 \uC0AC\uC2E4 \uB36E\uC5B4\uC500", "Rebuilds facts"],
    "set.badge_danger": ["\uBCF5\uAD6C \uBD88\uAC00", "Irreversible"],
    "set.act_history_desc": [
      "\uC544\uC9C1 \uCD94\uCD9C\uD558\uC9C0 \uC54A\uC740 \uACFC\uAC70 \uB300\uD654 \uD134\uC744 \uBC31\uADF8\uB77C\uC6B4\uB4DC\uC5D0\uC11C \uC77D\uC2B5\uB2C8\uB2E4.",
      "Queues older turns that have not been extracted yet."
    ],
    "set.act_retry_desc": [
      "\uC624\uB958\uB85C \uBA48\uCD98 \uCD94\uCD9C\xB7\uC784\uBCA0\uB529 \uC791\uC5C5\uB9CC \uB2E4\uC2DC \uC2DC\uB3C4\uD569\uB2C8\uB2E4.",
      "Retries only failed extraction or embedding jobs."
    ],
    "set.act_rebuild_desc": [
      "\uC774 \uCC44\uD305\uC758 \uAE30\uC874 \uCD94\uCD9C \uC0AC\uC2E4\uC744 \uBE44\uC6B0\uACE0 \uC804\uCCB4\uB97C \uCC98\uC74C\uBD80\uD130 \uB2E4\uC2DC \uCD94\uCD9C\uD569\uB2C8\uB2E4.",
      "Discards extracted facts for this chat and re-extracts from scratch."
    ],
    "set.act_export_desc": [
      "\uC774 \uCC44\uD305\uC758 \uAE30\uC5B5\uACFC \uBA54\uC2DC\uC9C0\uB97C \uBC31\uC5C5 \uC544\uCE74\uC774\uBE0C(.nmos.zip)\uB85C \uB0B4\uB824\uBC1B\uC2B5\uB2C8\uB2E4.",
      "Downloads a backup archive (.nmos.zip) of this chat."
    ],
    "set.act_delete_desc": [
      "NMOS\uC5D0 \uC800\uC7A5\uB41C \uC774 \uCC44\uD305\uC758 \uBAA8\uB4E0 \uAE30\uC5B5\uACFC \uAE30\uB85D\uC744 \uC601\uAD6C \uC0AD\uC81C\uD569\uB2C8\uB2E4.",
      "Permanently deletes everything NMOS recorded for this chat."
    ],
    // trimming old dialogue (PHASE-60 S1)
    "trim.left_out": ["\uC624\uB798\uB41C \uB300\uD654 {n}\uAC1C\uB97C \uBE7C\uACE0 \uBCF4\uB0C8\uC2B5\uB2C8\uB2E4 (\uC57D {t}\uD1A0\uD070 \uC808\uC57D)", "Left out {n} old messages (about {t} tokens saved)"],
    "trim.kept": ["\uC624\uB798\uB41C \uB300\uD654\uB97C \uBE7C\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4: {r}", "No old messages left out: {r}"],
    "trim.recorded_through": ["\uAE30\uC5B5\uC740 {n}\uD134\uAE4C\uC9C0 \uAE30\uB85D\uB418\uC5B4 \uC788\uC2B5\uB2C8\uB2E4", "Memory is recorded through turn {n}"],
    // settings: leaving out old dialogue (PHASE-60 S1)
    "trimset.title": ["\uC624\uB798\uB41C \uB300\uD654 \uBE7C\uAE30", "Leave out old dialogue"],
    "trimset.sub": [
      "\uAE30\uC5B5\uC774 \uC774\uBBF8 \uB2F4\uACE0 \uC788\uB294 \uC624\uB798\uB41C \uB300\uD654\uB294 \uBCF4\uB0B4\uB294 \uB0B4\uC6A9\uC5D0\uC11C \uBE8D\uB2C8\uB2E4. \uBE7C\uB294 \uC9C0\uC810\uC740 \uC544\uB798 \uD134 \uC218\uB9CC\uD07C\uC529 \uD55C\uAEBC\uBC88\uC5D0 \uC62E\uACA8\uC11C, \uC81C\uACF5\uC790\uC758 \uD504\uB86C\uD504\uD2B8 \uCE90\uC2DC\uAC00 \uACC4\uC18D \uB9DE\uC2B5\uB2C8\uB2E4. \uCC44\uD305\uC5D0\uC11C\uB294 \uC544\uBB34\uAC83\uB3C4 \uC9C0\uC6B0\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4. \uC7A5\uBA74 \uC694\uC57D \uB9CC\uB4E4\uAE30\uAC00 \uCF1C\uC838 \uC788\uC5B4\uC57C \uD569\uB2C8\uB2E4.",
      "Old dialogue that memory already holds is left out of what is sent, in steps of the number of turns below, so the provider's prompt cache keeps working. Nothing is removed from the chat. It needs Scene summaries on."
    ],
    "trimset.on": ["\uAE30\uC5B5\uC774 \uB2F4\uC740 \uC624\uB798\uB41C \uB300\uD654 \uBE7C\uAE30", "Leave out old dialogue memory holds"],
    "trimset.keep": ["\uD56D\uC0C1 \uBCF4\uB0B4\uB294 \uCD5C\uADFC \uD134 \uC218", "Recent turns always sent"],
    "trimset.needs_summaries": [
      "\uC8FC\uC758: \uC7A5\uBA74 \uC694\uC57D \uB9CC\uB4E4\uAE30\uAC00 \uAEBC\uC838 \uC788\uC5B4\uC11C, \uCF1C\uAE30 \uC804\uAE4C\uC9C0\uB294 \uC544\uBB34\uAC83\uB3C4 \uBE7C\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
      "Note: Scene summaries are off, so nothing is left out until they are on."
    ],
    // pinning a character (PHASE-60 S8)
    "tune.pin_at": ["\uBA54\uC2DC\uC9C0\uC5D0\uC11C @\uC774\uB984\uC73C\uB85C \uC778\uBB3C \uACE0\uC815", "Pin a character with @name in a message"],
    "tune.pin_at_hint": [
      '\uCF1C\uBA74 "@\uC138\uB77C \uC5B4\uB514 \uC788\uC5B4?"\uCC98\uB7FC \uBA54\uC2DC\uC9C0\uC5D0 @\uC774\uB984\uC73C\uB85C \uC4F4 \uC778\uBB3C\uC740, \uC7A5\uBA74\uC5D0 \uC774\uB984\uC774 \uB098\uC624\uC9C0 \uC54A\uC544\uB3C4 \uADF8 \uB2F5\uC7A5\uC758 \uAE30\uC5B5\uC5D0 \uB4E4\uC5B4\uAC11\uB2C8\uB2E4. \uB2E8\uC5B4 \uC548\uC758 @(\uC774\uBA54\uC77C \uC8FC\uC18C, \uC544\uC774\uB514)\uB098 \uC774 \uCC44\uD305\uC758 \uC778\uBB3C\uC774 \uC544\uB2CC \uC774\uB984 \uC55E\uC758 @\uB294 \uC544\uBB34 \uC77C\uB3C4 \uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.',
      'On: a message like "@Sera where are you?" keeps Sera in memory for that reply even when the scene does not name her. An @ inside a word (an e-mail address, a handle) or before a name that is no character of this chat does nothing.'
    ],
    "pin.title": ["{n} \uACE0\uC815", "Pin {n}"],
    "pin.toggle": ["\uD56D\uC0C1 \uAE30\uC5B5\uC5D0 \uB450\uAE30", "Always keep in memory"],
    "pin.sub": [
      "\uACE0\uC815\uD55C \uC778\uBB3C\uC758 \uD604\uC7AC \uC0AC\uC2E4\uC740 \uC7A5\uBA74\uC5D0 \uC774\uB984\uC774 \uB098\uC624\uC9C0 \uC54A\uC544\uB3C4 \uB9E4 \uB2F5\uC7A5\uC758 \uAE30\uC5B5\uC5D0 \uB4E4\uC5B4\uAC11\uB2C8\uB2E4. \uADF8\uB798\uC11C \uACE0\uC815\uC740 \uC694\uCCAD\uB9C8\uB2E4 \uAE30\uC5B5 \uC608\uC0B0\uC758 \uC77C\uBD80\uB97C \uC501\uB2C8\uB2E4. \uC5B8\uC81C\uB4E0 \uD480 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
      "A pinned character's current facts go into memory on every reply, even when the scene does not name them, so a pin uses part of the memory budget on every request. You can take it off any time."
    ],
    "pin.done": ["\uACE0\uC815\uD588\uC2B5\uB2C8\uB2E4", "Pinned"],
    "pin.undone": ["\uACE0\uC815\uC744 \uD480\uC5C8\uC2B5\uB2C8\uB2E4", "Unpinned"],
    "pins.title": ["\uACE0\uC815\uD55C \uC778\uBB3C", "Pinned characters"],
    "pins.unpin": ["\uACE0\uC815 \uD480\uAE30", "Unpin"],
    "pins.none": ["\uACE0\uC815\uD55C \uC778\uBB3C\uC774 \uC5C6\uC2B5\uB2C8\uB2E4. \uC778\uBB3C \uD398\uC774\uC9C0\uC5D0\uC11C \uACE0\uC815\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.", "No pinned characters. Pin one from a person's page."],
    "pins.failed": ["\uACE0\uC815\uD55C \uC778\uBB3C \uBAA9\uB85D\uC744 \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4.", "Could not load the pinned characters."],
    "hud.trim.left_out": [" \xB7 \uC624\uB798\uB41C \uB300\uD654 {n}\uAC1C \uBE8C (\uC57D {t}\uD1A0\uD070)", " \xB7 {n} old messages left out (~{t} tokens)"],
    "hud.trim.kept": [" \xB7 \uB300\uD654 \uADF8\uB300\uB85C: {r}", " \xB7 dialogue kept: {r}"],
    "trim.reason.format": ["\uD504\uB9AC\uC14B\uC774 \uB300\uD654\uB97C \uBA54\uC2DC\uC9C0\uBCC4\uB85C \uBCF4\uB0B4\uC9C0 \uC54A\uC544 \uC548\uC804\uD558\uAC8C \uBE84 \uC218 \uC5C6\uC74C", "the preset does not send the chat one message at a time"],
    "trim.reason.short": ["\uC544\uC9C1 \uBE84 \uB9CC\uD07C \uAE38\uC9C0 \uC54A\uC74C", "the chat is not long enough yet"],
    "trim.reason.uncovered": ["\uAE30\uC5B5 \uC815\uB9AC(\uCD94\uCD9C\xB7\uC694\uC57D)\uAC00 \uC544\uC9C1 \uB530\uB77C\uC624\uC9C0 \uBABB\uD568", "memory (extraction and summaries) has not caught up yet"],
    "trim.reason.no_summaries": ["\uC694\uC57D\uC774 \uAEBC\uC838 \uC788\uC74C (\uC694\uC57D\uC774 \uD544\uC694\uD569\uB2C8\uB2E4)", "summaries are off (trimming needs them)"],
    "trim.reason.stale": ["\uAE30\uC5B5\uC774 \uC774 \uCC44\uD305\uC758 \uCD5C\uC2E0 \uC0C1\uD0DC\uAC00 \uC544\uB2D8", "memory is not at the chat's latest state"],
    "trim.reason.empty_packet": ["\uC774\uBC88\uC5D0 \uB123\uC744 \uAE30\uC5B5\uC774 \uC5C6\uC74C", "no memory for this request"],
    "trim.reason.failed": ["NMOS\uC758 \uB2F5\uC744 \uBC1B\uC9C0 \uBABB\uD568", "no answer from NMOS"],
    "trim.reason.unsupported": ["NMOS\uAC00 \uC774 \uAE30\uB2A5\uC744 \uC9C0\uC6D0\uD558\uC9C0 \uC54A\uC74C (\uC5C5\uB370\uC774\uD2B8 \uD544\uC694)", "NMOS does not support it yet (update it)"],
    "trim.reason.other": ["\uAE30\uD0C0 ({r})", "other ({r})"],
    // carrying another chat's memory (PHASE-60 S6)
    "carry.title": ["\uC774\uC804 \uCC44\uD305 \uC774\uC5B4\uBC1B\uAE30", "Carry an earlier chat's memory"],
    "carry.sub": [
      "\uB2E4\uB978 \uCC44\uD305\uC758 \uAE30\uC5B5\uC744 \uC9C0\uAE08 \uD55C \uBC88 \uC77D\uC5B4 \uC774 \uCC44\uD305\uC5D0 \uC5F0\uACB0\uD569\uB2C8\uB2E4. \uC6D0\uBCF8 \uCC44\uD305\uC740 \uAC74\uB4DC\uB9AC\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
      "Read another chat's memory once now and link it to this chat. Neither chat is modified."
    ],
    "carry.policy_note": [
      "\uC774\uC5B4\uBC1B\uC740 \uAE30\uC5B5\uC740 \uC0AC\uC774\uB4DC\uCE74\uC5D0\uC11C \uC0C8 \uAE30\uC5B5 \uC815\uCC45(packet-v20)\uC744 \uC120\uD0DD\uD55C \uB3D9\uC548\uC5D0\uB9CC \uB2F5\uC7A5\uC5D0 \uBC18\uC601\uB418\uBA70, \uD328\uB110 \uD654\uBA74\uC5D0\uC11C\uB294 \uC815\uCC45\uACFC \uC0C1\uAD00\uC5C6\uC774 \uC5F0\uACB0\uC774 \uBCF4\uC785\uB2C8\uB2E4.",
      "Carried memory reaches replies only while the new memory policy (packet-v20) is selected on the sidecar; the panel screens show the link either way."
    ],
    "carry.source": ["\uC6D0\uBCF8 \uCC44\uD305", "Source chat"],
    "carry.no_other": ["\uC774\uC5B4\uBC1B\uC744 \uB2E4\uB978 \uCC44\uD305\uC774 \uC544\uC9C1 \uC5C6\uC2B5\uB2C8\uB2E4.", "No other recorded chats are available to carry from."],
    "carry.mode": ["\uC774\uC5B4\uBC1B\uAE30 \uBC29\uC2DD", "Mode"],
    "carry.mode_continue": ["\uC774\uC5B4\uAC00\uAE30", "Continue"],
    "carry.mode_continue_desc": [
      "\uC774 \uCC44\uD305\uC774 \uADF8 \uCC44\uD305\uC758 \uC774\uC57C\uAE30\uB97C \uC774\uC5B4\uAC11\uB2C8\uB2E4: \uADF8\uCABD\uC758 \uC0AC\uC2E4\xB7\uAD00\uACC4\xB7\uC5F4\uB9B0 \uC57D\uC18D\uACFC \uC9C0\uAE08\uAE4C\uC9C0\uC758 \uC774\uC57C\uAE30\uAC00 \uC774 \uCC44\uD305\uC774 \uC2DC\uC791\uB418\uAE30 \uC804\uC758 \uAE30\uC5B5\uC774 \uB429\uB2C8\uB2E4.",
      "This chat continues that story: its facts, ties, open threads and story so far become memory from before this chat began."
    ],
    "carry.mode_regression": ["\uD68C\uADC0", "Regression"],
    "carry.mode_regression_desc": [
      "\uC774\uC57C\uAE30\uAC00 \uCC98\uC74C\uBD80\uD130 \uB2E4\uC2DC \uC2DC\uC791\uB410\uACE0, \uACE0\uB978 \uC778\uBB3C\uB9CC \uC774\uC804 \uD0C0\uC784\uB77C\uC778\uC744 \uAE30\uC5B5\uD569\uB2C8\uB2E4. \uB2E4\uB978 \uB204\uAD6C\uB3C4 \uBAA8\uB974\uBA70, \uC9C0\uAE08\uB3C4 \uC0AC\uC2E4\uC774\uB77C\uB294 \uBCF4\uC7A5\uC740 \uC5C6\uC2B5\uB2C8\uB2E4.",
      "The story began again from the start, and only the chosen characters remember the previous timeline. Nobody else knows it, and it may not hold now."
    ],
    "carry.cutoff": ["\uC5B4\uB514\uAE4C\uC9C0 \uC77D\uC744\uC9C0 (\uD134 \uBC88\uD638, \uBE44\uC6B0\uBA74 \uB05D\uAE4C\uC9C0)", "Stop at turn (optional, leave empty for the end)"],
    "carry.cutoff_placeholder": ["\uBE44\uC6B0\uBA74 \uD604\uC7AC \uB05D\uAE4C\uC9C0", "Empty = current end"],
    "carry.cutoff_invalid": ["\uD134 \uBC88\uD638\uB294 0 \uC774\uC0C1\uC758 \uC815\uC218\uB85C \uC785\uB825\uD558\uAC70\uB098 \uBE44\uC6CC \uB450\uC138\uC694.", "Enter a whole turn number (0 or more), or leave empty."],
    "carry.preview_btn": ["\uBBF8\uB9AC \uBCF4\uAE30", "Preview"],
    "carry.link_btn": ["\uC5F0\uACB0", "Link"],
    "carry.read_again": ["\uB2E4\uC2DC \uC77D\uAE30", "Read again"],
    "carry.unlink": ["\uC5F0\uACB0 \uD574\uC81C", "Unlink"],
    "carry.unlink_confirm": ["\uD55C \uBC88 \uB354 \uB204\uB974\uBA74 \uC5F0\uACB0 \uD574\uC81C", "Tap again to unlink"],
    "carry.linked_badge": ["\uC5F0\uACB0\uB428", "Linked"],
    "carry.linked": ["\uC774\uC804 \uCC44\uD305\uC758 \uAE30\uC5B5\uC744 \uC5F0\uACB0\uD588\uC2B5\uB2C8\uB2E4.", "Linked the earlier chat's memory."],
    "carry.unlinked": ["\uC5F0\uACB0\uC744 \uD574\uC81C\uD588\uC2B5\uB2C8\uB2E4. \uC774\uC804 \uC5F0\uACB0 \uAE30\uB85D\uC740 \uB0A8\uC544 \uC788\uC2B5\uB2C8\uB2E4.", "Unlinked. The earlier link is kept for the record."],
    "carry.loading": ["\uBBF8\uB9AC \uBCF4\uAE30\uB97C \uBD88\uB7EC\uC624\uB294 \uC911\u2026", "Loading preview\u2026"],
    "carry.pv_title": ["\uC774\uC5B4\uBC1B\uC744 \uAE30\uC5B5 \uBBF8\uB9AC \uBCF4\uAE30", "Preview of carried memory"],
    "carry.pv_source": ["\uC6D0\uBCF8: {source} \xB7 {mode} \xB7 {cutoff}", "Source: {source} \xB7 {mode} \xB7 {cutoff}"],
    "carry.pv_counts": [
      "\uC0AC\uC2E4 {f}\uAC1C \xB7 \uC774\uB984/\uBCC4\uCE6D {a}\uAC1C \xB7 \uC5F4\uB9B0 \uC57D\uC18D {th}\uAC1C \xB7 \uC9C0\uAE08\uAE4C\uC9C0\uC758 \uC774\uC57C\uAE30: {story}",
      "{f} facts \xB7 {a} names/aliases \xB7 {th} open threads \xB7 story so far: {story}"
    ],
    "carry.story_yes": ["\uD3EC\uD568", "included"],
    "carry.story_no": ["\uD3EC\uD568 \uC548 \uB428", "not included"],
    "carry.pv_lines": ["\uC774\uC5B4\uBC1B\uC744 \uAE30\uC5B5 \uC55E\uBD80\uBD84", "First lines"],
    "carry.pv_lines_empty": ["\uC774\uC5B4\uBC1B\uC744 \uAE30\uC5B5 \uC904\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.", "No memory lines to carry."],
    "carry.pv_chars": ["\uC774\uC804 \uD0C0\uC784\uB77C\uC778\uC744 \uAE30\uC5B5\uD560 \uC778\uBB3C (1~8\uBA85)", "Characters who remember the previous timeline (1\u20138)"],
    "carry.pv_chars_pick": ["\uC778\uBB3C\uC744 \uCD5C\uC18C 1\uBA85 \uACE0\uB974\uBA74 \uC774\uC5B4\uBC1B\uC744 \uAE30\uC5B5\uC774 \uD45C\uC2DC\uB429\uB2C8\uB2E4.", "Tick at least one character to preview what they remember."],
    "carry.pv_chars_none": ["\uC6D0\uBCF8 \uCC44\uD305\uC5D0 \uC120\uD0DD\uD560 \uC778\uBB3C\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.", "No characters were found in the source chat."],
    "carry.pv_replaces": ["\uD604\uC7AC \uC5F0\uACB0\uB41C \uC774\uC804 \uCC44\uD305\uC744 \uC774 \uC5F0\uACB0\uB85C \uBC14\uAFC9\uB2C8\uB2E4.", "This replaces the link currently in force."],
    "carry.pv_notice": [
      '\uC6D0\uBCF8 \uCC44\uD305\uC740 \uC9C0\uAE08 \uD55C \uBC88\uB9CC \uC77D\uC73C\uBA70, \uC774\uD6C4 \uC6D0\uBCF8\uC774 \uBC14\uB00C\uC5B4\uB3C4 \uB530\uB77C\uC624\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4. \uC6D0\uBCF8 \uCC44\uD305\uC758 \uAC00\uC7A5 \uCD5C\uADFC \uB2F5\uC7A5\uC740 \uAE30\uC5B5 \uC815\uB9AC\uAC00 \uC544\uC9C1 \uB530\uB77C\uC624\uC9C0 \uC54A\uC544 \uBE60\uC84C\uC744 \uC218 \uC788\uC2B5\uB2C8\uB2E4. PocketRisu\uC758 \uC5B4\uB290 \uCC44\uD305\uB3C4 \uAC74\uB4DC\uB9AC\uC9C0 \uC54A\uC73C\uBA70, \uBAA8\uB378\uC744 \uD638\uCD9C\uD558\uC9C0 \uC54A\uC544 \uBE44\uC6A9\uC774 \uB4E4\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4. \uC5B8\uC81C\uB4E0 "\uC5F0\uACB0 \uD574\uC81C"\uB85C \uB418\uB3CC\uB9B4 \uC218 \uC788\uC2B5\uB2C8\uB2E4(\uC774\uC804 \uC5F0\uACB0 \uAE30\uB85D\uC740 \uB0A8\uC544 \uC788\uC2B5\uB2C8\uB2E4).',
      "The source chat is read once now, and later changes there do not follow. Its very last reply may not be included yet if memory has not caught up. This does not touch either chat in PocketRisu, calls no model, and costs nothing. You can undo it any time with Unlink (the earlier link is kept for the record)."
    ],
    "carry.changed": [
      "\uBBF8\uB9AC \uBCF4\uAE30 \uC774\uD6C4 \uC6D0\uBCF8 \uCC44\uD305\uC774 \uBC14\uB00C\uC5C8\uC2B5\uB2C8\uB2E4. \uC0C8\uB85C \uC77D\uC740 \uB0B4\uC6A9\uC744 \uD655\uC778\uD55C \uB4A4 \uB2E4\uC2DC \uC5F0\uACB0\uD574 \uC8FC\uC138\uC694.",
      "The source chat changed since the preview. Review the refreshed preview and confirm Link again."
    ],
    "carry.cutoff_turn": ["t{t}\uAE4C\uC9C0", "through t{t}"],
    "carry.cutoff_end": ["\uB05D\uAE4C\uC9C0", "through the end"],
    "carry.only_remember": ["\uC774\uC804 \uD0C0\uC784\uB77C\uC778 \xB7 {names}\uB9CC \uAE30\uC5B5", "earlier timeline \xB7 remembered only by {names}"],
    "carry.linked_continue": ["{source}\uC5D0\uC11C \uC774\uC5B4\uBC1B\uC740 \uAE30\uC5B5 (\uC774 \uCC44\uD305\uC758 \uD134\uC774 \uC544\uB2D8)", "Carried from {source} (not this chat's own turns)"],
    "carry.taken_at": ["\uC77D\uC740 \uC2DC\uAC01: {time}", "Taken: {time}"],
    "carry.too_large": [
      "\uC774 \uCC44\uD305\uC758 \uAE30\uC5B5\uC774 \uB108\uBB34 \uB9CE\uC544 \uC774\uC5B4\uBC1B\uC744 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4 ({n}\uC904, \uCD5C\uB300 {m}\uC904). \uB354 \uC774\uB978 \uD134\uC5D0\uC11C \uB04A\uC5B4 \uBCF4\uC138\uC694.",
      "This chat has too much memory to carry ({n} lines, maximum {m}). Try cutting off at an earlier turn."
    ],
    "carry.err_no_link": ["\uD604\uC7AC \uC5F0\uACB0\uB41C \uC774\uC804 \uCC44\uD305\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.", "There is no link in force."],
    "carry.err_not_found": ["\uD574\uB2F9 \uCC44\uD305\uC744 \uCC3E\uC744 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.", "That chat could not be found."],
    "carry.err_failed": ["\uC694\uCCAD\uC744 \uCC98\uB9AC\uD558\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4. \uC7A0\uC2DC \uD6C4 \uB2E4\uC2DC \uC2DC\uB3C4\uD574 \uC8FC\uC138\uC694.", "The request could not be completed. Please try again."]
  };
  function t(lang, key, vars = {}) {
    const text2 = STRINGS[key][lang === "en" ? 1 : 0];
    return text2.replace(/\{(\w+)\}/g, (m, name) => name in vars ? String(vars[name]) : m);
  }
  var STRING_KEYS = Object.keys(STRINGS);

  // src/manifest.ts
  var HASH_FORMAT_VERSION = 1;
  var SPECIAL_COMMENT = /\{\{specialcomment::[^]*?::\}\}/g;
  function selectedSwipe(message) {
    const swipes = message?.swipes;
    const id = message?.swipeId;
    return Array.isArray(swipes) && Number.isInteger(id) && id >= 0 && id < swipes.length ? swipes[id] ?? "" : void 0;
  }
  function selectedContent(message) {
    if (typeof message?.data === "string") return message.data;
    return selectedSwipe(message) ?? "";
  }
  function rewritten(message) {
    const swipe = selectedSwipe(message);
    return swipe !== void 0 && typeof message.data === "string" && message.data !== swipe;
  }
  function revisionMetadata(message) {
    const data = typeof message.data === "string" ? message.data : "";
    return {
      chatId: message.chatId ?? null,
      role: message.role ?? null,
      saying: message.saying ?? null,
      name: message.name ?? null,
      otherUser: message.otherUser ?? null,
      isComment: message.isComment ?? null,
      disabled: message.disabled ?? null,
      swipeId: message.swipeId ?? null,
      generationId: message.generationInfo?.generationId ?? null,
      swipeCount: Array.isArray(message.swipes) ? message.swipes.length : 0,
      specialComments: data.match(SPECIAL_COMMENT) ?? []
    };
  }
  function hashPayload(message) {
    const meta = revisionMetadata(message);
    return {
      v: HASH_FORMAT_VERSION,
      chatId: meta.chatId,
      role: meta.role,
      saying: meta.saying,
      name: meta.name,
      otherUser: meta.otherUser,
      isComment: meta.isComment,
      disabled: meta.disabled,
      swipeId: meta.swipeId,
      selectedContent: selectedContent(message),
      generationId: meta.generationId
    };
  }
  var bodyKey2 = (logicalId, revisionHash) => `${logicalId}
${revisionHash}`;
  var LABEL_MAX = 200;
  function labelOf(value) {
    const text2 = typeof value === "string" ? value.trim() : "";
    return text2 ? text2.slice(0, LABEL_MAX) : void 0;
  }
  function manifestEntry(m, revisionHash) {
    const meta = revisionMetadata(m);
    return {
      host_logical_id: String(m.chatId ?? ""),
      revision_hash: revisionHash,
      role: m.role,
      name: m.name ?? null,
      disabled: m.disabled ?? null,
      is_comment: m.isComment ?? null,
      swipe_id: m.swipeId ?? null,
      swipe_count: meta.swipeCount,
      generation_id: meta.generationId ?? null,
      special_comments: meta.specialComments
    };
  }
  function snapshotOf(m) {
    const content = selectedContent(m);
    const data = typeof m.data === "string" ? m.data : "";
    const out = [
      m.role,
      m.saying,
      m.name,
      m.otherUser,
      m.isComment,
      m.disabled,
      m.swipeId,
      m.generationInfo?.generationId,
      Array.isArray(m.swipes) ? m.swipes.length : 0,
      content,
      data === content ? null : data
    ];
    return out.every((v) => v === null || v === void 0 || typeof v !== "object" && typeof v !== "function") ? out : void 0;
  }
  function sameSnapshot(a, b) {
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
    return true;
  }
  function finish(chat, messages, entries, characterRef, labels, hashed) {
    const index = /* @__PURE__ */ new Map();
    entries.forEach((e, i) => index.set(bodyKey2(e.host_logical_id, e.revision_hash), i));
    const bodies = {
      get(key) {
        const i = index.get(key);
        if (i === void 0) return void 0;
        const m = messages[i];
        const e = entries[i];
        return {
          host_logical_id: e.host_logical_id,
          revision_hash: e.revision_hash,
          content: normalizeText(selectedContent(m)),
          metadata: revisionMetadata(m)
        };
      },
      rewritten(key) {
        const i = index.get(key);
        return i !== void 0 && rewritten(messages[i]);
      }
    };
    return {
      request: {
        host: "pocketrisu",
        chat_id: String(chat.id ?? ""),
        character_ref: characterRef,
        character_name: labelOf(labels.characterName),
        chat_name: labelOf(chat.name),
        persona_name: labelOf(labels.personaName),
        hash_version: 1,
        messages: entries
      },
      bodies,
      hashed
    };
  }
  var CACHED_CHATS = 2;
  function createManifestBuilder() {
    const chats = /* @__PURE__ */ new Map();
    return async function build(chat, characterRef, labels = {}) {
      const messages = Array.isArray(chat.message) ? chat.message : [];
      const chatKey = String(chat.id ?? "");
      const previous = chats.get(chatKey) ?? /* @__PURE__ */ new Map();
      chats.delete(chatKey);
      const next = /* @__PURE__ */ new Map();
      const entries = new Array(messages.length);
      const snapshots = new Array(messages.length);
      const missing = [];
      const seen = /* @__PURE__ */ new Set();
      messages.forEach((m, i) => {
        const id = m.chatId;
        const snapshot = typeof id === "string" && id !== "" && !seen.has(id) ? snapshotOf(m) : void 0;
        if (typeof id === "string") seen.add(id);
        snapshots[i] = snapshot;
        const hit = snapshot ? previous.get(id) : void 0;
        if (hit && sameSnapshot(hit.snapshot, snapshot)) {
          entries[i] = hit.entry;
          next.set(id, hit);
        } else {
          missing.push(i);
        }
      });
      const hashes = await Promise.all(missing.map((i) => sha256Hex(canonicalJson(hashPayload(messages[i])))));
      missing.forEach((i, j) => {
        const m = messages[i];
        const entry = manifestEntry(m, hashes[j]);
        entries[i] = entry;
        const snapshot = snapshots[i];
        if (snapshot) next.set(m.chatId, { snapshot, entry });
      });
      chats.set(chatKey, next);
      while (chats.size > CACHED_CHATS) chats.delete(chats.keys().next().value);
      return finish(chat, messages, entries, characterRef, labels, missing.length);
    };
  }

  // src/placement.ts
  var MEMORY_MARKER = "[NMOS.memory]";
  function isTextPart(part) {
    return typeof part === "object" && part !== null && !Array.isArray(part) && part.type === "text" && typeof part.text === "string";
  }
  function findMarker(prompt) {
    if (!Array.isArray(prompt)) return null;
    for (let i = 0; i < prompt.length; i += 1) {
      const m = prompt[i];
      if (!m || typeof m !== "object") continue;
      const content = m.content;
      if (typeof content === "string") {
        const offset = content.indexOf(MEMORY_MARKER);
        if (offset >= 0) return { message: i, part: null, offset };
      } else if (Array.isArray(content)) {
        for (let j = 0; j < content.length; j += 1) {
          const part = content[j];
          if (!isTextPart(part)) continue;
          const offset = part.text.indexOf(MEMORY_MARKER);
          if (offset >= 0) return { message: i, part: j, offset };
        }
      }
    }
    return null;
  }
  function replaceInString(text2, packet, placed) {
    if (!text2.includes(MEMORY_MARKER)) return { text: text2, changed: false, placed };
    const parts = text2.split(MEMORY_MARKER);
    if (placed) return { text: parts.join(""), changed: true, placed: true };
    return { text: `${parts[0] ?? ""}${packet}${parts.slice(1).join("")}`, changed: true, placed: true };
  }
  function resolvePlaceholders(prompt, packet) {
    if (!Array.isArray(prompt)) return prompt;
    const cleanPacket = typeof packet === "string" ? packet.split(MEMORY_MARKER).join("") : "";
    let out = null;
    let placed = false;
    for (let i = 0; i < prompt.length; i += 1) {
      const m = prompt[i];
      if (!m || typeof m !== "object") continue;
      const content = m.content;
      if (typeof content === "string") {
        const res = replaceInString(content, cleanPacket, placed);
        placed = res.placed;
        if (res.changed) {
          if (out === null) out = prompt.slice();
          out[i] = { ...m, content: res.text };
        }
      } else if (Array.isArray(content)) {
        let newParts = null;
        for (let j = 0; j < content.length; j += 1) {
          const part = content[j];
          if (!isTextPart(part)) continue;
          const res = replaceInString(part.text, cleanPacket, placed);
          placed = res.placed;
          if (res.changed) {
            if (newParts === null) newParts = content.slice();
            newParts[j] = { ...part, text: res.text };
          }
        }
        if (newParts !== null) {
          if (out === null) out = prompt.slice();
          out[i] = { ...m, content: newParts };
        }
      }
    }
    return out ?? prompt;
  }
  function stripMarkers(prompt) {
    return resolvePlaceholders(prompt, "");
  }
  function holdsText(prompt, text2) {
    if (!text2 || typeof text2 !== "string" || !Array.isArray(prompt)) return false;
    for (let i = 0; i < prompt.length; i += 1) {
      const m = prompt[i];
      if (!m || typeof m !== "object") continue;
      const content = m.content;
      if (typeof content === "string") {
        if (content.includes(text2)) return true;
      } else if (Array.isArray(content)) {
        for (let j = 0; j < content.length; j += 1) {
          const part = content[j];
          if (isTextPart(part) && part.text.includes(text2)) return true;
        }
      }
    }
    return false;
  }

  // src/prompt.ts
  var PACKET_TAG = '<NarrativeMemory version="0" source="nmos">';
  var GUARD_LINE = "(The user's most recent message comes before this memory and has already happened; where the two differ, that message wins.)";
  var GUARD_RESERVE_TOKENS = 40;
  function contentText(content) {
    if (typeof content === "string") return content;
    if (content == null) return "";
    return JSON.stringify(content);
  }
  function isActive(message) {
    return message != null && message.disabled !== true && !message.isComment;
  }
  function latestUserIndex(messages) {
    if (!Array.isArray(messages)) return -1;
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      if (m && m.role === "user" && isActive(m)) return i;
    }
    return -1;
  }
  function userTurnAnchor(hostMessages) {
    if (!Array.isArray(hostMessages)) return "";
    const hostIndex = latestUserIndex(hostMessages);
    if (hostIndex < 0) return "";
    const expected = cleanText(selectedContent(hostMessages[hostIndex]));
    return expected ? anchorOf(expected, 64) : "";
  }
  function userTurnIndex(prompt, hostMessages) {
    if (!Array.isArray(prompt)) return -1;
    const anchor = userTurnAnchor(hostMessages);
    if (!anchor) return -1;
    for (let i = prompt.length - 1; i >= 0; i -= 1) {
      if (prompt[i]?.role === "assistant") continue;
      const sent = cleanText(contentText(prompt[i]?.content));
      if (sent.includes(anchor)) return i;
    }
    return -1;
  }
  function hasPacket(prompt) {
    return Array.isArray(prompt) && prompt.some((m) => m?.role === "system" && contentText(m.content).includes(PACKET_TAG));
  }
  function cleanText(value) {
    return normalizeText(value).replace(/<(style|script)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, " ").replace(/<[^>\n]{1,500}>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim();
  }
  function anchorOf(text2, size = 48) {
    if (text2.length <= size) return text2;
    const start = Math.floor((text2.length - size) / 2);
    return text2.slice(start, start + size);
  }
  function matchPromptToHost(prompt, hostMessages, minAnchor = 16, maxMisses = 3) {
    const matches = /* @__PURE__ */ new Map();
    if (!Array.isArray(prompt) || !Array.isArray(hostMessages)) return matches;
    const texts = prompt.map((m) => cleanText(contentText(m?.content)));
    let pointer = texts.length - 1;
    let misses = 0;
    for (let i = hostMessages.length - 1; i >= 0 && pointer >= 0; i -= 1) {
      const m = hostMessages[i];
      if (!m || !isActive(m)) continue;
      const text2 = cleanText(selectedContent(m));
      if (text2.length < minAnchor) continue;
      const anchor = anchorOf(text2);
      let found = -1;
      for (let k = pointer; k >= 0; k -= 1) {
        if (texts[k].includes(anchor)) {
          found = k;
          break;
        }
      }
      if (found >= 0) {
        matches.set(i, found);
        pointer = found - 1;
        misses = 0;
      } else if (++misses >= maxMisses) {
        break;
      }
    }
    return matches;
  }
  function inContextIds(prompt, hostMessages, minAnchor = 16, maxMisses = 3) {
    const matches = matchPromptToHost(prompt, hostMessages, minAnchor, maxMisses);
    if (matches.size === 0) return [];
    let boundary = hostMessages.length;
    for (const i of matches.keys()) {
      if (i < boundary) boundary = i;
    }
    return hostMessages.slice(boundary).map((m) => String(m.chatId ?? "")).filter(Boolean);
  }
  function injectPacket(prompt, packet, position = "before_last_user", turn = -1) {
    if (!packet || hasPacket(prompt)) return prompt;
    const message = { role: "system", content: packet };
    const out = prompt.slice();
    if (position === "end") {
      let index2 = out.length;
      while (index2 > 0 && out[index2 - 1]?.role === "assistant") index2 -= 1;
      out.splice(index2, 0, message);
      return out;
    }
    let index = turn >= 0 && turn < out.length && out[turn]?.role !== "assistant" ? turn : out.length;
    for (let i = out.length - 1; index === out.length && i >= 0; i -= 1) {
      if (out[i]?.role === "user") index = i;
    }
    while (index > 0 && out[index]?.role === "user" && out[index - 1]?.role === "user") index -= 1;
    out.splice(index, 0, message);
    return out;
  }
  function withGuard(packet) {
    return packet ? `${packet}
${GUARD_LINE}` : "";
  }
  function textAfterMarker(message, marker) {
    const content = message?.content;
    const start = marker.offset + MEMORY_MARKER.length;
    if (marker.part === null) {
      return typeof content === "string" ? content.slice(start) : "";
    }
    if (!Array.isArray(content)) return "";
    const chunks = [];
    const part = content[marker.part];
    if (isTextPart(part)) chunks.push(part.text.slice(start));
    for (let j = marker.part + 1; j < content.length; j += 1) {
      const later = content[j];
      if (isTextPart(later)) chunks.push(later.text);
    }
    return chunks.join("\n");
  }
  function landsAfterUserTurn(prompt, hostMessages, position, turn, marker) {
    if (turn < 0) return position === "end" || marker !== null;
    if (marker === null) return position === "end";
    if (marker.message > turn) return true;
    if (marker.message < turn) return false;
    const anchor = userTurnAnchor(hostMessages);
    if (!anchor) return true;
    const after = Array.isArray(prompt) ? textAfterMarker(prompt[marker.message], marker) : "";
    return !cleanText(after).includes(anchor);
  }
  function queryTexts(hostMessages) {
    const userIndex = latestUserIndex(hostMessages);
    const query = userIndex >= 0 ? normalizeText(selectedContent(hostMessages[userIndex])) : "";
    let previousAi = "";
    for (let i = userIndex - 1; i >= 0; i -= 1) {
      const m = hostMessages[i];
      if (m.role === "char" && isActive(m)) {
        previousAi = normalizeText(selectedContent(m));
        break;
      }
    }
    return { query, previousAi };
  }

  // src/budget.ts
  var FIT_CAP = 8e3;
  function budgetAdvice(r, current2) {
    if (!r || r.outcome === "failed" || !r.memory || !(r.memory.cut > 0) || !(r.budgetTokens && r.budgetTokens > 0)) return null;
    const all = typeof r.memory.fits_at === "number";
    const suggest = all ? r.memory.fits_at : FIT_CAP;
    if (suggest <= r.budgetTokens || current2 !== void 0 && current2 >= suggest) return null;
    return { cut: r.memory.cut, offered: r.memory.offered, budget: r.budgetTokens, suggest, all };
  }
  function estimateTokens(text2) {
    if (!text2) return 0;
    let asciiChars = 0;
    let otherChars = 0;
    for (const ch of text2) {
      if (ch.charCodeAt(0) < 128) asciiChars += 1;
      else otherChars += 1;
    }
    return Math.ceil(asciiChars / 3.5 + otherChars * 1.2);
  }

  // src/trim.ts
  var DROPPABLE_KEYS = /* @__PURE__ */ new Set(["role", "content", "memo", "attr", "thoughts"]);
  var MIN_ANCHOR = 16;
  function sameText(prompt, hostMessages, p, i) {
    const m = prompt[p];
    if (!m || typeof m.content !== "string") return false;
    const sent = cleanText(m.content);
    if (!sent) return false;
    return sent === cleanText(selectedContent(hostMessages[i]));
  }
  function trimPrompt(prompt, hostMessages, keepFromId) {
    const refuse = () => ({ prompt, dropped: 0, savedTokens: 0, reason: "format" });
    if (!Array.isArray(prompt) || !Array.isArray(hostMessages) || typeof keepFromId !== "string" || !keepFromId) {
      return refuse();
    }
    try {
      const b = hostMessages.findIndex(
        (m) => isActive(m) && m?.chatId != null && String(m.chatId) === keepFromId
      );
      if (b < 0) return refuse();
      if (b > latestUserIndex(hostMessages)) return refuse();
      const turn = userTurnIndex(prompt, hostMessages);
      if (turn < 0) return refuse();
      const pairs = matchPromptToHost(prompt, hostMessages);
      let K = turn;
      for (const [hostIdx, promptIdx] of pairs) {
        if (hostIdx >= b && promptIdx < K) K = promptIdx;
      }
      let j = -1;
      for (let i = b - 1; i >= 0; i -= 1) {
        if (isActive(hostMessages[i]) && pairs.has(i)) {
          j = i;
          break;
        }
      }
      if (j < 0) return refuse();
      const jPrompt = pairs.get(j);
      if (jPrompt === void 0) return refuse();
      const run = /* @__PURE__ */ new Map([[jPrompt, j]]);
      let q = jPrompt + 1;
      for (let i = j + 1; i < b; i += 1) {
        if (!isActive(hostMessages[i])) continue;
        if (pairs.has(i)) return refuse();
        if (q < K && sameText(prompt, hostMessages, q, i)) {
          run.set(q, i);
          q += 1;
        } else {
          break;
        }
      }
      let p = jPrompt - 1;
      for (let i = j - 1; i >= 0; i -= 1) {
        if (!isActive(hostMessages[i])) continue;
        if (pairs.has(i)) {
          if (pairs.get(i) === p) {
            run.set(p, i);
            p -= 1;
            continue;
          }
          break;
        }
        if (p >= 0 && sameText(prompt, hostMessages, p, i)) {
          run.set(p, i);
          p -= 1;
          continue;
        }
        break;
      }
      for (const [hostIdx, promptIdx] of pairs) {
        if (hostIdx < b && !run.has(promptIdx)) return refuse();
      }
      if (run.size === 0) return refuse();
      let runStart = Infinity;
      let runOldest = Infinity;
      for (const [k, hostIdx] of run) {
        if (k < runStart) runStart = k;
        if (hostIdx < runOldest) runOldest = hostIdx;
      }
      const before = prompt.slice(0, runStart).map((m) => cleanText(contentText(m?.content)));
      if (before.length > 0) {
        for (let i = runOldest - 1; i >= 0; i -= 1) {
          if (!isActive(hostMessages[i])) continue;
          const text2 = cleanText(selectedContent(hostMessages[i]));
          if (text2.length < MIN_ANCHOR) continue;
          const anchor = anchorOf(text2);
          if (before.some((t2) => t2.includes(anchor))) return refuse();
        }
      }
      let savedTokens = 0;
      for (const [k, hostIdx] of run) {
        const m = prompt[k];
        if (!m || m.role !== "user" && m.role !== "assistant") return refuse();
        if (typeof m.content !== "string") return refuse();
        if (Object.keys(m).some((key) => !DROPPABLE_KEYS.has(key))) return refuse();
        if (m.content.includes(MEMORY_MARKER)) return refuse();
        if (k >= K || k >= turn) return refuse();
        const sent = cleanText(m.content).length;
        const own = cleanText(selectedContent(hostMessages[hostIdx])).length;
        if (sent > 1.25 * own + 64) return refuse();
        savedTokens += estimateTokens(m.content);
      }
      const boundary = cleanText(selectedContent(hostMessages[b]));
      if (boundary) {
        let newest = -1;
        for (const k of run.keys()) if (k > newest) newest = k;
        const sent = cleanText(prompt[newest]?.content);
        const own = cleanText(selectedContent(hostMessages[run.get(newest)]));
        const at = own ? sent.lastIndexOf(own) : -1;
        const tail = at >= 0 ? sent.slice(at + own.length) : sent;
        if (tail.includes(boundary)) return refuse();
      }
      const out = prompt.filter((_, idx) => !run.has(idx));
      return { prompt: out, dropped: run.size, savedTokens, reason: null };
    } catch {
      return refuse();
    }
  }

  // src/failure.ts
  var INSECURE_ERROR = "insecure page: open PocketRisu over HTTPS or localhost (crypto.subtle is missing)";
  function secureContext() {
    return typeof globalThis.crypto?.subtle?.digest === "function";
  }
  function failureKind(error) {
    if (!error) return null;
    if (error.startsWith("deadline")) return "deadline";
    if (error.startsWith("insecure page")) return "insecure";
    const status = /-> HTTP (\d{3})/.exec(error);
    if (status) {
      if (status[1] === "401") return "unauthorized";
      if (status[1] === "400" && /not allowed without a token/.test(error)) return "host_refused";
      return ["502", "503", "504"].includes(status[1]) ? "unreachable" : "other";
    }
    return /^sidecar /.test(error) ? "other" : "unreachable";
  }

  // src/core.ts
  var DeadlineError = class extends Error {
  };
  var FAILED_TRIM = { keepFromId: null, keepFromTurn: null, reason: "failed" };
  function keepRecentTurnsOf(settings) {
    if (!settings.trimOldTurns) return 0;
    const n = settings.keepRecentTurns;
    const k = typeof n === "number" && Number.isFinite(n) && n > 0 ? Math.floor(n) : DEFAULT_KEEP_RECENT_TURNS;
    return Math.min(MAX_KEEP_RECENT_TURNS, Math.max(MIN_KEEP_RECENT_TURNS, k));
  }
  var finiteOrNull = (value) => typeof value === "number" && Number.isFinite(value) ? value : null;
  function trimDecisionOf(fresh, trim) {
    if (!fresh) return FAILED_TRIM;
    if (!trim || typeof trim !== "object") return { keepFromId: null, keepFromTurn: null, reason: "unsupported" };
    const t2 = trim;
    const keepFromId = typeof t2.keep_from_id === "string" && t2.keep_from_id ? t2.keep_from_id : null;
    const reason = typeof t2.reason === "string" ? t2.reason : null;
    if (!keepFromId && reason === null) return FAILED_TRIM;
    return { keepFromId, keepFromTurn: finiteOrNull(t2.keep_from_turn), reason };
  }
  function coverageOf(coverage) {
    if (!coverage || typeof coverage !== "object") return null;
    const c = coverage;
    return { recordedThroughTurn: finiteOrNull(c.recorded_through_turn), coveredThroughTurn: finiteOrNull(c.covered_through_turn) };
  }
  var SUCCESS_TTL_MS = 10 * 6e4;
  var FAILURE_TTL_MS = 3e4;
  var CACHE_LIMIT = 64;
  var RETRY_MEMO_TTL_MS = 12e4;
  var RETRY_MEMO_LIMIT = 4;
  var BODY_CHUNK = 250;
  var NAME_TTL_MS = 10 * 6e4;
  var CANON_TIMEOUT_MS = 3e4;
  var CANON_ROUNDS = 20;
  var CANON_BATCH_CHARS = 8e5;
  var TEXT_HASH_LIMIT = 4e3;
  var PERSONA_TTL_MS = 3e4;
  function personaOf(chat, host) {
    const list = Array.isArray(host.personas) ? host.personas : [];
    const bound = chat.bindedPersona ? list.find((p) => p?.id === chat.bindedPersona) : void 0;
    const name = (bound ?? list[host.selected])?.name;
    return typeof name === "string" && name.trim() ? name.trim() : null;
  }
  function createAdapter(host, onActivity) {
    const cache = /* @__PURE__ */ new Map();
    const returnedMemo = /* @__PURE__ */ new Map();
    const conversations = /* @__PURE__ */ new Map();
    const names = /* @__PURE__ */ new Map();
    const canonSent = /* @__PURE__ */ new Map();
    const canonQueue = /* @__PURE__ */ new Map();
    const textHashes = /* @__PURE__ */ new Map();
    let canonUnsupported = false;
    let personas = null;
    const buildManifest = createManifestBuilder();
    let last = null;
    let epoch = 0;
    function invalidate() {
      epoch++;
      cache.clear();
    }
    function emit(event) {
      try {
        onActivity?.(event);
      } catch {
      }
    }
    function refreshCharacter(chatId) {
      const hit = names.get(chatId);
      names.set(chatId, { name: hit?.name ?? null, card: hit?.card ?? null, at: host.now() });
      if (host.card) {
        host.card(chatId).then((card) => {
          if (card) names.set(chatId, { name: card.name?.trim() || null, card, at: host.now() });
        }).catch(() => {
        });
      } else if (host.characterName) {
        host.characterName(chatId).then((name) => {
          if (name) names.set(chatId, { name, card: null, at: host.now() });
        }).catch(() => {
        });
      }
    }
    function characterName(chatId) {
      const hit = names.get(chatId);
      if ((host.card || host.characterName) && (!hit || host.now() - hit.at > NAME_TTL_MS)) refreshCharacter(chatId);
      return hit?.name ?? null;
    }
    function personaRecord(chat) {
      const list = personas?.value?.personas ?? [];
      const bound = chat.bindedPersona ? list.find((p) => p?.id === chat.bindedPersona) : void 0;
      return bound ?? list[personas?.value?.selected ?? 0] ?? null;
    }
    async function observeCanon(chat, prompt, deadline) {
      if (!host.lorebook) return null;
      let lore;
      try {
        lore = await within(host.lorebook(), deadline, "the lorebook");
      } catch (error) {
        if (error instanceof DeadlineError) throw error;
        return null;
      }
      if (!Array.isArray(lore)) return null;
      const character = names.get(chat.id);
      const texts = canonTexts(character?.card ?? null, chat, lore, personaRecord(chat));
      const held = heldKeys(texts, prompt);
      if (character?.card?.desc?.trim() && !held.includes("card:desc")) refreshCharacter(chat.id);
      if (!character?.card) return { held, snapshot: null };
      const entries = await within(Promise.all(texts.map(async (t2) => {
        let hash = textHashes.get(t2.text);
        if (!hash) {
          hash = await canonHash(t2.text);
          textHashes.set(t2.text, hash);
          while (textHashes.size > TEXT_HASH_LIMIT) textHashes.delete(textHashes.keys().next().value);
        }
        return { key: t2.key, hash, metadata: t2.metadata };
      })), deadline, "the canon hashes");
      return { held, snapshot: { id: await canonManifestId(entries), entries, texts, observedAt: Date.now() } };
    }
    function syncCanon(settings, conversationId, chatId, snapshot) {
      const key = `${settings.sidecarUrl}|${conversationId}`;
      if (canonUnsupported || canonSent.get(key) === snapshot.id) return;
      const queue = canonQueue.get(key) ?? { running: false, next: null };
      canonQueue.set(key, queue);
      if (queue.running) {
        queue.next = snapshot;
        return;
      }
      queue.running = true;
      void (async () => {
        for (let current2 = snapshot; current2; current2 = queue.next, queue.next = null) {
          if (canonSent.get(key) === current2.id) continue;
          try {
            if (await uploadCanon(settings, chatId, current2)) {
              canonSent.set(key, current2.id);
              while (canonSent.size > CACHE_LIMIT) canonSent.delete(canonSent.keys().next().value);
            }
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            if (/HTTP 404/.test(message) && !/conversation not found/.test(message)) canonUnsupported = true;
            host.debug("[NMOS] canon not synced:", message);
            if (canonUnsupported) break;
          }
        }
        queue.running = false;
        queue.next = null;
      })();
    }
    async function uploadCanon(settings, chatId, snapshot) {
      const texts = new Map(snapshot.entries.map((e, i) => [e.hash, snapshot.texts[i].text]));
      const deadline = host.now() + CANON_TIMEOUT_MS;
      const body = { host: "pocketrisu", chat_id: chatId, entries: snapshot.entries, observed_at: snapshot.observedAt };
      let out = await call(settings, "/v1/sync/canon", body, deadline);
      for (let round = 0; out.needed.length && round < CANON_ROUNDS; round++) {
        const contents = {};
        let size = 0;
        for (const h of out.needed) {
          const text2 = texts.get(h);
          if (text2 === void 0 || size && size + text2.length > CANON_BATCH_CHARS) continue;
          contents[h] = text2;
          size += text2.length;
        }
        out = await call(settings, "/v1/sync/canon", { ...body, contents }, deadline);
      }
      return !out.needed.length;
    }
    function warmPersonas() {
      if (!host.personas) return;
      personas = { value: personas?.value ?? null, at: host.now() };
      host.personas().then((value) => {
        personas = { value, at: host.now() };
      }).catch(() => {
        personas = { value: null, at: host.now() };
      });
    }
    function personaName(chat) {
      if (!personas || host.now() - personas.at > PERSONA_TTL_MS) warmPersonas();
      return personas?.value ? personaOf(chat, personas.value) : null;
    }
    function remember(key, packet, ttl, failed = false, memory = null, vectors = null, canon, trim = null, coverage = null) {
      cache.set(key, { packet, expires: host.now() + ttl, failed, memory, vectors, canon, trim, coverage });
      while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value);
    }
    function promptSignature(prompt) {
      if (!Array.isArray(prompt)) return null;
      try {
        return JSON.stringify(prompt.map((m) => [m?.role ?? null, m?.content ?? null]));
      } catch {
        return null;
      }
    }
    function isReturnedMemo(prompt, now) {
      if (returnedMemo.size === 0) return false;
      const sig = promptSignature(prompt);
      if (sig === null) return false;
      const expires = returnedMemo.get(sig);
      if (expires === void 0) return false;
      if (expires <= now) {
        returnedMemo.delete(sig);
        return false;
      }
      return true;
    }
    function memoiseReturned(prompt) {
      const sig = promptSignature(prompt);
      if (sig === null) return;
      returnedMemo.delete(sig);
      returnedMemo.set(sig, host.now() + RETRY_MEMO_TTL_MS);
      while (returnedMemo.size > RETRY_MEMO_LIMIT) {
        returnedMemo.delete(returnedMemo.keys().next().value);
      }
    }
    async function within(work, deadline, what) {
      const remaining = deadline - host.now();
      if (remaining <= 0) throw new DeadlineError(`deadline before ${what}`);
      let timer;
      const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new DeadlineError(`deadline during ${what}`)), remaining);
      });
      try {
        return await Promise.race([work, timeout]);
      } finally {
        clearTimeout(timer);
      }
    }
    async function call(settings, path, body, deadline, method, onLate) {
      const remaining = deadline - host.now();
      if (remaining <= 0) throw new DeadlineError(`deadline before ${path}`);
      const url = settings.sidecarUrl.replace(/\/+$/, "") + path;
      const headers = { "Content-Type": "application/json" };
      if (settings.authToken) headers.Authorization = `Bearer ${settings.authToken}`;
      const verb = method ?? (body === void 0 ? "GET" : "POST");
      const pending2 = host.request(verb, url, body, headers, remaining, settings.route);
      try {
        const res = await within(pending2, deadline, path);
        if (res.status < 200 || res.status >= 300) {
          const detail = res.json?.detail;
          throw new Error(`${path} -> HTTP ${res.status}${detail ? `: ${Array.isArray(detail) ? detail.join("; ") : String(detail)}` : ""}`);
        }
        return res.json;
      } catch (error) {
        if (error instanceof DeadlineError && onLate) pending2.then(() => onLate(host.now()), () => {
        });
        throw error;
      }
    }
    async function sync(settings, manifest, bodies, deadline) {
      const request = { ...manifest, plugin_build: PLUGIN_BUILD };
      let result = await call(settings, "/v1/sync/reconcile", request, deadline);
      let rewritten2 = 0;
      if (result.status === "needs_bodies") {
        const keys = (result.needed_bodies ?? []).map((n) => bodyKey2(n.host_logical_id, n.revision_hash));
        rewritten2 = keys.filter((k) => bodies.rewritten(k)).length;
        const needed = keys.map((k) => bodies.get(k));
        if (needed.some((b) => !b)) throw new Error("sidecar asked for an unknown body");
        for (let i = 0; i < needed.length; i += BODY_CHUNK) {
          const last2 = i + BODY_CHUNK >= needed.length;
          const out = await call(settings, "/v1/sync/bodies", {
            host: "pocketrisu",
            chat_id: request.chat_id,
            bodies: needed.slice(i, i + BODY_CHUNK),
            then_reconcile: last2 ? request : null
          }, deadline);
          if (!out.ok) throw new Error("sidecar rejected bodies");
          if (last2) {
            if (!out.reconcile) throw new Error("sidecar did not reconcile");
            result = out.reconcile;
          }
        }
      }
      if (result.status === "needs_bodies") throw new Error("sidecar still needs bodies");
      return { ...result, rewritten: rewritten2 };
    }
    async function prepare(prompt, mode) {
      const started = host.now();
      const since = epoch;
      let settings = null;
      let key = null;
      let chatId = null;
      let announced = false;
      let failure = null;
      let lateAt = null;
      let k = 0;
      const late = (at) => {
        lateAt = at;
        if (failure) failure.neededMs = Math.round(at - started);
      };
      try {
        if (mode !== "model") return prompt;
        if (isReturnedMemo(prompt, started) || hasPacket(prompt)) return prompt;
        settings = await within(host.settings(), started + DEFAULT_DEADLINE_MS, "the plugin settings");
        if (!settings.enabled || !settings.sidecarUrl) return prompt;
        if (!secureContext()) throw new Error(INSECURE_ERROR);
        const deadline = started + settings.deadlineMs;
        k = keepRecentTurnsOf(settings);
        emit({ type: "request-start" });
        announced = true;
        const chat = await within(host.currentChat(), deadline, "the host chat read");
        const messages = Array.isArray(chat?.message) ? chat.message : [];
        if (!chat?.id) {
          emit({ type: "request-abandon" });
          return prompt;
        }
        chatId = chat.id;
        if (settings.offChats?.includes(chat.id)) {
          emit({ type: "request-end", outcome: "chat-off", chars: 0, conversationId: null });
          return prompt;
        }
        const turn = userTurnIndex(prompt, messages);
        if (turn < 0) {
          const reason = "the latest user message was not found in the prompt";
          host.warn("[NMOS] memory skipped for this request:", reason, {
            promptMessages: prompt.length,
            chatMessages: messages.length
          });
          last = {
            at: Date.now(),
            ms: Math.round(host.now() - started),
            packetChars: 0,
            packet: "",
            outcome: "skipped",
            error: reason,
            deadlineMs: settings.deadlineMs
          };
          emit({
            type: "request-end",
            outcome: "skipped",
            chars: 0,
            error: reason,
            conversationId: conversations.get(chat.id) ?? null
          });
          return prompt;
        }
        const marker = findMarker(prompt);
        const position = settings.injectPosition;
        const after = landsAfterUserTurn(prompt, messages, position, turn, marker);
        const budget = after ? Math.max(0, settings.reservedMemoryTokens - GUARD_RESERVE_TOKENS) : settings.reservedMemoryTokens;
        const place = (p, packet2, at) => {
          if (!packet2) return { out: stripMarkers(p), placed: false };
          if (holdsText(p, packet2.split(MEMORY_MARKER).join(""))) return { out: stripMarkers(p), placed: false };
          const text2 = after ? withGuard(packet2) : packet2;
          return {
            out: marker ? resolvePlaceholders(p, text2) : stripMarkers(injectPacket(p, text2, position, at)),
            placed: true
          };
        };
        const finishPrompt = (packet2, decision2) => {
          let p = prompt;
          let dropped = 0;
          let savedTokens = 0;
          let reason = decision2?.reason ?? null;
          if (decision2?.keepFromId) {
            if (!packet2) reason = "empty_packet";
            else {
              const r = trimPrompt(prompt, messages, decision2.keepFromId);
              p = r.prompt;
              dropped = r.dropped;
              savedTokens = r.savedTokens;
              reason = r.reason;
            }
          }
          const { out, placed } = place(p, packet2, turn - dropped);
          if (out !== prompt && (placed || dropped > 0)) memoiseReturned(out);
          const outcome2 = {
            dropped,
            savedTokens,
            reason,
            keepFromTurn: dropped > 0 ? decision2?.keepFromTurn ?? null : null
          };
          return { out, trim: outcome2 };
        };
        const shown = (o) => ({ dropped: o.dropped, savedTokens: o.savedTokens, reason: o.reason });
        const t0 = host.now();
        const { request, bodies } = await within(buildManifest(
          chat,
          firstSaying(messages),
          { characterName: characterName(chat.id), personaName: personaName(chat) }
        ), deadline, "the manifest");
        const manifestMs = host.now() - t0;
        const inContext = inContextIds(prompt, messages);
        key = await within(sha256Hex(JSON.stringify([
          chat.id,
          mode,
          prompt.length,
          request.messages.map((m) => [m.host_logical_id, m.revision_hash]),
          inContext,
          request.persona_name ?? null,
          // the sidecar reads `{{user}}` from the sync a cached packet skips (ADR 0023)
          settings.sidecarUrl.replace(/\/+$/, ""),
          settings.route,
          settings.authToken,
          budget,
          !!settings.trimOldTurns,
          k
        ])), deadline, "the cache key");
        const canon = await observeCanon(chat, prompt, deadline);
        const canonKey = JSON.stringify([canon?.snapshot?.id ?? null, canon?.held ?? []]);
        const cached = cache.get(key);
        if (cached && cached.expires > host.now() && (cached.failed || cached.canon === canonKey)) {
          const known = conversations.get(chat.id);
          if (canon?.snapshot && known) syncCanon(settings, known, chat.id, canon.snapshot);
          const outcome2 = cached.packet ? "injected" : "nothing-relevant";
          const done2 = finishPrompt(cached.packet, k > 0 ? cached.failed ? FAILED_TRIM : cached.trim ?? FAILED_TRIM : null);
          if (!cached.failed) last = {
            at: Date.now(),
            ms: Math.round(host.now() - started),
            packetChars: cached.packet.length,
            packet: cached.packet,
            outcome: outcome2,
            deadlineMs: settings.deadlineMs,
            budgetTokens: budget,
            memory: cached.memory ?? null,
            vectors: cached.vectors ?? null,
            ...k > 0 ? { trim: done2.trim } : {},
            ...cached.coverage ? { coverage: cached.coverage } : {}
          };
          emit({
            type: "request-end",
            outcome: outcome2,
            chars: cached.packet.length,
            reused: true,
            vectors: cached.vectors ?? null,
            conversationId: conversations.get(chat.id) ?? null,
            ...k > 0 ? { trim: shown(done2.trim) } : {}
          });
          return done2.out;
        }
        const t1 = host.now();
        const synced = await sync(settings, request, bodies, deadline);
        const syncMs = host.now() - t1;
        if (synced.conversation_id) {
          conversations.delete(chat.id);
          conversations.set(chat.id, synced.conversation_id);
          while (conversations.size > CACHE_LIMIT) conversations.delete(conversations.keys().next().value);
        }
        const { query, previousAi } = queryTexts(messages);
        const t2 = host.now();
        const retrieved = await call(settings, "/v1/retrieve", {
          host: "pocketrisu",
          chat_id: chat.id,
          active_commit: synced.active_commit,
          manifest_hash: synced.manifest_hash,
          query,
          previous_ai: previousAi,
          in_context_ids: inContext,
          budget_tokens: budget,
          client_timings_ms: { manifest: manifestMs, sync: syncMs, before_retrieve: t2 - started },
          canon_manifest_id: canon?.snapshot?.id ?? null,
          canon_held: canon?.held ?? [],
          // Only when the owner turned trimming on: without it the request is the one sent before PHASE-60.
          ...k > 0 ? { trim: { keep_recent_turns: k, step: k } } : {}
        }, deadline, void 0, late);
        if (canon?.snapshot && synced.conversation_id) syncCanon(settings, synced.conversation_id, chat.id, canon.snapshot);
        const packet = retrieved.freshness === "fresh" ? retrieved.packet.text : "";
        const memory = retrieved.freshness === "fresh" ? retrieved.memory ?? null : null;
        const vectors = retrieved.freshness === "fresh" ? retrieved.vectors ?? null : null;
        const decision = k > 0 ? trimDecisionOf(retrieved.freshness === "fresh", retrieved.trim) : null;
        const coverage = coverageOf(retrieved.coverage);
        if (epoch !== since) throw new Error("memory changed during this request");
        remember(key, packet, SUCCESS_TTL_MS, false, memory, vectors, canonKey, decision, coverage);
        host.debug("[NMOS] request done", {
          ms: Math.round(host.now() - started),
          manifestMs: Math.round(manifestMs),
          syncMs: Math.round(syncMs),
          retrieveMs: Math.round(host.now() - t2),
          packetChars: packet.length
        });
        const outcome = packet ? "injected" : "nothing-relevant";
        const done = finishPrompt(packet, decision);
        last = {
          at: Date.now(),
          ms: Math.round(host.now() - started),
          packetChars: packet.length,
          packet,
          outcome,
          deadlineMs: settings.deadlineMs,
          budgetTokens: budget,
          memory,
          vectors,
          ...k > 0 ? { trim: done.trim } : {},
          ...coverage ? { coverage } : {}
        };
        emit({
          type: "request-end",
          outcome,
          chars: packet.length,
          vectors,
          conversationId: synced.conversation_id ?? null,
          ...synced.rewritten > 0 ? { rewritten: synced.rewritten } : {},
          ...k > 0 ? { trim: shown(done.trim) } : {}
        });
        return done.out;
      } catch (error) {
        if (key && epoch === since) remember(key, "", FAILURE_TTL_MS, true);
        last = failure = {
          at: Date.now(),
          ms: Math.round(host.now() - started),
          packetChars: 0,
          packet: "",
          outcome: "failed",
          error: error instanceof Error ? error.message : String(error),
          deadlineMs: settings?.deadlineMs ?? 0,
          // Nothing is left out on any failure: the host's prompt goes as it is.
          ...k > 0 ? { trim: { dropped: 0, savedTokens: 0, reason: "failed", keepFromTurn: null } } : {}
        };
        if (lateAt !== null) failure.neededMs = Math.round(lateAt - started);
        if (announced) emit({
          type: "request-end",
          outcome: "failed",
          chars: 0,
          error: last.error,
          deadlineMs: last.deadlineMs,
          conversationId: chatId && conversations.get(chatId) || null,
          ...k > 0 ? { trim: { dropped: 0, savedTokens: 0, reason: "failed" } } : {}
        });
        host.warn("[NMOS] memory skipped for this request (fail open):", error instanceof Error ? error.message : error);
        return prompt;
      }
    }
    async function beforeRequest(prompt, mode) {
      try {
        return stripMarkers(await prepare(prompt, mode));
      } catch {
        return stripMarkers(prompt);
      }
    }
    function onOutput(arg2) {
      void (async () => {
        const settings = await host.settings();
        if (!settings.enabled || !settings.sidecarUrl || !arg2?.chat?.id || settings.offChats?.includes(arg2.chat.id)) return;
        adviseOnce(settings.language);
        reachOnce(settings.language, settings.sidecarUrl);
        emit({ type: "background", conversationId: conversations.get(arg2.chat.id) ?? null });
        const index = arg2.messageIndex ?? -1;
        const message = index >= 0 ? arg2.chat.message?.[index] : void 0;
        await call(settings, "/v1/output", {
          host: "pocketrisu",
          chat_id: arg2.chat.id,
          host_logical_id: message?.chatId ?? null,
          generation_id: message?.generationInfo?.generationId ?? null,
          revision_hash: message ? await sha256Hex(canonicalJson(hashPayload(message))) : null,
          message_index: index
        }, host.now() + settings.deadlineMs);
      })().catch((error) => host.debug("[NMOS] output notification failed:", error instanceof Error ? error.message : error));
    }
    let alerted = false;
    function adviseOnce(lang) {
      const advice = deadlineAdvice(last);
      if (alerted || !host.alert || advice?.level !== "over") return;
      alerted = true;
      const took = advice.tookMs === null ? "" : t(lang, "deadline.took", { n: formatMs(advice.tookMs) });
      host.alert(t(lang, "deadline.alert", { d: formatMs(advice.deadlineMs), took, s: formatMs(advice.suggestMs) }));
    }
    let reachAlerted = false;
    function reachOnce(lang, url) {
      const kind = last?.outcome === "failed" ? failureKind(last.error) : null;
      if (reachAlerted || !host.alert || !kind || kind === "deadline" || kind === "other") return;
      reachAlerted = true;
      host.alert(t(lang, `reach.${kind}`, { url: url.replace(/\/+$/, "") }));
    }
    async function status() {
      const settings = await host.settings();
      const info = {
        enabled: settings.enabled,
        sidecarUrl: settings.sidecarUrl,
        language: settings.language,
        connected: false,
        last,
        insecure: !secureContext()
      };
      try {
        const res = await call(settings, "/v1/health", void 0, host.now() + 3e3);
        Object.assign(info, {
          connected: true,
          version: res.version,
          features: res.features ?? {},
          pluginExpected: res.plugin?.expected ?? null,
          install: res.install ?? null
        });
      } catch (error) {
        info.error = error instanceof Error ? error.message : String(error);
      }
      return info;
    }
    async function api(method, path, body, timeoutMs = 9e4) {
      const settings = await host.settings();
      const change = method !== "GET";
      if (change) invalidate();
      try {
        return await call(settings, path, body, host.now() + timeoutMs, method, change ? invalidate : void 0);
      } finally {
        if (change) invalidate();
      }
    }
    async function file(path, timeoutMs = 3e5) {
      if (!host.requestFile) throw new Error("this host cannot fetch a file");
      const settings = await host.settings();
      const headers = {};
      if (settings.authToken) headers.Authorization = `Bearer ${settings.authToken}`;
      const res = await host.requestFile(settings.sidecarUrl.replace(/\/+$/, "") + path, headers, timeoutMs, settings.route);
      if (res.status < 200 || res.status >= 300 || !res.bytes) {
        const detail = res.json?.detail;
        throw new Error(`${path.split("?")[0]} -> HTTP ${res.status}${detail ? `: ${String(detail)}` : ""}`);
      }
      return res.bytes;
    }
    return { beforeRequest, onOutput, status, api, file, warmPersonas };
  }
  function firstSaying(messages) {
    for (const m of messages) if (m.role === "char" && m.saying) return m.saying;
    return null;
  }

  // src/chatoff.ts
  var CHAT_OFF_ARG = "disabled_chats";
  function parseChatIds(value) {
    return [...new Set(value.split(/[\s,]+/).filter(Boolean))];
  }
  function withChat(ids, chatId, off) {
    const rest = ids.filter((id) => id !== chatId);
    return off ? [...rest, chatId] : rest;
  }
  function formatChatIds(ids) {
    return ids.join(" ");
  }
  function createChatSwitch(deps) {
    let queue = Promise.resolve();
    function serial(task) {
      const next = queue.then(task, task);
      queue = next.catch(() => {
      });
      return next;
    }
    async function current2() {
      const id = await deps.currentChatId();
      return { id, off: id !== null && parseChatIds(await deps.getArg(CHAT_OFF_ARG)).includes(id) };
    }
    async function write(id, off) {
      const ids = parseChatIds(await deps.getArg(CHAT_OFF_ARG));
      if (ids.includes(id) !== off) await deps.setArg(CHAT_OFF_ARG, formatChatIds(withChat(ids, id, off)));
      return { id, off };
    }
    return {
      current: () => serial(current2),
      set: (id, off) => serial(() => write(id, off)),
      toggle: () => serial(async () => {
        const now = await current2();
        return now.id === null ? now : write(now.id, !now.off);
      })
    };
  }

  // src/trimtext.ts
  var REASON_KEYS = /* @__PURE__ */ new Map([
    ["format", "trim.reason.format"],
    ["short", "trim.reason.short"],
    ["uncovered", "trim.reason.uncovered"],
    ["no_summaries", "trim.reason.no_summaries"],
    ["stale", "trim.reason.stale"],
    ["empty_packet", "trim.reason.empty_packet"],
    ["failed", "trim.reason.failed"],
    ["unsupported", "trim.reason.unsupported"]
  ]);
  function trimReason(lang, reason) {
    if (reason === null) return "";
    const key = REASON_KEYS.get(reason);
    return key ? t(lang, key) : t(lang, "trim.reason.other", { r: reason });
  }
  function trimStatusLine(lang, trim) {
    if (!trim) return null;
    if (trim.dropped > 0) {
      const locale = lang === "en" ? "en-US" : "ko-KR";
      return t(lang, "trim.left_out", { n: trim.dropped, t: trim.savedTokens.toLocaleString(locale) });
    }
    if (trim.reason !== null) {
      return t(lang, "trim.kept", { r: trimReason(lang, trim.reason) });
    }
    return null;
  }
  function coverageLine(lang, coverage) {
    const n = coverage?.recordedThroughTurn;
    if (typeof n !== "number" || !Number.isFinite(n)) return null;
    return t(lang, "trim.recorded_through", { n: n.toLocaleString(lang === "en" ? "en-US" : "ko-KR") });
  }
  function trimHudSuffix(lang, trim) {
    if (!trim) return "";
    if (trim.dropped > 0) {
      const locale = lang === "en" ? "en-US" : "ko-KR";
      return t(lang, "hud.trim.left_out", { n: trim.dropped, t: trim.savedTokens.toLocaleString(locale) });
    }
    if (trim.reason !== null) {
      return t(lang, "hud.trim.kept", { r: trimReason(lang, trim.reason) });
    }
    return "";
  }

  // src/hud.ts
  var OUTCOME_MS = 4e3;
  var DONE_MS = 3e3;
  var EMPTY = { request: null, progress: null };
  function pending(c) {
    return (c.extract?.pending ?? 0) + (c.embed?.pending ?? 0) + (c.summarize?.pending ?? 0);
  }
  function reduce(state, event, now) {
    switch (event.type) {
      case "request-start":
        return { ...state, request: { phase: "running" } };
      case "request-abandon":
        return state.request?.phase === "running" ? { ...state, request: null } : state;
      case "request-end":
        return { ...state, request: {
          phase: "done",
          outcome: event.outcome,
          chars: event.chars,
          error: event.error,
          deadlineMs: event.deadlineMs,
          until: now + OUTCOME_MS,
          reused: event.reused,
          vectors: event.vectors,
          rewritten: event.rewritten,
          trim: event.trim
        } };
      case "coverage": {
        const shown = state.progress && "coverage" in state.progress ? state.progress : null;
        if (pending(event.coverage) > 0) {
          return { ...state, progress: {
            coverage: event.coverage,
            since: shown ? shown.since : event.coverage.produced ?? null,
            // The fewest seen: a failure of an old window that leaves the head must not hide a new one.
            failedSince: Math.min(shown ? shown.failedSince : Infinity, failures(event.coverage))
          } };
        }
        return shown ? { ...state, progress: {
          finishedUntil: now + DONE_MS,
          made: added(shown.since, event.coverage.produced),
          failed: Math.max(0, failures(event.coverage) - shown.failedSince)
        } } : state;
      }
      case "reset":
        return EMPTY;
      case "background":
        return state;
    }
  }
  function view(state, now, lang) {
    const r = state.request;
    if (r?.phase === "running") return { kind: "busy", text: t(lang, "hud.recalling"), fraction: null, icon: true };
    if (r?.phase === "done" && now < r.until) {
      if (r.outcome === "injected") {
        const how = [
          r.reused ? t(lang, "hud.reused") : "",
          r.vectors === "fallback" ? t(lang, "hud.lexical") : "",
          r.rewritten ? t(lang, "hud.rewritten", { n: r.rewritten }) : "",
          trimHudSuffix(lang, r.trim)
        ].filter(Boolean).join("");
        return { kind: "ok", text: t(lang, "hud.injected", { n: r.chars }) + how, fraction: null };
      }
      if (r.outcome === "nothing-relevant") {
        return { kind: "muted", text: t(lang, "hud.nothing") + (r.rewritten ? t(lang, "hud.rewritten", { n: r.rewritten }) : "") + trimHudSuffix(lang, r.trim), fraction: null };
      }
      if (r.outcome === "chat-off") return { kind: "muted", text: t(lang, "hud.chat_off"), fraction: null };
      if (r.outcome === "skipped") return { kind: "warn", text: t(lang, "hud.skipped", { r: t(lang, "hud.reason.no_turn") }), fraction: null };
      const reason = r.error?.startsWith("deadline") ? t(lang, "hud.reason.deadline", { s: Math.round((r.deadlineMs ?? 0) / 100) / 10 }) : t(lang, "hud.reason.error");
      return { kind: "warn", text: t(lang, "hud.skipped", { r: reason }), fraction: null };
    }
    const p = state.progress;
    if (p && "coverage" in p) return progressView(p.coverage, lang);
    if (p && now < p.finishedUntil) {
      return p.failed ? { kind: "warn", text: doneText(p.made, lang, p.failed), fraction: 1 } : { kind: "ok", text: doneText(p.made, lang), fraction: 1 };
    }
    return null;
  }
  function added(since, now) {
    if (!since || !now) return null;
    return { facts: Math.max(0, now.facts - since.facts), summaries: Math.max(0, now.summaries - since.summaries) };
  }
  function failures(c) {
    return (c.extract?.failed ?? 0) + (c.embed?.failed ?? 0) + (c.summarize?.failed ?? 0);
  }
  function doneText(made, lang, failed = 0) {
    const parts = [
      made?.facts ? t(lang, "hud.made.facts", { n: made.facts }) : "",
      made?.summaries ? t(lang, "hud.made.summaries", { n: made.summaries }) : ""
    ].filter(Boolean);
    if (failed) return [t(lang, "hud.failed", { n: failed }), ...parts].join(" \xB7 ");
    return parts.length ? `\u2713 ${parts.join(" \xB7 ")}` : t(lang, "hud.done");
  }
  function progressView(c, lang) {
    const parts = [];
    let done = 0;
    let total = 0;
    let failed = 0;
    for (const [key, counts] of [["hud.extract", c.extract], ["hud.embed", c.embed]]) {
      if (!counts || counts.total === 0) continue;
      parts.push(t(lang, key, { d: counts.done, n: counts.total }));
      done += counts.done;
      total += counts.total;
      failed += counts.failed;
    }
    if (c.summarize?.pending) parts.push(t(lang, "hud.summarize", { n: c.summarize.pending }));
    failed += c.summarize?.failed ?? 0;
    if (failed) parts.push(t(lang, "hud.failed", { n: failed }));
    return { kind: "busy", text: parts.join(" \xB7 "), fraction: total && !c.summarize?.pending ? done / total : null };
  }
  function nextChange(state, now) {
    const times = [
      state.request?.phase === "done" ? state.request.until : null,
      state.progress && "finishedUntil" in state.progress ? state.progress.finishedUntil : null
    ].filter((x) => x !== null && x > now);
    return times.length ? Math.min(...times) : null;
  }
  function parseCoverage(json) {
    const body = json ?? {};
    const counts = (section, doneKey) => section?.generation && typeof section.eligible === "number" ? {
      done: Number(section[doneKey]) || 0,
      total: section.eligible,
      pending: Number(section.pending) || 0,
      failed: Number(section.failed) || 0
    } : null;
    const jobs = body.summaries;
    const summarize = jobs && typeof jobs.pending === "number" ? { pending: jobs.pending, failed: Number(jobs.failed) || 0 } : null;
    const made = body.produced;
    const produced = made && typeof made.facts === "number" && typeof made.summaries === "number" ? { facts: made.facts, summaries: made.summaries } : null;
    return { extract: counts(body.extraction, "compiled"), embed: counts(body.embeddings, "embedded"), produced, summarize };
  }

  // src/icon.ts
  var SHAPE = '<path d="M6 19V5l12 14V9.5"/><circle cx="18" cy="5.5" r="1.75" fill="currentColor"/>';
  var svg = (a11y, title) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" ${a11y}>${title}${SHAPE}</svg>`;
  var NMOS_ICON = svg('aria-hidden="true"', "");
  function namedIcon(name) {
    const text2 = name.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    return svg(`role="img" aria-label="${text2}"`, `<title>${text2}</title>`);
  }

  // src/palette.ts
  var PALETTE = {
    // Surfaces, darkest to lightest (soft charcoal for long reading sessions).
    bg: "#16181e",
    sunken: "#12141a",
    surface: "#1e212a",
    raised: "#262a35",
    raisedHover: "#303543",
    // Hairlines on any surface.
    line: "rgba(255,255,255,0.08)",
    lineStrong: "rgba(255,255,255,0.13)",
    lineHover: "rgba(255,255,255,0.2)",
    // Text, strongest to faintest. `textFaint` still passes 4.5:1 on `surface`; `textGhost` is for marks only.
    textStrong: "#eef1f7",
    text: "#dce1ec",
    textSoft: "#b6bece",
    textMuted: "#9294a0",
    textFaint: "#878b99",
    textGhost: "#676c7d",
    // White text on `accent` passes 4.5:1.
    accent: "#4a6af5",
    accentHover: "#3f5ee6",
    link: "#85a6ff",
    ok: "#4fd18b",
    err: "#f05d5e",
    warn: "#e8ac43",
    violet: "#a78bfa",
    cyan: "#38bdf8"
  };
  function alpha(key, a) {
    const hex = PALETTE[key];
    if (!hex.startsWith("#")) throw new Error(`palette ${key} is not a hex colour`);
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${n >> 16},${n >> 8 & 255},${n & 255},${a})`;
  }
  function paletteVars() {
    return Object.entries(PALETTE).map(([k, v]) => `--c-${k.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase())}:${v}`).join(";");
  }

  // src/hud-host.ts
  var POLL_MS = 3e3;
  var MAX_POLL_ERRORS = 5;
  var MIN_POLL_GAP_MS = 1e3;
  var CLASS = "nmos-hud";
  var ROOT_STYLE = `position:fixed;top:calc(8px + env(safe-area-inset-top));right:calc(8px + env(safe-area-inset-right));z-index:900;min-width:140px;max-width:min(320px,calc(100vw - 72px));background:${alpha("surface", 0.92)};border:1px solid ${PALETTE.lineStrong};border-radius:16px;padding:6px 12px;font:13px/1.4 system-ui,-apple-system,"Noto Sans KR",sans-serif;backdrop-filter:blur(14px);box-shadow:0 4px 16px rgba(0,0,0,.45);cursor:pointer;user-select:none;transition:all .15s ease`;
  var LINE_STYLE = `display:flex;align-items:center;gap:7px;color:${PALETTE.text}`;
  var ICON_STYLE = "display:none;flex:none;width:14px;height:14px";
  var TEXT_STYLE = "display:block;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis";
  var TRACK_STYLE = `display:none;height:2px;margin-top:5px;background:${PALETTE.lineStrong};border-radius:1px;overflow:hidden`;
  var FILL_STYLE = `height:2px;width:0;background:${PALETTE.accent};border-radius:1px;transition:width .3s ease`;
  var COLORS = { busy: PALETTE.text, ok: PALETTE.ok, muted: PALETTE.textMuted, warn: PALETTE.warn };
  function createHud(deps) {
    let state = EMPTY;
    let problem = null;
    let drawn = null;
    let conversation = null;
    let where = null;
    let pollTimer = null;
    let expiryTimer = null;
    let pollErrors = 0;
    let lastPoll = -Infinity;
    let queue = Promise.resolve();
    function run(task) {
      queue = queue.then(task).catch(fail);
    }
    async function fail(error) {
      problem = error instanceof Error ? error.message : String(error);
      deps.debug("[NMOS] progress display stopped for this session:", problem);
      stopPolling();
      await erase().catch(() => {
      });
    }
    async function active() {
      if (!problem && await deps.enabled()) return true;
      stopPolling();
      await erase();
      return false;
    }
    async function erase() {
      if (expiryTimer !== null) deps.clearTimer(expiryTimer);
      expiryTimer = null;
      const d = drawn;
      drawn = null;
      if (!d) return;
      await d.root.removeEventListener("click", d.listener);
      await d.root.remove();
    }
    async function draw() {
      const doc = await deps.rootDocument();
      if (!doc) throw new Error("no access to the PocketRisu page (mainDom permission)");
      await (await doc.querySelector(`.${CLASS}`))?.remove();
      const body = await doc.querySelector("body");
      if (!body) throw new Error("the PocketRisu page has no body");
      const root = await doc.createElement("div");
      await root.addClass(CLASS);
      await root.setStyleAttribute(ROOT_STYLE);
      const line = await doc.createElement("div");
      await line.setStyleAttribute(LINE_STYLE);
      const icon2 = await doc.createElement("span");
      await icon2.setStyleAttribute(ICON_STYLE);
      await icon2.setInnerHTML(NMOS_ICON);
      const text2 = await doc.createElement("span");
      await text2.setStyleAttribute(TEXT_STYLE);
      await line.appendChild(icon2);
      await line.appendChild(text2);
      const track = await doc.createElement("div");
      await track.setStyleAttribute(TRACK_STYLE);
      const fill = await doc.createElement("div");
      await fill.setStyleAttribute(FILL_STYLE);
      await track.appendChild(fill);
      await root.appendChild(line);
      await root.appendChild(track);
      await body.appendChild(root);
      const listener = await root.addEventListener("click", (event) => {
        void hit(event);
      });
      return { root, line, icon: icon2, text: text2, track, fill, listener, last: "" };
    }
    async function hit(event) {
      try {
        const d = drawn;
        if (!d) return;
        const r = await d.root.getBoundingClientRect();
        if (event.clientX >= r.left && event.clientX <= r.right && event.clientY >= r.top && event.clientY <= r.bottom) {
          deps.openPanel();
        }
      } catch (error) {
        deps.debug("[NMOS] progress display click failed:", error instanceof Error ? error.message : error);
      }
    }
    async function render2() {
      if (expiryTimer !== null) deps.clearTimer(expiryTimer);
      expiryTimer = null;
      const now = deps.now();
      const v = view(state, now, await deps.lang());
      if (!v) return erase();
      drawn ??= await draw();
      const d = drawn;
      const key = JSON.stringify(v);
      if (d.last !== key) {
        d.last = key;
        await d.text.setTextContent(v.text);
        await d.line.setStyle("color", COLORS[v.kind]);
        await d.icon.setStyle("display", v.icon ? "block" : "none");
        await d.track.setStyle("display", v.fraction === null ? "none" : "block");
        if (v.fraction !== null) await d.fill.setStyle("width", `${Math.round(v.fraction * 100)}%`);
      }
      const next = nextChange(state, now);
      if (next !== null) expiryTimer = deps.setTimer(() => {
        expiryTimer = null;
        run(render2);
      }, next - now);
    }
    async function follow(conversationId) {
      if (!conversationId) return;
      where = await deps.position();
      if (conversationId === conversation) return;
      conversation = conversationId;
      state = { ...state, progress: null };
      stopPolling();
    }
    function startPolling() {
      if (pollTimer !== null || !conversation) return;
      pollErrors = 0;
      pollTimer = deps.setTimer(() => run(poll), Math.max(0, lastPoll + MIN_POLL_GAP_MS - deps.now()));
    }
    function stopPolling() {
      if (pollTimer !== null) deps.clearTimer(pollTimer);
      pollTimer = null;
    }
    async function poll() {
      pollTimer = null;
      if (!await active() || !conversation) return;
      if (where !== null && await deps.position() !== where) {
        conversation = null;
        state = { ...state, progress: null };
        return render2();
      }
      let again = false;
      lastPoll = deps.now();
      try {
        const coverage = parseCoverage(await deps.coverage(conversation));
        pollErrors = 0;
        state = reduce(state, { type: "coverage", coverage }, deps.now());
        again = pending(coverage) > 0;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        deps.debug("[NMOS] coverage poll failed:", message);
        again = !/HTTP 404/.test(message) && ++pollErrors < MAX_POLL_ERRORS;
      }
      await render2();
      if (again) pollTimer = deps.setTimer(() => run(poll), POLL_MS);
    }
    return {
      /** Request-path activity from core.ts. */
      event(event) {
        run(async () => {
          if (!await active()) return;
          if (event.type === "request-end" && event.outcome === "chat-off") {
            conversation = null;
            where = null;
            stopPolling();
            state = { ...reduce(state, event, deps.now()), progress: null };
            return render2();
          }
          if (event.type === "request-end" || event.type === "background") await follow(event.conversationId);
          state = reduce(state, event, deps.now());
          await render2();
          if (event.type === "request-end" || event.type === "background") startPolling();
        });
      },
      /** A panel action queued background work: follow that conversation, or the last one seen. */
      background(conversationId) {
        run(async () => {
          if (!await active()) return;
          if (conversationId) await follow(conversationId);
          startPolling();
        });
      },
      /** The toggle changed: off erases at once; on clears an earlier failure. */
      refresh() {
        run(async () => {
          if (await deps.enabled()) {
            problem = null;
            return;
          }
          stopPolling();
          state = EMPTY;
          await erase();
        });
      },
      /** Why the display stopped for this session, if it did. */
      problem: () => problem,
      /** Resolves when queued work has run (tests). */
      settled: () => queue
    };
  }

  // src/route.ts
  function routeFor(url, setting) {
    if (setting === "direct" || setting === "server") return setting;
    try {
      const host = new URL(url).hostname.replace(/^\[|\]$/g, "");
      return ["localhost", "127.0.0.1", "::1"].includes(host) ? "direct" : "server";
    } catch {
      return "direct";
    }
  }

  // src/parser-form.ts
  function parserDraft(text2) {
    if (!text2.trim()) return { ok: false, error: "blank" };
    let spec;
    try {
      spec = JSON.parse(text2);
    } catch {
      return { ok: false, error: "json" };
    }
    if (!spec || typeof spec !== "object" || Array.isArray(spec) || !("rules" in spec) || !Array.isArray(spec.rules) || spec.rules.some((r) => !r || typeof r !== "object" || Array.isArray(r))) {
      return { ok: false, error: "shape" };
    }
    return { ok: true, rules: spec.rules };
  }
  function presetRules(rules) {
    return rules.map(({ card: _card, ...rule }) => rule);
  }
  function parserBindings(spec) {
    const parsed = parserDraft(JSON.stringify(spec) ?? "");
    const cards = /* @__PURE__ */ new Map();
    let unbound = 0;
    if (parsed.ok) for (const rule of parsed.rules) {
      if (typeof rule.card !== "string" || !rule.card.trim()) unbound += 1;
      else cards.set(rule.card, (cards.get(rule.card) ?? 0) + 1);
    }
    return { cards: [...cards].map(([name, count2]) => ({ name, count: count2 })), unbound };
  }

  // src/icons.ts
  var SVG_NS = "http://www.w3.org/2000/svg";
  var SHAPES = {
    // Official NMOS mark from icon.ts: one-stroke N with a memory node.
    brand: [
      ["path", { d: "M6 19V5l12 14V9.5", "stroke-width": "1.75" }],
      ["circle", { cx: "18", cy: "5.5", r: "1.75", fill: "currentColor", stroke: "none" }]
    ],
    home: [
      ["path", { d: "M3 10.5 12 3l9 7.5" }],
      ["path", { d: "M5.5 9.5V20a1 1 0 0 0 1 1h4v-6h3v6h4a1 1 0 0 0 1-1V9.5" }]
    ],
    book: [
      ["path", { d: "M4 5.5A2.5 2.5 0 0 1 6.5 3H12v18H6.5A2.5 2.5 0 0 0 4 21Z" }],
      ["path", { d: "M20 5.5A2.5 2.5 0 0 0 17.5 3H12v18h5.5a2.5 2.5 0 0 1 2.5 0Z" }]
    ],
    feather: [
      ["path", { d: "M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5Z" }],
      ["line", { x1: "16", y1: "8", x2: "2", y2: "22" }],
      ["line", { x1: "17.5", y1: "15", x2: "9", y2: "15" }]
    ],
    sliders: [
      ["line", { x1: "4", y1: "6", x2: "20", y2: "6" }],
      ["line", { x1: "4", y1: "12", x2: "20", y2: "12" }],
      ["line", { x1: "4", y1: "18", x2: "20", y2: "18" }],
      ["circle", { cx: "9", cy: "6", r: "2", fill: "var(--c-bg)" }],
      ["circle", { cx: "15", cy: "12", r: "2", fill: "var(--c-bg)" }],
      ["circle", { cx: "10", cy: "18", r: "2", fill: "var(--c-bg)" }]
    ],
    chat: [
      ["path", { d: "M21 11.5a8.5 8.5 0 0 1-8.5 8.5 8.6 8.6 0 0 1-3.8-.9L3 21l1.9-5.7a8.5 8.5 0 1 1 16.1-3.8Z" }]
    ],
    chevronDown: [
      ["path", { d: "m6 9 6 6 6-6" }]
    ],
    alert: [
      ["path", { d: "M10.3 3.9 1.8 18.2A2 2 0 0 0 3.5 21h17a2 2 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0Z" }],
      ["line", { x1: "12", y1: "9", x2: "12", y2: "13.5" }],
      ["line", { x1: "12", y1: "17", x2: "12.01", y2: "17" }]
    ],
    map: [
      ["circle", { cx: "6", cy: "7", r: "2.5" }],
      ["circle", { cx: "18", cy: "7", r: "2.5" }],
      ["circle", { cx: "12", cy: "18", r: "2.5" }],
      ["line", { x1: "8.2", y1: "7", x2: "15.8", y2: "7" }],
      ["line", { x1: "7.3", y1: "9.1", x2: "10.7", y2: "15.8" }],
      ["line", { x1: "16.7", y1: "9.1", x2: "13.3", y2: "15.8" }]
    ],
    terminal: [
      ["polyline", { points: "4 17 10 11 4 5" }],
      ["line", { x1: "12", y1: "19", x2: "20", y2: "19" }]
    ],
    refresh: [
      ["path", { d: "M21 12a9 9 0 1 1-2.64-6.36" }],
      ["polyline", { points: "21 3 21 9 15 9" }]
    ],
    close: [
      ["line", { x1: "18", y1: "6", x2: "6", y2: "18" }],
      ["line", { x1: "6", y1: "6", x2: "18", y2: "18" }]
    ],
    copy: [
      ["rect", { x: "9", y: "9", width: "13", height: "13", rx: "2" }],
      ["path", { d: "M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" }]
    ],
    sparkles: [
      ["path", { d: "M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6Z" }],
      ["path", { d: "M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9Z" }]
    ],
    power: [
      ["path", { d: "M18.36 6.64a9 9 0 1 1-12.73 0" }],
      ["line", { x1: "12", y1: "2", x2: "12", y2: "12" }]
    ],
    plug: [
      ["path", { d: "M12 22v-5" }],
      ["path", { d: "M9 8V2" }],
      ["path", { d: "M15 8V2" }],
      ["path", { d: "M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z" }]
    ],
    cpu: [
      ["rect", { x: "6", y: "6", width: "12", height: "12", rx: "2" }],
      ["rect", { x: "9.5", y: "9.5", width: "5", height: "5", rx: "0.5" }],
      ["path", { d: "M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" }]
    ],
    database: [
      ["ellipse", { cx: "12", cy: "5", rx: "8", ry: "3" }],
      ["path", { d: "M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5" }],
      ["path", { d: "M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3" }]
    ],
    shield: [
      ["path", { d: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" }]
    ],
    eye: [
      ["path", { d: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" }],
      ["circle", { cx: "12", cy: "12", r: "3" }]
    ],
    archive: [
      ["rect", { x: "3", y: "4", width: "18", height: "4", rx: "1" }],
      ["path", { d: "M5 8v11a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8" }],
      ["line", { x1: "10", y1: "13", x2: "14", y2: "13" }]
    ],
    check: [
      ["polyline", { points: "20 6 9 17 4 12" }]
    ]
  };
  function icon(name, size = 16, cls = "ic") {
    const svg2 = document.createElementNS(SVG_NS, "svg");
    svg2.setAttribute("viewBox", "0 0 24 24");
    svg2.setAttribute("width", String(size));
    svg2.setAttribute("height", String(size));
    svg2.setAttribute("fill", "none");
    svg2.setAttribute("stroke", "currentColor");
    svg2.setAttribute("stroke-width", "1.9");
    svg2.setAttribute("stroke-linecap", "round");
    svg2.setAttribute("stroke-linejoin", "round");
    svg2.setAttribute("aria-hidden", "true");
    if (cls) svg2.setAttribute("class", cls);
    for (const [tag, attrs] of SHAPES[name]) {
      const child = document.createElementNS(SVG_NS, tag);
      for (const [k, v] of Object.entries(attrs)) child.setAttribute(k, v);
      svg2.appendChild(child);
    }
    return svg2;
  }

  // src/inspector.ts
  var TAGS = /* @__PURE__ */ new Set([
    "DIV",
    "P",
    "H1",
    "H2",
    "SPAN",
    "B",
    "BR",
    "A",
    "TABLE",
    "THEAD",
    "TBODY",
    "TR",
    "TH",
    "TD",
    "DETAILS",
    "SUMMARY"
  ]);
  var UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
  var TURN = "/t/(?:0|[1-9][0-9]{0,6})";
  var SECTION = /^s-[a-z]{1,20}$/;
  var MAP = `map(?:\\?focus=${UUID})?`;
  var ACTS = /* @__PURE__ */ new Set(["notes", "settings", "backup", "retry"]);
  function inspectorApiPath(href) {
    const m = new RegExp(`^/inspector(/c/${UUID}(?:/e/${UUID}|${TURN})?)?(?:[?#]|$)`, "i").exec(href ?? "");
    if (m) return `/v1/inspector${m[1] ?? ""}`;
    const v = new RegExp(`^/views(/chats|/c/${UUID}/(?:memory|working|${MAP}|person/${UUID})|/hub\\?conversation=${UUID})(?:#|$)`, "i").exec(href ?? "");
    return v ? `/v1/views${v[1]}` : null;
  }
  function inspectorConversation(path) {
    const m = new RegExp(`^/v1/inspector/c/(${UUID})(?:/e/${UUID}|${TURN})?$`, "i").exec(path) ?? new RegExp(`^/v1/views/c/(${UUID})/(?:memory|working|${MAP}|person/${UUID})$`, "i").exec(path);
    return m ? m[1] : null;
  }
  function inspectorEntity(path) {
    const m = new RegExp(`^/v1/inspector/c/(${UUID})/e/(${UUID})$`, "i").exec(path) ?? new RegExp(`^/v1/views/c/(${UUID})/person/(${UUID})$`, "i").exec(path);
    return m ? { conversation: m[1], entity: m[2] } : null;
  }
  var REPAIR = /^(thread_close|thread_reopen|secret_found_out|secret_keep|fact_retract|fact_correct|fact_lock|fact_restore|state_dismiss|entity_exclude|undo|undo_batch|alias_join):(-?[0-9a-f-]{1,64})(?::([A-Za-z0-9%._~,-]{1,600}))?$/;
  var BULK_KINDS = /* @__PURE__ */ new Set(["thread_close", "fact_retract", "fact_lock", "fact_restore", "state_dismiss"]);
  var ID2 = /^-?[0-9a-f-]{1,64}$/;
  function bulkRequest(raw) {
    if (raw === void 0) return void 0;
    if (!raw || typeof raw !== "object") return null;
    const r = raw;
    if ("undo" in r) return typeof r.undo === "string" && ID2.test(r.undo) && Object.keys(r).length === 1 ? { undo: r.undo } : null;
    if (typeof r.kind !== "string" || !BULK_KINDS.has(r.kind) || typeof r.item !== "string" || !ID2.test(r.item)) return null;
    if (r.outcome !== void 0 && (typeof r.outcome !== "string" || !/^[a-z_]{1,32}$/.test(r.outcome))) return null;
    return { kind: r.kind, item: r.item, ...typeof r.outcome === "string" ? { outcome: r.outcome } : {} };
  }
  function bulkMark(value) {
    if (!value || value.length > 2e3) return null;
    let raw;
    try {
      raw = JSON.parse(value);
    } catch {
      return null;
    }
    if (!raw || typeof raw !== "object") return null;
    const r = raw;
    if (typeof r.g !== "string" || !/^[a-z_]{1,40}$/.test(r.g) || typeof r.l !== "string" || r.l.length > 120) return null;
    const apply = bulkRequest(r.apply);
    const retract = bulkRequest(r.retract);
    if (apply === null || retract === null || !apply && !retract) return null;
    return { g: r.g, l: r.l, ...apply ? { apply } : {}, ...retract ? { retract } : {} };
  }
  function repairAction(value) {
    const m = value ? REPAIR.exec(value) : null;
    if (!m?.[1] || !m[2]) return null;
    let extra = null;
    if (m[3] !== void 0) {
      try {
        extra = decodeURIComponent(m[3]);
      } catch {
        return null;
      }
      if (!extra.trim() || extra.length > 120 || /[\u0000-\u001f\u007f]/.test(extra)) return null;
    }
    return { kind: m[1], item: m[2], extra };
  }
  function aliasPair(action) {
    if (action.kind !== "alias_join" || !action.extra || !/^[0-9]+$/.test(action.item)) return null;
    const at = action.extra.indexOf("|");
    const name = at > 0 ? action.extra.slice(0, at).trim() : "";
    const same_as = at > 0 ? action.extra.slice(at + 1).trim() : "";
    return name && same_as ? { name, same_as } : null;
  }
  function closeOutcomes(extra) {
    return (extra ?? "").split(",").filter((o) => /^[a-z_]{1,24}$/.test(o));
  }
  function splitChoices(self) {
    const own = new Set(self.names.map((n) => n.trim().toLowerCase()));
    const seen = /* @__PURE__ */ new Set();
    const out = [];
    for (const { name, other } of self.aliases ?? []) {
      const a = name.trim().toLowerCase();
      const b = other.trim().toLowerCase();
      const key = a < b ? `${a}\0${b}` : `${b}\0${a}`;
      if (a === b || !own.has(a) || !own.has(b) || seen.has(key)) continue;
      seen.add(key);
      out.push({ name, other });
    }
    return out;
  }
  function linkChoices(entities, id) {
    const self = entities.find((e) => e.id === id);
    if (!self || !Array.isArray(self.links)) return null;
    const others = entities.filter((e) => e.id !== id && e.type === self.type).sort((a, b) => b.mentions - a.mentions);
    return { self, others };
  }
  function entityNamed(entities, type, name) {
    return entities.find((e) => e.type === type && e.names.includes(name)) ?? null;
  }
  function sectionTarget(href) {
    const id = href?.startsWith("#") ? href.slice(1) : "";
    return SECTION.test(id) ? id : null;
  }
  var PERCENT = /^(?:100(?:\.0{1,3})?|\d{1,2}(?:\.\d{1,3})?)$/;
  var MARK_TEXT = /* @__PURE__ */ new Set(["data-v", "data-s", "data-o", "data-k", "data-p"]);
  var MARK_TEXT_MAX = 400;
  function keepAttribute(name, value) {
    switch (name) {
      case "data-act":
        return ACTS.has(value);
      case "class":
      case "title":
      case "open":
        return true;
      case "id":
        return SECTION.test(value);
      case "href":
        return inspectorApiPath(value) !== null || sectionTarget(value) !== null;
      case "data-repair":
        return repairAction(value) !== null;
      case "data-bulk":
        return bulkMark(value) !== null;
      case "data-l":
      case "data-w":
        return PERCENT.test(value);
      case "data-span":
        return value === "" || value === "recent";
      default:
        return MARK_TEXT.has(name) && value.length <= MARK_TEXT_MAX;
    }
  }
  function placeMarks(root) {
    for (const mark of Array.from(root.querySelectorAll("[data-l]"))) {
      const left = mark.getAttribute("data-l") ?? "";
      if (!PERCENT.test(left)) continue;
      mark.style.left = `${Number(left)}%`;
      const width = mark.getAttribute("data-w");
      if (width !== null && PERCENT.test(width)) mark.style.width = `calc(${Number(width)}% - 2px)`;
    }
  }
  function markDetail(mark, notes) {
    const card = document.createElement("div");
    card.className = "tl-card";
    const line = (text2, cls = "") => {
      const p = document.createElement("p");
      p.textContent = text2;
      if (cls) p.className = cls;
      card.append(p);
    };
    const row = mark.closest(".tl-row");
    line(mark.getAttribute("data-k") || ((row?.querySelector(".tl-lab .tl-k") ?? row?.querySelector(".tl-lab"))?.textContent ?? ""), "muted");
    line(mark.getAttribute("data-v") ?? "", "v");
    const outcome = mark.getAttribute("data-o");
    line((mark.getAttribute("data-s") ?? "") + (outcome ? ` \xB7 ${outcome}` : ""));
    const who = mark.getAttribute("data-p");
    if (who) line(who, "muted");
    if (mark.classList.contains("canon")) line(notes.canon, "muted");
    if (mark.classList.contains("owner")) line(notes.owner, "warn");
    const lane = mark.classList.contains("tl-bar") && mark.parentElement ? Array.from(mark.parentElement.children).filter((b) => b.classList.contains("tl-bar")) : [];
    if (lane.length > 1) {
      const list = document.createElement("div");
      list.className = "tl-hist";
      for (const bar of lane) {
        const row2 = document.createElement("p");
        if (bar === mark) row2.className = "cur";
        row2.textContent = `${bar.getAttribute("data-s") ?? ""}  ${bar.getAttribute("data-v") ?? ""}`;
        list.append(row2);
      }
      card.append(list);
    }
    return card;
  }
  function safeFragment(html) {
    const template = document.createElement("template");
    template.innerHTML = html;
    const clean = (parent) => {
      for (const node of Array.from(parent.childNodes)) {
        if (node.nodeType === Node.TEXT_NODE) continue;
        if (node.nodeType !== Node.ELEMENT_NODE || !TAGS.has(node.nodeName)) {
          node.remove();
          continue;
        }
        const element = node;
        for (const { name, value } of Array.from(element.attributes)) {
          if (!keepAttribute(name, value)) element.removeAttribute(name);
        }
        clean(element);
      }
    };
    clean(template.content);
    return template.content;
  }
  function localTime(iso, lang, now = /* @__PURE__ */ new Date()) {
    const then = new Date(iso);
    if (Number.isNaN(then.getTime())) return null;
    const locale = lang === "en" ? "en" : "ko";
    const title = then.toLocaleString(locale);
    const seconds = Math.round((then.getTime() - now.getTime()) / 1e3);
    const ago = Math.abs(seconds);
    if (seconds > 60 || ago >= 7 * 86400) {
      const date = then.toLocaleDateString(locale, { year: "numeric", month: "2-digit", day: "2-digit" });
      const time = then.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
      return { text: `${date} ${time}`, title };
    }
    const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
    const [value, unit] = ago < 45 ? [0, "second"] : ago < 2700 ? [Math.round(seconds / 60), "minute"] : ago < 79200 ? [Math.round(seconds / 3600), "hour"] : [Math.round(seconds / 86400), "day"];
    return { text: rtf.format(value, unit), title };
  }
  var PREVIEW_ORDER = [
    "persona",
    "self_relation",
    "self_thread",
    "secret",
    "fact_replaced",
    "fact_ended",
    "conflict_new",
    "repair",
    "canon_alias",
    "fact_merged",
    "thread_status",
    "thread_merged",
    "secret_merged",
    "fact_back",
    "thread_back",
    "secret_back",
    "self_relation_gone",
    "self_thread_gone",
    "conflict_gone",
    "persona_gone",
    "canon_alias_gone"
  ];
  function previewWarning(x) {
    return x.kind === "persona" || x.kind === "self_relation" || x.kind === "self_thread" || x.kind === "secret" && !!x.kept_from_holder;
  }
  function previewSubject(x) {
    if (x.kind === "fact_replaced") return x.by;
    return x.fact ?? x.thread ?? x.secret ?? x.conflict;
  }
  function previewLine(x, say2, status) {
    const text2 = previewWords(x, say2, status);
    if (text2 === null) return null;
    const turn = previewSubject(x)?.turn;
    return typeof turn === "number" && turn >= 0 ? `${text2}${say2("pv.turn", { t: turn })}` : text2;
  }
  function previewWords(x, say2, status) {
    const a = (i) => i?.text ?? "";
    switch (x.kind) {
      case "fact_replaced":
        return say2("pv.fact_replaced", { a: a(x.fact), b: a(x.by) });
      case "fact_merged":
        return say2("pv.fact_merged", { a: a(x.fact), b: a(x.by) });
      case "fact_ended":
        return say2("pv.fact_ended", { a: a(x.fact) });
      case "fact_back":
        return x.instead_of ? say2("pv.fact_back_instead", { a: a(x.fact), b: a(x.instead_of) }) : say2("pv.fact_back", { a: a(x.fact) });
      case "self_relation":
      case "self_relation_gone":
        return say2(`pv.${x.kind}`, { a: a(x.fact) });
      case "self_thread":
      case "self_thread_gone":
        return say2(`pv.${x.kind}`, { a: a(x.thread), w: x.thread?.by ?? "" });
      case "thread_status":
        return say2("pv.thread_status", { a: a(x.thread), s: status(x.status ?? "") });
      case "thread_merged":
      case "thread_back":
        return say2(`pv.${x.kind}`, { a: a(x.thread) });
      case "secret":
        if (x.kept_from_holder) return say2("pv.secret_holder", { a: a(x.secret) });
        if (x.kept_from_holder_gone) return say2("pv.secret_holder_gone", { a: a(x.secret) });
        return say2("pv.secret", { a: a(x.secret) });
      case "secret_merged":
      case "secret_back":
        return say2(`pv.${x.kind}`, { a: a(x.secret) });
      case "repair": {
        const k = x.repair?.kind ?? "";
        if (x.after == null) return say2("pv.repair_stops", { k });
        return say2(x.before == null ? "pv.repair_starts" : "pv.repair_moves", { k });
      }
      case "conflict_new":
      case "conflict_gone":
        return say2(`pv.${x.kind}`, { a: a(x.conflict) });
      case "persona":
      case "persona_gone":
        return say2(`pv.${x.kind}`);
      case "canon_alias":
      case "canon_alias_gone":
        return say2(`pv.${x.kind}`, { a: x.name ?? "", b: x.other ?? "" });
      default:
        return null;
    }
  }
  function previewText(p, say2, status = (s) => s, max = 8) {
    if (!p.changes) return [say2("pv.nothing")];
    const names = (es) => es.map((e) => e.name).join(", ");
    const out = [say2("pv.entities", { a: names(p.before), b: names(p.after) })];
    for (const e of p.after) {
      const others = e.names.filter((n) => n !== e.name);
      if (others.length) out.push(say2("pv.names", { a: e.name, n: others.join(", ") }));
    }
    const kept = p.after.length === 1 && p.before.length > 1 ? p.before.find((e) => e.id === p.after[0].id) : void 0;
    if (kept) out.push(say2("pv.kept", { a: kept.name }));
    const rank = (x) => {
      const i = PREVIEW_ORDER.indexOf(x.kind);
      return (previewWarning(x) ? 0 : 1e3) + (i < 0 ? PREVIEW_ORDER.length : i);
    };
    const lines = [...p.lines].sort((x, y) => rank(x) - rank(y)).map((x) => previewLine(x, say2, status)).filter((x) => x !== null);
    out.push(...lines.slice(0, max));
    const rest = p.lines.length - Math.min(lines.length, max);
    if (rest > 0) out.push(say2("pv.more", { n: rest }));
    return out;
  }

  // src/graph.ts
  var SVG = "http://www.w3.org/2000/svg";
  var UUID2 = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  var KINDS = /* @__PURE__ */ new Set(["character", "group", "place"]);
  var EDGE_KINDS = /* @__PURE__ */ new Set(["tie", "group", "place"]);
  var MARKS = /* @__PURE__ */ new Set(["setting", "story", "changed"]);
  var LIMIT = { nodes: 2e3, edges: 6e3, text: 200 };
  var LABEL_PX = 14;
  var ARC = 96;
  var NAMES_FROM = 60;
  var NAME_MAX = 24;
  var str = (v, max = LIMIT.text) => typeof v === "string" && v.length <= max ? v : null;
  var num2 = (v) => typeof v === "number" && Number.isFinite(v) && Math.abs(v) < 1e6 ? v : null;
  function parseGraph(raw) {
    if (!raw || typeof raw !== "object") return null;
    const r = raw;
    if (!Array.isArray(r.nodes) || !Array.isArray(r.edges) || !Array.isArray(r.suspects)) return null;
    if (r.nodes.length > LIMIT.nodes || r.edges.length + r.suspects.length > LIMIT.edges) return null;
    const nodes = [];
    for (const n of r.nodes) {
      const id = str(n?.id), name = str(n?.name), kind = str(n?.kind), x = num2(n?.x), y = num2(n?.y);
      const entity = n?.entity === null ? null : str(n?.entity);
      if (id === null || name === null || kind === null || !KINDS.has(kind) || x === null || y === null) return null;
      if (entity !== null && !UUID2.test(entity)) return null;
      nodes.push({ id, name, kind, lead: n.lead === true, entity, x, y });
    }
    const ids = new Set(nodes.map((n) => n.id));
    const ends = (e) => {
      const a = str(e?.a), b = str(e?.b);
      return a !== null && b !== null && ids.has(a) && ids.has(b) ? { a, b } : null;
    };
    const edges = [];
    for (const e of r.edges) {
      const ab = ends(e), kind = str(e?.kind), mark = str(e?.mark);
      if (!ab || kind === null || !EDGE_KINDS.has(kind) || mark === null || !MARKS.has(mark)) return null;
      edges.push({ ...ab, kind, mark });
    }
    const suspects = [];
    for (const s of r.suspects) {
      const ab = ends(s);
      if (!ab) return null;
      suspects.push(ab);
    }
    const w = r.words ?? {};
    const words = {};
    for (const k of ["legend", "fit", "all", "fewer", "tap", "ties", "left"]) words[k] = str(w[k], 400) ?? "";
    const focus = r.focus === null || r.focus === void 0 ? null : str(r.focus);
    return {
      nodes,
      edges,
      suspects,
      focus: focus !== null && ids.has(focus) ? focus : null,
      everyone: r.everyone === true,
      capped: r.capped === true,
      words
    };
  }
  function fitView(nodes, width, height) {
    const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
    const x0 = Math.min(0, ...xs), x1 = Math.max(0, ...xs), y0 = Math.min(0, ...ys), y1 = Math.max(0, ...ys);
    const pad = 36;
    const s = Math.min(Math.max(width - 2 * pad, 1) / Math.max(x1 - x0, 1), Math.max(height - 2 * pad, 1) / Math.max(y1 - y0, 1), 1);
    const w = width / s, h = height / s;
    return { x: (x0 + x1 - w) / 2, y: (y0 + y1 - h) / 2, w, h };
  }
  function zoomAt(v, factor, px, py, width, min, max) {
    const scale = Math.min(Math.max(width / v.w * factor, min), max);
    const f = scale / (width / v.w);
    const w = v.w / f, h = v.h / f;
    return { x: px - (px - v.x) / f, y: py - (py - v.y) / f, w, h };
  }
  function around(g, id) {
    const out = /* @__PURE__ */ new Set([id]);
    for (const e of g.edges) {
      if (e.a === id) out.add(e.b);
      if (e.b === id) out.add(e.a);
    }
    return out;
  }
  var make = (tag, cls) => {
    const node = document.createElementNS(SVG, tag);
    if (cls) node.setAttribute("class", cls);
    return node;
  };
  function drawGraph(box, g, open, toggle) {
    const svg2 = make("svg", "g-panel");
    const edges = make("g", ""), nodes = make("g", "");
    svg2.append(edges, nodes);
    const caption = document.createElement("p");
    caption.className = "v-note";
    caption.textContent = g.words.legend;
    const buttons = document.createElement("div");
    buttons.className = "v-graph-btns";
    const button = (text2, act) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = text2;
      b.addEventListener("click", act);
      buttons.append(b);
    };
    const pos = new Map(g.nodes.map((n) => [n.id, n]));
    const lines = [];
    for (const e of [...g.edges, ...g.suspects.map((s) => ({ ...s, mark: "split" }))]) {
      const a = pos.get(e.a), b = pos.get(e.b);
      const line = make("line", `g-e ${e.mark}`);
      line.setAttribute("x1", String(a.x));
      line.setAttribute("y1", String(a.y));
      line.setAttribute("x2", String(b.x));
      line.setAttribute("y2", String(b.y));
      edges.append(line);
      lines.push({ e, el: line });
    }
    const dots = /* @__PURE__ */ new Map();
    const parts = [];
    const far = Math.max(...g.nodes.map((n) => Math.abs(n.x))) / 3;
    for (const n of g.nodes) {
      const group = make("g", "g-node");
      const dot = make("circle", `g-n ${n.kind}${n.lead ? " lead" : ""}`);
      dot.setAttribute("cx", String(n.x));
      dot.setAttribute("cy", String(n.y));
      const label = make("text", `g-t${n.lead ? " lead" : ""}`);
      label.setAttribute("x", String(n.x));
      label.setAttribute("text-anchor", n.x < -far ? "start" : n.x > far ? "end" : "middle");
      label.textContent = n.name.length > NAME_MAX ? `${n.name.slice(0, NAME_MAX - 1)}\u2026` : n.name;
      group.append(dot, label);
      nodes.append(group);
      dots.set(group, n);
      parts.push({ n, dot, label, group });
    }
    box.replaceChildren(svg2, caption, buttons);
    const size = () => ({ w: svg2.clientWidth || 360, h: svg2.clientHeight || 420 });
    let fit = fitView(g.nodes, size().w, size().h);
    let view2 = fit;
    let picked = null;
    const scaleOf = (v) => size().w / v.w;
    const apply = () => {
      svg2.setAttribute("viewBox", `${view2.x} ${view2.y} ${view2.w} ${view2.h}`);
      const s = scaleOf(view2);
      const near = picked ? around(g, picked) : null;
      const names = ARC * s >= NAMES_FROM;
      for (const { n, dot, label } of parts) {
        dot.setAttribute("r", String((n.lead ? 9 : 6) / s));
        label.setAttribute("y", String(n.y + ((n.lead ? 9 : 6) + LABEL_PX + 2) / s));
        label.style.fontSize = `${LABEL_PX / s}px`;
        label.style.display = names || n.lead || near?.has(n.id) ? "" : "none";
      }
    };
    const pick = (id) => {
      picked = id;
      svg2.classList.toggle("sel", id !== null);
      const near = id ? around(g, id) : /* @__PURE__ */ new Set();
      for (const { n: n2, group } of parts) group.classList.toggle("on", near.has(n2.id));
      for (const { e, el: el2 } of lines) el2.classList.toggle("on", id !== null && (e.a === id || e.b === id));
      const n = id ? pos.get(id) : null;
      caption.textContent = n ? `${n.name} \xB7 ${g.words.ties.replace("{n}", String(near.size - 1))}${n.entity ? ` \xB7 ${g.words.tap}` : ""}` : g.words.legend;
      apply();
    };
    button(g.words.fit, () => {
      view2 = fit = fitView(g.nodes, size().w, size().h);
      apply();
    });
    if (g.capped || g.everyone) button(g.everyone ? g.words.fewer : g.words.all, () => toggle(!g.everyone));
    if (g.capped && g.words.left) {
      const left = document.createElement("span");
      left.className = "v-meta";
      left.textContent = g.words.left;
      buttons.append(left);
    }
    const pointers = /* @__PURE__ */ new Map();
    let moved = 0;
    let downOn = null;
    const unit = (clientX, clientY) => {
      const r = svg2.getBoundingClientRect();
      const s = scaleOf(view2);
      return { x: view2.x + (clientX - r.left) / s, y: view2.y + (clientY - r.top) / s };
    };
    const limits = () => [scaleOf(fit) * 0.8, Math.max(scaleOf(fit) * 8, 3)];
    svg2.addEventListener("pointerdown", (ev) => {
      pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
      if (pointers.size === 1) {
        moved = 0;
        downOn = ev.target instanceof Element ? ev.target : null;
      }
      svg2.setPointerCapture?.(ev.pointerId);
    });
    svg2.addEventListener("pointermove", (ev) => {
      const last = pointers.get(ev.pointerId);
      if (!last) return;
      const s = scaleOf(view2);
      if (pointers.size === 1) {
        moved += Math.abs(ev.clientX - last.x) + Math.abs(ev.clientY - last.y);
        view2 = { ...view2, x: view2.x - (ev.clientX - last.x) / s, y: view2.y - (ev.clientY - last.y) / s };
      } else if (pointers.size === 2) {
        const [p, q] = [...pointers.entries()].map(([id, at]) => id === ev.pointerId ? { x: ev.clientX, y: ev.clientY } : at);
        const [p0, q0] = [...pointers.values()];
        const before = Math.hypot(p0.x - q0.x, p0.y - q0.y), after = Math.hypot(p.x - q.x, p.y - q.y);
        const mid = unit((p.x + q.x) / 2, (p.y + q.y) / 2);
        if (before > 0) view2 = zoomAt(view2, after / before, mid.x, mid.y, size().w, ...limits());
        moved += 99;
      }
      pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
      apply();
    });
    const up = (ev) => {
      const single = pointers.size === 1;
      pointers.delete(ev.pointerId);
      if (!single || moved > 8 || ev.type === "pointercancel") return;
      const target = downOn?.closest(".g-node") ?? null;
      const n = target ? dots.get(target) : void 0;
      if (!n) return pick(null);
      if (picked === n.id && n.entity) return open(n.entity);
      pick(n.id);
    };
    svg2.addEventListener("pointerup", up);
    svg2.addEventListener("pointercancel", up);
    svg2.addEventListener("wheel", (ev) => {
      ev.preventDefault();
      const at = unit(ev.clientX, ev.clientY);
      view2 = zoomAt(view2, Math.exp(-ev.deltaY * 15e-4), at.x, at.y, size().w, ...limits());
      apply();
    }, { passive: false });
    pick(g.focus);
  }

  // src/carrytext.ts
  var CARRY_MAX_NAMES = 8;
  var REFUSAL_MARKER = /^(?:\/v1\/\S+ -> HTTP 422:\s*)?too_many_rows:\s*rows=(\d+)\s+max=(\d+)\b/;
  function carryRefusal(message) {
    const m = REFUSAL_MARKER.exec(message.trim());
    if (!m) return null;
    return { rows: Number(m[1]), max: Number(m[2]) };
  }
  function rawMessage(error) {
    return error instanceof Error ? error.message : String(error);
  }
  function isCarryNotFound(error) {
    return /\bHTTP 404\b|^404\b/.test(rawMessage(error));
  }
  function isCarryConflict(error) {
    return /\bHTTP 409\b|^409\b/.test(rawMessage(error));
  }
  function parseCutoffTurn(raw) {
    const trimmed = raw.trim();
    if (!trimmed) return { ok: true, value: null };
    if (!/^\d+$/.test(trimmed)) return { ok: false };
    const n = Number(trimmed);
    return Number.isSafeInteger(n) ? { ok: true, value: n } : { ok: false };
  }
  function carrySourceLabel(source) {
    const ch = (source.character ?? "").trim();
    const chat = (source.chat ?? "").trim();
    return ch && chat && chat !== ch ? `${ch} \xB7 ${chat}` : ch || chat || source.id.slice(0, 8);
  }
  function carryCutoffLabel(lang, turn) {
    return typeof turn === "number" && Number.isFinite(turn) ? t(lang, "carry.cutoff_turn", { t: turn }) : t(lang, "carry.cutoff_end");
  }
  function carryCountsLine(lang, counts) {
    return t(lang, "carry.pv_counts", {
      f: counts.facts,
      a: counts.aliases,
      th: counts.threads,
      story: t(lang, counts.story ? "carry.story_yes" : "carry.story_no")
    });
  }
  function carryErrorText(lang, error, fallback) {
    const raw = rawMessage(error);
    const refusal = carryRefusal(raw);
    if (refusal) return t(lang, "carry.too_large", { n: refusal.rows, m: refusal.max });
    if (isCarryNotFound(error)) {
      return /no link in force/i.test(raw) ? t(lang, "carry.err_no_link") : t(lang, "carry.err_not_found");
    }
    if (/^\/v1\/\S+ -> HTTP 422: /.test(raw)) return fallback(lang, error);
    const http = /^(?:\/v1\/\S+ -> )?HTTP \d{3}(?::\s*(.*))?$/.exec(raw.trim());
    if (http) {
      const detail = (http[1] ?? "").trim();
      return detail && detail !== "[object Object]" ? `${t(lang, "sidecar_error")}${detail}` : t(lang, "carry.err_failed");
    }
    return fallback(lang, error);
  }

  // src/restore.ts
  function base64Of(bytes) {
    let s = "";
    for (let i = 0; i < bytes.length; i += 32768) s += String.fromCharCode(...bytes.subarray(i, i + 32768));
    return btoa(s);
  }
  var CHUNK_TIMEOUT_MS = 12e4;
  async function uploadArchive(api, file, progress) {
    const up = await api("POST", "/v1/archive/uploads", { bytes: file.size });
    const size = up.chunk_bytes;
    progress(0, file.size);
    for (let index = 0, offset = 0; offset < file.size; index++, offset += size) {
      const bytes = await file.slice(offset, offset + size).arrayBuffer();
      const body = { data: base64Of(new Uint8Array(bytes)), sha256: await sha256HexOf(bytes) };
      const path = `/v1/archive/uploads/${up.id}/chunks/${index}`;
      try {
        await api("PUT", path, body, CHUNK_TIMEOUT_MS);
      } catch {
        await api("PUT", path, body, CHUNK_TIMEOUT_MS);
      }
      progress(Math.min(offset + size, file.size), file.size);
    }
    return up;
  }
  async function waitFor(api, id, states, sleep = (ms) => new Promise((r) => setTimeout(r, ms)), everyMs = 1e3) {
    for (; ; ) {
      const view2 = await api("GET", `/v1/archive/uploads/${id}`);
      if (states.includes(view2.state)) return view2;
      await sleep(everyMs);
    }
  }

  // src/usage.ts
  var count = (n) => n.toLocaleString("en-US");
  var calls = (n, lang) => lang === "en" ? `${count(n)} call${n === 1 ? "" : "s"}` : count(n);
  function usageText(u, lang) {
    const older = u.not_recorded ?? 0;
    if (!u.calls) return t(lang, older ? "usage.older_only" : "usage.none");
    const before = older ? t(lang, "usage.older", { n: count(older) }) : "";
    if (!u.reported) return t(lang, "usage.unreported", { calls: calls(u.calls, lang) }) + before;
    const cached = u.cached ? t(lang, "usage.cached", { n: count(u.cached) }) : "";
    const partial = u.reported < u.calls ? t(lang, "usage.partial", { r: count(u.reported), calls: calls(u.calls, lang) }) : "";
    const sides = [
      u.input_reported === 0 ? "" : t(lang, "usage.input", { n: count(u.input) }),
      u.output_reported === 0 ? "" : t(lang, "usage.output", { n: count(u.output) })
    ].filter(Boolean).join(" \xB7 ");
    if (!sides) {
      const only = u.cached ? ` \xB7 ${t(lang, "usage.cached_side", { n: count(u.cached) })}` : "";
      return t(lang, "usage.calls", { calls: calls(u.calls, lang) }) + only + partial + before;
    }
    return t(lang, "usage.line", { calls: calls(u.calls, lang), sides, cached }) + partial + before;
  }

  // src/ui.ts
  var LLM_PRESETS = [
    { label: "preset.off", url: "" },
    { label: "preset.ollama", url: OLLAMA_DOCKER },
    { label: "OpenRouter", url: "https://openrouter.ai/api/v1" },
    { label: "OpenAI", url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
    { label: "Google Gemini", url: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-2.5-flash" },
    { label: "Google Vertex AI", url: VERTEX_URL, model: "google/gemini-3.8-flash" },
    // checked on real Vertex (ADR 0022)
    { label: "preset.custom", url: "custom" }
  ];
  var EMBED_PRESETS = [
    { label: "preset.off", url: "" },
    { label: "preset.ollama", url: OLLAMA_DOCKER, model: "qwen3-embedding:0.6b", minSim: 0.42 },
    { label: "OpenAI", url: "https://api.openai.com/v1", model: "text-embedding-3-small" },
    { label: "Voyage AI", url: "https://api.voyageai.com/v1", model: "voyage-4-large", minSim: 0.3, hint: "emb.voyage_hint" },
    { label: "preset.custom", url: "custom" }
  ];
  var PARSER_EXAMPLE = {
    rules: [
      { id: "roster", kind: "block", role: "char", start: "<status>", end: "</status>", entity_line: "\\[(?P<entity>[^\\]]+)\\]" },
      { id: "hp", kind: "regex", pattern: "HP\\s*[:\uFF1A]\\s*(?P<value>\\d+\\s*/\\s*\\d+)", key: "HP" }
    ]
  };
  var SECTION_TITLE = {
    conn: "conn.title",
    llm: "llm.title",
    emb: "emb.title",
    rerank: "rerank.title",
    tune: "tune.title",
    trim: "trimset.title"
  };
  var CSS = `
html,body{margin:0;background:${PALETTE.bg}}
.nmos{${paletteVars()}}
.nmos{position:fixed;inset:0;overflow:auto;background:var(--c-bg);font:15px/1.6 system-ui,-apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;color:var(--c-text);-webkit-font-smoothing:antialiased}
.nmos *{box-sizing:border-box}
.nmos svg.ic{flex:none;display:inline-block;vertical-align:-2px}
.nmos .wrap{max-width:760px;margin:0 auto;padding:20px 16px 32px}
.nmos.shell-on .wrap{max-width:1120px;padding:18px 22px 48px}
.nmos header{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.nmos h1{font-size:20px;font-weight:600;letter-spacing:-0.01em;margin:0;flex:1;white-space:nowrap;color:var(--c-text-strong)}
.nmos .tabs{display:flex;gap:6px;border-bottom:1px solid var(--c-line);margin:8px 0 8px}
.nmos .tabs button{background:none;border:0;border-bottom:2px solid transparent;border-radius:0;padding:9px 14px;color:var(--c-text-muted);font-size:15px;font-weight:500;transition:all .15s ease}
.nmos .tabs button:hover:not(:disabled){background:none;border-bottom-color:transparent;color:var(--c-text)}
.nmos .tabs button.on,.nmos .tabs button.on:hover:not(:disabled){color:var(--c-text-strong);border-bottom-color:var(--c-accent)}
.nmos .card{background:var(--c-surface);border:1px solid var(--c-line);border-radius:12px;padding:18px 20px;margin:14px 0}
.nmos h2{font-size:16.5px;font-weight:650;letter-spacing:-0.01em;color:var(--c-text-strong);margin:0 0 4px}
.nmos .sub{color:var(--c-text-muted);font-size:13.5px;line-height:1.55;margin:0 0 12px}
.nmos label{display:block;font-size:13px;font-weight:500;color:var(--c-text-muted);margin:12px 0 5px;letter-spacing:0.01em}
.nmos input,.nmos select,.nmos textarea{width:100%;background:var(--c-sunken);color:var(--c-text);border:1px solid var(--c-line-strong);border-radius:8px;padding:9px 12px;font:inherit;font-size:15px;transition:border-color .15s ease,box-shadow .15s ease}
.nmos input:focus,.nmos select:focus,.nmos textarea:focus{border-color:${alpha("accent", 0.7)};outline:none;box-shadow:0 0 0 3px ${alpha("accent", 0.22)}}
.nmos header select,.nmos .nmos-top-right select{width:auto;padding:5px 9px;font-size:13px;border-radius:8px}
.nmos textarea{min-height:150px;font-family:ui-monospace,monospace;font-size:13.5px;line-height:1.6}
.nmos .row{display:flex;gap:12px;flex-wrap:wrap}.nmos .row>*{flex:1;min-width:140px}
.nmos .btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;align-items:center}
.nmos button{background:var(--c-raised);color:var(--c-text);border:1px solid var(--c-line-strong);border-radius:8px;padding:8px 14px;font:inherit;font-size:14px;font-weight:500;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px;transition:background .15s ease,border-color .15s ease,color .15s ease}
.nmos button:hover:not(:disabled){background:var(--c-raised-hover);color:var(--c-text-strong);border-color:var(--c-line-hover)}
.nmos button:focus-visible{outline:2px solid ${alpha("accent", 0.65)};outline-offset:1px}
.nmos button.primary{background:var(--c-accent);border-color:var(--c-accent);color:#fff}
.nmos button.primary:hover:not(:disabled){background:var(--c-accent-hover);border-color:var(--c-accent-hover)}
.nmos button.danger{background:${alpha("err", 0.14)};border-color:${alpha("err", 0.42)};color:var(--c-err)}
.nmos button.danger:hover:not(:disabled){background:${alpha("err", 0.24)};border-color:${alpha("err", 0.6)};color:var(--c-text-strong)}
.nmos button.ghost{background:transparent;border-color:transparent;color:var(--c-text-muted)}
.nmos button.ghost:hover:not(:disabled){background:var(--c-raised);color:var(--c-text-strong);border-color:var(--c-line)}
.nmos button:disabled{opacity:.42;cursor:default}
.nmos .msg{margin-top:10px;font-size:13.5px;white-space:pre-wrap}
.nmos .ok{color:var(--c-ok)}.nmos .err{color:var(--c-err)}.nmos .warn{color:var(--c-warn)}.nmos .muted{color:var(--c-text-muted)}
.nmos .check{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:14px;color:var(--c-text-soft)}.nmos .check input{width:auto}
.nmos .preview{margin:8px 0;padding:10px 12px;border-left:3px solid var(--c-accent);background:var(--c-sunken);border-radius:0 8px 8px 0;font-size:13.5px;line-height:1.6}.nmos .preview>b{display:block;margin-bottom:4px;color:var(--c-text-strong)}
.nmos .line{display:flex;align-items:center;gap:8px;margin:5px 0}
.nmos .dot{flex:none;width:8px;height:8px;border-radius:50%;background:var(--c-text-ghost)}
.nmos .dot.ok{background:var(--c-ok);box-shadow:0 0 0 3px ${alpha("ok", 0.18)}}
.nmos .dot.err{background:var(--c-err);box-shadow:0 0 0 3px ${alpha("err", 0.18)}}
.nmos .dot.warn{background:var(--c-warn);box-shadow:0 0 0 3px ${alpha("warn", 0.18)}}
.nmos .pills{display:flex;gap:8px;flex-wrap:wrap}
.nmos .pill{border:1px solid var(--c-line-strong);border-radius:999px;padding:3px 10px;font-size:12.5px;color:var(--c-text-muted);background:var(--c-sunken)}
.nmos .pill.on{border-color:${alpha("ok", 0.4)};background:${alpha("ok", 0.1)};color:var(--c-ok)}
.nmos .badge{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid var(--c-line-strong);background:var(--c-raised);color:var(--c-text-soft);white-space:nowrap}
.nmos .badge.b-llm{background:${alpha("violet", 0.14)};border-color:${alpha("violet", 0.36)};color:var(--c-violet)}
.nmos .badge.b-free{background:${alpha("ok", 0.12)};border-color:${alpha("ok", 0.34)};color:var(--c-ok)}
.nmos .badge.b-warn{background:${alpha("warn", 0.14)};border-color:${alpha("warn", 0.38)};color:var(--c-warn)}
.nmos .badge.b-danger{background:${alpha("err", 0.14)};border-color:${alpha("err", 0.4)};color:var(--c-err)}
.nmos .badge.b-info{background:${alpha("cyan", 0.12)};border-color:${alpha("cyan", 0.34)};color:var(--c-cyan)}
.nmos .mono{font-family:ui-monospace,monospace;font-size:12.5px;word-break:break-all}
.nmos.wide>.wrap{max-width:1120px}

/* PHASE-59: persistent top chrome + chat switcher + mobile bottom nav */
.nmos .nmos-topbar{position:sticky;top:0;z-index:30;background:${alpha("bg", 0.9)};backdrop-filter:blur(16px);border-bottom:1px solid var(--c-line)}
.nmos .nmos-topbar-in{max-width:1120px;margin:0 auto;padding:10px 22px;display:flex;align-items:center;gap:12px}
.nmos .nmos-brand{background:none;border:0;padding:4px 6px 4px 2px;border-radius:9px;display:inline-flex;align-items:center;gap:8px;color:var(--c-text-strong);font-size:16px;font-weight:750;letter-spacing:-0.02em}
.nmos .nmos-brand:hover:not(:disabled){background:var(--c-raised);border-color:transparent}
.nmos .nmos-logo{width:28px;height:28px;border-radius:7px;display:inline-flex;align-items:center;justify-content:center;background:var(--c-raised);border:1px solid var(--c-line-strong);color:var(--c-text-strong)}
.nmos .chat-picker{position:relative;flex:0 1 240px;min-width:120px}
.nmos .chat-btn{width:100%;justify-content:space-between;padding:6px 10px;border-radius:9px;background:var(--c-surface);border-color:var(--c-line-strong);color:var(--c-text-strong);font-size:13.5px}
.nmos .chat-btn .chat-lbl{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left}
.nmos .chat-pop{position:absolute;top:calc(100% + 6px);left:0;width:300px;max-width:calc(100vw - 24px);background:var(--c-surface);border:1px solid var(--c-line-strong);border-radius:12px;padding:10px;box-shadow:0 16px 40px rgba(0,0,0,0.52);z-index:40}
.nmos .chat-pop input{padding:7px 10px;font-size:13.5px;margin-bottom:8px}
.nmos .chat-list{max-height:260px;overflow:auto;display:flex;flex-direction:column;gap:3px}
.nmos .chat-opt{width:100%;justify-content:space-between;text-align:left;padding:8px 10px;border-radius:8px;background:transparent;border-color:transparent;font-size:13.5px;color:var(--c-text)}
.nmos .chat-opt:hover:not(:disabled){background:var(--c-raised);border-color:var(--c-line)}
.nmos .chat-opt.on{background:${alpha("accent", 0.16)};border-color:${alpha("accent", 0.38)};color:var(--c-text-strong)}
.nmos .chat-opt .chat-meta{font-size:11.5px;color:var(--c-text-muted);flex:none}
.nmos .chat-pop-foot{margin-top:8px;padding-top:8px;border-top:1px solid var(--c-line);display:flex;justify-content:flex-end}
.nmos .nmos-nav{display:flex;align-items:center;gap:4px;padding:3px;background:var(--c-sunken);border:1px solid var(--c-line);border-radius:11px;margin:0 auto}
.nmos .nmos-nav button{background:transparent;border:1px solid transparent;border-radius:8px;padding:6px 12px;font-size:13.5px;font-weight:550;color:var(--c-text-muted)}
.nmos .nmos-nav button:hover:not(:disabled){color:var(--c-text-strong);background:var(--c-raised);border-color:transparent}
.nmos .nmos-nav button.on{background:var(--c-raised-hover);color:var(--c-text-strong);border-color:var(--c-line-strong);box-shadow:0 1px 4px rgba(0,0,0,0.28)}
.nmos .nav-badge{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;padding:0 5px;border-radius:999px;background:var(--c-warn);color:#120d02;font-size:11px;font-weight:750;line-height:1}
.nmos .nmos-top-right{display:flex;align-items:center;gap:8px;margin-left:auto}
.nmos .status-pill{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;background:var(--c-surface);border:1px solid var(--c-line);font-size:12.5px;font-weight:550;color:var(--c-text-soft);white-space:nowrap}
.nmos .status-pill.ok{border-color:${alpha("ok", 0.35)};background:${alpha("ok", 0.08)};color:var(--c-ok)}
.nmos .status-pill.warn{border-color:${alpha("warn", 0.4)};background:${alpha("warn", 0.1)};color:var(--c-warn)}
.nmos .status-pill.err{border-color:${alpha("err", 0.4)};background:${alpha("err", 0.1)};color:var(--c-err)}
.nmos .nmos-close{padding:6px 9px;border-radius:8px}
.nmos .nmos-bottomnav{display:none}

/* PHASE-59: Home inline quick bar + advisories */
.nmos .home-quick{display:flex;flex-direction:column;gap:10px;margin:0 0 14px}
.nmos .chat-strip{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:12px 16px;border-radius:12px;background:var(--c-surface);border:1px solid var(--c-line)}
.nmos .chat-strip.off{border-color:${alpha("warn", 0.38)};background:linear-gradient(90deg,${alpha("warn", 0.1)},var(--c-surface) 55%)}
.nmos .chat-strip-info{display:flex;align-items:center;gap:10px;min-width:0;flex:1}
.nmos .chat-strip-title{font-size:14.5px;font-weight:600;color:var(--c-text-strong)}
.nmos .chat-strip-sub{font-size:12.5px;color:var(--c-text-muted)}
.nmos .adv-card{padding:12px 16px;border-radius:12px;background:var(--c-surface);border:1px solid ${alpha("warn", 0.4)};display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.nmos .adv-card.err{border-color:${alpha("err", 0.45)};background:${alpha("err", 0.08)}}
.nmos .adv-card p{margin:3px 0 0;font-size:13px;color:var(--c-text-muted)}

/* PHASE-59: Memory workspace sub-tab bar */
.nmos .mem-subbar{margin:0 0 14px;padding:12px 14px;border-radius:12px;background:var(--c-surface);border:1px solid var(--c-line)}
.nmos .mem-subtabs{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.nmos .mem-subtabs button{background:transparent;border:1px solid transparent;border-radius:8px;padding:6px 12px;font-size:13.5px;color:var(--c-text-muted)}
.nmos .mem-subtabs button:hover:not(:disabled){background:var(--c-raised);color:var(--c-text-strong)}
.nmos .mem-subtabs button.on{background:${alpha("accent", 0.16)};border-color:${alpha("accent", 0.4)};color:var(--c-text-strong)}
.nmos .mem-subhead{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-top:8px;padding-top:8px;border-top:1px solid var(--c-line)}
.nmos .mem-subtext{margin:0;font-size:13px;color:var(--c-text-muted)}
.nmos .diag-toggle{display:inline-flex;gap:3px;padding:2px;background:var(--c-sunken);border:1px solid var(--c-line);border-radius:8px}
.nmos .diag-toggle button{padding:4px 10px;font-size:12.5px;border-radius:6px;background:transparent;border:0;color:var(--c-text-muted)}
.nmos .diag-toggle button.on{background:var(--c-raised-hover);color:var(--c-text-strong)}

/* PHASE-59: Dedicated Author's Note Studio */
.nmos .studio-head{margin-bottom:14px}
.nmos .notes-studio{display:grid;grid-template-columns:minmax(310px,420px) minmax(0,1fr);gap:18px;align-items:start}
.nmos .studio-col{background:var(--c-surface);border:1px solid var(--c-line);border-radius:14px;padding:18px 20px}
.nmos .studio-col h3{margin:0 0 12px;font-size:14px;font-weight:650;color:var(--c-text-soft);letter-spacing:0.01em}
.nmos .note-opt{display:flex;align-items:flex-start;gap:10px;padding:11px 12px;margin:0 0 8px;border-radius:10px;background:var(--c-sunken);border:1px solid var(--c-line);cursor:pointer;transition:border-color .15s ease,background .15s ease}
.nmos .note-opt:hover{border-color:var(--c-line-hover)}
.nmos .note-opt.on{background:${alpha("accent", 0.08)};border-color:${alpha("accent", 0.45)}}
.nmos .note-opt input[type=checkbox]{width:auto;margin-top:3px;flex:none}
.nmos .note-opt-body{flex:1;min-width:0}
.nmos .note-opt-top{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}
.nmos .note-opt-title{font-size:14px;font-weight:600;color:var(--c-text-strong)}
.nmos .note-opt-desc{font-size:12.5px;color:var(--c-text-muted);margin-top:3px;line-height:1.45}
.nmos .notes-est{margin:12px 0 0;padding:8px 12px;border-radius:8px;background:var(--c-sunken);border:1px solid var(--c-line);font-size:12.5px;color:var(--c-text-soft);display:flex;align-items:center;gap:6px}
.nmos .studio-empty{padding:42px 20px;text-align:center;color:var(--c-text-muted);font-size:14px;border:1px dashed var(--c-line-strong);border-radius:10px;background:var(--c-sunken)}

/* PHASE-59: 2-column Settings + Chat Maintenance rows */
.nmos .settings-shell{display:grid;grid-template-columns:236px minmax(0,1fr);gap:20px;align-items:start}
.nmos .settings-shell .groups{position:sticky;top:72px;display:flex;flex-direction:column;gap:4px;margin:0;padding:10px;background:var(--c-surface);border:1px solid var(--c-line);border-radius:14px}
.nmos .grp-label{font-size:11.5px;font-weight:650;letter-spacing:.04em;color:var(--c-text-faint);padding:8px 10px 4px;text-transform:uppercase}
.nmos .grp-label:first-child{padding-top:2px}
.nmos .settings-shell .groups button.group{display:flex;flex-direction:row;align-items:center;justify-content:flex-start;gap:10px;text-align:left;padding:9px 11px;border-radius:9px;background:transparent;border:1px solid transparent;font-size:14px;color:var(--c-text-soft)}
.nmos .settings-shell .groups button.group:hover:not(:disabled){background:var(--c-raised);color:var(--c-text-strong);border-color:transparent}
.nmos .settings-shell .groups button.group.on{background:${alpha("accent", 0.16)};border-color:${alpha("accent", 0.42)};color:var(--c-text-strong)}
.nmos .settings-shell .groups button.group .grp-txt{display:flex;flex-direction:column;min-width:0}
.nmos .settings-shell .groups button.group .sub{font-size:11.5px;margin:1px 0 0;color:var(--c-text-muted);display:none}
.nmos .settings-pane{min-width:0}
.nmos .settings-pane>.card:first-child,.nmos .settings-pane>[data-group]>.card:first-child{margin-top:0}
.nmos .maint-list{display:flex;flex-direction:column;gap:8px;margin-top:10px}
.nmos .maint-row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:12px 14px;border-radius:10px;background:var(--c-sunken);border:1px solid var(--c-line)}
.nmos .maint-row.danger-row{border-color:${alpha("err", 0.3)}}
.nmos .maint-info{flex:1;min-width:200px}
.nmos .maint-title{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:14px;font-weight:600;color:var(--c-text-strong)}
.nmos .maint-desc{font-size:12.5px;color:var(--c-text-muted);margin-top:3px}

/* Inspector & Timeline (kept intact, refined surfaces) */
.nmos .insp{margin-top:8px}.nmos .insp+.sub{margin-top:18px}
.nmos .insp h1{font-size:16px;font-weight:600;margin:4px 0;color:var(--c-text-strong)}
.nmos .insp h2{margin:22px 0 8px;font-size:13.5px;font-weight:600;color:var(--c-text-strong)}
.nmos .insp .top{display:flex;justify-content:space-between;align-items:baseline;gap:12px}.nmos .insp .top p{margin:0}
.nmos .insp a{color:var(--c-link);text-decoration:none;cursor:pointer}
.nmos .insp a:hover{text-decoration:underline}
.nmos .insp .tl{margin:6px 0 16px}.nmos .insp .tl .tl-h{font-size:13px;font-weight:500;letter-spacing:.04em;color:var(--c-text-muted);margin:16px 0 4px;cursor:pointer;list-style:none}
.nmos .insp .tl .tl-h::-webkit-details-marker{display:none}.nmos .insp .tl .tl-h::before{content:"\\25BE  "}.nmos .insp .tl details:not([open])>.tl-h::before{content:"\\25B8  "}
.nmos .insp .tl-switch{font-size:14px;margin:0 0 8px}.nmos .insp .tl-span{color:var(--c-link);cursor:pointer}
.nmos .insp .tl-hint{font-size:13px;color:var(--c-text-faint);margin:0 0 8px}
.nmos .insp .tl-row{display:grid;grid-template-columns:112px minmax(0,1fr);gap:8px;align-items:center;padding:3px 0;color:inherit}.nmos .insp a.tl-line{text-decoration:none;border-radius:6px}
.nmos .insp .tl-cast .tl-row{display:block}
.nmos .insp .tl-lab{display:block;font-size:14px;line-height:1.3;color:var(--c-text);overflow:hidden;text-overflow:ellipsis;max-height:2.6em}
.nmos .insp .tl-cast .tl-lab{white-space:nowrap;margin-bottom:2px}
.nmos .insp .tl-lab .tl-k{display:block;font-size:13px;color:var(--c-text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nmos .insp .tl-lab .tl-val{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.nmos .insp .tl-lab .tl-val.canon{color:var(--c-text-muted)}
.nmos .insp .tl-last{color:var(--c-text-faint);font-size:13px}.nmos .insp .tl-end{display:none}
.nmos .insp .tl-me{font-size:13px;color:var(--c-link);margin-left:6px}
.nmos .insp .tl-track{display:block;position:relative;height:26px}
.nmos .insp .tl-rule{position:absolute;left:0;right:0;top:13px;height:1px;background:var(--c-line)}
.nmos .insp .tl-bar{position:absolute;top:5px;height:16px;min-width:6px;border-radius:4px;overflow:hidden;box-sizing:border-box;background:var(--c-raised);border:1px solid var(--c-text-faint);cursor:pointer}
.nmos .insp .tl-bar.short{z-index:2}
.nmos .insp .tl-bar.past{background:transparent;border-color:var(--c-line-hover)}.nmos .insp .tl-bar.neg{border-style:dotted}
.nmos .insp .tl-bar.open{border-right-style:dashed}.nmos .insp .tl-bar.canon{border-left:2px dotted var(--c-text-muted)}
.nmos .insp .tl-bar.owner{border-color:var(--c-warn)}
.nmos .insp .tl .sel{background:var(--c-accent);border-color:var(--c-accent);color:#fff}
.nmos .insp .tl-dot{position:absolute;top:2px;bottom:2px;width:10px;margin-left:-5px;cursor:pointer}
.nmos .insp .tl-dot::after{content:"";position:absolute;left:4px;bottom:2px;width:2px;height:10px;border-radius:1px;background:var(--c-text-muted)}
.nmos .insp .tl-dot.s-major::after{height:18px;background:var(--c-text-strong)}.nmos .insp .tl-dot.s-minor::after{height:6px}
.nmos .insp .tl-dot.n1{transform:translateX(4px)}.nmos .insp .tl-dot.n2{transform:translateX(8px)}.nmos .insp .tl-dot.n3{transform:translateX(12px)}
.nmos .insp .tl .tl-dot.sel{background:transparent}.nmos .insp .tl .tl-dot.sel::after{background:var(--c-accent)}
.nmos .insp .tl-tick{position:absolute;top:5px;width:2px;height:16px;margin-left:-1px;border-radius:1px;background:var(--c-text-soft)}
.nmos .insp .tl-axis .tl-track{height:18px}
.nmos .insp .tl-axis .tl-track span{position:absolute;top:0;font-size:13px;color:var(--c-text-faint);transform:translateX(-50%);white-space:nowrap}
.nmos .insp .tl-axis .tl-track span.first{transform:none}.nmos .insp .tl-axis .tl-track span.last{transform:translateX(-100%)}
.nmos .insp .tl-axis .tl-track span.odd,.nmos .insp .tl-axis .tl-track span.near{display:none}
.nmos .insp .tl-card{margin:6px 0 10px;padding:10px 12px;border-radius:8px;background:var(--c-raised);font-size:14px}
.nmos .insp .tl-card p{margin:2px 0}.nmos .insp .tl-card .v{font-size:17px;font-weight:600;line-height:1.35;color:var(--c-text-strong);overflow-wrap:anywhere}
.nmos .insp .tl-hist{margin-top:8px;color:var(--c-text-muted)}.nmos .insp .tl-hist .cur{color:var(--c-text-strong)}
.nmos .insp .tl-more{font-size:13px;color:var(--c-text-faint);margin:2px 0}
.nmos .insp .tl-fold>summary,.nmos .insp .tl-others>summary{font-size:13px;color:var(--c-text-muted);margin:8px 0 2px;cursor:pointer}
.nmos .insp .ref{display:block;font-family:ui-monospace,monospace;font-size:12.5px;color:var(--c-text-faint)}
.nmos .insp .wrap{max-width:none;margin:0;padding:0;overflow-x:auto}
.nmos .insp table{width:100%;border-collapse:collapse;font-size:14px}
.nmos .insp th,.nmos .insp td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--c-line);vertical-align:top}
.nmos .insp th{font-weight:500;color:var(--c-text-faint);font-size:13px;letter-spacing:0.02em;white-space:nowrap}
.nmos .insp tr:hover td{background:rgba(255,255,255,0.02)}
.nmos .insp .chip{display:inline-block;padding:1px 7px;border-radius:999px;background:var(--c-raised);border:1px solid var(--c-line);font-size:12.5px;color:var(--c-text-soft)}
.nmos .insp span.rp{display:inline-flex;flex-wrap:wrap;align-items:center;gap:5px;margin-left:6px;vertical-align:middle}
.nmos .insp span.rp input,.nmos .insp span.rp select{width:auto;padding:3px 7px;font-size:13px;border-radius:6px}
.nmos .insp span.rp input[type=text]{width:12em}.nmos .insp span.rp input.turn{width:7em}
.nmos button.mini{padding:4px 9px;font-size:12.5px;border-radius:6px}
.nmos .groups{display:flex;flex-direction:column;gap:8px;margin:8px 0}
.nmos .groups button.group{display:flex;flex-direction:column;align-items:flex-start;gap:2px;text-align:left;padding:14px 16px;border-radius:12px;font-size:16px}
.nmos .groups button.group .sub{margin:0}
.nmos .inspbar{position:sticky;top:0;z-index:5;background:var(--c-bg);padding:8px 0;margin-top:0}
.nmos.shell-on .inspbar{position:static;background:transparent;padding:0 0 10px}
.nmos .help{margin:8px 0 0}.nmos .help summary{cursor:pointer;color:var(--c-text-muted)}.nmos .help p{margin:6px 0 0}
.nmos .packet{margin:8px 0 0;max-height:420px;overflow:auto;background:var(--c-sunken);border:1px solid var(--c-line);border-radius:8px;padding:12px;font-family:ui-monospace,monospace;font-size:13px;line-height:1.6;color:var(--c-text-soft);white-space:pre-wrap;word-break:break-word}
.nmos .insp.busy{opacity:.5;transition:opacity .15s}
.nmos .insp details>summary{cursor:pointer;list-style:none}.nmos .insp details>summary::-webkit-details-marker{display:none}
.nmos .insp details>summary h2{display:inline-block}
.nmos .insp details>summary h2::before{content:"\u25B8 ";color:var(--c-text-ghost)}.nmos .insp details[open]>summary h2::before{content:"\u25BE "}
.nmos .insp .n{color:var(--c-text-muted);font-weight:400;font-size:13px}
.nmos .insp .toc{font-size:14px;line-height:1.9;margin:8px 0}.nmos .insp a.warn{color:var(--c-warn)}
.nmos .insp .who{display:flex;align-items:center;gap:8px;margin:10px 0}.nmos .insp .who select{width:auto;min-width:180px;padding:5px 8px}
.nmos .insp details.meta{font-size:13px;margin-top:2px;color:var(--c-text-muted)}.nmos .insp details.meta p{margin:4px 0}
.nmos .bulk-card{padding:10px 14px;border-radius:10px;background:var(--c-surface);border:1px solid var(--c-line);margin:0 0 12px}
.nmos .bulk-card .btns{margin-top:0}.nmos .bulk-card .btns+.btns{margin-top:8px}
.nmos .bar{position:sticky;bottom:0;background:${alpha("surface", 0.96)};backdrop-filter:blur(12px);border-top:1px solid var(--c-line-strong);padding:12px max(16px,calc((100% - 760px) / 2 + 16px));display:flex;align-items:center;gap:10px;flex-wrap:wrap;z-index:20}
.nmos.shell-on .bar{padding:12px max(22px,calc((100% - 1120px) / 2 + 22px))}
.nmos .bar .text{flex:1;min-width:160px;font-size:14px}
.nmos .bar .model-change{flex:1;display:flex;flex-direction:column;gap:2px;font-size:14px}.nmos .bar .model-change p{margin:0}
.nmos .bar .model-change .btns{justify-content:flex-end;margin-top:8px}

@media (max-width: 860px){
  .nmos .notes-studio{grid-template-columns:1fr}
  .nmos .settings-shell{grid-template-columns:1fr}
  .nmos .settings-shell .groups{position:static;flex-direction:row;flex-wrap:wrap;gap:6px;padding:8px}
  .nmos .settings-shell .grp-label{width:100%;padding:4px 4px 2px}
  .nmos .settings-shell .groups button.group{padding:7px 10px;font-size:13px}
}
@media (max-width: 720px){
  .nmos.shell-on .wrap{padding:12px 12px 84px}
  .nmos .nmos-topbar-in{padding:8px 12px;gap:8px}
  .nmos .nmos-nav{display:none}
  .nmos .status-pill .st-txt{display:none}
  .nmos .chat-picker{flex:1;min-width:0}
  .nmos .nmos-bottomnav{position:fixed;left:0;right:0;bottom:0;z-index:35;display:grid;grid-template-columns:repeat(4,1fr);background:${alpha("surface", 0.96)};backdrop-filter:blur(16px);border-top:1px solid var(--c-line-strong);padding:6px 6px max(8px,env(safe-area-inset-bottom))}
  .nmos .nmos-bottomnav button{flex-direction:column;gap:3px;padding:6px 4px;border:0;background:transparent;color:var(--c-text-muted);font-size:11px;font-weight:550;border-radius:8px;position:relative}
  .nmos .nmos-bottomnav button.on{color:var(--c-accent-hover);background:${alpha("accent", 0.12)}}
  .nmos .nmos-bottomnav .nav-badge{position:absolute;top:2px;right:calc(50% - 22px);min-width:16px;height:16px;font-size:10px}
  .nmos.shell-on .bar{bottom:58px;padding:10px 12px}
}
`;
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === void 0 || v === false) continue;
      if (k === "class") node.className = String(v);
      else if (k === "text") node.textContent = String(v);
      else node.setAttribute(k, v === true ? "" : String(v));
    }
    for (const child of children) node.append(child);
    return node;
  }
  function archiveName(kind, at) {
    const p = (n) => String(n).padStart(2, "0");
    const stamp = `${at.getFullYear()}${p(at.getMonth() + 1)}${p(at.getDate())}-${p(at.getHours())}${p(at.getMinutes())}${p(at.getSeconds())}`;
    return `nmos-${kind}-${stamp}.nmos.zip`;
  }
  function say(target, text2, kind = "muted") {
    target.className = `${target.classList.contains("text") ? "text" : "msg"} ${kind}`;
    target.textContent = text2;
  }
  function field(labelText, input) {
    return el("div", {}, el("label", { text: labelText }), input);
  }
  function presetIndex(presets, url) {
    if (!url) return 0;
    const i = presets.findIndex((p) => presetMatches(p.url, url));
    return i >= 0 ? i : presets.length - 1;
  }
  function fixFor(error) {
    const kind = failureKind(error);
    return kind === "unauthorized" ? "status.fix_token" : kind === "host_refused" ? "status.fix_host" : "status.fix";
  }
  function errorText(lang, error) {
    const text2 = error instanceof Error ? error.message : String(error);
    return text2.replace(/^\/v1\/\S+ -> HTTP 422: /, t(lang, "invalid")).replace(/^\/v1\/\S+ -> /, t(lang, "sidecar_error"));
  }
  var current = null;
  async function openPanel(deps, tab) {
    if (current && document.body.contains(current.root)) {
      current.select(tab);
      await deps.show();
      return;
    }
    if (!document.getElementById("nmos-style")) document.head.append(el("style", { id: "nmos-style", text: CSS }));
    const lang = langOf(await deps.getArg("language"));
    current = await render(deps, lang, tab);
    await deps.show();
  }
  async function render(deps, lang, tab) {
    const L = (key, vars) => t(lang, key, vars);
    const root = el("div", { class: "nmos", id: "nmos-panel" });
    const wrap = el("div", { class: "wrap" });
    root.append(wrap);
    const language = el(
      "select",
      { "aria-label": L("language") },
      el("option", { value: "ko", text: "\uD55C\uAD6D\uC5B4" }),
      el("option", { value: "en", text: "English" })
    );
    language.value = lang;
    const close = el("button", { text: L("close") });
    const tabStatus = el("button", { text: L("tab.status") });
    const tabInspector = el("button", { text: L("tab.inspector") });
    const tabSettings = el("button", { text: L("tab.settings") });
    const title = el("h1", { text: L("title") });
    const legacyHeader = el("header", {}, title, language, close);
    const tabs = el("nav", { class: "tabs" }, tabStatus, tabInspector, tabSettings);
    wrap.append(legacyHeader, tabs);
    const statusView = el("div");
    const inspectorView = el("div");
    const notesStudioView = el("div", { style: "display:none" });
    const settingsView = el("div");
    wrap.append(statusView, inspectorView, notesStudioView, settingsView);
    let shown = tab;
    let usageRound = 0;
    async function refreshStatus() {
      statusView.replaceChildren(el("div", { class: "card muted", text: L("status.checking") }));
      const s = await deps.status();
      const base = s.sidecarUrl.replace(/\/+$/, "");
      const conn = el("div", { class: "card" }, el("h2", { text: L("status.sidecar") }));
      if (s.connected) {
        conn.append(
          el(
            "div",
            { class: "line" },
            el("span", { class: "dot ok" }),
            el("span", { text: `${L("status.connected")} \xB7 NMOS ${s.version ?? ""}` })
          ),
          el("div", { class: "mono muted", text: base })
        );
        if (s.pluginExpected && s.pluginExpected !== PLUGIN_BUILD) {
          const get = el("button", { class: "mini", text: L("status.plugin_file") });
          const got = el("div", { class: "msg" });
          get.addEventListener("click", async () => {
            get.disabled = true;
            try {
              await deps.download("/v1/plugin/nmos-pocketrisu.js", "nmos-pocketrisu.js");
              say(got, L("status.plugin_saved", { name: "nmos-pocketrisu.js" }), "ok");
            } catch (error) {
              say(got, errorText(lang, error), "err");
            } finally {
              get.disabled = false;
            }
          });
          conn.append(
            el(
              "div",
              { class: "line warn" },
              el("span", { class: "dot warn" }),
              el("span", { text: L("status.plugin_mismatch", { mine: PLUGIN_BUILD, theirs: s.pluginExpected }) })
            ),
            el("div", { class: "btns" }, get),
            got
          );
        } else if (s.pluginExpected) {
          conn.append(el("div", { class: "muted", text: L("status.plugin_ok", { b: PLUGIN_BUILD }) }));
        }
        if (s.enabled && !s.last) conn.append(el("div", { class: "muted", text: L("status.no_requests") }));
      } else {
        conn.append(
          el(
            "div",
            { class: "line" },
            el("span", { class: "dot err" }),
            el("span", { class: "err", text: `${L("status.unreachable")}: ${base}` })
          ),
          el("div", { class: "muted", text: s.error ?? "" }),
          el("p", { class: "sub", text: L(fixFor(s.error)) })
        );
      }
      if (!s.enabled) conn.append(el(
        "div",
        { class: "line warn" },
        el("span", { class: "dot warn" }),
        el("span", { text: L("status.memory_off") })
      ));
      const features = el("div", { class: "card" }, el("h2", { text: L("status.features") }));
      const pills = el("div", { class: "pills" });
      for (const [key, name] of [["state", "feature.state"], ["extraction", "feature.extraction"], ["vectors", "feature.vectors"]]) {
        const on = Boolean(s.features?.[key]);
        pills.append(el("span", { class: on ? "pill on" : "pill", text: `${L(name)} ${on ? L("on") : L("off")}` }));
      }
      features.append(s.connected ? pills : el("div", { class: "muted", text: "\u2014" }));
      const lastCard = el("div", { class: "card" }, el("h2", { text: L("status.last") }));
      if (s.last) {
        const kind = s.last.outcome === "injected" ? "ok" : s.last.outcome === "failed" ? "err" : "muted";
        const what = s.last.outcome === "injected" ? L("outcome.injected", { n: s.last.packetChars }) : s.last.outcome === "nothing-relevant" ? L("outcome.nothing") : s.last.outcome === "skipped" ? L("outcome.skipped") : L("outcome.failed");
        lastCard.append(
          el("div", { class: "line" }, el("span", { class: `dot ${kind}` }), el("span", { text: what })),
          el("div", { class: "muted", text: `${L("status.ago", { n: Math.round((Date.now() - s.last.at) / 1e3) })} \xB7 ${s.last.ms}ms` })
        );
        const trimmed = trimStatusLine(lang, s.last.trim);
        if (trimmed !== null) lastCard.append(el("div", { class: "muted", text: trimmed }));
        const recorded = coverageLine(lang, s.last.coverage);
        if (recorded !== null) lastCard.append(el("div", { class: "muted", text: recorded }));
        if (s.last.packet) lastCard.append(el(
          "details",
          { class: "help" },
          el("summary", { text: L("status.packet") }),
          el("pre", { class: "packet", text: s.last.packet })
        ));
        if (s.last.error) lastCard.append(el("div", { class: "mono muted", text: s.last.error }));
      } else {
        lastCard.append(el("div", { class: "muted", text: L("status.none") }));
      }
      const cards = [conn, features, lastCard];
      if (s.insecure) cards.unshift(el("div", { class: "card err" }, el("div", { text: L("status.insecure") })));
      const advice = deadlineAdvice(s.last);
      if (advice) {
        const open = el("button", { text: L("deadline.open_settings") });
        open.addEventListener("click", () => select("settings"));
        const took = advice.tookMs === null ? "" : L("deadline.took", { n: formatMs(advice.tookMs) });
        const text2 = advice.level === "over" ? L("deadline.over", { d: formatMs(advice.deadlineMs), took, s: formatMs(advice.suggestMs) }) : L("deadline.near", { d: formatMs(advice.deadlineMs), n: formatMs(advice.tookMs ?? 0), s: formatMs(advice.suggestMs) });
        cards.unshift(el(
          "div",
          { class: "card" },
          el("h2", { class: advice.level === "over" ? "err" : "warn", text: L(`deadline.${advice.level}.title`) }),
          el("p", { class: "sub", text: text2 }),
          el("div", { class: "btns" }, open)
        ));
      }
      const current2 = Number(await deps.getArg("reserved_memory_tokens")) || DEFAULT_RESERVED_TOKENS;
      const budget = budgetAdvice(s.last, current2);
      if (budget) {
        const apply = el("button", { class: "primary", text: L("budget.apply", { n: budget.suggest }) });
        const msg = el("div", { class: "msg" });
        apply.addEventListener("click", async () => {
          apply.disabled = true;
          try {
            await deps.setArg("reserved_memory_tokens", budget.suggest);
            say(msg, L("budget.applied", { n: budget.suggest, d: budget.suggest - current2 }), "ok");
          } catch (error) {
            apply.disabled = false;
            say(msg, errorText(lang, error), "err");
          }
        });
        const text2 = L(budget.all ? "budget.text" : "budget.text_more", {
          m: budget.offered,
          c: budget.cut,
          b: budget.budget,
          s: budget.suggest,
          d: budget.suggest - current2
        });
        cards.splice(1, 0, el(
          "div",
          { class: "card" },
          el("h2", { class: "warn", text: L("budget.title", { c: budget.cut }) }),
          el("p", { class: "sub", text: text2 }),
          el("div", { class: "btns" }, apply),
          msg
        ));
      }
      if (s.last?.vectors === "fallback") {
        cards.splice(1, 0, el(
          "div",
          { class: "card" },
          el("h2", { class: "warn", text: L("vectors.title") }),
          el("p", { class: "sub", text: L("vectors.text") })
        ));
      }
      const problem = deps.hud.problem();
      if (Number(await deps.getArg("hud")) !== 1) {
        const turnOn = el("button", { text: L("hud.enable") });
        const msg = el("div", { class: "msg" });
        turnOn.addEventListener("click", async () => {
          turnOn.disabled = true;
          const result = await deps.hud.enable();
          if (result === "on") return void refreshStatus();
          turnOn.disabled = false;
          say(msg, L(result === "denied" ? "hud.denied" : "hud.unsupported"), "warn");
        });
        cards.push(el(
          "div",
          { class: "card" },
          el("h2", { text: L("hud.title") }),
          el("div", { class: "muted", text: L("hud.hint") }),
          el("div", { class: "btns" }, turnOn),
          msg
        ));
      } else if (problem) {
        cards.push(el(
          "div",
          { class: "card" },
          el("h2", { text: L("hud.title") }),
          el("div", { class: "warn", text: L("hud.broken", { e: problem }) })
        ));
      }
      cards.unshift(await chatCard(s.enabled, s.connected));
      const refresh = el("button", { text: L("refresh") });
      refresh.addEventListener("click", () => void refreshStatus());
      statusView.replaceChildren(...cards, el("div", { class: "btns" }, refresh));
    }
    async function chatCard(enabled2, connected) {
      const card = el("div", { class: "card" }, el("h2", { text: L("chat.title") }));
      let state;
      try {
        state = await deps.chat.current();
      } catch (error) {
        card.append(el("div", { class: "err", text: errorText(lang, error) }));
        return card;
      }
      if (state.id === null) {
        card.append(el("div", { class: "muted", text: L("chat.none") }));
        return card;
      }
      const id = state.id;
      const off = state.off;
      const flip = el("button", { class: off ? "primary" : "", text: L(off ? "chat.turn_on" : "chat.turn_off") });
      const msg = el("div", { class: "msg" });
      flip.addEventListener("click", async () => {
        flip.disabled = true;
        try {
          await deps.chat.set(id, !off);
          await refreshStatus();
        } catch (error) {
          flip.disabled = false;
          say(msg, errorText(lang, error), "err");
        }
      });
      card.append(
        el(
          "div",
          { class: off ? "line warn" : "line" },
          el("span", { class: off ? "dot warn" : "dot ok" }),
          el("span", { text: L(off ? "chat.off" : "chat.on") })
        ),
        el("p", { class: "sub", text: L(off ? "chat.off_sub" : "chat.on_sub") }),
        el("div", { class: "btns" }, flip),
        msg
      );
      if (connected) {
        const shownFor = ++usageRound;
        void usageLine(id).then((spent) => {
          if (spent && shownFor === usageRound && card.isConnected) card.insertBefore(spent, card.querySelector("p.sub"));
        });
      }
      if (!enabled2) card.insertBefore(el(
        "div",
        { class: "line warn" },
        el("span", { class: "dot warn" }),
        el("span", { text: L("chat.all_off") })
      ), card.children[1] ?? null);
      return card;
    }
    async function usageLine(hostChatId) {
      try {
        const chats = await deps.api(
          "GET",
          `/v1/conversations?host=pocketrisu&host_chat_ref=${encodeURIComponent(hostChatId)}`,
          void 0,
          5e3
        );
        const chat = chats.find((c) => c.host_chat_ref === hostChatId);
        if (!chat) return null;
        const cov = await deps.api(
          "GET",
          `/v1/conversations/${encodeURIComponent(chat.id)}/coverage?usage=true`,
          void 0,
          5e3
        );
        const lines = [
          cov.usage?.total ? el("div", { class: "muted", text: usageText(cov.usage.total, lang) }) : null,
          // the facts a re-extraction dropped (PHASE-22 Q6), when there are any
          typeof cov.dropped === "number" && cov.dropped > 0 ? el("div", { class: "muted", text: L("chat.dropped", { n: cov.dropped }) }) : null
        ].filter((x) => x !== null);
        return lines.length ? el("div", {}, ...lines) : null;
      } catch {
        return null;
      }
    }
    let inspectorPath = "/v1/inspector";
    let shownPath = null;
    let loads = 0;
    const visited = [];
    const inspectorBody = el("div", { class: "insp" });
    const inspectorBack = el("button", { text: L("insp.back") });
    const inspectorRefresh = el("button", { text: L("refresh") });
    const inspectorAddress = el("p", { class: "sub mono" });
    const historyButton = el("button", { text: L("act.history") });
    const retryButton = el("button", { text: L("act.retry"), style: "display:none" });
    const rebuildButton = el("button", { text: L("act.rebuild") });
    const deleteButton = el("button", { text: L("act.delete") });
    const exportButton = el("button", { text: L("exp.chat") });
    const notesButton = el("button", { text: L("notes.open") });
    const notesCard = el("div", { class: "card", style: "display:none" });
    let notesFor = null;
    let hubConversation = null;
    let viewsOn = false;
    let mapOn = false;
    let graphOn = false;
    const actionMsg = el("div", { class: "msg" });
    const actions = el(
      "div",
      {},
      el(
        "div",
        { class: "btns" },
        retryButton,
        historyButton,
        rebuildButton,
        exportButton,
        notesButton,
        deleteButton
      ),
      el("details", { class: "sub help" }, el("summary", { text: L("act.help") }), el("p", { text: L("act.sub") }))
    );
    const linkCard = el("div", { class: "card", style: "display:none" });
    const pinCard = el("div", { class: "card", style: "display:none" });
    const modeCard = el("div", { class: "card", style: "display:none" });
    const statusCard = el("div", { id: "nmos-status-windows", class: "card", style: "display:none" });
    const picked = /* @__PURE__ */ new Set();
    const chosen = /* @__PURE__ */ new Map();
    let closers = /* @__PURE__ */ new Map();
    const bulkClose = el("button");
    const bulkPicked = /* @__PURE__ */ new Map();
    let bulkGroups = /* @__PURE__ */ new Map();
    let pendingBulk = null;
    const bulkKinds = el("div", { class: "btns" });
    const bulkApply = el("button");
    const bulkRetract = el("button");
    const bulkBar = el(
      "div",
      { class: "bulk-card", style: "display:none" },
      el("div", { class: "btns" }, bulkClose, bulkApply, bulkRetract),
      bulkKinds
    );
    const inspbar = el("div", { class: "btns inspbar" }, inspectorBack, inspectorRefresh);
    const homeQuickBar = el("div", { class: "home-quick", style: "display:none" });
    const memSubBar = el("div", { class: "mem-subbar", style: "display:none" });
    inspectorView.append(
      inspbar,
      homeQuickBar,
      memSubBar,
      actions,
      actionMsg,
      notesCard,
      bulkBar,
      modeCard,
      statusCard,
      pinCard,
      linkCard,
      inspectorBody,
      inspectorAddress
    );
    function updateBulk() {
      bulkBar.style.display = picked.size || bulkGroups.size ? "" : "none";
      bulkClose.style.display = picked.size ? "" : "none";
      bulkClose.textContent = L("rp.bulk", { n: picked.size });
      const marks = [...bulkPicked.values()];
      for (const [button, side, key] of [[bulkApply, "apply", "bk.apply"], [bulkRetract, "retract", "bk.retract"]]) {
        button.style.display = marks.length ? "" : "none";
        button.textContent = pendingBulk === side ? L("bk.again") : L(key, { n: marks.filter((m) => m[side]).length });
      }
      bulkKinds.style.display = bulkGroups.size ? "" : "none";
    }
    async function runBulk(side, button) {
      const conversation = inspectorConversation(inspectorPath);
      if (!conversation || !bulkPicked.size) return;
      const marks = [...bulkPicked.values()];
      const sent = marks.map((m) => m[side]).filter((r) => r !== void 0);
      const skipped = marks.length - sent.length;
      if (!sent.length) return void say(actionMsg, L("bk.none", { n: skipped }), "warn");
      const body = { items: sent.filter((r) => "kind" in r), undo: sent.flatMap((r) => "undo" in r ? [r.undo] : []) };
      const path = `/v1/conversations/${conversation}/repairs/batch`;
      button.disabled = true;
      try {
        if (pendingBulk !== side) {
          const plan = await deps.api(
            "POST",
            path,
            { ...body, preview: true },
            15e3
          );
          if (plan.errors) {
            const first = plan.plan.find((p) => p.error)?.error ?? "";
            return void say(actionMsg, L("bk.refused", { n: plan.errors, e: first }), "err");
          }
          const what = Object.entries(plan.counts).map(([k, n]) => `${L(`rp.${k}`)} ${n}`).join(", ");
          pendingBulk = side;
          say(actionMsg, L("bk.confirm", { what, n: skipped }), "warn");
          return;
        }
        pendingBulk = null;
        await deps.api("POST", path, body, 3e4);
        bulkPicked.clear();
        say(actionMsg, L("bk.done", { n: sent.length }), "ok");
        await showInspector();
      } catch (error) {
        pendingBulk = null;
        say(actionMsg, errorText(lang, error), "err");
      } finally {
        button.disabled = false;
        updateBulk();
      }
    }
    bulkApply.addEventListener("click", () => void runBulk("apply", bulkApply));
    bulkRetract.addEventListener("click", () => void runBulk("retract", bulkRetract));
    function outcomeOf(item) {
      const c = closers.get(item);
      const outcome = c?.selects[0]?.value ?? c?.first;
      return outcome ? { outcome } : {};
    }
    function repairControls(action) {
      if (action.kind === "thread_close") return closeControls(action);
      const field2 = (action.extra ?? "").split(".")[0];
      const n = action.kind === "fact_correct" ? L(field2 === "object" ? "rp.field_object" : "rp.field_value") : action.extra ?? "";
      const label = action.kind === "fact_correct" && action.extra?.endsWith(".lock") ? "rp.fact_correct_lock" : `rp.${action.kind}`;
      const button = el("button", { class: "mini", text: L(label, { n }) });
      const spot = el("div");
      button.addEventListener("click", () => {
        if (action.kind === "fact_correct") correctForm(action, button);
        else if (action.kind === "undo" && (action.extra === "name_split" || action.extra === "entity_exclude")) {
          void undoSplit(action, button, spot);
        } else if (action.kind === "entity_exclude") void notACharacter(action, button, spot);
        else if (action.kind === "alias_join") void aliasJoin(action, button, spot);
        else void repairNow(action, button);
      });
      return [button, spot];
    }
    function closeControls(action) {
      const item = action.item;
      const choices = closeOutcomes(action.extra);
      if (inspectorPath.startsWith("/v1/views/")) {
        const ends = (choices.length ? choices : [""]).map((o) => {
          const b = el("button", { class: "mini", text: o ? outcomeLabel(o) : L("rp.thread_close") });
          b.addEventListener("click", () => void repairNow(action, b, o ? { outcome: o } : {}));
          return b;
        });
        return [el("span", { class: "rp-ask", text: L("rp.how_ended") }), ...ends];
      }
      let c = closers.get(item);
      if (!c) closers.set(item, c = { first: choices[0], boxes: [], selects: [] });
      const group = c;
      const nodes = [];
      const box = el("input", { type: "checkbox", "aria-label": L("rp.select") });
      box.checked = picked.has(item);
      box.addEventListener("change", () => {
        if (box.checked) picked.add(item);
        else picked.delete(item);
        for (const other of group.boxes) other.checked = box.checked;
        updateBulk();
      });
      group.boxes.push(box);
      nodes.push(box);
      if (choices.length > 1) {
        const select2 = el(
          "select",
          { class: "mini", "aria-label": L("rp.outcome") },
          ...choices.map((o) => el("option", { value: o, text: outcomeLabel(o) }))
        );
        const was = chosen.get(item);
        if (was && choices.includes(was)) select2.value = was;
        select2.addEventListener("change", () => {
          chosen.set(item, select2.value);
          for (const other of group.selects) other.value = select2.value;
        });
        group.selects.push(select2);
        nodes.push(select2);
      }
      const button = el("button", { class: "mini", text: L("rp.thread_close") });
      button.addEventListener("click", () => void repairNow(action, button, outcomeOf(item)));
      nodes.push(button);
      return nodes;
    }
    function outcomeLabel(outcome) {
      const key = `oc.${outcome}`;
      return STRING_KEYS.includes(key) ? L(key) : outcome;
    }
    function correctForm(action, button) {
      const spot = button.parentElement;
      if (!spot) return;
      const field2 = (action.extra ?? "").split(".")[0] === "object" ? "object" : "value";
      const text2 = el("input", {
        type: "text",
        placeholder: L("rp.correct_prompt", { f: L(`rp.field_${field2}`) }),
        "aria-label": L(`rp.field_${field2}`)
      });
      const turn = el("input", {
        type: "number",
        min: "0",
        step: "1",
        class: "turn",
        placeholder: L("rp.turn_hint"),
        "aria-label": L("rp.turn")
      });
      const save2 = el("button", { class: "mini", text: L("save") });
      const cancel = el("button", { class: "mini", text: L("cancel") });
      cancel.addEventListener("click", () => spot.replaceChildren(...repairControls(action)));
      save2.addEventListener("click", () => {
        const next = text2.value.trim();
        if (!next) return void text2.focus();
        const body = { [field2 === "object" ? "new_object" : "new_value"]: next };
        if (action.extra?.endsWith(".lock")) body.lock = true;
        const at = turn.value.trim();
        if (at) {
          const n = Number(at);
          if (!Number.isInteger(n) || n < 0) return void say(actionMsg, L("rp.bad_turn"), "err");
          body.turn = n;
        }
        void repairNow(action, save2, body);
      });
      spot.replaceChildren(el("span", { class: "rpform" }, text2, turn, save2, cancel));
      text2.focus();
    }
    async function aliasJoin(action, button, spot) {
      const conversation = inspectorConversation(inspectorPath);
      const pair = aliasPair(action);
      if (!conversation || !pair) return;
      const path = `/v1/conversations/${conversation}/entity-links`;
      const body = { entity_type: "character", ...pair, held_alias: Number(action.item) };
      await withPreview(spot, button, `${path}/preview`, body, "pv.confirm_join", async (expect) => {
        await deps.api("POST", path, { ...body, expect }, 15e3);
        say(actionMsg, L("link.done", { a: pair.name, b: pair.same_as }), "ok");
        await showInspector();
      });
    }
    async function notACharacter(action, button, spot) {
      const conversation = inspectorConversation(inspectorPath);
      if (!conversation) return;
      const path = `/v1/conversations/${conversation}/repairs`;
      const body = { kind: "entity_exclude", item: action.item };
      const preview = (scope) => deps.api("POST", `${path}/preview`, { ...body, scope }, 15e3);
      button.disabled = true;
      let p;
      try {
        p = await preview("cast");
      } catch (error) {
        say(actionMsg, errorText(lang, error), "err");
        button.disabled = false;
        return;
      }
      const also = el("input", { type: "checkbox", "aria-label": L("ex.also", { f: p.scopes.memory.facts }) });
      const ok = el("button", { class: "mini", text: L("ex.confirm") });
      const cancel = el("button", { class: "mini", text: L("cancel") });
      cancel.addEventListener("click", () => {
        spot.replaceChildren();
        button.disabled = false;
      });
      ok.addEventListener("click", async () => {
        ok.disabled = true;
        const scope = also.checked ? "memory" : "cast";
        try {
          const expect = scope === "cast" ? p.fingerprint : (await preview("memory")).fingerprint;
          await deps.api("POST", path, { ...body, scope, expect }, 15e3);
          spot.replaceChildren();
          say(actionMsg, L("ex.done"), "ok");
          await showInspector();
        } catch (error) {
          say(actionMsg, errorText(lang, error), "err");
          ok.disabled = false;
        }
      });
      spot.replaceChildren(el(
        "div",
        { class: "preview" },
        el("b", { text: L("pv.title") }),
        el("div", { text: L("ex.cast", { p: p.scopes.cast.pairs }) }),
        el("div", { class: "check" }, also, el("span", { text: L("ex.also", { f: p.scopes.memory.facts }) })),
        el("div", { class: "btns" }, ok, cancel)
      ));
    }
    async function undoSplit(action, button, spot) {
      const conversation = inspectorConversation(inspectorPath);
      if (!conversation) return;
      const base = `/v1/conversations/${conversation}/repairs/${action.item}`;
      await withPreview(spot, button, `${base}/remove/preview`, {}, "pv.confirm_undo", async (expect) => {
        await deps.api("POST", `${base}/remove`, { expect }, 15e3);
        say(actionMsg, L("rp.undone"), "ok");
        await showInspector();
      });
    }
    async function repairNow(action, button, extra = {}) {
      const conversation = inspectorConversation(inspectorPath);
      if (!conversation) return;
      let path = `/v1/conversations/${conversation}/repairs`;
      let body = { kind: action.kind, item: action.item, ...extra };
      if (action.kind === "undo") {
        path = `${path}/${action.item}/remove`;
        body = {};
      } else if (action.kind === "undo_batch") {
        path = `${path}/batch/${action.item}/remove`;
        body = {};
      } else if (action.kind === "secret_found_out" || action.kind === "secret_keep") {
        body.character = action.extra;
      }
      button.disabled = true;
      try {
        await deps.api("POST", path, body, 15e3);
        picked.delete(action.item);
        updateBulk();
        say(actionMsg, L(action.kind === "undo" || action.kind === "undo_batch" ? "rp.undone" : "rp.done"), "ok");
        await showInspector();
      } catch (error) {
        say(actionMsg, errorText(lang, error), "err");
        button.disabled = false;
      }
    }
    bulkClose.addEventListener("click", async () => {
      const conversation = inspectorConversation(inspectorPath);
      if (!conversation || !picked.size) return;
      bulkClose.disabled = true;
      let done = 0;
      let failed = 0;
      let firstError = null;
      for (const item of Array.from(picked)) {
        try {
          await deps.api(
            "POST",
            `/v1/conversations/${conversation}/repairs`,
            { kind: "thread_close", item, ...outcomeOf(item) },
            15e3
          );
          picked.delete(item);
          done += 1;
        } catch (error) {
          failed += 1;
          firstError ??= error;
        }
      }
      if (failed) {
        say(
          actionMsg,
          `${L("rp.bulk_done", { n: done })} ${L("rp.bulk_failed", { n: failed })} ${errorText(lang, firstError)}`,
          "err"
        );
      } else {
        say(actionMsg, L("rp.bulk_done", { n: done }), "ok");
      }
      bulkClose.disabled = false;
      updateBulk();
      await showInspector();
    });
    let actionConversation = null;
    function place() {
      const open = Array.from(inspectorBody.querySelectorAll("details[id]")).filter((d) => d.open);
      return { path: inspectorPath, scroll: root.scrollTop, open: open.map((d) => d.id) };
    }
    function restore(at) {
      for (const d of Array.from(inspectorBody.querySelectorAll("details[id]"))) d.open = at.open.includes(d.id);
      root.scrollTop = at.scroll;
    }
    function enhance(page) {
      closers = /* @__PURE__ */ new Map();
      for (const slot of Array.from(page.querySelectorAll(".v-filter"))) {
        const box = el("input", { type: "search", placeholder: L("chats.search"), "aria-label": L("chats.search") });
        box.addEventListener("input", () => {
          const q = box.value.trim().toLowerCase();
          for (const row of Array.from(inspectorBody.querySelectorAll(".v-chat"))) {
            row.style.display = !q || (row.textContent ?? "").toLowerCase().includes(q) ? "" : "none";
          }
        });
        slot.append(box);
      }
      for (const box of Array.from(page.querySelectorAll("details > .tl-lazy"))) {
        const section = box.parentElement;
        section.addEventListener("toggle", () => {
          if (section.open && !box.dataset.state) void loadTimeline(box, "");
        });
      }
      const note = graphOn ? page.querySelector(".v-graph-note") : null;
      if (note) {
        const box = el("div", { class: "v-graph panel" });
        note.replaceWith(box);
        void loadGraph(box, note, false);
      }
      for (const spot of Array.from(page.querySelectorAll("span.rp[data-repair]"))) {
        const action = repairAction(spot.getAttribute("data-repair"));
        if (action) spot.replaceChildren(...repairControls(action));
      }
      for (const item of Array.from(picked)) if (!closers.has(item)) picked.delete(item);
      bulkGroups = /* @__PURE__ */ new Map();
      const shown2 = /* @__PURE__ */ new Set();
      for (const spot of Array.from(page.querySelectorAll("span.rq[data-bulk]"))) {
        const mark = bulkMark(spot.getAttribute("data-bulk"));
        if (!mark) continue;
        const key = JSON.stringify([mark.g, mark.apply ?? null, mark.retract ?? null]);
        shown2.add(key);
        const box = el("input", { type: "checkbox", "aria-label": L("bk.select") });
        box.checked = bulkPicked.has(key);
        box.addEventListener("change", () => {
          if (box.checked) bulkPicked.set(key, mark);
          else bulkPicked.delete(key);
          pendingBulk = null;
          updateBulk();
        });
        let group = bulkGroups.get(mark.g);
        if (!group) bulkGroups.set(mark.g, group = { label: mark.l, boxes: [] });
        group.boxes.push(box);
        spot.replaceChildren(box);
      }
      for (const key of Array.from(bulkPicked.keys())) if (!shown2.has(key)) bulkPicked.delete(key);
      pendingBulk = null;
      bulkKinds.replaceChildren(...Array.from(bulkGroups.values(), (group) => {
        const all = el("button", { class: "mini", text: L("bk.all", { k: group.label, n: group.boxes.length }) });
        all.addEventListener("click", () => {
          const on = !group.boxes.every((b) => b.checked);
          for (const b of group.boxes) if (b.checked !== on) {
            b.checked = on;
            b.dispatchEvent(new Event("change"));
          }
        });
        return all;
      }));
      updateBulk();
      for (const span of Array.from(page.querySelectorAll("span.ts[title]"))) {
        const shown3 = localTime(span.getAttribute("title") ?? "", lang);
        if (!shown3) continue;
        span.textContent = shown3.text;
        span.setAttribute("title", shown3.title);
      }
      const who = page.querySelector("p.who");
      if (!who) return;
      const name = who.querySelector("span")?.textContent ?? "";
      const picker = el("select", { "aria-label": name });
      for (const choice of Array.from(who.querySelectorAll("a, b"))) {
        const path = choice.tagName === "B" ? inspectorPath : inspectorApiPath(choice.getAttribute("href"));
        if (path) picker.append(el("option", { value: path, text: choice.textContent ?? "", selected: choice.tagName === "B" }));
      }
      picker.addEventListener("change", () => go(picker.value));
      who.replaceChildren(el("span", { class: "muted", text: name }), picker);
    }
    async function loadGraph(box, note, everyone) {
      const from = inspectorPath;
      const conv = /^\/v1\/views\/c\/[^/]+\/map(?:\?|$)/.test(from) ? inspectorConversation(from) : null;
      if (!conv) return void box.replaceWith(note);
      const focus = /\?focus=([0-9a-f-]{36})$/i.exec(from)?.[1];
      box.replaceChildren(el("div", { class: "muted", text: L("insp.loading") }));
      try {
        const query = [focus ? `focus=${focus}` : "", everyone ? "all=1" : "", lang === "en" ? "lang=en" : ""].filter(Boolean).join("&");
        const raw = await deps.api("GET", `/v1/views/c/${conv}/map/graph${query ? `?${query}` : ""}`, void 0, 15e3);
        if (!box.isConnected || inspectorPath !== from) return;
        const graph = parseGraph(raw);
        if (!graph?.edges.length) return void box.replaceWith(note);
        drawGraph(box, graph, (entity) => go(`/v1/views/c/${conv}/map?focus=${entity}`), (all) => void loadGraph(box, note, all));
      } catch {
        if (box.isConnected) box.replaceWith(note);
      }
    }
    async function loadTimeline(box, span) {
      const from = inspectorPath;
      box.dataset.state = "loading";
      box.replaceChildren(el("div", { class: "muted", text: L("insp.loading") }));
      try {
        const asked = box.classList.contains("tl-status") ? "part=status" : "part=timeline";
        const query = [asked, span ? `span=${span}` : "", lang === "en" ? "lang=en" : ""].filter(Boolean).join("&");
        const r = await deps.api("GET", `${from}?${query}`, void 0, 15e3);
        if (!box.isConnected || inspectorPath !== from) return;
        const part = safeFragment(r.html);
        placeMarks(part);
        box.replaceChildren(part);
        box.dataset.state = "loaded";
      } catch (error) {
        if (!box.isConnected) return;
        delete box.dataset.state;
        box.replaceChildren(el("div", { class: "card err", text: errorText(lang, error) }));
      }
    }
    function showMark(mark) {
      const timeline = mark.closest(".tl");
      const row = mark.closest(".tl-row");
      if (!timeline || !row) return;
      timeline.querySelector(".tl-card")?.remove();
      if (mark.classList.contains("sel")) return void mark.classList.remove("sel");
      for (const on of Array.from(timeline.querySelectorAll(".sel"))) on.classList.remove("sel");
      mark.classList.add("sel");
      row.after(markDetail(mark, { canon: L("tl.canon"), owner: L("tl.owner") }));
    }
    let pendingSection = null;
    function go(path, section = null) {
      pendingSection = section;
      if (path === inspectorPath && !section) return void showInspector();
      if (shownPath) visited.push(place());
      if (visited.length > 30) visited.shift();
      void showInspector(path);
    }
    async function showInspector(path = inspectorPath, at) {
      const load = ++loads;
      const again = path === shownPath;
      const keep = at ?? (again ? place() : void 0);
      inspectorPath = path;
      inspectorBack.style.display = visited.length ? "" : "none";
      const conversation = inspectorConversation(path);
      if (conversation) {
        hubConversation = conversation;
        activeChatId = conversation;
      }
      if (conversation !== actionConversation) {
        actionConversation = conversation;
        notesCard.replaceChildren();
        notesCard.style.display = "none";
        notesFor = null;
        say(actionMsg, "");
        disarm();
        picked.clear();
        updateBulk();
      }
      const isView = path.startsWith("/v1/views/");
      const attentionMode = viewsOn && pendingSection === "s-attention";
      const rawInspector = Boolean(conversation && !isView && !attentionMode);
      if (rawInspector) {
        restoreLegacyActions();
        if (actionMsg.parentElement !== inspectorView) actions.after(actionMsg);
        if (modeCard.parentElement !== inspectorView) bulkBar.after(modeCard, statusCard);
      }
      actions.style.display = rawInspector ? "" : "none";
      const shownEntity = inspectorEntity(path);
      if (!shownEntity) {
        linkCard.style.display = "none";
        pinCard.style.display = "none";
      }
      if (!rawInspector || shownEntity) {
        modeCard.style.display = "none";
        statusCard.style.display = "none";
      }
      if (viewsOn) syncShellForPath(path);
      if (again) {
        inspectorBody.classList.add("busy");
      } else {
        shownPath = null;
        inspectorBody.replaceChildren(el("div", { class: "card muted", text: L("insp.loading") }));
        pinCard.style.display = "none";
      }
      const base = (await deps.getArg("sidecar_url") || "http://127.0.0.1:8790").replace(/\/+$/, "");
      const direct = routeFor(base, await deps.getArg("route")) === "direct";
      inspectorAddress.textContent = direct ? L("insp.browser", { url: `${base}/inspector${lang === "en" ? "?lang=en" : ""}` }) : "";
      try {
        const query = [conversation ? "timeline=lazy&status=lazy" : "", isView && mapOn ? "map=1" : "", lang === "en" ? "lang=en" : ""].filter(Boolean).join("&");
        const r = await deps.api(
          "GET",
          `${path}${query ? `${path.includes("?") ? "&" : "?"}${query}` : ""}`,
          void 0,
          15e3
        );
        if (load !== loads) return;
        if (path.startsWith("/v1/views/hub")) {
          hubConversation = r.conversation ?? null;
          if (hubConversation) activeChatId = hubConversation;
          if (viewsOn) applyHubMeta(r.meta);
        }
        const page = safeFragment(r.html);
        placeMarks(page);
        enhance(page);
        retryButton.style.display = page.querySelector(".has-failed") ? "" : "none";
        inspectorBody.replaceChildren(page);
        shownPath = path;
        const focusSec = pendingSection;
        pendingSection = null;
        if (focusSec) {
          const target = inspectorBody.querySelector(`#${focusSec}`);
          if (target) {
            if (target instanceof HTMLDetailsElement) target.open = true;
            target.scrollIntoView({ block: "start" });
          } else if (keep) restore(keep);
          else root.scrollTop = 0;
        } else if (keep) restore(keep);
        else root.scrollTop = 0;
        if (viewsOn) syncShellForPath(path);
        if (shownEntity) void showEntityCards(shownEntity.conversation, shownEntity.entity, load);
        else if (conversation && !isView && !attentionMode) {
          void showMode(conversation, load);
          void showStatusWindows(conversation, load);
        }
      } catch (error) {
        if (load !== loads) return;
        shownPath = null;
        retryButton.style.display = "none";
        pinCard.style.display = "none";
        inspectorBody.replaceChildren(el("div", { class: "card err", text: errorText(lang, error) }));
      } finally {
        if (load === loads) inspectorBody.classList.remove("busy");
      }
    }
    async function showMode(conversation, load) {
      let mode;
      try {
        mode = await deps.api("GET", `/v1/conversations/${conversation}/memory-mode`, void 0, 15e3);
      } catch {
        modeCard.style.display = "none";
        return;
      }
      if (load !== loads) return;
      const strict = el("input", { type: "checkbox" });
      strict.checked = mode.strict;
      const narrators = [
        ["", L("mode.narrator_none")],
        ["{{user}}", L("mode.narrator_user")],
        ...mode.characters.map((n) => [n, n])
      ];
      if (mode.narrator && !narrators.some(([v]) => v === mode.narrator)) narrators.push([mode.narrator, mode.narrator]);
      const narrator = el(
        "select",
        { "aria-label": L("mode.narrator") },
        ...narrators.map(([value, text2]) => el("option", { value, text: text2 }))
      );
      narrator.value = mode.narrator ?? "";
      const save2 = el("button", { class: "primary", text: L("mode.save") });
      const msg = el("div", { class: "msg" });
      save2.addEventListener("click", async () => {
        save2.disabled = true;
        try {
          const r = await deps.api(
            "PUT",
            `/v1/conversations/${conversation}/memory-mode`,
            { strict: strict.checked, narrator: narrator.value || null },
            15e3
          );
          say(msg, L("mode.saved", { s: L(r.strict ? "mode.on" : "mode.off"), n: r.narrator ?? L("mode.narrator_none") }), "ok");
        } catch (error) {
          say(msg, errorText(lang, error), "err");
        } finally {
          save2.disabled = false;
        }
      });
      modeCard.replaceChildren(
        el("h2", { text: L("mode.title") }),
        el("p", { class: "sub", text: L("mode.sub") }),
        el("div", { class: "check" }, strict, el("span", { text: L("mode.strict") })),
        el("p", { class: "sub", text: L("mode.strict_sub") }),
        el("div", { class: "row" }, field(L("mode.narrator"), narrator)),
        el("p", { class: "sub", text: L("mode.narrator_sub") }),
        el("div", { class: "btns" }, save2),
        msg,
        ...await repliesOnly(conversation)
      );
      modeCard.style.display = "";
    }
    async function repliesOnly(conversation) {
      let on;
      try {
        on = (await deps.api("GET", `/v1/conversations/${conversation}/replies-only`, void 0, 15e3)).on;
      } catch {
        return [];
      }
      const box = el("input", { type: "checkbox", "aria-label": L("ro.title") });
      box.checked = on;
      const msg = el("div", { class: "msg" });
      box.addEventListener("change", async () => {
        box.disabled = true;
        try {
          const r = await deps.api(
            "PUT",
            `/v1/conversations/${conversation}/replies-only`,
            { on: box.checked },
            15e3
          );
          box.checked = r.on;
          say(msg, L(r.on ? "ro.on" : "ro.off"), "ok");
        } catch (error) {
          box.checked = !box.checked;
          say(msg, errorText(lang, error), "err");
        } finally {
          box.disabled = false;
        }
      });
      return [
        el("div", { class: "check" }, box, el("span", { text: L("ro.title") })),
        el("p", { class: "sub", text: L("ro.sub") }),
        msg
      ];
    }
    async function showStatusWindows(conversation, load) {
      let found;
      try {
        found = await deps.api("GET", `/v1/conversations/${conversation}/status/candidates`, void 0, 15e3);
      } catch {
        statusCard.style.display = "none";
        return;
      }
      if (load !== loads) return;
      if (!found || !Array.isArray(found.candidates)) {
        statusCard.style.display = "none";
        return;
      }
      const msg = el("div", { class: "msg", role: "status" });
      const card = found.card;
      const act = async (button, method, path, body, done) => {
        button.disabled = true;
        try {
          await deps.api(method, path, body, 3e4);
          await showStatusWindows(conversation, load);
          say(statusCard.querySelector(".msg"), done, "ok");
        } catch (error) {
          say(msg, errorText(lang, error), "err");
          button.disabled = false;
        }
      };
      const rows = found.candidates.map((c) => {
        const preview = c.keys.slice(0, 8).map((k) => `${k}: ${c.values[k] ?? ""}`).join(" \xB7 ") + (c.keys.length > 8 ? " \u2026" : "");
        const head = el(
          "div",
          { class: "line" },
          el("span", { class: `dot ${c.tracked ? "ok" : "muted"}` }),
          el("span", { text: L(c.tracked ? "sw.tracked" : "sw.found", { n: c.keys.length, c: c.count }) })
        );
        const box = el("div", { class: "sw-window" }, head, el("div", { class: "sub", text: preview }));
        if (!card) return box;
        if (!c.tracked) {
          const track = el("button", { class: "primary", text: L("sw.track") });
          track.addEventListener("click", () => void act(
            track,
            "POST",
            "/v1/parsers/card/track",
            { card, keys: c.keys },
            L("sw.tracked_now", { card })
          ));
          box.append(el("div", { class: "btns" }, track));
          return box;
        }
        const pins = c.keys.map((k) => {
          const box2 = el("input", { type: "checkbox", value: k });
          box2.checked = found.pins.includes(k);
          return el("label", { class: "check" }, box2, el("span", { text: `\u{1F4CC} ${k}` }));
        });
        const savePins = el("button", { text: L("sw.save_pins") });
        savePins.addEventListener("click", () => void act(savePins, "PUT", "/v1/parsers/card/pins", {
          card,
          keys: pins.map((p) => p.querySelector("input")).filter((i) => i.checked).map((i) => i.value)
        }, L("sw.pins_saved")));
        const buttons = el("div", { class: "btns" }, savePins);
        if (c.rule_id) {
          const untrack = el("button", { text: L("sw.untrack") });
          untrack.addEventListener("click", () => void act(
            untrack,
            "POST",
            "/v1/parsers/card/untrack",
            { card, rule_id: c.rule_id },
            L("sw.untracked")
          ));
          buttons.append(untrack);
        } else {
          box.append(el("p", { class: "sub", text: L("sw.by_rule") }));
        }
        box.append(el("p", { class: "sub", text: L("sw.pins_sub") }), el("div", { class: "pins" }, ...pins), buttons);
        return box;
      });
      statusCard.replaceChildren(
        el("h2", { text: L("sw.title") }),
        el("p", { class: "sub", text: card ? L("sw.sub", { card }) : L("sw.no_card") }),
        ...rows.length ? rows : [el("p", { class: "muted", text: L("sw.none") })],
        msg
      );
      statusCard.style.display = "";
    }
    const previewRound = /* @__PURE__ */ new WeakMap();
    function nextRound(spot) {
      const n = (previewRound.get(spot) ?? 0) + 1;
      previewRound.set(spot, n);
      return n;
    }
    async function withPreview(spot, button, previewPath, previewBody, confirmKey, commit, changed = false) {
      const round = nextRound(spot);
      button.disabled = true;
      let p;
      try {
        p = await deps.api("POST", previewPath, previewBody, 15e3);
      } catch (error) {
        if (previewRound.get(spot) !== round) return;
        say(actionMsg, errorText(lang, error), "err");
        button.disabled = false;
        return;
      }
      if (previewRound.get(spot) !== round) return;
      const lines = previewText(p, (key, vars) => L(key, vars), outcomeLabel);
      const box = el(
        "div",
        { class: "preview" },
        el("b", { text: L("pv.title") }),
        ...changed ? [el("div", { class: "warn", text: L("pv.changed") })] : [],
        ...lines.map((text2) => el("div", { class: /^(주의|Note):/.test(text2) ? "warn" : "", text: text2 }))
      );
      const list = p.after.length > 1 ? p.reextract?.list ?? [] : [];
      const turns = list.length;
      const again = el("input", { type: "checkbox", "aria-label": L("pv.reextract", { n: turns }) });
      if (turns > 0) box.append(el("div", { class: "check" }, again, el("span", { text: L("pv.reextract", { n: turns }) })));
      const ok = el("button", { class: "mini", text: L(confirmKey) });
      const cancel = el("button", { class: "mini", text: L("cancel") });
      cancel.addEventListener("click", () => {
        nextRound(spot);
        spot.replaceChildren();
        button.disabled = false;
      });
      ok.addEventListener("click", async () => {
        ok.disabled = true;
        try {
          await commit(p.fingerprint, again.checked ? list : null);
          spot.replaceChildren();
        } catch (error) {
          if (/HTTP 409\b/.test(String(error?.message ?? error))) {
            void withPreview(spot, button, previewPath, previewBody, confirmKey, commit, true);
            return;
          }
          say(actionMsg, errorText(lang, error), "err");
          ok.disabled = false;
        }
      });
      box.append(el("div", { class: "btns" }, ok, cancel));
      spot.replaceChildren(box);
    }
    async function showEntityCards(conversation, entity, load) {
      let entities;
      try {
        const rows = await deps.api("GET", `/v1/conversations/${conversation}/entities`, void 0, 15e3);
        entities = Array.isArray(rows) ? rows : null;
      } catch {
        entities = null;
      }
      if (load !== loads) return;
      showPin(conversation, entity, entities);
      showLinks(conversation, entity, entities ?? []);
    }
    let pinSaid = null;
    function showPin(conversation, entity, entities) {
      const row = entities?.find((e) => e.id === entity);
      const said = pinSaid?.entity === entity ? pinSaid.key : null;
      pinSaid = null;
      if (!row || row.type !== "character" || row.persona || row.excluded) {
        pinCard.style.display = "none";
        pinCard.replaceChildren();
        return;
      }
      const pinned = typeof row.pinned === "string" && row.pinned ? row.pinned : null;
      const box = el("input", { type: "checkbox" });
      box.checked = pinned !== null;
      const msg = el("div", { class: "msg", role: "status" });
      if (said) say(msg, L(said), "ok");
      box.addEventListener("change", async () => {
        const on = box.checked;
        box.disabled = true;
        say(msg, "");
        try {
          if (on) await deps.api("POST", `/v1/conversations/${conversation}/repairs`, { kind: "entity_pin", item: entity }, 15e3);
          else if (pinned) await deps.api("POST", `/v1/conversations/${conversation}/repairs/${pinned}/remove`, {}, 15e3);
          pinSaid = { entity, key: on ? "pin.done" : "pin.undone" };
          say(msg, L(pinSaid.key), "ok");
          await showInspector();
        } catch (error) {
          box.checked = !on;
          say(msg, errorText(lang, error), "err");
        } finally {
          box.disabled = false;
        }
      });
      pinCard.replaceChildren(
        el("h2", { text: L("pin.title", { n: row.name }) }),
        el("p", { class: "sub", text: L("pin.sub") }),
        el("label", { class: "check" }, box, el("span", { text: L("pin.toggle") })),
        msg
      );
      pinCard.style.display = "";
    }
    function showLinks(conversation, entity, entities) {
      const choices = linkChoices(entities, entity);
      if (!choices) {
        linkCard.style.display = "none";
        return;
      }
      const { self, others } = choices;
      const msg = el("div", { class: "msg" });
      const rows = [];
      for (const link of self.links ?? []) {
        const undo = el("button", { text: L("link.remove") });
        const spot = el("div");
        const base = `/v1/conversations/${conversation}/entity-links/${link.id}`;
        undo.addEventListener("click", () => void withPreview(
          spot,
          undo,
          `${base}/remove/preview`,
          {},
          "pv.confirm_undo",
          async (expect, reextract) => {
            await deps.api("POST", `${base}/remove`, { expect }, 15e3);
            let failed = null;
            let queued = 0;
            if (reextract) {
              try {
                queued = (await deps.api("POST", `${base}/reextract`, { turns: reextract }, 15e3)).turns.length;
              } catch (error) {
                failed = error;
              }
            }
            try {
              const now = await deps.api("GET", `/v1/conversations/${conversation}/entities`, void 0, 15e3);
              const next = entityNamed(now, self.type, self.name);
              if (next && next.id !== entity) go(`/v1/inspector/c/${conversation}/e/${next.id}`);
              else await showInspector();
            } catch {
            }
            if (failed && reextract) {
              say(actionMsg, L("pv.reextract_failed", { e: errorText(lang, failed) }), "err");
              const retry = el("button", { class: "mini", text: L("pv.retry") });
              retry.addEventListener("click", async () => {
                retry.disabled = true;
                try {
                  const r = await deps.api("POST", `${base}/reextract`, { turns: reextract }, 15e3);
                  say(actionMsg, L("pv.reextracted", { n: r.turns.length }), "ok");
                } catch (error) {
                  say(actionMsg, L("pv.reextract_failed", { e: errorText(lang, error) }), "err");
                  actionMsg.append(" ", retry);
                  retry.disabled = false;
                }
              });
              actionMsg.append(" ", retry);
            } else {
              say(actionMsg, reextract ? `${L("link.removed")} ${L("pv.reextracted", { n: queued })}` : L("link.removed"), "ok");
            }
          }
        ));
        rows.push(el("div", { class: "btns" }, el("span", { text: `${link.name} = ${link.same_as}` }), undo), spot);
      }
      const card = [el("h2", { text: L("link.title") }), el("p", { class: "sub", text: L("link.sub") }), ...rows];
      const splits = [];
      for (const alias of splitChoices(self)) {
        const split = el("button", { text: L("split.do") });
        const spot = el("div");
        const body = { kind: "name_split", item: alias.name, other: alias.other, entity_type: self.type };
        split.addEventListener("click", () => void withPreview(
          spot,
          split,
          `/v1/conversations/${conversation}/repairs/preview`,
          body,
          "pv.confirm_split",
          async (expect) => {
            await deps.api("POST", `/v1/conversations/${conversation}/repairs`, { ...body, expect }, 15e3);
            const now = await deps.api("GET", `/v1/conversations/${conversation}/entities`, void 0, 15e3);
            const next = entityNamed(now, self.type, self.name);
            say(actionMsg, L("split.done", { a: alias.name, b: alias.other }), "ok");
            if (next && next.id !== entity) go(`/v1/inspector/c/${conversation}/e/${next.id}`);
            else await showInspector();
          }
        ));
        splits.push(el("div", { class: "btns" }, el("span", { text: `${alias.name} ~ ${alias.other}` }), split), spot);
      }
      if (others.length) {
        const pick = el(
          "select",
          { "aria-label": L("link.pick") },
          ...others.map((e) => el("option", { value: e.name, text: `${e.name} (${e.mentions})` }))
        );
        const join = el("button", { text: L("link.join") });
        const spot = el("div");
        const path = `/v1/conversations/${conversation}/entity-links`;
        join.addEventListener("click", () => {
          const body = { entity_type: self.type, name: self.name, same_as: pick.value };
          void withPreview(spot, join, `${path}/preview`, body, "pv.confirm_join", async (expect) => {
            const r = await deps.api("POST", path, { ...body, expect }, 15e3);
            say(actionMsg, L("link.done", { a: body.name, b: body.same_as }), "ok");
            if (r.entity && r.entity.id !== entity) go(`/v1/inspector/c/${conversation}/e/${r.entity.id}`);
            else await showInspector();
          });
        });
        pick.addEventListener("change", () => {
          nextRound(spot);
          spot.replaceChildren();
          join.disabled = false;
        });
        card.push(el("div", { class: "row" }, field(L("link.pick"), pick), el("div", { class: "btns" }, join)), spot);
      } else {
        card.push(el("div", { class: "muted", text: L("link.none") }));
      }
      if (splits.length) card.push(el("h2", { text: L("split.title") }), el("p", { class: "sub", text: L("split.sub") }), ...splits);
      linkCard.replaceChildren(...card, msg);
      linkCard.style.display = "";
    }
    inspectorBody.addEventListener("click", (event) => {
      const clicked = event.target instanceof Element ? event.target : null;
      const act = clicked?.closest("[data-act]")?.getAttribute("data-act");
      if (act) {
        event.preventDefault();
        return void doAct(act);
      }
      const row = clicked?.closest(".v-line");
      if (row && !clicked?.closest("a, button, select, input, label, .rp")) return void row.classList.toggle("open");
      const choice = clicked?.closest(".tl-span[data-span]");
      const box = choice?.closest(".tl-lazy");
      if (choice && box) return void loadTimeline(box, choice.getAttribute("data-span") ?? "");
      const mark = clicked?.closest(".tl [data-v]");
      if (mark) return showMark(mark);
      const link = clicked ? clicked.closest("a") : null;
      if (!link) return;
      event.preventDefault();
      const href = link.getAttribute("href");
      const section = sectionTarget(href);
      const path = inspectorApiPath(href);
      if (!path || path === inspectorPath) {
        const target = section ? inspectorBody.querySelector(`#${section}`) : null;
        if (target) {
          if (target instanceof HTMLDetailsElement) target.open = true;
          target.scrollIntoView({ block: "start", behavior: "smooth" });
          return;
        }
      }
      if (path) go(path, section);
    });
    inspectorBack.addEventListener("click", () => {
      const at = visited.pop();
      if (at) void showInspector(at.path, at);
    });
    inspectorRefresh.addEventListener("click", () => void showInspector());
    const confirmable = [
      [rebuildButton, "act.rebuild", "primary"],
      [deleteButton, "act.delete", "danger"]
    ];
    let armed = null;
    let armTimer = 0;
    function disarm() {
      window.clearTimeout(armTimer);
      armed = null;
      for (const [button, label] of confirmable) {
        button.textContent = L(label);
        button.className = "";
      }
    }
    function confirmed(button, confirm, cls) {
      if (armed === button) {
        disarm();
        return true;
      }
      disarm();
      armed = button;
      button.textContent = L(confirm);
      button.className = cls;
      armTimer = window.setTimeout(disarm, 6e3);
      return false;
    }
    function actionError(error) {
      return /HTTP 409/.test(error instanceof Error ? error.message : String(error)) ? L("act.off") : errorText(lang, error);
    }
    retryButton.addEventListener("click", async () => {
      const conversation = actionConversation;
      if (!conversation) return;
      disarm();
      retryButton.disabled = true;
      say(actionMsg, L("act.working"));
      try {
        const r = await deps.api(
          "POST",
          `/v1/conversations/${conversation}/retry-failed`,
          {},
          3e4
        );
        const n = Object.values(r.retried ?? {}).reduce((a, b) => a + (Number(b) || 0), 0);
        say(actionMsg, n ? L("act.retry_done", { n }) : L("act.retry_none"), "ok");
        if (n) deps.hud.background(conversation);
        await showInspector();
      } catch (error) {
        say(actionMsg, actionError(error), "err");
      } finally {
        retryButton.disabled = false;
      }
    });
    historyButton.addEventListener("click", async () => {
      const conversation = actionConversation;
      if (!conversation) return;
      disarm();
      historyButton.disabled = true;
      say(actionMsg, L("act.working"));
      try {
        const r = await deps.api("POST", `/v1/conversations/${conversation}/extract-history`, {}, 3e4);
        const n = (r.queued.extract ?? 0) + (r.queued.embed ?? 0);
        say(actionMsg, n ? L("act.history_done", { t: r.queued.extract ?? 0, m: r.queued.embed ?? 0 }) : L("act.history_none"), "ok");
        if (n) deps.hud.background(conversation);
        await showInspector();
      } catch (error) {
        say(actionMsg, actionError(error), "err");
      } finally {
        historyButton.disabled = false;
      }
    });
    rebuildButton.addEventListener("click", async () => {
      const conversation = actionConversation;
      if (!conversation || !confirmed(rebuildButton, "act.rebuild_confirm", "primary")) return;
      rebuildButton.disabled = true;
      say(actionMsg, L("act.working"));
      try {
        const r = await deps.api("POST", `/v1/conversations/${conversation}/rebuild`, {}, 3e4);
        say(actionMsg, L("act.rebuild_done", { d: r.discarded ?? 0, t: r.queued.extract ?? 0 }), "ok");
        deps.hud.background(conversation);
        await showInspector();
      } catch (error) {
        say(actionMsg, actionError(error), "err");
      } finally {
        rebuildButton.disabled = false;
      }
    });
    deleteButton.addEventListener("click", async () => {
      const conversation = actionConversation;
      if (!conversation || !confirmed(deleteButton, "act.delete_confirm", "danger")) return;
      deleteButton.disabled = true;
      say(actionMsg, L("act.working"));
      try {
        const r = await deps.api("POST", `/v1/conversations/${conversation}/delete`, {}, 6e4);
        visited.length = 0;
        await showInspector("/v1/inspector");
        say(actionMsg, L("act.delete_done", { m: r.deleted.messages ?? 0 }), "ok");
      } catch (error) {
        say(actionMsg, errorText(lang, error), "err");
      } finally {
        deleteButton.disabled = false;
      }
    });
    notesButton.addEventListener("click", () => {
      const conversation = actionConversation;
      if (!conversation) return;
      if (notesCard.style.display !== "none") return void (notesCard.style.display = "none");
      if (!notesCard.childElementCount) buildNotes(conversation);
      notesCard.style.display = "";
    });
    function buildNotes(conversation, target = notesCard, studio = false) {
      notesFor = conversation;
      const specs = [
        { key: "notes.diverged", kind: "diverged", on: true, desc: "notes.desc_diverged", badge: "notes.badge_llm", badgeCls: "b-llm", calls: 1 },
        { key: "notes.chronicle", kind: "chronicle", on: false, desc: "notes.desc_chronicle", badge: "notes.badge_llm", badgeCls: "b-llm", calls: 1 },
        { key: "notes.address", kind: "address", on: false, desc: "notes.desc_address", badge: "notes.badge_free", badgeCls: "b-free", calls: 0 },
        { key: "notes.custom", kind: "custom", on: false, desc: "notes.desc_custom", badge: "notes.badge_unchecked", badgeCls: "b-warn", calls: 1 }
      ];
      const estBar = el("div", { class: "notes-est" });
      const kinds = specs.map((s) => {
        const box = el("input", { type: "checkbox", value: s.kind });
        box.checked = s.on;
        if (!studio) {
          return { box, calls: s.calls, row: el("div", { class: "check" }, box, el("span", { text: L(s.key) })) };
        }
        const card = el(
          "label",
          { class: `note-opt${s.on ? " on" : ""}` },
          box,
          el(
            "div",
            { class: "note-opt-body" },
            el(
              "div",
              { class: "note-opt-top" },
              el("span", { class: "note-opt-title", text: L(s.key) }),
              el("span", { class: `badge ${s.badgeCls}`, text: L(s.badge) })
            ),
            el("div", { class: "note-opt-desc", text: L(s.desc) })
          )
        );
        box.addEventListener("change", () => {
          card.classList.toggle("on", box.checked);
          updateEst();
        });
        return { box, calls: s.calls, row: card };
      });
      const updateEst = () => {
        const calls2 = kinds.reduce((sum, k) => sum + (k.box.checked ? k.calls : 0), 0);
        estBar.replaceChildren(
          icon(calls2 > 0 ? "sparkles" : "check", 14),
          el("span", { text: calls2 > 0 ? L("notes.calls_est", { n: calls2 }) : L("notes.calls_free") })
        );
      };
      if (studio) updateEst();
      const custom = kinds[3].box;
      const prompt = el("textarea", {
        rows: 6,
        maxlength: String(PROMPT_MAX),
        spellcheck: "false",
        style: "font-family:inherit",
        "aria-label": L("notes.custom_prompt"),
        placeholder: L("notes.custom_placeholder")
      });
      const count2 = el("p", { class: "sub" });
      const counted = () => {
        count2.textContent = L("notes.custom_count", { n: prompt.value.trim().length, max: PROMPT_MAX });
      };
      prompt.addEventListener("input", counted);
      counted();
      const setting = el("input", { type: "checkbox" });
      const customArea = el(
        "div",
        { style: "display:none;margin:8px 0 12px" },
        prompt,
        count2,
        el("div", { class: "check" }, setting, el("span", { text: L("notes.custom_setting") })),
        el("p", { class: "sub", text: L("notes.custom_setting_sub") }),
        el("p", { class: "sub", text: L("notes.custom_unchecked") })
      );
      custom.addEventListener("change", () => {
        customArea.style.display = custom.checked ? "" : "none";
      });
      let saved = "";
      void deps.api("GET", "/v1/notes/prompt", void 0, 15e3).then((r) => {
        saved = typeof r?.prompt === "string" ? r.prompt : "";
        if (!prompt.value) {
          prompt.value = saved;
          counted();
        }
      }).catch(() => {
      });
      const length = el(
        "select",
        { "aria-label": L("notes.length") },
        el("option", { value: "3000", text: L("notes.short") }),
        el("option", { value: "6000", text: L("notes.long") })
      );
      const secrets = el("input", { type: "checkbox" });
      const warn = el("p", { class: "sub warn", text: L("notes.secrets_warn"), style: "display:none" });
      secrets.addEventListener("change", () => {
        warn.style.display = secrets.checked ? "" : "none";
      });
      const make2 = el("button", { class: "primary" }, ...studio ? [icon("sparkles", 15)] : [], L("notes.make"));
      const msg = el("div", { class: "msg" });
      const results = el("div", {}, ...studio ? [el("div", { class: "studio-empty", text: L("notes.empty_hint") })] : []);
      make2.addEventListener("click", async () => {
        const sections = kinds.filter((k) => k.box.checked).map((k) => k.box.value);
        if (!sections.length) return say(msg, L("notes.pick"), "warn");
        const text2 = prompt.value.trim();
        if (custom.checked && !text2) return say(msg, L("notes.custom_empty"), "warn");
        make2.disabled = true;
        say(msg, L("act.working"));
        results.replaceChildren(...studio ? [el("div", { class: "studio-empty", text: L("act.working") })] : []);
        let unsaved = false;
        if (custom.checked && text2 !== saved) {
          try {
            await deps.api("PUT", "/v1/notes/prompt", { prompt: text2 }, 15e3);
            saved = text2;
          } catch {
            unsaved = true;
          }
        }
        const body = { sections, chars: Number(length.value), secrets: secrets.checked };
        if (custom.checked) Object.assign(body, { custom_prompt: text2, custom_setting: setting.checked });
        try {
          const r = await deps.api(
            "POST",
            `/v1/conversations/${conversation}/notes`,
            body,
            9e5
          );
          if (notesFor !== conversation) return;
          results.replaceChildren(noteResult(r, msg));
          const done = r.text ? L("notes.done") : L("notes.part_none", { part: L("notes.title") });
          say(msg, unsaved ? `${done} ${L("notes.custom_unsaved")}` : done, r.text && !unsaved ? "ok" : "warn");
        } catch (error) {
          say(msg, errorText(lang, error), "err");
        } finally {
          make2.disabled = false;
        }
      });
      if (!studio) {
        target.replaceChildren(
          el("h2", { text: L("notes.title") }),
          el("p", { class: "sub", text: L("notes.sub") }),
          ...kinds.map((k) => k.row),
          customArea,
          el("div", { class: "row" }, field(L("notes.length"), length)),
          el("div", { class: "check" }, secrets, el("span", { text: L("notes.secrets") })),
          warn,
          el("div", { class: "btns" }, make2),
          msg,
          results
        );
        return;
      }
      const leftCol = el(
        "div",
        { class: "studio-col" },
        el("h3", { text: L("notes.config_head") }),
        ...kinds.map((k) => k.row),
        customArea,
        el("div", { class: "row" }, field(L("notes.length"), length)),
        el("div", { class: "check" }, secrets, el("span", { text: L("notes.secrets") })),
        warn,
        estBar,
        el("div", { class: "btns" }, make2),
        msg
      );
      const rightCol = el(
        "div",
        { class: "studio-col" },
        el("h3", { text: L("notes.preview_head") }),
        results
      );
      target.replaceChildren(
        el("div", { class: "studio-head" }, el("h2", { text: L("notes.title") }), el("p", { class: "sub", text: L("notes.studio_sub") })),
        el("div", { class: "notes-studio" }, leftCol, rightCol)
      );
    }
    function noteResult(r, msg) {
      const how = (p) => {
        const part = L(`notes.part.${p.kind}`);
        if (p.reason === "no_scenes") return L("notes.part_no_scenes", { part });
        if (p.reason === "none") return L("notes.part_none", { part });
        if (p.reason === "no_model" || p.reason === "failed" || p.reason === "held") {
          return L(`notes.part_${p.reason}`, { part });
        }
        const bits = [L(`notes.made_${p.made}`)];
        if (p.cached) bits.push(L("notes.cached"));
        if (p.held) bits.push(L("notes.held", { n: p.held }));
        if (p.entries !== void 0) bits.push(L("notes.entries", { n: p.entries, m: p.left_out ?? 0 }));
        if (p.kind === "custom") bits.push(L("notes.unchecked"));
        return L("notes.part_made", { part, how: bits.join(", ") });
      };
      const stale = r.sections.reduce((n, p) => Math.max(n, p.stale ?? 0), 0);
      const about = el(
        "ul",
        { class: "sub" },
        ...r.sections.map((p) => el("li", { text: how(p) })),
        ...stale ? [el("li", { text: L("notes.stale", { n: stale }) })] : []
      );
      if (!r.text) return el("div", {}, about);
      const box = el("textarea", {
        readonly: true,
        rows: 14,
        spellcheck: "false",
        style: "font-family:inherit",
        "aria-label": L("notes.result")
      });
      box.value = r.text;
      const copy = el("button", { class: "primary" }, icon("copy", 15), L("notes.copy"));
      copy.addEventListener("click", async () => {
        const copied = await copyText(box, navigator.clipboard);
        say(msg, L(copied ? "notes.copied" : "notes.copy_hint"), copied ? "ok" : "warn");
      });
      return el(
        "div",
        {},
        el("h2", { text: L("notes.result") }),
        about,
        el("p", { class: "sub", text: L("notes.chars", { n: r.chars }) }),
        box,
        el("div", { class: "btns" }, copy)
      );
    }
    exportButton.addEventListener("click", async () => {
      const conversation = actionConversation;
      if (!conversation) return;
      await exportTo(exportButton, actionMsg, `/v1/archive?conversation=${conversation}`, "chat");
    });
    async function exportTo(button, msg, path, kind) {
      button.disabled = true;
      say(msg, L("exp.working"));
      try {
        const size = await deps.download(path, archiveName(kind, /* @__PURE__ */ new Date()));
        say(msg, L("exp.saved", { mb: (size / 1048576).toFixed(1) }), "ok");
      } catch (error) {
        say(msg, errorText(lang, error), "err");
      } finally {
        button.disabled = false;
      }
    }
    const hudBox = el("input", { type: "checkbox" });
    const hudMsg = el("div", { class: "msg" });
    hudBox.addEventListener("change", async () => {
      hudBox.disabled = true;
      try {
        if (!hudBox.checked) {
          await deps.hud.disable();
          return say(hudMsg, L("hud.off"), "muted");
        }
        const result = await deps.hud.enable();
        hudBox.checked = result === "on";
        if (result === "on") say(hudMsg, L("hud.on"), "ok");
        else say(hudMsg, L(result === "denied" ? "hud.denied" : "hud.unsupported"), "warn");
      } catch (error) {
        say(hudMsg, errorText(lang, error), "err");
      } finally {
        hudBox.disabled = false;
      }
    });
    settingsView.append(el(
      "div",
      { class: "card" },
      el("h2", { text: L("hud.title") }),
      el("p", { class: "sub", text: L("hud.sub") }),
      el("div", { class: "check" }, hudBox, el("span", { text: L("hud.toggle") })),
      hudMsg
    ));
    const url = el("input", { spellcheck: "false" });
    const route = el("select", {}, ...["auto", "direct", "server"].map((v) => el("option", { value: v, text: v })));
    const enabled = el("input", { type: "checkbox" });
    const reserved = el("input", { type: "number", min: 100, max: PANEL_MAX_RESERVED_TOKENS });
    const deadline = el("input", { type: "number", min: 200, max: MAX_DEADLINE_MS, step: 100 });
    const token = el("input", { type: "password", placeholder: L("conn.token_placeholder"), autocomplete: "off" });
    let install = null;
    settingsView.append(el(
      "div",
      { class: "card" },
      el("h2", { text: L("conn.title") }),
      el("p", { class: "sub", text: L("conn.sub") }),
      field(L("conn.url"), url),
      field(L("conn.token"), token),
      el("div", { class: "row" }, field(L("conn.route"), route), field(L("conn.budget"), reserved), field(L("conn.deadline"), deadline)),
      el("div", { class: "check" }, enabled, el("span", { text: L("conn.enabled") })),
      el("p", { class: "sub", text: L("conn.hint") }),
      el("p", { class: "sub", text: L("conn.deadline_hint") })
    ));
    function modelSection(kind, title2, sub, presets, onPreset, extra) {
      const preset = el("select", {}, ...presets.map((p, i) => el("option", {
        value: String(i),
        text: p.label.includes(".") ? L(p.label) : p.label
      })));
      const endpoint = el("input", { placeholder: "https://\u2026/v1", spellcheck: "false" });
      const model = el("input", { placeholder: L(kind === "llm" ? "model.llm_placeholder" : "model.emb_placeholder"), spellcheck: "false" });
      const list = el("select", { style: "display:none" });
      const key = el("input", { type: "password", placeholder: L("model.key_placeholder"), autocomplete: "off" });
      const msg = el("div", { class: "msg" });
      const load = el("button", { text: L("model.load") });
      const test = el("button", { text: L("model.test") });
      const keyFile = el("input", { type: "file", accept: ".json,application/json", style: "display:none" });
      const pickKey = el("button", { text: L("model.key_file"), style: "display:none" });
      const syncPickKey = () => {
        pickKey.style.display = kind === "llm" && isVertexEndpoint(endpoint.value) ? "" : "none";
      };
      pickKey.addEventListener("click", () => keyFile.click());
      keyFile.addEventListener("change", async () => {
        const file = keyFile.files?.[0];
        keyFile.value = "";
        if (!file) return;
        let text2;
        try {
          text2 = (await file.text()).trim();
        } catch (error) {
          return say(msg, errorText(lang, error), "err");
        }
        const project = serviceAccountProject(text2);
        if (!project) return say(msg, L("model.key_file_bad"), "err");
        const vertexModel = presets.find((p) => p.url === VERTEX_URL)?.model;
        key.value = text2;
        endpoint.value = endpointForKey(endpoint.value, text2);
        preset.value = String(presetIndex(presets, endpoint.value));
        if (!model.value.trim().startsWith("google/") && vertexModel) model.value = vertexModel;
        update();
        say(msg, L("model.key_file_ok", { project }), "ok");
        load.click();
      });
      preset.addEventListener("change", () => {
        const p = presets[Number(preset.value)];
        if (p.url !== "custom") endpoint.value = fillProject(presetUrl(p.url, install), key.value);
        if (p.model) model.value = p.model;
        if (!p.url) model.value = "";
        say(msg, p.hint ? L(p.hint) : p.url.includes("{project}") ? L("model.vertex_hint") : "");
        onPreset?.(p);
        syncPickKey();
        update();
      });
      endpoint.addEventListener("input", syncPickKey);
      key.addEventListener("input", () => {
        endpoint.value = fillProject(endpoint.value, key.value);
      });
      list.addEventListener("change", () => {
        model.value = list.value;
        update();
      });
      load.addEventListener("click", async () => {
        say(msg, L("model.loading"));
        try {
          const r = await deps.api(
            "POST",
            "/v1/config/models",
            { kind, url: endpoint.value.trim(), api_key: key.value.trim() || void 0 }
          );
          if (!r.ok) return say(msg, L("model.list_failed", { e: r.error ?? "" }), "err");
          list.replaceChildren(
            el("option", { value: "", text: L("model.pick", { n: r.models.length }) }),
            ...r.models.map((m) => el("option", { value: m, text: m }))
          );
          list.style.display = "";
          say(msg, L("model.found", { n: r.models.length }), "ok");
        } catch (error) {
          say(msg, errorText(lang, error), "err");
        }
      });
      test.addEventListener("click", async () => {
        const more = extra ? extra.test() : {};
        if (!more) return say(msg, L("extra.invalid"), "err");
        test.disabled = true;
        say(msg, L("model.testing"));
        try {
          const r = await deps.api(
            "POST",
            "/v1/config/test",
            { kind, url: endpoint.value.trim(), model: model.value.trim(), api_key: key.value.trim() || void 0, ...more }
          );
          say(msg, r.ok ? L("model.test_ok", { ms: r.ms }) + (r.dimensions ? L("model.dims", { n: r.dimensions }) : "") : L("model.test_failed", { e: r.error ?? "" }), r.ok ? "ok" : "err");
        } catch (error) {
          say(msg, errorText(lang, error), "err");
        } finally {
          test.disabled = false;
        }
      });
      settingsView.append(el(
        "div",
        { class: "card" },
        el("h2", { text: L(title2) }),
        el("p", { class: "sub", text: L(sub) }),
        field(L("model.provider"), preset),
        field(L("model.endpoint"), endpoint),
        field(L("model.model"), model),
        list,
        field(L("model.key"), key),
        ...extra?.nodes ?? [],
        el("div", { class: "btns" }, pickKey, load, test),
        keyFile,
        msg
      ));
      return {
        values: () => ({ url: endpoint.value, model: model.value, key: key.value }),
        fill(cfg) {
          preset.value = String(presetIndex(presets, cfg.url));
          endpoint.value = cfg.url;
          model.value = cfg.model;
          key.value = "";
          key.placeholder = L(cfg.api_key_set ? "model.key_saved" : "model.key_placeholder");
          syncPickKey();
        }
      };
    }
    let extraKnown = false;
    const extraText = el("textarea", {
      rows: 4,
      spellcheck: "false",
      placeholder: "{}",
      style: "min-height:96px",
      "aria-label": L("extra.body")
    });
    const extraErr = el("div", { class: "msg err", text: L("extra.invalid"), style: "display:none" });
    const effortCustom = el("option", { value: "custom", text: L("extra.custom") });
    const effort = el(
      "select",
      { "aria-label": L("extra.effort") },
      el("option", { value: "", text: "\u2014" }),
      ...EFFORTS.map((e) => el("option", { value: e, text: e }))
    );
    const effortRow = el("div", {}, field(L("extra.effort"), effort), el("p", { class: "sub", text: L("extra.effort_sub") }));
    const noTemp = el("input", { type: "checkbox" });
    const extraBox = el(
      "div",
      { style: "display:none" },
      field(L("extra.body"), extraText),
      extraErr,
      el("p", { class: "sub", text: L("extra.body_sub") }),
      effortRow,
      el("div", { class: "check" }, noTemp, el("span", { text: L("extra.no_temp") })),
      el("p", { class: "sub", text: L("extra.no_temp_sub") })
    );
    const writeEffort = () => {
      if (effort.value !== "custom") extraText.value = withEffort(extraText.value, effort.value || null);
    };
    effort.addEventListener("input", writeEffort);
    effort.addEventListener("change", writeEffort);
    function syncExtra() {
      extraBox.style.display = extraKnown ? "" : "none";
      effortRow.style.display = isOpenRouter(llm.values().url) ? "" : "none";
      const s = effortOf(extraText.value);
      if (s.state === "custom") effort.append(effortCustom);
      else effortCustom.remove();
      effort.value = s.state === "value" ? s.effort : s.state === "custom" ? "custom" : "";
      effort.disabled = s.state === "invalid";
      extraErr.style.display = s.state === "invalid" ? "" : "none";
    }
    const extraValues = () => extraKnown ? { extra: extraText.value, noTemp: noTemp.checked } : {};
    const llm = modelSection("llm", "llm.title", "llm.sub", LLM_PRESETS, void 0, { nodes: [extraBox], test: () => {
      if (!extraKnown) return {};
      const body = bodyOf(extraText.value);
      return body && { extra_body: body, no_temperature: noTemp.checked };
    } });
    const emb = modelSection(
      "embeddings",
      "emb.title",
      "emb.sub",
      EMBED_PRESETS,
      (p) => {
        if (p.minSim !== void 0) minSim.value = String(p.minSim);
      }
    );
    let rerankKnown = false;
    const rerankUrl = el("input", { placeholder: "https://\u2026/v1", spellcheck: "false" });
    const rerankModel = el("input", { placeholder: L("rerank.model_placeholder"), spellcheck: "false" });
    const rerankKey = el("input", { type: "password", placeholder: L("model.key_placeholder"), autocomplete: "off" });
    const rerankTimeout = el("input", { type: "number", min: MIN_RERANK_TIMEOUT_MS, max: MAX_RERANK_TIMEOUT_MS, step: 50 });
    const rerankDot = el("span", { class: "dot" });
    const rerankStateText = el("span", { text: L("rerank.off") });
    const rerankState = el("div", { class: "line muted" }, rerankDot, rerankStateText);
    const rerankCard = el(
      "div",
      { class: "card", style: "display:none" },
      el("h2", { text: L("rerank.title") }),
      rerankState,
      el("p", { class: "sub", text: L("rerank.sub") }),
      field(L("rerank.url"), rerankUrl),
      field(L("model.model"), rerankModel),
      field(L("model.key"), rerankKey),
      field(L("rerank.timeout"), rerankTimeout)
    );
    settingsView.append(rerankCard);
    const rerank = {
      values: () => ({ url: rerankUrl.value, model: rerankModel.value, key: rerankKey.value, timeout: rerankTimeout.value }),
      fill(cfg) {
        rerankKnown = Boolean(cfg);
        if (cfg) {
          rerankUrl.value = cfg.url;
          rerankModel.value = cfg.model;
          rerankKey.value = "";
          rerankKey.placeholder = L(cfg.key_set ? "model.key_saved" : "model.key_placeholder");
          rerankTimeout.value = String(cfg.timeout_ms);
          rerankState.className = cfg.configured ? "line ok" : "line muted";
          rerankDot.className = cfg.configured ? "dot ok" : "dot";
          rerankStateText.textContent = L(cfg.configured ? "rerank.on" : "rerank.off");
        } else {
          rerankUrl.value = "";
          rerankModel.value = "";
          rerankKey.value = "";
          rerankKey.placeholder = L("model.key_placeholder");
          rerankTimeout.value = "";
          rerankState.className = "line muted";
          rerankDot.className = "dot";
          rerankStateText.textContent = L("rerank.off");
        }
        rerankCard.style.display = rerankKnown && (!viewsOn || currentGroup === "models") ? "" : "none";
      }
    };
    const threshold = el("input", { type: "number", step: 0.05, min: 0.05, max: 1 });
    const minSim = el("input", { type: "number", step: 0.01, min: 0, max: 1 });
    const embedWait = el("input", { type: "number", step: 100, min: 100, max: 5e3 });
    const topK = el("input", { type: "number", min: 0, max: 20 });
    const factsLimit = el("input", { type: "number", min: 0, max: 30 });
    const backfill = el("input", { type: "number", min: 0, max: 5e3 });
    const summaries = el("input", { type: "checkbox" });
    const canonFacts = el("input", { type: "checkbox" });
    const pinAt = el("input", { type: "checkbox", disabled: true });
    let pinAtKnown = false;
    settingsView.append(el(
      "div",
      { class: "card" },
      el("h2", { text: L("tune.title") }),
      el("p", { class: "sub", text: L("tune.sub") }),
      el(
        "div",
        { class: "row" },
        field(L("tune.threshold"), threshold),
        field(L("tune.min_sim"), minSim),
        field(L("tune.embed_wait"), embedWait)
      ),
      el("p", { class: "sub", text: L("tune.embed_wait_hint") }),
      el("div", { class: "row" }, field(L("tune.top_k"), topK), field(L("tune.facts"), factsLimit), field(L("tune.backfill"), backfill)),
      el("div", { class: "check" }, summaries, el("span", { text: L("tune.summaries") })),
      el("p", { class: "sub", text: L("tune.summaries_hint") }),
      el("div", { class: "check" }, canonFacts, el("span", { text: L("tune.canon_facts") })),
      el("p", { class: "sub", text: L("tune.canon_facts_hint") }),
      el("div", { class: "check" }, pinAt, el("span", { text: L("tune.pin_at") })),
      el("p", { class: "sub", text: L("tune.pin_at_hint") })
    ));
    const trimOn = el("input", { type: "checkbox" });
    const trimKeep = el("input", { type: "number", min: MIN_KEEP_RECENT_TURNS, max: MAX_KEEP_RECENT_TURNS, step: 1 });
    trimKeep.value = String(DEFAULT_KEEP_RECENT_TURNS);
    const trimWarn = el("div", { class: "warn", text: L("trimset.needs_summaries"), style: "display:none" });
    const syncTrimWarn = () => {
      trimWarn.style.display = trimOn.checked && !summaries.checked ? "" : "none";
    };
    settingsView.append(el(
      "div",
      { class: "card" },
      el("h2", { text: L("trimset.title") }),
      el("p", { class: "sub", text: L("trimset.sub") }),
      el("div", { class: "check" }, trimOn, el("span", { text: L("trimset.on") })),
      field(L("trimset.keep"), trimKeep),
      trimWarn
    ));
    const rules = el("textarea", {
      id: "nmos-parser-draft",
      spellcheck: "false",
      "aria-label": L("rules.draft"),
      placeholder: L("rules.none")
    });
    const parserTarget = el("input", {
      id: "nmos-parser-target",
      list: "nmos-parser-cards",
      "aria-label": L("rules.target"),
      placeholder: L("rules.choose_target")
    });
    const parserCards = el("datalist", { id: "nmos-parser-cards" });
    const parserActive = el("div", { id: "nmos-parser-active", class: "sub", style: "white-space:pre-line" });
    const parserStored = el("pre", {});
    const parserPreview = el("p", { id: "nmos-parser-preview", class: "sub" });
    const parserMessage = el("div", { class: "msg", role: "status" });
    const parserApply = el("button", { id: "nmos-parser-apply", text: L("rules.apply") });
    const parserClear = el("button", { text: L("rules.prepare_disable") });
    const parserFile = el("input", { id: "nmos-parser-file", type: "file", accept: ".json,application/json", style: "display:none" });
    const parserPick = el("button", { text: L("rules.import") });
    const parserPreset = el("select", { id: "nmos-parser-preset", "aria-label": L("rules.preset") });
    const parserName = el("input", { id: "nmos-parser-name", "aria-label": L("rules.preset_name") });
    const parserSavePreset = el("button", { id: "nmos-parser-save-preset", text: L("rules.save_preset") });
    const parserRemovePreset = el("button", { id: "nmos-parser-remove-preset", text: L("rules.remove_preset") });
    const example = el("button", { text: L("rules.example") });
    let parserSupported = false;
    let parserBusy = false;
    let parserPresets = [];
    let appliedDraft = "";
    let appliedTarget = "";
    const knownCards = /* @__PURE__ */ new Set();
    const parserDirty = () => rules.value !== appliedDraft || parserTarget.value !== appliedTarget;
    function updateParser() {
      const parsed = parserDraft(rules.value);
      const target = parserTarget.value.trim();
      parserApply.disabled = parserBusy || !parserSupported || !target || !parsed.ok;
      parserApply.textContent = L(parsed.ok && parsed.rules.length === 0 ? "rules.disable" : "rules.apply");
      parserSavePreset.disabled = parserBusy || !parserSupported || !parserName.value.trim() || !parsed.ok;
      parserRemovePreset.disabled = parserBusy || !parserSupported || !parserPreset.value;
      parserPreview.textContent = !target ? L("rules.choose_target") : !parsed.ok ? L(parsed.error === "blank" ? "rules.blank" : parsed.error === "json" ? "rules.invalid_json" : "rules.invalid_shape") : L("rules.preview", { card: target, n: parsed.rules.length });
    }
    function fillParsers(cfg) {
      parserSupported = cfg.parsers.spec !== void 0 && Array.isArray(cfg.parsers.presets);
      const spec = cfg.parsers.spec ?? cfg.parsers.rules;
      const bindings = parserBindings(spec);
      const notes = bindings.cards.map(({ name, count: count2 }) => L("rules.binding", { card: name, n: count2 }));
      if (bindings.unbound) notes.push(L("rules.unbound", { n: bindings.unbound }));
      if (!notes.length) notes.push(L("rules.no_active"));
      if (!parserSupported) notes.push(L("rules.upgrade"));
      notes.push(...cfg.parsers.errors);
      parserActive.textContent = notes.join("\n");
      parserStored.textContent = JSON.stringify(spec ?? { rules: [] }, null, 2);
      for (const { name } of bindings.cards) knownCards.add(name);
      parserCards.replaceChildren(...[...knownCards].sort().map((name) => el("option", { value: name })));
      parserPresets = cfg.parsers.presets ?? [];
      const selected = parserPreset.value;
      parserPreset.replaceChildren(
        el("option", { value: "", text: L("rules.choose_preset") }),
        ...parserPresets.map((p) => el("option", { value: p.name, text: p.name }))
      );
      parserPreset.value = parserPresets.some((p) => p.name === selected) ? selected : "";
      updateParser();
    }
    parserPick.addEventListener("click", () => parserFile.click());
    parserFile.addEventListener("change", async () => {
      const file = parserFile.files?.[0];
      parserFile.value = "";
      if (!file) return;
      try {
        rules.value = await file.text();
        parserPreset.value = "";
        say(parserMessage, L("rules.loaded"));
        updateParser();
      } catch (error) {
        say(parserMessage, errorText(lang, error), "err");
      }
    });
    parserPreset.addEventListener("change", () => {
      const chosen2 = parserPresets.find((p) => p.name === parserPreset.value);
      if (chosen2) {
        rules.value = JSON.stringify({ rules: chosen2.rules }, null, 2);
        parserName.value = chosen2.name;
      }
      updateParser();
    });
    for (const control of [rules, parserTarget, parserName]) control.addEventListener("input", updateParser);
    example.addEventListener("click", () => {
      rules.value = JSON.stringify(PARSER_EXAMPLE, null, 2);
      updateParser();
    });
    parserClear.addEventListener("click", () => {
      rules.value = JSON.stringify({ rules: [] }, null, 2);
      updateParser();
    });
    parserApply.addEventListener("click", async () => {
      const parsed = parserDraft(rules.value);
      const card = parserTarget.value.trim();
      if (parserBusy || !parserSupported || !card || !parsed.ok) return;
      const draft = rules.value;
      const target = parserTarget.value;
      parserBusy = true;
      updateParser();
      try {
        const cfg = await deps.api("PUT", "/v1/parsers/card", { card, rules: parsed.rules });
        fillParsers(cfg);
        appliedDraft = draft;
        appliedTarget = target;
        say(parserMessage, L("rules.applied", { card, n: parsed.rules.length }), "ok");
      } catch (error) {
        say(parserMessage, errorText(lang, error), "err");
      } finally {
        parserBusy = false;
        updateParser();
      }
    });
    async function savePresets(next, selected) {
      if (parserBusy || !parserSupported) return;
      parserBusy = true;
      updateParser();
      try {
        const cfg = await deps.api("PUT", "/v1/config", { parser_presets: next });
        fillParsers(cfg);
        parserPreset.value = selected;
        say(parserMessage, L("rules.preset_saved"), "ok");
      } catch (error) {
        say(parserMessage, errorText(lang, error), "err");
      } finally {
        parserBusy = false;
        updateParser();
      }
    }
    parserSavePreset.addEventListener("click", () => {
      const parsed = parserDraft(rules.value);
      const name = parserName.value.trim();
      if (!parsed.ok || !name) return;
      void savePresets([...parserPresets.filter((p) => p.name !== name), { name, rules: presetRules(parsed.rules) }], name);
    });
    parserRemovePreset.addEventListener("click", () => {
      const name = parserPreset.value;
      if (name) void savePresets(parserPresets.filter((p) => p.name !== name), "");
    });
    settingsView.append(el(
      "div",
      { class: "card" },
      el("h2", { text: L("rules.title") }),
      el("p", { class: "sub", text: L("rules.where") }),
      el(
        "details",
        {},
        el("summary", { text: L("rules.all_cards") }),
        parserActive,
        el("details", {}, el("summary", { text: L("rules.stored") }), parserStored)
      ),
      el(
        "details",
        {},
        el("summary", { text: L("rules.advanced") }),
        el("p", { class: "sub", text: L("rules.scope") }),
        field(L("rules.target"), parserTarget),
        parserCards,
        el("div", { class: "btns" }, parserPick, example),
        parserFile,
        field(L("rules.preset"), parserPreset),
        field(L("rules.draft"), rules),
        el("p", { class: "sub", text: L("rules.sub") }),
        field(L("rules.preset_name"), parserName),
        el("div", { class: "btns" }, parserSavePreset, parserRemovePreset),
        parserPreview,
        el("div", { class: "btns" }, parserApply, parserClear)
      ),
      parserMessage
    ));
    updateParser();
    const exportEmbeddings = el("input", { type: "checkbox" });
    const exportAll = el("button", { text: L("exp.all") });
    const exportMsg = el("div", { class: "msg" });
    exportAll.addEventListener("click", () => void exportTo(
      exportAll,
      exportMsg,
      `/v1/archive${exportEmbeddings.checked ? "?embeddings=true" : ""}`,
      "all"
    ));
    settingsView.append(el(
      "div",
      { class: "card", id: "nmos-backup" },
      el("h2", { text: L("exp.title") }),
      el("p", { class: "sub", text: L("exp.sub") }),
      el("div", { class: "check" }, exportEmbeddings, el("span", { text: L("exp.embeddings") })),
      el("div", { class: "btns" }, exportAll),
      exportMsg
    ));
    const restoreFile = el("input", { type: "file", accept: ".zip,application/zip", style: "display:none" });
    const restorePick = el("button", { text: L("rst.pick") });
    const restoreMsg = el("div", { class: "msg" });
    const restoreSummary = el("div", {});
    const restoreGo = el("button", { text: L("rst.restore"), style: "display:none" });
    const restoreCancel = el("button", { text: L("rst.cancel"), style: "display:none" });
    let restoreId = null;
    const restoreIdle = (id) => {
      restoreId = id;
      restorePick.disabled = false;
      restoreGo.style.display = restoreCancel.style.display = id ? "" : "none";
      restoreGo.disabled = restoreCancel.disabled = false;
    };
    restorePick.addEventListener("click", () => restoreFile.click());
    restoreFile.addEventListener("change", async () => {
      const file = restoreFile.files?.[0];
      restoreFile.value = "";
      if (!file) return;
      restoreSummary.replaceChildren();
      restoreIdle(null);
      if (!globalThis.crypto?.subtle) return say(restoreMsg, L("rst.insecure"), "err");
      restorePick.disabled = true;
      try {
        const up = await uploadArchive(deps.api, file, (sent, total) => say(restoreMsg, L("rst.uploading", {
          pct: total ? Math.floor(sent / total * 100) : 100,
          sent: (sent / 1048576).toFixed(1),
          total: (total / 1048576).toFixed(1)
        })));
        say(restoreMsg, L("rst.checking"));
        await deps.api("POST", `/v1/archive/uploads/${up.id}/check`, {});
        const view2 = await waitFor(deps.api, up.id, ["checked", "refused"]);
        if (view2.state === "refused" || !view2.summary) {
          say(restoreMsg, L("rst.refused", { why: view2.detail ?? "" }), "err");
          restoreIdle(null);
          return;
        }
        showSummary(view2.summary);
        const blocked = view2.summary.conversations.some((c) => c.here);
        say(restoreMsg, blocked ? L("rst.blocked") : "", blocked ? "err" : "muted");
        restoreIdle(up.id);
        restoreGo.disabled = blocked;
      } catch (error) {
        say(restoreMsg, errorText(lang, error), "err");
        restoreIdle(null);
      }
    });
    function showSummary(s) {
      const head = L("rst.summary", {
        scope: L(s.scope === "install" ? "rst.scope_install" : "rst.scope_chats"),
        n: s.conversations.length,
        version: s.nmos_version ?? "?",
        date: (s.created_at ?? "").slice(0, 10)
      });
      const list = el("ul", {}, ...s.conversations.map((c) => el("li", {
        text: `${c.character ?? L("rst.no_character")} \u2014 ${c.chat ?? `${L("rst.no_chat")} (${c.host_chat_ref.slice(0, 8)})`}` + (c.here ? ` (${L("rst.here")})` : "")
      })));
      restoreSummary.replaceChildren(
        el("p", { class: "sub", text: head }),
        list,
        ...s.settings_added.length ? [el("p", { class: "sub", text: L("rst.settings", {
          keys: s.settings_added.map((x) => x.value !== void 0 ? `${x.key} = ${String(x.value)}` : x.key).join(", ")
        }) })] : [],
        ...s.migrations.length ? [el("p", { class: "sub", text: L("rst.migrations", { list: s.migrations.join(", ") }) })] : []
      );
    }
    restoreGo.addEventListener("click", async () => {
      const id = restoreId;
      if (!id) return;
      restoreGo.disabled = restoreCancel.disabled = restorePick.disabled = true;
      say(restoreMsg, L("rst.restoring"));
      try {
        await deps.api("POST", `/v1/archive/uploads/${id}/restore`, {});
        const view2 = await waitFor(deps.api, id, ["restored", "failed"]);
        if (view2.state === "restored" && view2.result) {
          say(restoreMsg, L("rst.done", { n: view2.result.conversations.length, jobs: view2.result.queued_jobs ?? 0 }) + (view2.detail ? ` ${view2.detail}` : ""), "ok");
        } else {
          say(restoreMsg, L("rst.failed", { why: view2.detail ?? "" }), "err");
        }
        restoreSummary.replaceChildren();
      } catch (error) {
        say(restoreMsg, errorText(lang, error), "err");
      }
      restoreIdle(null);
    });
    restoreCancel.addEventListener("click", async () => {
      const id = restoreId;
      restoreIdle(null);
      restoreSummary.replaceChildren();
      say(restoreMsg, "");
      if (id) await deps.api("DELETE", `/v1/archive/uploads/${id}`).catch(() => void 0);
    });
    settingsView.append(el(
      "div",
      { class: "card" },
      el("h2", { text: L("rst.title") }),
      el("p", { class: "sub", text: L("rst.sub") }),
      el("div", { class: "btns" }, restorePick, restoreGo, restoreCancel),
      restoreFile,
      restoreSummary,
      restoreMsg
    ));
    const barText = el("span", { class: "text muted" });
    const revert = el("button", { text: L("revert") });
    const save = el("button", { class: "primary", text: L("save") });
    const bar = el("div", { class: "bar" }, barText, revert, save);
    root.append(bar);
    function values() {
      return {
        conn: {
          url: url.value,
          route: route.value,
          enabled: enabled.checked,
          reserved: reserved.value,
          deadline: deadline.value,
          token: token.value
        },
        llm: { ...llm.values(), ...extraValues() },
        emb: emb.values(),
        rerank: rerank.values(),
        tune: {
          threshold: threshold.value,
          minSim: minSim.value,
          embedWait: embedWait.value,
          topK: topK.value,
          facts: factsLimit.value,
          backfill: backfill.value,
          summaries: summaries.checked,
          canonFacts: canonFacts.checked,
          pinAt: pinAt.checked
        },
        trim: { on: trimOn.checked, keep: trimKeep.value }
      };
    }
    let baseline = values();
    let closing = false;
    const dirty = () => dirtySections(baseline, values());
    function update(message) {
      const d = dirty();
      syncTrimWarn();
      syncExtra();
      save.disabled = d.length === 0;
      revert.disabled = d.length === 0;
      if (message) say(barText, message.text, message.kind);
      else if (d.length) say(barText, L("unsaved", { s: d.map((s) => L(SECTION_TITLE[s])).join(", ") }), "warn");
      else say(barText, "", "muted");
    }
    settingsView.addEventListener("input", () => update());
    settingsView.addEventListener("change", () => update());
    async function loadConn() {
      url.value = await deps.getArg("sidecar_url") || "http://127.0.0.1:8790";
      route.value = await deps.getArg("route") || "auto";
      enabled.checked = Number(await deps.getArg("disabled")) !== 1;
      reserved.value = String(Number(await deps.getArg("reserved_memory_tokens")) || DEFAULT_RESERVED_TOKENS);
      deadline.value = String(Number(await deps.getArg("deadline_ms")) || DEFAULT_DEADLINE_MS);
      token.value = await deps.getArg("auth_token") || "";
      hudBox.checked = Number(await deps.getArg("hud")) === 1;
    }
    async function loadTrim() {
      const stored = trimArgs({
        on: Number(await deps.getArg("trim_old_turns")) === 1,
        keep: String(await deps.getArg("keep_recent_turns") ?? "")
      });
      trimOn.checked = stored.trim_old_turns === 1;
      trimKeep.value = String(stored.keep_recent_turns);
    }
    function fillServer(cfg) {
      install = cfg.install ?? null;
      llm.fill(cfg.llm);
      emb.fill(cfg.embeddings);
      rerank.fill(cfg.rerank);
      extraKnown = typeof cfg.llm.extra_body === "object" && cfg.llm.extra_body !== null;
      extraText.value = extraKnown ? showBody(cfg.llm.extra_body) : "";
      noTemp.checked = cfg.llm.no_temperature === true;
      threshold.value = String(cfg.recall.threshold);
      minSim.value = String(cfg.recall.vector_min_sim);
      embedWait.value = cfg.recall.embed_timeout_ms === void 0 ? "" : String(cfg.recall.embed_timeout_ms);
      embedWait.disabled = cfg.recall.embed_timeout_ms === void 0;
      topK.value = String(cfg.recall.top_k);
      factsLimit.value = String(cfg.recall.facts_limit);
      backfill.value = String(cfg.extraction.backfill);
      summaries.checked = cfg.extraction.summaries !== false;
      canonFacts.checked = cfg.extraction.canon_facts !== false;
      pinAtKnown = typeof cfg.recall.pin_at_mentions === "boolean";
      pinAt.checked = cfg.recall.pin_at_mentions === true;
      pinAt.disabled = !pinAtKnown;
      fillParsers(cfg);
    }
    async function loadAll() {
      await loadConn();
      await loadTrim();
      try {
        fillServer(await deps.api("GET", "/v1/config", void 0, 5e3));
      } catch {
      }
      baseline = values();
      update();
      void deps.api("GET", "/v1/conversations?host=pocketrisu", void 0, 5e3).then((chats) => {
        if (!Array.isArray(chats)) return;
        for (const c of chats) if (c.host_character_name?.trim()) knownCards.add(c.host_character_name.trim());
        parserCards.replaceChildren(...[...knownCards].sort().map((name) => el("option", { value: name })));
      }).catch(() => {
      });
    }
    const jobsOf = (q) => Object.values(q ?? {}).reduce((a, b) => a + b, 0);
    function askModelChange(p, turns) {
      return new Promise((resolve) => {
        const name = `nmos-model-change-${Date.now()}`;
        const carry = el("input", { type: "radio", name, value: "continue" });
        const redo = el("input", { type: "radio", name, value: "recent" });
        const canon = el("input", { type: "checkbox" });
        carry.checked = true;
        const extra = Math.max(0, (p.queued.canon?.canon ?? 0) - (p.queued.continue?.canon ?? 0));
        const go2 = el("button", { class: "primary", text: L("save") });
        const back = el("button", { text: L("cancel") });
        const done = (answer) => {
          bar.replaceChildren(barText, revert, save);
          resolve(answer);
        };
        go2.addEventListener("click", () => done({ mode: redo.checked ? "recent" : "continue", canon: canon.checked }));
        back.addEventListener("click", () => done(null));
        bar.replaceChildren(el(
          "div",
          { class: "model-change" },
          el("p", { text: L("mc.title") }),
          el("label", { class: "check" }, carry, el("span", { text: L("mc.continue", { n: jobsOf(p.queued.continue) }) })),
          el("label", { class: "check" }, redo, el("span", { text: L("mc.recent", { t: turns, n: jobsOf(p.queued.recent) }) })),
          el("label", { class: "check" }, canon, el("span", { text: L("mc.canon", { n: extra }) })),
          el("div", { class: "btns" }, back, go2)
        ));
      });
    }
    async function saveAll() {
      const d = dirty();
      if (!d.length) {
        update({ text: L("no_changes"), kind: "muted" });
        return true;
      }
      if (extraKnown && !bodyOf(extraText.value)) {
        update({ text: L("extra.invalid"), kind: "err" });
        return false;
      }
      save.disabled = true;
      say(barText, L("saving"));
      const v = values();
      let connSaved = 0;
      let connTotal = 0;
      let connComplete = !d.includes("conn");
      let trimComplete = !d.includes("trim");
      try {
        if (d.includes("trim")) {
          const args = trimArgs(v.trim);
          await deps.setArg("trim_old_turns", args.trim_old_turns);
          await deps.setArg("keep_recent_turns", args.keep_recent_turns);
          trimComplete = true;
          trimKeep.value = String(args.keep_recent_turns);
          baseline = { ...baseline, trim: values().trim };
          if (d.length === 1) {
            update({ text: L("saved"), kind: "ok" });
            return true;
          }
        }
        if (d.includes("conn")) {
          parserSupported = false;
          updateParser();
          const args = connArgs(v.conn);
          connTotal = Object.keys(args).length;
          for (const [k, value] of Object.entries(args)) {
            await deps.setArg(k, value);
            connSaved += 1;
          }
          connComplete = true;
          reserved.value = String(args.reserved_memory_tokens);
          deadline.value = String(args.deadline_ms);
          baseline = { ...baseline, conn: values().conn };
        }
        const body = configBody(d, v, { pinAt: pinAtKnown, rerank: rerankKnown }, baseline);
        const tight = (d.includes("tune") || d.includes("conn")) && embedWaitTooLong(v.tune.embedWait, v.conn.deadline) ? ` ${L("tune.embed_wait_tight", { w: v.tune.embedWait.trim(), d: v.conn.deadline.trim() || String(DEFAULT_DEADLINE_MS) })}` : "";
        if (!Object.keys(body).length) {
          fillServer(await deps.api("GET", "/v1/config", void 0, 5e3));
          baseline = values();
          update({ text: L("saved") + tight, kind: tight ? "warn" : "ok" });
          return true;
        }
        const modelChanged = d.includes("llm") && modelChange(baseline, v);
        if (modelChanged) {
          const p = await deps.api("POST", "/v1/config/preview", body, 1e4).catch(() => null);
          if (p?.model_change) {
            const answer = await askModelChange(p, v.tune.backfill.trim() || backfill.value);
            if (!answer) {
              update({ text: L("mc.cancelled"), kind: "muted" });
              return false;
            }
            body.on_model_change = answer;
          }
        }
        const r = await deps.api("PUT", "/v1/config", body);
        fillServer(r);
        baseline = values();
        const parts = [r.queued_jobs ? L("saved_queued", { n: r.queued_jobs }) : L("saved")];
        if (r.queued_jobs) deps.hud.background();
        update({ text: parts.join(" ") + tight, kind: tight ? "warn" : "ok" });
        return true;
      } catch (error) {
        const text2 = errorText(lang, error);
        update({ text: !trimComplete ? text2 : !connComplete ? L("conn_save_failed", { n: connSaved, total: connTotal, e: text2 }) : d.includes("conn") ? L("conn_saved_server_failed", { e: text2 }) : text2, kind: "err" });
        return false;
      }
    }
    save.addEventListener("click", () => void saveAll());
    revert.addEventListener("click", () => void loadAll());
    let onDocClick = null;
    let onDocKey = null;
    function shut() {
      if (onDocClick) document.removeEventListener("click", onDocClick);
      if (onDocKey) document.removeEventListener("keydown", onDocKey);
      root.remove();
      current = null;
      void deps.hide();
    }
    close.addEventListener("click", () => {
      if (closing) return;
      if (!dirty().length && !parserDirty()) return shut();
      closing = true;
      const saveClose = el("button", { class: "primary", text: L("save_and_close") });
      const discard = el("button", { text: L("discard_and_close") });
      const cancel = el("button", { text: L("cancel") });
      const restore2 = (refresh = true) => {
        closing = false;
        bar.replaceChildren(barText, revert, save);
        if (refresh) update();
      };
      saveClose.addEventListener("click", async () => {
        saveClose.disabled = true;
        if (await saveAll()) shut();
        else restore2(false);
      });
      discard.addEventListener("click", shut);
      cancel.addEventListener("click", () => restore2());
      select("settings");
      bar.replaceChildren(
        el("span", { class: "text warn", text: L(parserDirty() ? "rules.close_draft" : "close_unsaved") }),
        cancel,
        discard,
        ...parserDirty() ? [] : [saveClose]
      );
    });
    language.addEventListener("change", async () => {
      if (dirty().length || parserDirty()) {
        language.value = lang;
        select("settings");
        update({ text: L("lang_unsaved"), kind: "warn" });
        return;
      }
      const next = langOf(language.value);
      await deps.setArg("language", next);
      if (onDocClick) document.removeEventListener("click", onDocClick);
      if (onDocKey) document.removeEventListener("keydown", onDocKey);
      root.remove();
      current = await render(deps, next, shown);
    });
    let activePrimary = "home";
    let activeMemSub = "story";
    let activeChatId = null;
    let activeChatName = "";
    let attentionCount = 0;
    let lastMeta = null;
    let knownChats = [];
    let chatPopOpen = false;
    let currentGroup = "chat";
    const navButtons = /* @__PURE__ */ new Map();
    const attnBadges = [];
    let chatBtnLabel = null;
    let chatPop = null;
    let chatSearchInput = null;
    let chatListEl = null;
    let statusPill = null;
    function setPrimaryNav(next) {
      activePrimary = next;
      for (const [k, btns] of navButtons.entries()) {
        for (const b of btns) b.classList.toggle("on", k === next);
      }
    }
    function updateAttentionBadges(n) {
      attentionCount = Math.max(0, n);
      for (const badge of attnBadges) {
        badge.textContent = attentionCount > 99 ? "99+" : String(attentionCount);
        badge.style.display = attentionCount > 0 ? "" : "none";
      }
      const subBadge = memSubBar.querySelector(".mem-attn-badge");
      if (subBadge) {
        subBadge.textContent = String(attentionCount);
        subBadge.style.display = attentionCount > 0 ? "" : "none";
      }
    }
    function updateChatLabel() {
      if (!chatBtnLabel) return;
      chatBtnLabel.textContent = activeChatName || L("shell.no_chat");
    }
    function updateStatusPill(s, meta) {
      if (!statusPill) return;
      let kind = "";
      let key = "shell.status_ok";
      if (s && !s.connected) {
        kind = "err";
        key = "shell.status_err";
      } else if (s && !s.enabled) {
        kind = "";
        key = "shell.status_off";
      } else if (meta?.working?.state === "failed" || (meta?.working?.failed ?? 0) > 0) {
        kind = "err";
        key = "shell.status_warn";
      } else if (meta?.working?.state === "working" || (meta?.working?.queued ?? 0) > 0) {
        kind = "warn";
        key = "shell.status_working";
      } else if ((meta?.attention ?? attentionCount) > 0) {
        kind = "warn";
        key = "shell.status_warn";
      } else {
        kind = "ok";
        key = "shell.status_ok";
      }
      statusPill.className = `status-pill${kind ? ` ${kind}` : ""}`;
      statusPill.replaceChildren(
        el("span", { class: `dot${kind ? ` ${kind}` : ""}` }),
        el("span", { class: "st-txt", text: L(key) })
      );
    }
    function applyHubMeta(meta) {
      if (!meta) return;
      lastMeta = meta;
      if (meta.conv) {
        activeChatId = meta.conv.id;
        activeChatName = meta.conv.name;
        updateChatLabel();
      }
      if (typeof meta.attention === "number") updateAttentionBadges(meta.attention);
      if (Array.isArray(meta.chats) && meta.chats.length) knownChats = meta.chats;
      void deps.status().then((s) => updateStatusPill(s, meta)).catch(() => updateStatusPill(null, meta));
    }
    function renderChatOptions(filter = "") {
      if (!chatListEl) return;
      const q = filter.trim().toLowerCase();
      const items = knownChats.filter((c) => !q || c.name.toLowerCase().includes(q) || (c.character ?? "").toLowerCase().includes(q) || (c.title ?? "").toLowerCase().includes(q));
      if (!items.length) {
        chatListEl.replaceChildren(el("div", { class: "muted", style: "padding:8px;font-size:13px", text: L("shell.chats_empty") }));
        return;
      }
      chatListEl.replaceChildren(...items.map((c) => {
        const isActive2 = c.id === (activeChatId ?? hubConversation);
        const opt = el(
          "button",
          { class: `chat-opt${isActive2 ? " on" : ""}`, "data-chat-id": c.id },
          el("span", { style: "overflow:hidden;text-overflow:ellipsis;white-space:nowrap", text: c.name }),
          el("span", { class: "chat-meta", text: typeof c.turns === "number" ? `${c.turns}t` : isActive2 ? "\u2713" : "" })
        );
        opt.addEventListener("click", () => {
          closeChatPop();
          void switchActiveChat(c);
        });
        return opt;
      }));
    }
    function closeChatPop() {
      chatPopOpen = false;
      if (chatPop) chatPop.style.display = "none";
    }
    async function openChatPop() {
      if (!chatPop) return;
      chatPopOpen = !chatPopOpen;
      chatPop.style.display = chatPopOpen ? "" : "none";
      if (!chatPopOpen) return;
      renderChatOptions(chatSearchInput?.value ?? "");
      chatSearchInput?.focus();
      try {
        const rows = await deps.api(
          "GET",
          "/v1/conversations?host=pocketrisu",
          void 0,
          5e3
        );
        if (Array.isArray(rows) && rows.length) {
          knownChats = rows.map((r) => {
            const ch = (r.host_character_name ?? "").trim();
            const ti = (r.title ?? "").trim();
            const name = ch && ti && ti !== ch ? `${ch} \xB7 ${ti}` : ch || ti || r.id.slice(0, 8);
            return { id: r.id, name, character: ch, title: ti, turns: typeof r.message_count === "number" ? r.message_count : void 0 };
          });
          const cur = knownChats.find((c) => c.id === (activeChatId ?? hubConversation));
          if (cur && !activeChatName) {
            activeChatName = cur.name;
            updateChatLabel();
          }
          if (chatPopOpen) renderChatOptions(chatSearchInput?.value ?? "");
        }
      } catch {
      }
    }
    async function switchActiveChat(chat) {
      activeChatId = chat.id;
      hubConversation = chat.id;
      activeChatName = chat.name;
      updateChatLabel();
      if (activePrimary === "home") {
        visited.length = 0;
        const base = await hubPath(chat.id);
        inspectorPath = base;
        void showInspector(base);
      } else if (activePrimary === "memory") {
        openMemorySub(activeMemSub, false);
      } else if (activePrimary === "notes") {
        notesFor = null;
        openNotesStudio(chat.id);
      } else if (activePrimary === "settings" && currentGroup === "chat") {
        showChatPage();
      }
    }
    let quickRound = 0;
    async function refreshHomeQuick() {
      if (!viewsOn) return;
      const round = ++quickRound;
      const items = [];
      let s = null;
      try {
        s = await deps.status();
      } catch {
        s = null;
      }
      if (round !== quickRound) return;
      updateStatusPill(s, lastMeta);
      try {
        const state = await deps.chat.current();
        if (round !== quickRound) return;
        if (state.id !== null) {
          const id = state.id;
          const off = state.off;
          const allOff = s ? !s.enabled : false;
          const flip = el("button", { class: off ? "primary" : "", text: L(off ? "chat.turn_on" : "chat.turn_off") });
          const msg = el("div", { class: "msg" });
          flip.addEventListener("click", async () => {
            flip.disabled = true;
            try {
              await deps.chat.set(id, !off);
              const nextHub = await hubPath(activeChatId ?? void 0);
              inspectorPath = nextHub;
              void showInspector(nextHub);
              void refreshHomeQuick();
            } catch (error) {
              flip.disabled = false;
              say(msg, errorText(lang, error), "err");
            }
          });
          const badgeText = allOff ? L("home.all_off_badge") : L(off ? "home.chat_off_badge" : "home.chat_on_badge");
          const strip = el(
            "div",
            { class: `chat-strip${off || allOff ? " off" : ""}` },
            el(
              "div",
              { class: "chat-strip-info" },
              el("span", { class: `dot ${off || allOff ? "warn" : "ok"}` }),
              el(
                "div",
                {},
                el("div", { class: "chat-strip-title", text: `${L("chat.title")} \xB7 ${badgeText}` }),
                el("div", { class: "chat-strip-sub", text: allOff ? L("chat.all_off") : L(off ? "chat.off_sub" : "chat.on_sub") })
              )
            ),
            flip
          );
          items.push(strip);
          if (msg.textContent) items.push(msg);
        }
      } catch {
      }
      if (s) {
        if (s.insecure) {
          items.unshift(el("div", { class: "adv-card err" }, el("div", {}, el("b", { class: "err", text: L("status.insecure") }))));
        }
        const advice = deadlineAdvice(s.last);
        if (advice) {
          const open = el("button", { class: "mini", text: L("deadline.open_settings") });
          open.addEventListener("click", () => {
            selectPrimary("settings");
            openGroup("connection");
          });
          const took = advice.tookMs === null ? "" : L("deadline.took", { n: formatMs(advice.tookMs) });
          const text2 = advice.level === "over" ? L("deadline.over", { d: formatMs(advice.deadlineMs), took, s: formatMs(advice.suggestMs) }) : L("deadline.near", { d: formatMs(advice.deadlineMs), n: formatMs(advice.tookMs ?? 0), s: formatMs(advice.suggestMs) });
          items.push(el(
            "div",
            { class: `adv-card${advice.level === "over" ? " err" : ""}` },
            el(
              "div",
              {},
              el("b", { class: advice.level === "over" ? "err" : "warn", text: L(`deadline.${advice.level}.title`) }),
              el("p", { text: text2 })
            ),
            open
          ));
        }
        const curTokens = Number(await deps.getArg("reserved_memory_tokens")) || DEFAULT_RESERVED_TOKENS;
        if (round !== quickRound) return;
        const budget = budgetAdvice(s.last, curTokens);
        if (budget) {
          const apply = el("button", { class: "primary mini", text: L("budget.apply", { n: budget.suggest }) });
          const bmsg = el("div", { class: "msg" });
          apply.addEventListener("click", async () => {
            apply.disabled = true;
            try {
              await deps.setArg("reserved_memory_tokens", budget.suggest);
              say(bmsg, L("budget.applied", { n: budget.suggest, d: budget.suggest - curTokens }), "ok");
            } catch (error) {
              apply.disabled = false;
              say(bmsg, errorText(lang, error), "err");
            }
          });
          const text2 = L(budget.all ? "budget.text" : "budget.text_more", {
            m: budget.offered,
            c: budget.cut,
            b: budget.budget,
            s: budget.suggest,
            d: budget.suggest - curTokens
          });
          items.push(el(
            "div",
            { class: "adv-card" },
            el("div", {}, el("b", { class: "warn", text: L("budget.title", { c: budget.cut }) }), el("p", { text: text2 }), bmsg),
            apply
          ));
        }
        if (s.last?.vectors === "fallback") {
          items.push(el(
            "div",
            { class: "adv-card" },
            el("div", {}, el("b", { class: "warn", text: L("vectors.title") }), el("p", { text: L("vectors.text") }))
          ));
        }
      }
      homeQuickBar.replaceChildren(...items);
    }
    function renderMemSubBar(sub, rawMode = false) {
      activeMemSub = sub;
      const defs = [
        { key: "story", label: "mem.story", ic: "book" },
        { key: "map", label: "mem.map", ic: "map", hide: !mapOn },
        { key: "attention", label: "mem.attention", ic: "alert" },
        { key: "diag", label: "mem.diag", ic: "terminal" }
      ];
      const tabsRow = el("div", { class: "mem-subtabs" });
      for (const d of defs) {
        if (d.hide) continue;
        const children = [icon(d.ic, 14), L(d.label)];
        if (d.key === "attention") {
          const badge = el("span", {
            class: "nav-badge mem-attn-badge",
            text: String(attentionCount),
            style: attentionCount > 0 ? "" : "display:none"
          });
          children.push(badge);
        }
        const btn = el("button", { class: sub === d.key ? "on" : "", "data-memsub": d.key }, ...children);
        btn.addEventListener("click", () => openMemorySub(d.key));
        tabsRow.append(btn);
      }
      const subHead = el(
        "div",
        { class: "mem-subhead" },
        el("p", { class: "mem-subtext", text: L(`mem.${sub}_sub`) })
      );
      if (sub === "diag") {
        const cid = activeChatId ?? hubConversation;
        const bWork = el("button", { class: !rawMode ? "on" : "", text: L("mem.diag_working") });
        const bRaw = el("button", { class: rawMode ? "on" : "", text: L("mem.diag_raw") });
        bWork.addEventListener("click", () => {
          if (cid) go(`/v1/views/c/${cid}/working`);
        });
        bRaw.addEventListener("click", () => {
          if (cid) go(`/v1/inspector/c/${cid}`);
        });
        subHead.append(el("div", { class: "diag-toggle" }, bWork, bRaw));
      }
      memSubBar.replaceChildren(tabsRow, subHead);
    }
    function openMemorySub(sub, pushHistory = true) {
      activeMemSub = sub;
      const cid = activeChatId ?? hubConversation;
      notesStudioView.style.display = "none";
      settingsView.style.display = "none";
      statusView.style.display = "none";
      inspectorView.style.display = "";
      bar.style.display = "none";
      shown = "inspector";
      root.classList.add("wide");
      setPrimaryNav("memory");
      homeQuickBar.style.display = "none";
      memSubBar.style.display = "";
      renderMemSubBar(sub, false);
      if (!cid) {
        inspbar.style.display = "none";
        inspectorBody.replaceChildren(el("div", { class: "card muted", text: L("mem.no_chat") }));
        return;
      }
      const target = sub === "story" ? `/v1/views/c/${cid}/memory` : sub === "map" ? `/v1/views/c/${cid}/map` : sub === "attention" ? `/v1/inspector/c/${cid}` : `/v1/views/c/${cid}/working`;
      const section = sub === "attention" ? "s-attention" : null;
      if (pushHistory) go(target, section);
      else {
        pendingSection = section;
        void showInspector(target);
      }
    }
    function openNotesStudio(conversation) {
      const cid = conversation ?? activeChatId ?? hubConversation;
      inspectorView.style.display = "none";
      settingsView.style.display = "none";
      statusView.style.display = "none";
      notesStudioView.style.display = "";
      bar.style.display = "none";
      root.classList.add("wide");
      setPrimaryNav("notes");
      if (!cid) {
        notesStudioView.replaceChildren(el("div", { class: "card muted", text: L("notes.no_chat") }));
        return;
      }
      if (notesFor !== cid || !notesStudioView.childElementCount) {
        buildNotes(cid, notesStudioView, true);
      }
    }
    function syncShellForPath(path) {
      if (!viewsOn) return;
      if (path.startsWith("/v1/views/hub")) {
        setPrimaryNav("home");
        homeQuickBar.style.display = "";
        memSubBar.style.display = "none";
        inspbar.style.display = visited.length ? "" : "none";
        void refreshHomeQuick();
        return;
      }
      if (path.startsWith("/v1/views/chats")) {
        setPrimaryNav("home");
        homeQuickBar.style.display = "none";
        memSubBar.style.display = "none";
        inspbar.style.display = "";
        return;
      }
      homeQuickBar.style.display = "none";
      if (shown !== "inspector") return;
      setPrimaryNav("memory");
      memSubBar.style.display = "";
      const isPerson = /\/(person|e)\//.test(path);
      inspbar.style.display = visited.length || isPerson ? "" : "none";
      if (path.includes("/memory")) renderMemSubBar("story", false);
      else if (path.includes("/map")) renderMemSubBar("map", false);
      else if (path.includes("/working")) renderMemSubBar("diag", false);
      else if (path.startsWith("/v1/inspector/c/")) {
        const isAttn = pendingSection === "s-attention" || activeMemSub === "attention";
        renderMemSubBar(isAttn ? "attention" : "diag", !isAttn);
      } else {
        renderMemSubBar(activeMemSub, false);
      }
    }
    function selectPrimary(next) {
      if (!viewsOn) {
        select(next === "settings" ? "settings" : next === "home" ? "status" : "inspector");
        return;
      }
      closeChatPop();
      if (next === "home") {
        void goHome();
        return;
      }
      if (next === "memory") {
        openMemorySub(activeMemSub);
        return;
      }
      if (next === "notes") {
        openNotesStudio(activeChatId ?? hubConversation);
        return;
      }
      select("settings");
    }
    function buildShell() {
      root.classList.add("shell-on");
      legacyHeader.style.display = "none";
      tabs.style.display = "none";
      const brand = el(
        "button",
        { class: "nmos-brand", "aria-label": L("nav.home") },
        el("span", { class: "nmos-logo" }, icon("brand", 18)),
        el("span", { text: "NMOS" })
      );
      brand.addEventListener("click", () => selectPrimary("home"));
      chatBtnLabel = el("span", { class: "chat-lbl", text: L("shell.no_chat") });
      const chatBtn = el(
        "button",
        { class: "chat-btn", "aria-label": L("shell.switch_chat") },
        icon("chat", 14),
        chatBtnLabel,
        icon("chevronDown", 14)
      );
      chatSearchInput = el("input", { type: "search", placeholder: L("shell.search_chat"), "aria-label": L("shell.search_chat") });
      chatSearchInput.addEventListener("input", () => renderChatOptions(chatSearchInput?.value ?? ""));
      chatListEl = el("div", { class: "chat-list" });
      const allChatsBtn = el("button", { class: "mini ghost", text: L("shell.chats_all") });
      allChatsBtn.addEventListener("click", () => {
        closeChatPop();
        notesStudioView.style.display = "none";
        settingsView.style.display = "none";
        statusView.style.display = "none";
        inspectorView.style.display = "";
        bar.style.display = "none";
        shown = "inspector";
        go("/v1/views/chats");
      });
      chatPop = el(
        "div",
        { class: "chat-pop", style: "display:none" },
        chatSearchInput,
        chatListEl,
        el("div", { class: "chat-pop-foot" }, allChatsBtn)
      );
      const chatPicker = el("div", { class: "chat-picker" }, chatBtn, chatPop);
      chatBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        void openChatPop();
      });
      chatPop.addEventListener("click", (e) => e.stopPropagation());
      const makeNavBtn = (key, ic, labelKey, mobile = false) => {
        const children = [icon(ic, mobile ? 18 : 15), el("span", { text: L(labelKey) })];
        if (key === "memory") {
          const badge = el("span", { class: "nav-badge", text: "0", style: "display:none" });
          attnBadges.push(badge);
          children.push(badge);
        }
        const btn = el("button", { "data-nav": key }, ...children);
        btn.addEventListener("click", () => selectPrimary(key));
        const list = navButtons.get(key) ?? [];
        list.push(btn);
        navButtons.set(key, list);
        return btn;
      };
      const topNav = el(
        "nav",
        { class: "nmos-nav", "aria-label": "NMOS" },
        makeNavBtn("home", "home", "nav.home"),
        makeNavBtn("memory", "book", "nav.memory"),
        makeNavBtn("notes", "feather", "nav.notes"),
        makeNavBtn("settings", "sliders", "nav.settings")
      );
      const bottomNav = el(
        "nav",
        { class: "nmos-bottomnav", "aria-label": "NMOS" },
        makeNavBtn("home", "home", "nav.home", true),
        makeNavBtn("memory", "book", "nav.memory", true),
        makeNavBtn("notes", "feather", "nav.notes", true),
        makeNavBtn("settings", "sliders", "nav.settings", true)
      );
      statusPill = el("span", { class: "status-pill" }, el("span", { class: "dot" }), el("span", { class: "st-txt", text: L("shell.status_ok") }));
      close.className = "nmos-close ghost";
      close.replaceChildren(icon("close", 16));
      close.setAttribute("aria-label", L("close"));
      close.setAttribute("title", L("close"));
      const topbar = el(
        "div",
        { class: "nmos-topbar" },
        el(
          "div",
          { class: "nmos-topbar-in" },
          brand,
          chatPicker,
          topNav,
          el("div", { class: "nmos-top-right" }, statusPill, language, close)
        )
      );
      root.prepend(topbar);
      root.append(bottomNav);
      onDocClick = () => {
        if (chatPopOpen) closeChatPop();
      };
      onDocKey = (e) => {
        if (e.key === "Escape" && chatPopOpen) closeChatPop();
      };
      document.addEventListener("click", onDocClick);
      document.addEventListener("keydown", onDocKey);
    }
    function select(next) {
      shown = next;
      notesStudioView.style.display = "none";
      if (viewsOn && next === "settings") {
        setPrimaryNav("settings");
        openGroup(currentGroup);
      }
      const views = [
        ["status", statusView, tabStatus],
        ["inspector", inspectorView, tabInspector],
        ["settings", settingsView, tabSettings]
      ];
      for (const [name, view2, button] of views) {
        view2.style.display = name === next ? "" : "none";
        button.className = name === next ? "on" : "";
      }
      bar.style.display = next === "settings" ? "" : "none";
      root.classList.toggle("wide", viewsOn || next === "inspector");
      if (next === "status") void refreshStatus();
      if (next === "inspector") void showInspector();
    }
    tabStatus.addEventListener("click", () => select("status"));
    tabInspector.addEventListener("click", () => select("inspector"));
    tabSettings.addEventListener("click", () => select("settings"));
    function doAct(act) {
      if (act === "settings" || act === "backup") {
        if (act === "backup") currentGroup = "backup";
        select("settings");
        if (act === "backup") openGroup("backup");
        return;
      }
      if (act === "retry") return void retryFrom(inspectorConversation(inspectorPath));
      if (act === "notes") {
        const cid = activeChatId ?? hubConversation;
        if (viewsOn) {
          openNotesStudio(cid);
        } else if (cid) {
          notesCard.replaceChildren();
          buildNotes(cid);
          notesCard.style.display = "";
          notesCard.scrollIntoView({ block: "start" });
        }
      }
    }
    async function goHome() {
      visited.length = 0;
      inspectorPath = await hubPath();
      select("inspector");
    }
    const GROUPS = ["chat", "connection", "models", "memory", "rules", "display", "backup"];
    const GROUP_ICONS = {
      chat: "chat",
      connection: "plug",
      models: "cpu",
      memory: "database",
      rules: "shield",
      display: "eye",
      backup: "archive"
    };
    const groupList = el("div", { class: "groups" });
    const settingsPane = el("div", { class: "settings-pane" });
    const settingsShell = el("div", { class: "settings-shell" }, groupList, settingsPane);
    const chatPage = el("div", { "data-group": "chat", style: "display:none" });
    const legacyActionBtns = actions.firstElementChild;
    function restoreLegacyActions() {
      if (historyButton.parentElement !== legacyActionBtns) {
        legacyActionBtns.replaceChildren(retryButton, historyButton, rebuildButton, exportButton, notesButton, deleteButton);
      }
    }
    function groupSettings() {
      const byTitle = {
        [L("hud.title")]: "display",
        [L("conn.title")]: "connection",
        [L("llm.title")]: "models",
        [L("emb.title")]: "models",
        [L("rerank.title")]: "models",
        [L("tune.title")]: "memory",
        [L("trimset.title")]: "memory",
        [L("rules.title")]: "rules",
        [L("exp.title")]: "backup",
        [L("rst.title")]: "backup"
      };
      const existingCards = Array.from(settingsView.children);
      for (const card of existingCards) {
        const group = byTitle[card.querySelector("h2")?.textContent ?? ""];
        if (group) card.dataset.group = group;
      }
      statusView.dataset.group = "connection";
      settingsPane.replaceChildren(chatPage, statusView, ...existingCards);
      settingsView.replaceChildren(settingsShell);
      const makeGroupBtn = (g) => {
        const b = el(
          "button",
          { class: "group", "data-group": g },
          icon(GROUP_ICONS[g], 16),
          el(
            "span",
            { class: "grp-txt" },
            el("b", { text: L(`grp.${g}`) }),
            el("span", { class: "sub", text: L(`grp.${g}_sub`) })
          )
        );
        b.addEventListener("click", () => openGroup(g));
        return b;
      };
      groupList.replaceChildren(
        el("div", { class: "grp-label", text: L("set.scope_chat") }),
        makeGroupBtn("chat"),
        el("div", { class: "grp-label", text: L("set.scope_global") }),
        ...GROUPS.filter((g) => g !== "chat").map(makeGroupBtn)
      );
    }
    function pages() {
      return Array.from(settingsPane.children).filter((x) => x instanceof HTMLElement && "group" in x.dataset);
    }
    function openGroup(group) {
      currentGroup = group;
      for (const btn of Array.from(groupList.querySelectorAll("button[data-group]"))) {
        btn.classList.toggle("on", btn.dataset.group === group);
      }
      for (const page of pages()) {
        page.style.display = page.dataset.group === group && (page !== rerankCard || rerankKnown) ? "" : "none";
      }
      if (group === "connection") void refreshStatus();
      if (group === "chat") showChatPage();
    }
    function showChatPage() {
      const cid = activeChatId ?? hubConversation;
      if (!cid) {
        chatPage.replaceChildren(el("div", { class: "card muted", text: L("grp.chat_none") }));
        return;
      }
      actionConversation = cid;
      disarm();
      const switchSlot = el("div");
      void deps.status().then((s) => chatCard(s.enabled, s.connected)).then((card) => {
        if (switchSlot.isConnected) switchSlot.replaceChildren(card);
      }).catch(() => {
      });
      const maintRow = (titleText, desc, badgeKey, badgeCls, btn, danger = false) => el(
        "div",
        { class: `maint-row${danger ? " danger-row" : ""}` },
        el(
          "div",
          { class: "maint-info" },
          el("div", { class: "maint-title" }, el("span", { text: titleText }), el("span", { class: `badge ${badgeCls}`, text: L(badgeKey) })),
          el("div", { class: "maint-desc", text: L(desc) })
        ),
        btn
      );
      const maintRows = [];
      if (retryButton.style.display !== "none") {
        maintRows.push(maintRow(L("act.retry"), "set.act_retry_desc", "set.badge_llm", "b-llm", retryButton));
      }
      maintRows.push(
        maintRow(L("act.history"), "set.act_history_desc", "set.badge_llm", "b-llm", historyButton),
        maintRow(L("act.rebuild"), "set.act_rebuild_desc", "set.badge_warn", "b-warn", rebuildButton),
        maintRow(L("exp.chat"), "set.act_export_desc", "set.badge_local", "b-free", exportButton),
        maintRow(L("act.delete"), "set.act_delete_desc", "set.badge_danger", "b-danger", deleteButton, true)
      );
      const maintCard = el(
        "div",
        { class: "card" },
        el("h2", { text: L("set.maint_title") }),
        el("p", { class: "sub", text: L("set.maint_sub") }),
        el("div", { class: "maint-list" }, ...maintRows),
        actionMsg
      );
      const pinsCard = el("div", { class: "card" }, el("h2", { text: L("pins.title") }), el("p", { class: "sub", text: L("pin.sub") }));
      const carryCard = el("div", { class: "card", style: "display:none" });
      chatPage.replaceChildren(switchSlot, modeCard, statusCard, pinsCard, carryCard, maintCard);
      void showPins(cid, pinsCard);
      void showCarry(cid, carryCard);
      void showMode(cid, loads);
      void showStatusWindows(cid, loads);
    }
    async function showCarry(conversation, card, said) {
      const carryHead = () => [
        el("h2", { text: L("carry.title") }),
        el("p", { class: "sub", text: L("carry.sub") }),
        el("p", { class: "sub", text: L("carry.policy_note") })
      ];
      let state;
      try {
        const res = await deps.api("GET", `/v1/conversations/${conversation}/carry`, void 0, 15e3);
        if (!res || typeof res !== "object" || !("in_force" in res)) {
          card.style.display = "none";
          card.replaceChildren();
          return;
        }
        state = res;
      } catch (error) {
        if (!card.isConnected || actionConversation !== conversation) return;
        if (isCarryNotFound(error)) {
          card.style.display = "none";
          card.replaceChildren();
          return;
        }
        const errMsg = el("div", { class: "msg", role: "status" });
        say(errMsg, carryErrorText(lang, error, errorText), "err");
        card.replaceChildren(...carryHead(), errMsg);
        card.style.display = "";
        return;
      }
      if (!card.isConnected || actionConversation !== conversation) return;
      const msg = el("div", { class: "msg", role: "status" });
      if (said) say(msg, L(said), "ok");
      const previewSpot = el("div");
      const carryCharacters = (rows) => rows.filter((e) => e && e.type === "character" && !e.persona && e.excluded !== "memory" && typeof e.name === "string").map((e, i) => ({ name: String(e.name), mentions: Number(e.mentions) || 0, i })).sort((a, b) => b.mentions - a.mentions || a.i - b.i).map((e) => e.name);
      async function openPreview(trigger, req, changed = false) {
        const round = nextRound(previewSpot);
        say(msg, "");
        trigger.disabled = true;
        const discover = req.mode === "regression" && req.entity_names.length === 0;
        const body = {
          source_conversation_id: req.source_conversation_id,
          mode: discover ? "continue" : req.mode,
          entity_names: discover ? [] : [...req.entity_names],
          cutoff_turn: req.cutoff_turn
        };
        let first = null;
        let chars = [];
        try {
          first = await deps.api("POST", `/v1/conversations/${conversation}/carry/preview`, body, 15e3);
          chars = first.characters ?? [];
        } catch (error) {
          if (previewRound.get(previewSpot) !== round) return;
          const refused = () => {
            say(msg, carryErrorText(lang, error, errorText), "err");
            trigger.disabled = false;
          };
          if (!discover || !carryRefusal(error instanceof Error ? error.message : String(error))) {
            refused();
            return;
          }
          let rows;
          try {
            rows = await deps.api("GET", `/v1/conversations/${req.source_conversation_id}/entities`, void 0, 15e3);
          } catch {
            rows = null;
          }
          if (previewRound.get(previewSpot) !== round) return;
          if (!Array.isArray(rows)) {
            refused();
            return;
          }
          chars = carryCharacters(rows);
        }
        if (previewRound.get(previewSpot) !== round) return;
        let active = discover ? null : first;
        let pickedNames = discover ? [] : [...req.entity_names];
        const detailsSpot = el("div");
        const ok = el("button", { class: "primary", text: L("carry.link_btn") });
        const cancel = el("button", { text: L("cancel") });
        ok.disabled = active === null;
        function renderDetails(pv, loading = false) {
          if (loading) {
            detailsSpot.replaceChildren(el("div", { class: "muted", text: L("carry.loading") }));
            return;
          }
          if (!pv) {
            const hint = chars.length ? L("carry.pv_chars_pick") : L("carry.pv_chars_none");
            detailsSpot.replaceChildren(el("div", { class: "muted", text: hint }));
            return;
          }
          const modeText = L(pv.mode === "regression" ? "carry.mode_regression" : "carry.mode_continue");
          const headLine = L("carry.pv_source", {
            source: carrySourceLabel(pv.source),
            mode: modeText,
            cutoff: carryCutoffLabel(lang, pv.cutoff.turn)
          });
          const items = [
            el("div", { text: headLine }),
            el("div", { text: carryCountsLine(lang, pv.counts) })
          ];
          if (pv.first_lines.length) {
            items.push(
              el("div", { class: "muted", style: "margin-top:6px", text: L("carry.pv_lines") }),
              ...pv.first_lines.map((line) => el("div", { text: `\xB7 ${line}` }))
            );
          } else {
            items.push(el("div", { class: "muted", text: L("carry.pv_lines_empty") }));
          }
          if (pv.replaces) items.push(el("div", { class: "warn", style: "margin-top:6px", text: L("carry.pv_replaces") }));
          detailsSpot.replaceChildren(...items);
        }
        const box = el("div", { class: "preview" }, el("b", { text: L("carry.pv_title") }));
        if (changed) box.append(el("div", { class: "warn", text: L("carry.changed") }));
        if (req.mode === "regression") {
          const allChars = [...chars, ...pickedNames.filter((n) => !chars.includes(n))];
          box.append(el("div", { style: "margin-top:6px;font-weight:500", text: L("carry.pv_chars") }));
          if (allChars.length) {
            const boxes = [];
            const syncCap = () => {
              const count2 = boxes.filter((b) => b.checked).length;
              for (const b of boxes) b.disabled = !b.checked && count2 >= CARRY_MAX_NAMES;
            };
            const charList = el("div", { class: "pins" }, ...allChars.map((name) => {
              const cb = el("input", { type: "checkbox", value: name });
              cb.checked = pickedNames.includes(name);
              boxes.push(cb);
              cb.addEventListener("change", async () => {
                syncCap();
                const chosen2 = boxes.filter((b) => b.checked).map((b) => b.value);
                pickedNames = chosen2;
                say(msg, "");
                if (chosen2.length === 0) {
                  nextRound(previewSpot);
                  active = null;
                  ok.disabled = true;
                  renderDetails(null);
                  return;
                }
                const subRound = nextRound(previewSpot);
                active = null;
                ok.disabled = true;
                renderDetails(null, true);
                try {
                  const pv = await deps.api("POST", `/v1/conversations/${conversation}/carry/preview`, {
                    source_conversation_id: req.source_conversation_id,
                    mode: "regression",
                    entity_names: chosen2,
                    cutoff_turn: req.cutoff_turn
                  }, 15e3);
                  if (previewRound.get(previewSpot) !== subRound) return;
                  active = pv;
                  renderDetails(pv);
                  ok.disabled = false;
                } catch (error) {
                  if (previewRound.get(previewSpot) !== subRound) return;
                  renderDetails(null);
                  say(msg, carryErrorText(lang, error, errorText), "err");
                }
              });
              return el("label", { class: "check" }, cb, el("span", { text: name }));
            }));
            syncCap();
            box.append(charList);
          }
        }
        renderDetails(active);
        cancel.addEventListener("click", () => {
          nextRound(previewSpot);
          previewSpot.replaceChildren();
          trigger.disabled = false;
          say(msg, "");
        });
        ok.addEventListener("click", async () => {
          if (!active) return;
          const chosenNames = req.mode === "regression" ? [...pickedNames] : [];
          if (req.mode === "regression" && chosenNames.length === 0) return;
          ok.disabled = true;
          say(msg, "");
          const linkBody = {
            source_conversation_id: req.source_conversation_id,
            mode: req.mode,
            entity_names: chosenNames,
            cutoff_turn: req.cutoff_turn,
            expect: active.fingerprint
          };
          try {
            await deps.api("POST", `/v1/conversations/${conversation}/carry`, linkBody, 15e3);
            previewSpot.replaceChildren();
            await showCarry(conversation, card, "carry.linked");
          } catch (error) {
            if (isCarryConflict(error)) {
              void openPreview(trigger, {
                source_conversation_id: req.source_conversation_id,
                mode: req.mode,
                entity_names: chosenNames,
                cutoff_turn: req.cutoff_turn
              }, true);
              return;
            }
            say(msg, carryErrorText(lang, error, errorText), "err");
            ok.disabled = false;
          }
        });
        box.append(
          detailsSpot,
          el("p", { class: "sub", style: "margin-top:8px", text: L("carry.pv_notice") }),
          el("div", { class: "btns" }, ok, cancel)
        );
        previewSpot.replaceChildren(box);
      }
      if (state.in_force) {
        const link = state.in_force;
        const modeText = L(link.mode === "regression" ? "carry.mode_regression" : "carry.mode_continue");
        const lt = localTime(link.created_at, lang);
        const takenEl = el("div", { class: "muted", text: L("carry.taken_at", { time: lt ? lt.text : link.created_at }) });
        if (lt) takenEl.title = lt.title;
        const sourceText = carrySourceLabel(link.source);
        const summaryLines = [
          el(
            "div",
            { class: "line" },
            el("span", { class: "badge b-info", text: L("carry.linked_badge") }),
            el("strong", { text: sourceText })
          ),
          el("div", { text: `${modeText} \xB7 ${carryCutoffLabel(lang, link.cutoff_turn)}` }),
          el("div", {
            text: link.mode === "regression" ? L("carry.only_remember", { names: link.entity_names.join(", ") }) : L("carry.linked_continue", { source: sourceText })
          }),
          takenEl
        ];
        const readAgainBtn = el("button", { text: L("carry.read_again") });
        const unlinkBtn = el("button", { text: L("carry.unlink") });
        let unlinkArmed = false;
        let unlinkTimer = 0;
        const disarmUnlink = () => {
          window.clearTimeout(unlinkTimer);
          unlinkArmed = false;
          unlinkBtn.textContent = L("carry.unlink");
          unlinkBtn.className = "";
        };
        readAgainBtn.addEventListener("click", () => {
          disarmUnlink();
          void openPreview(readAgainBtn, {
            source_conversation_id: link.source_conversation_id,
            mode: link.mode,
            entity_names: [...link.entity_names],
            cutoff_turn: link.cutoff_turn
          });
        });
        unlinkBtn.addEventListener("click", async () => {
          if (!unlinkArmed) {
            unlinkArmed = true;
            unlinkBtn.textContent = L("carry.unlink_confirm");
            unlinkBtn.className = "danger";
            unlinkTimer = window.setTimeout(disarmUnlink, 6e3);
            return;
          }
          disarmUnlink();
          nextRound(previewSpot);
          previewSpot.replaceChildren();
          readAgainBtn.disabled = true;
          unlinkBtn.disabled = true;
          say(msg, "");
          try {
            await deps.api("DELETE", `/v1/conversations/${conversation}/carry`, void 0, 15e3);
            await showCarry(conversation, card, "carry.unlinked");
          } catch (error) {
            readAgainBtn.disabled = false;
            unlinkBtn.disabled = false;
            say(msg, carryErrorText(lang, error, errorText), "err");
          }
        });
        card.replaceChildren(
          ...carryHead(),
          ...summaryLines,
          el("div", { class: "btns" }, readAgainBtn, unlinkBtn),
          previewSpot,
          msg
        );
        card.style.display = "";
        return;
      }
      if (!knownChats.length) {
        try {
          const rows = await deps.api("GET", "/v1/conversations?host=pocketrisu", void 0, 5e3);
          if (Array.isArray(rows) && rows.length) {
            knownChats = rows.map((r) => {
              const ch = (r.host_character_name ?? "").trim();
              const ti = (r.host_chat_name ?? r.title ?? "").trim();
              const name = ch && ti && ti !== ch ? `${ch} \xB7 ${ti}` : ch || ti || r.id.slice(0, 8);
              const turns = typeof r.messages === "number" ? r.messages : typeof r.message_count === "number" ? r.message_count : void 0;
              return { id: r.id, name, character: ch, title: ti, turns };
            });
          }
        } catch {
        }
        if (!card.isConnected || actionConversation !== conversation) return;
      }
      const choices = knownChats.filter((c) => c.id !== conversation);
      if (!choices.length) {
        card.replaceChildren(
          ...carryHead(),
          el("div", { class: "muted", text: L("carry.no_other") }),
          msg
        );
        card.style.display = "";
        return;
      }
      const sourceSelect = el(
        "select",
        { "aria-label": L("carry.source") },
        ...choices.map((c) => el("option", { value: c.id, text: c.name }))
      );
      const radioName = `nmos-carry-mode-${conversation}`;
      const continueRadio = el("input", { type: "radio", name: radioName, value: "continue" });
      continueRadio.checked = true;
      const regressionRadio = el("input", { type: "radio", name: radioName, value: "regression" });
      const cutoffInput = el("input", {
        type: "number",
        min: "0",
        step: "1",
        placeholder: L("carry.cutoff_placeholder"),
        "aria-label": L("carry.cutoff")
      });
      const previewBtn = el("button", { class: "primary", text: L("carry.preview_btn") });
      const resetPreview = () => {
        nextRound(previewSpot);
        previewSpot.replaceChildren();
        previewBtn.disabled = false;
        say(msg, "");
      };
      sourceSelect.addEventListener("change", resetPreview);
      continueRadio.addEventListener("change", resetPreview);
      regressionRadio.addEventListener("change", resetPreview);
      cutoffInput.addEventListener("input", resetPreview);
      previewBtn.addEventListener("click", () => {
        const parsed = parseCutoffTurn(cutoffInput.value);
        if (cutoffInput.validity?.badInput || !parsed.ok) {
          say(msg, L("carry.cutoff_invalid"), "err");
          return;
        }
        const mode = regressionRadio.checked ? "regression" : "continue";
        void openPreview(previewBtn, {
          source_conversation_id: sourceSelect.value,
          mode,
          entity_names: [],
          cutoff_turn: parsed.value
        });
      });
      card.replaceChildren(
        ...carryHead(),
        field(L("carry.source"), sourceSelect),
        el("label", { text: L("carry.mode") }),
        el("label", { class: "check" }, continueRadio, el("strong", { text: L("carry.mode_continue") })),
        el("p", { class: "sub", text: L("carry.mode_continue_desc") }),
        el("label", { class: "check" }, regressionRadio, el("strong", { text: L("carry.mode_regression") })),
        el("p", { class: "sub", text: L("carry.mode_regression_desc") }),
        field(L("carry.cutoff"), cutoffInput),
        el("div", { class: "btns" }, previewBtn),
        previewSpot,
        msg
      );
      card.style.display = "";
    }
    async function showPins(conversation, card, said) {
      const head = [el("h2", { text: L("pins.title") }), el("p", { class: "sub", text: L("pin.sub") })];
      const msg = el("div", { class: "msg", role: "status" });
      if (said) say(msg, L(said), "ok");
      let rows;
      try {
        const list = await deps.api("GET", `/v1/conversations/${conversation}/entities`, void 0, 15e3);
        if (!Array.isArray(list)) throw new Error("not a list");
        rows = list;
      } catch {
        card.replaceChildren(...head, el("div", { class: "muted", text: L("pins.failed") }));
        return;
      }
      const lines = rows.filter((e) => typeof e.pinned === "string" && e.pinned).map((e) => {
        const unpin = el("button", { class: "mini", text: L("pins.unpin") });
        unpin.addEventListener("click", async () => {
          unpin.disabled = true;
          say(msg, "");
          try {
            await deps.api("POST", `/v1/conversations/${conversation}/repairs/${e.pinned}/remove`, {}, 15e3);
            await showPins(conversation, card, "pin.undone");
          } catch (error) {
            unpin.disabled = false;
            say(msg, errorText(lang, error), "err");
          }
        });
        return el("div", { class: "btns" }, el("span", { text: e.name }), unpin);
      });
      card.replaceChildren(...head, ...lines.length ? lines : [el("div", { class: "muted", text: L("pins.none") })], msg);
    }
    async function retryFrom(conversation) {
      if (!conversation) return;
      say(actionMsg, L("act.working"));
      try {
        const r = await deps.api(
          "POST",
          `/v1/conversations/${conversation}/retry-failed`,
          {},
          3e4
        );
        const n = Object.values(r.retried ?? {}).reduce((a, b) => a + (Number(b) || 0), 0);
        say(actionMsg, n ? L("act.retry_done", { n }) : L("act.retry_none"), "ok");
        if (n) deps.hud.background(conversation);
        await showInspector();
      } catch (error) {
        say(actionMsg, actionError(error), "err");
      }
    }
    async function hubPath(explicitConversation) {
      let chat = null;
      let off = false;
      let allOff = false;
      try {
        ({ id: chat, off } = await deps.chat.current());
      } catch {
      }
      try {
        allOff = !(await deps.status()).enabled;
      } catch {
      }
      const q = [
        explicitConversation ? `conversation=${encodeURIComponent(explicitConversation)}` : chat ? `chat=${encodeURIComponent(chat)}` : "",
        off ? "off=true" : "",
        allOff ? "all_off=true" : ""
      ].filter(Boolean).join("&");
      return `/v1/views/hub${q ? `?${q}` : ""}`;
    }
    async function viewsStyle() {
      if (document.getElementById("nmos-views-style")) return;
      try {
        const r = await deps.api("GET", "/v1/views/style", void 0, 5e3);
        if (typeof r.css === "string" && !/@import|url\s*\(/i.test(r.css)) {
          document.head.append(el("style", { id: "nmos-views-style", text: r.css }));
        }
      } catch {
      }
    }
    document.body.append(root);
    try {
      const features = (await deps.status()).features;
      viewsOn = !!features?.views;
      mapOn = viewsOn && !!features?.map;
      graphOn = mapOn && !!features?.map_graph;
    } catch {
      viewsOn = false;
    }
    if (viewsOn) {
      await viewsStyle();
      inspectorPath = await hubPath();
      if (tab === "status") tab = "inspector";
      buildShell();
      groupSettings();
    }
    select(tab);
    await loadAll();
    return { root, select };
  }

  // src/host.ts
  var DEFAULT_SIDECAR_URL = "http://127.0.0.1:8790";
  async function arg(key) {
    return String(await risuai.getArgument(key) ?? "").trim();
  }
  function fetchOptions(route) {
    return route === "server" ? { networkRoute: "local_network" } : {};
  }
  function positiveInt(value, fallback, max) {
    const n = Number(value);
    return Number.isFinite(n) && n > 0 ? Math.min(max, Math.floor(n)) : fallback;
  }
  var risuHost = {
    async settings() {
      const position = await arg("inject_position");
      const sidecarUrl = await arg("sidecar_url") || DEFAULT_SIDECAR_URL;
      return {
        sidecarUrl,
        route: routeFor(sidecarUrl, await arg("route")),
        authToken: await arg("auth_token"),
        enabled: Number(await arg("disabled")) !== 1,
        reservedMemoryTokens: positiveInt(await arg("reserved_memory_tokens"), DEFAULT_RESERVED_TOKENS, MAX_RESERVED_TOKENS),
        deadlineMs: positiveInt(await arg("deadline_ms"), DEFAULT_DEADLINE_MS, MAX_DEADLINE_MS),
        injectPosition: position === "end" ? "end" : "before_last_user",
        language: langOf(await arg("language")),
        offChats: parseChatIds(await arg(CHAT_OFF_ARG)),
        trimOldTurns: Number(await arg("trim_old_turns")) === 1,
        keepRecentTurns: Math.max(
          MIN_KEEP_RECENT_TURNS,
          positiveInt(await arg("keep_recent_turns"), DEFAULT_KEEP_RECENT_TURNS, MAX_KEEP_RECENT_TURNS)
        )
      };
    },
    async currentChat() {
      const characterIndex = await risuai.getCurrentCharacterIndex();
      const chatIndex = await risuai.getCurrentChatIndex();
      return risuai.getChatFromIndex(characterIndex, chatIndex);
    },
    async characterName(chatId) {
      const card = await this.card(chatId);
      return typeof card?.name === "string" && card.name.trim() ? card.name.trim() : null;
    },
    async card(chatId) {
      const character = await risuai.getCharacterFromIndex(await risuai.getCurrentCharacterIndex());
      if (!character?.chats?.some((c) => c?.id === chatId)) return null;
      const { name, desc, personality, scenario, firstMessage, alternateGreetings, globalLore } = character;
      return { name, desc, personality, scenario, firstMessage, alternateGreetings, globalLore };
    },
    async lorebook() {
      if (typeof risuai.getCurrentLorebookEntries !== "function") throw new Error("no lorebook call on this host");
      const entries = await risuai.getCurrentLorebookEntries();
      if (!Array.isArray(entries)) throw new Error("the host returned no lorebook list");
      return entries;
    },
    async personas() {
      if (typeof risuai.getDatabase !== "function") return null;
      const db = await risuai.getDatabase(["personas", "selectedPersona"]);
      if (!db || !Array.isArray(db.personas)) return null;
      const personas = db.personas.map((p) => {
        const { id, name, personaPrompt } = p ?? {};
        return {
          id: typeof id === "string" ? id : void 0,
          name: typeof name === "string" ? name : void 0,
          personaPrompt: typeof personaPrompt === "string" ? personaPrompt : void 0
        };
      });
      return { personas, selected: Number.isInteger(db.selectedPersona) ? Number(db.selectedPersona) : 0 };
    },
    async request(method, url, body, headers, timeoutMs, route) {
      const res = await risuai.nativeFetch(url, {
        method,
        headers,
        ...body === void 0 ? {} : { body: JSON.stringify(body) },
        requestTimeoutMs: Math.max(1, Math.floor(timeoutMs)),
        ...fetchOptions(route)
      });
      let json = null;
      try {
        json = await res.json();
      } catch {
        json = null;
      }
      return { status: res.status, json };
    },
    async requestFile(url, headers, timeoutMs, route) {
      const res = await risuai.nativeFetch(url, {
        method: "GET",
        headers,
        requestTimeoutMs: Math.max(1, Math.floor(timeoutMs)),
        ...fetchOptions(route)
      });
      const bytes = await res.arrayBuffer();
      if (res.status >= 200 && res.status < 300) return { status: res.status, bytes, json: null };
      let json = null;
      try {
        json = JSON.parse(new TextDecoder().decode(bytes));
      } catch {
        json = null;
      }
      return { status: res.status, bytes: null, json };
    },
    warn: (...args) => console.warn(...args),
    debug: (...args) => console.debug(...args),
    now: () => performance.now(),
    // PocketRisu's alertNormal: one global dialog, so core.ts calls it only after a reply (audit A-09).
    alert: (message) => {
      risuai.alert(message).catch(() => {
      });
    }
  };
  function createRisuHud(link) {
    const hud = createHud({
      enabled: async () => Number(await arg("hud")) === 1,
      lang: async () => langOf(await arg("language")),
      rootDocument: async () => typeof risuai.getRootDocument === "function" ? risuai.getRootDocument() : null,
      position: async () => `${await risuai.getCurrentCharacterIndex()}:${await risuai.getCurrentChatIndex()}`,
      coverage: (conversationId) => link.coverage(conversationId),
      openPanel: () => link.openPanel(),
      now: () => performance.now(),
      debug: (...args) => console.debug(...args),
      setTimer: (fn, ms) => setTimeout(fn, ms),
      clearTimer: (handle) => clearTimeout(handle)
    });
    const control = {
      event: hud.event,
      async enable() {
        if (typeof risuai.requestPluginPermission !== "function" || typeof risuai.getRootDocument !== "function") {
          return "unsupported";
        }
        await risuai.hideContainer();
        let granted = false;
        try {
          granted = await risuai.requestPluginPermission("mainDom") === true;
        } finally {
          await risuai.showContainer("fullscreen");
        }
        await risuai.setArgument("hud", granted ? 1 : 0);
        hud.refresh();
        return granted ? "on" : "denied";
      },
      async disable() {
        await risuai.setArgument("hud", 0);
        hud.refresh();
      },
      problem: hud.problem,
      background: hud.background
    };
    return control;
  }
  var risuChatSwitch = createChatSwitch({
    getArg: arg,
    setArg: (key, value) => risuai.setArgument(key, value),
    async currentChatId() {
      const characterIndex = await risuai.getCurrentCharacterIndex();
      if (characterIndex < 0) return null;
      const chat = await risuai.getChatFromIndex(characterIndex, await risuai.getCurrentChatIndex());
      return typeof chat?.id === "string" && chat.id ? chat.id : null;
    }
  });
  function chatSwitchNotice(lang, state, enabled) {
    if (state.id === null) return t(lang, "chat.none");
    if (state.off) return t(lang, "chat.switched_off");
    return t(lang, enabled ? "chat.switched_on" : "chat.switched_on_all_off");
  }
  function saveFile(bytes, name, type = "application/zip") {
    const url = URL.createObjectURL(new Blob([bytes], { type }));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.style.display = "none";
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 6e4);
  }
  async function registerHooks(beforeRequest, onOutput, status, api, file, hud) {
    await risuai.addRisuReplacer("beforeRequest", beforeRequest);
    await risuai.addRisuChatListener("output", onOutput);
    const deps = {
      api,
      status,
      getArg: arg,
      setArg: (key, value) => risuai.setArgument(key, value),
      show: () => risuai.showContainer("fullscreen"),
      hide: () => risuai.hideContainer(),
      hud,
      chat: risuChatSwitch,
      async download(path, name) {
        const bytes = await file(path);
        saveFile(bytes, name);
        return bytes.byteLength;
      }
    };
    const open = (tab) => openPanel(deps, tab);
    const lang = langOf(await arg("language"));
    await risuai.registerSetting(t(lang, "menu.panel"), () => open("status"), NMOS_ICON, "html", "nmos-panel");
    await risuai.registerButton(
      { name: t(lang, "menu.panel"), icon: NMOS_ICON, iconType: "html", location: "chat", id: "nmos-chat" },
      () => open("status")
    );
    await risuai.registerButton({
      name: t(lang, "menu.chat_switch"),
      icon: "\u23FB",
      iconType: "html",
      location: "chat",
      id: "nmos-chat-switch"
    }, () => {
      risuChatSwitch.toggle().then(async (state) => risuai.alert(chatSwitchNotice(lang, state, Number(await arg("disabled")) !== 1))).catch((error) => console.warn("[NMOS] chat switch failed:", error instanceof Error ? error.message : error));
    });
    await risuai.registerButton({
      name: t(lang, "menu.panel"),
      icon: namedIcon(t(lang, "menu.panel")),
      iconType: "html",
      location: "hamburger",
      id: "nmos-sidebar"
    }, () => open("status"));
    return () => void open("status");
  }

  // src/entry.ts
  (async () => {
    let openStatus = () => {
    };
    const hud = createRisuHud({
      coverage: (conversationId) => adapter.api("GET", `/v1/conversations/${conversationId}/coverage`, void 0, 5e3),
      openPanel: () => openStatus()
    });
    const adapter = createAdapter(risuHost, (event) => hud.event(event));
    openStatus = await registerHooks(
      async (prompt, mode) => {
        try {
          return await adapter.beforeRequest(prompt, mode);
        } catch {
          return prompt;
        }
      },
      (arg2) => adapter.onOutput(arg2),
      () => adapter.status(),
      (method, path, body, timeoutMs) => adapter.api(method, path, body, timeoutMs),
      (path) => adapter.file(path),
      hud
    );
    adapter.warmPersonas();
    console.log("[NMOS] adapter loaded", { version: "0.6.0" });
  })().catch((error) => console.error("[NMOS] adapter failed to load", error));
})();
