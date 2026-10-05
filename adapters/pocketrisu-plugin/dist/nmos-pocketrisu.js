//@name nmos_memory
//@display-name NMOS Narrative Memory
//@api 3.0
//@version 0.3.0
//@link https://github.com/Sallos725/NMOS Documentation
//@update-url https://raw.githubusercontent.com/Sallos725/NMOS/main/adapters/pocketrisu-plugin/dist/nmos-pocketrisu.js
//@arg sidecar_url string NMOS sidecar URL (empty = http://127.0.0.1:8790)
//@arg auth_token string Optional; only if the sidecar sets NMOS_AUTH_TOKEN
//@arg disabled int 1 = pass every request through untouched
//@arg reserved_memory_tokens int Max packet tokens; lower the host max context by this much (0 = 2000)
//@arg deadline_ms int Hard request-path deadline in ms (0 = 3000)
//@arg inject_position string before_last_user (default) or end
//@arg route string auto (default) / direct / server — how to reach the sidecar
//@arg language string Panel language: ko (default) or en
//@arg hud int 1 = progress display on the chat screen (turn it on from the NMOS panel)
//@arg disabled_chats string Chat ids NMOS is off for (switched from the NMOS panel or the chat menu)
"use strict";
(() => {
  // src/build.ts
  var PLUGIN_BUILD = true ? "nmos-build:a3100b8e5741".replace("nmos-build:", "") : "dev";

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
    const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(text2));
    return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
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
    add("note", chat.note);
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

  // src/form.ts
  var DEFAULT_DEADLINE_MS = 3e3;
  var MAX_DEADLINE_MS = 3e4;
  var DEFAULT_RESERVED_TOKENS = 4e3;
  var MAX_RESERVED_TOKENS = 2e4;
  var PANEL_MAX_RESERVED_TOKENS = 8e3;
  var SECTIONS = ["conn", "llm", "emb", "tune", "rules"];
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
  function presetMatches(presetUrl, url) {
    if (!presetUrl.includes("{project}")) return presetUrl === url;
    const [head, tail] = presetUrl.split("{project}");
    return url.startsWith(head) && url.endsWith(tail) && url.length > head.length + tail.length && !url.slice(head.length, url.length - tail.length).includes("/");
  }
  function dirtySections(baseline, current2) {
    return SECTIONS.filter((s) => JSON.stringify(baseline[s]) !== JSON.stringify(current2[s]));
  }
  function num(value) {
    const n = Number(value.trim());
    return value.trim() !== "" && Number.isFinite(n) ? n : value;
  }
  function configBody(dirty, v) {
    const body = {};
    for (const [section, prefix] of [["llm", "llm"], ["emb", "embed"]]) {
      if (!dirty.includes(section)) continue;
      body[`${prefix}_url`] = v[section].url.trim();
      body[`${prefix}_model`] = v[section].model.trim();
      if (v[section].key.trim()) body[`${prefix}_api_key`] = v[section].key.trim();
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
    }
    if (dirty.includes("rules")) body.parsers = v.rules.trim() ? v.rules : null;
    return body;
  }
  function connArgs(v) {
    return {
      sidecar_url: v.url.trim(),
      route: v.route,
      disabled: v.enabled ? 0 : 1,
      reserved_memory_tokens: Math.min(PANEL_MAX_RESERVED_TOKENS, Math.floor(Number(v.reserved)) > 0 ? Math.floor(Number(v.reserved)) : DEFAULT_RESERVED_TOKENS),
      deadline_ms: Math.min(MAX_DEADLINE_MS, Math.max(200, Math.floor(Number(v.deadline)) || DEFAULT_DEADLINE_MS))
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
      "\uD655\uC778: docker compose up -d \xB7 \uC8FC\uC18C \xB7 NMOS_CORS_ORIGINS\uC5D0 \uC774 PocketRisu \uC8FC\uC18C \uD3EC\uD568 \xB7 localhost \uB610\uB294 HTTPS\uB85C \uC811\uC18D",
      "Check: docker compose up -d \xB7 the address \xB7 NMOS_CORS_ORIGINS includes this PocketRisu address \xB7 open via localhost or HTTPS"
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
      "\uB9C8\uC9C0\uB9C9 \uC694\uCCAD\uC5D0\uC11C \uC784\uBCA0\uB529 \uBAA8\uB378\uC774 \uC81C\uB54C \uB2F5\uD558\uC9C0 \uC54A\uC558\uAC70\uB098 \uC624\uB958\uB97C \uB0B4\uC11C, \uAE30\uC5B5\uC744 \uB2E8\uC5B4\uAC00 \uACB9\uCE58\uB294 \uAC83\uC73C\uB85C\uB9CC \uCC3E\uC558\uC2B5\uB2C8\uB2E4. \uB9D0\uC744 \uBC14\uAFD4 \uC4F4 \uC61B \uC7A5\uBA74\uC740 \uC774\uB54C \uBE60\uC9C8 \uC218 \uC788\uC2B5\uB2C8\uB2E4. \uBA3C\uC800 \uC124\uC815 \uD0ED\uC758 \uC758\uBBF8 \uAC80\uC0C9 \uC784\uBCA0\uB529 \uC5F0\uACB0 \uD14C\uC2A4\uD2B8\uB85C \uC8FC\uC18C\uC640 \uD0A4\uB97C \uD655\uC778\uD558\uC138\uC694. \uBAA8\uB378\uC774 \uC26C\uB2E4\uAC00 \uB2E4\uC2DC \uC62C\uB77C\uC624\uB294 \uC911\uC774\uC5C8\uB2E4\uBA74(Ollama\uB294 5\uBD84 \uC26C\uBA74 \uB0B4\uB9BC) \uB2E4\uC74C \uC694\uCCAD\uC740 \uAD1C\uCC2E\uC2B5\uB2C8\uB2E4. \uC5F0\uACB0\uC740 \uB418\uB294\uB370 \uC790\uC8FC \uB728\uBA74 \uC784\uBCA0\uB529 \uBAA8\uB378\uC744 \uACC4\uC18D \uC62C\uB824 \uB450\uAC70\uB098(Ollama keep_alive) \uC0AC\uC774\uB4DC\uCE74\uC758 NMOS_EMBED_TIMEOUT_MS\uB97C \uB298\uB824 \uC8FC\uC138\uC694.",
      "On the last request the embedding model did not answer in time or answered with an error, so memory was found by shared words only; an earlier scene in other words can be missed then. First check the address and key with the embedding connection test in the Settings tab. If the model was loading after a pause (Ollama unloads it after 5 minutes idle), the next request is fine. If it connects and this still shows often, keep the embedding model loaded (Ollama keep_alive) or raise the sidecar's NMOS_EMBED_TIMEOUT_MS."
    ],
    "deadline.took": [" (\uC2E4\uC81C\uB85C\uB294 \uC57D {n}ms \uAC78\uB9BC)", " (it took about {n} ms)"],
    "status.plugin_mismatch": [
      "\uC774 \uD50C\uB7EC\uADF8\uC778(\uBE4C\uB4DC {mine})\uC774 \uC0AC\uC774\uB4DC\uCE74\uC758 \uD50C\uB7EC\uADF8\uC778(\uBE4C\uB4DC {theirs})\uACFC \uB2E4\uB985\uB2C8\uB2E4. \uC0AC\uC774\uB4DC\uCE74\uC640 \uAC19\uC740 \uBC84\uC804\uC758 \uD50C\uB7EC\uADF8\uC778 \uD30C\uC77C\uB85C \uAD50\uCCB4\uD558\uACE0 \uC0C8\uB85C \uACE0\uCE68\uD558\uC138\uC694. \uC778\uC2A4\uD399\uD130 \uCCAB \uD654\uBA74\uC5D0\uC11C \uB9DE\uB294 \uD30C\uC77C\uC744 \uBC1B\uC744 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
      "This plugin (build {mine}) differs from the sidecar's (build {theirs}). Replace it with the plugin file of the sidecar's version and reload. The Inspector's first page links the matching file."
    ],
    "status.plugin_ok": ["\uD50C\uB7EC\uADF8\uC778 \uBE4C\uB4DC {b} \xB7 \uC0AC\uC774\uB4DC\uCE74\uC640 \uAC19\uC74C", "Plugin build {b} \xB7 matches the sidecar"],
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
    // inspector view
    "insp.loading": ["\uC778\uC2A4\uD399\uD130\uB97C \uBD88\uB7EC\uC624\uB294 \uC911\u2026", "Loading the inspector\u2026"],
    "insp.back": ["\u2190 \uB4A4\uB85C", "\u2190 Back"],
    "insp.browser": ["\uBE0C\uB77C\uC6B0\uC800\uC5D0\uC11C \uC9C1\uC811 \uC5F4 \uC218\uB3C4 \uC788\uC2B5\uB2C8\uB2E4: {url}", "Also available in a browser: {url}"],
    "act.history": ["\uACFC\uAC70 \uC804\uCCB4 \uCD94\uCD9C", "Extract all history"],
    "act.rebuild": ["\uAE30\uC5B5 \uC7AC\uAD6C\uCD95", "Rebuild memory"],
    "act.rebuild_confirm": ["\uD55C \uBC88 \uB354 \uB204\uB974\uBA74 \uC7AC\uAD6C\uCD95\uD569\uB2C8\uB2E4", "Click again to rebuild"],
    "act.delete": ["\uB300\uD654 \uC0AD\uC81C", "Delete conversation"],
    "act.delete_confirm": ["\uD55C \uBC88 \uB354 \uB204\uB974\uBA74 \uC601\uAD6C \uC0AD\uC81C\uD569\uB2C8\uB2E4", "Click again to delete for good"],
    "act.sub": [
      "\uACFC\uAC70 \uC804\uCCB4 \uCD94\uCD9C: \uCC98\uC74C \uC5F0\uACB0\uD560 \uB54C \uAC74\uB108\uB6F4 \uC774 \uCC44\uD305\uC758 \uC774\uC804 \uD134\uAE4C\uC9C0 \uC0AC\uC2E4\uC744 \uCD94\uCD9C\uD558\uACE0 \uC784\uBCA0\uB529\uD569\uB2C8\uB2E4. \uAE30\uC5B5 \uC7AC\uAD6C\uCD95: \uC774 \uCC44\uD305\uC758 \uC0AC\uC2E4\uC744 \uBC84\uB9AC\uACE0 \uBAA8\uB4E0 \uD134\uC744 \uB2E4\uC2DC \uCD94\uCD9C\uD569\uB2C8\uB2E4(\uC6D0\uBB38\uC740 \uADF8\uB300\uB85C). \uC720\uB8CC API\uB294 \uD134\uB9C8\uB2E4 \uBE44\uC6A9\uC774 \uB4ED\uB2C8\uB2E4. \uB300\uD654 \uC0AD\uC81C: NMOS\uC5D0 \uC800\uC7A5\uB41C \uC774 \uCC44\uD305\uC758 \uBAA8\uB4E0 \uAE30\uB85D(\uC6D0\uBB38 \uD3EC\uD568)\uC744 \uC9C0\uC6C1\uB2C8\uB2E4. \uB418\uB3CC\uB9B4 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4. PocketRisu\uC758 \uCC44\uD305\uC740 \uADF8\uB300\uB85C\uC774\uACE0, \uADF8 \uCC44\uD305\uC5D0\uC11C \uB2E4\uC2DC \uC0DD\uC131\uD558\uBA74 \uC0C8 \uB300\uD654\uB85C \uCC98\uC74C\uBD80\uD130 \uAE30\uB85D\uB429\uB2C8\uB2E4.",
      "Extract all history: extract facts and embeddings for the older turns of this chat that the first sync skipped. Rebuild memory: discard this chat's facts and extract every turn again (raw messages stay). Paid APIs cost money per turn. Delete conversation: delete everything NMOS stored for this chat, raw messages included. This cannot be undone. The chat in PocketRisu stays; generating in it again records it as a new conversation from scratch."
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
    "exp.title": ["\uB0B4\uBCF4\uB0B4\uAE30", "Export"],
    "exp.sub": [
      "NMOS\uAC00 \uAE30\uC5B5\uD558\uB294 \uBAA8\uB4E0 \uB300\uD654\uC640 \uC124\uC815(API \uD0A4\uB294 \uBE7C\uACE0)\uC744 .nmos.zip \uD30C\uC77C \uD558\uB098\uB85C \uC800\uC7A5\uD569\uB2C8\uB2E4. \uCC44\uD305 \uC6D0\uBB38\uC774 \uB4E4\uC5B4 \uC788\uC73C\uB2C8 \uCC44\uD305\uCC98\uB7FC \uBCF4\uAD00\uD558\uC138\uC694.",
      "Saves every conversation NMOS keeps and its settings (never an API key) as one .nmos.zip file. It holds the chat text: keep it as you keep the chat."
    ],
    "exp.embeddings": ["\uC784\uBCA0\uB529\uB3C4 \uB123\uAE30 (\uD30C\uC77C\uC774 \uCEE4\uC9C0\uC9C0\uB9CC \uBCF5\uC6D0 \uB4A4 \uB2E4\uC2DC \uACC4\uC0B0\uD558\uC9C0 \uC54A\uC74C)", "Include embeddings (a larger file, not recomputed after a restore)"],
    "exp.all": ["\uC804\uBD80 \uB0B4\uBCF4\uB0B4\uAE30", "Export everything"],
    "exp.working": ["\uD30C\uC77C\uC744 \uC900\uBE44\uD558\uB294 \uC911\u2026", "Preparing the file\u2026"],
    "exp.saved": ["{mb} MB\uB97C \uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4. \uBE0C\uB77C\uC6B0\uC800\uC758 \uB2E4\uC6B4\uB85C\uB4DC\uB97C \uD655\uC778\uD558\uC138\uC694.", "Saved {mb} MB. Check the browser's downloads."],
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
    "rp.undo": ["\uB418\uB3CC\uB9AC\uAE30", "Undo"],
    "rp.select": ["\uC77C\uAD04 \uB2EB\uAE30\uC5D0 \uB123\uAE30", "Select to close"],
    "rp.outcome": ["\uB2EB\uB294 \uACB0\uACFC", "Outcome"],
    "oc.kept": ["\uC9C0\uD0B4", "kept"],
    "oc.broken": ["\uAE68\uC9D0", "broken"],
    "oc.achieved": ["\uC774\uB8F8", "achieved"],
    "oc.abandoned": ["\uADF8\uB9CC\uB460", "abandoned"],
    "oc.failed": ["\uC2E4\uD328", "failed"],
    "oc.answered": ["\uB2F5\uC774 \uB098\uC634", "answered"],
    "oc.averted": ["\uD53C\uD568", "averted"],
    "oc.paid": ["\uAC1A\uC74C", "paid"],
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
    "emb.title": ["\uC758\uBBF8 \uAC80\uC0C9 \uC784\uBCA0\uB529", "Semantic recall embeddings"],
    "emb.sub": [
      "\uB2E4\uB978 \uB9D0\uB85C \uBB3C\uC5B4\uB3C4 \uC608\uC804 \uC7A5\uBA74\uC744 \uCC3E\uC2B5\uB2C8\uB2E4. Ollama\uC758 qwen3-embedding:0.6b\uB97C \uCD94\uCC9C\uD569\uB2C8\uB2E4.",
      "Finds earlier scenes even when asked in other words. Ollama qwen3-embedding:0.6b is recommended."
    ],
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
    "rules.sub": [
      'block: \uC2DC\uC791~\uB05D \uC0AC\uC774\uC758 "\uD0A4: \uAC12" \uC904\uC744 \uC77D\uC2B5\uB2C8\uB2E4. entity_line\uC73C\uB85C [\uC778\uBB3C] \uC904\uB9C8\uB2E4 \uC778\uBB3C\uBCC4\uB85C \uB098\uB215\uB2C8\uB2E4 (\uC2DC\uBBAC\uBD07). regex: key/value \uC774\uB984 \uADF8\uB8F9.',
      'block: reads "key: value" lines between start and end; entity_line splits them per [character] line (sim bots). regex: named groups key/value.'
    ],
    "rules.example": ["\uC608\uC2DC \uB123\uAE30", "Insert example"],
    "rules.none": ['\uADDC\uCE59 \uC5C6\uC74C \u2014 "\uC608\uC2DC \uB123\uAE30"\uB85C \uC2DC\uC791\uD558\uC138\uC694', 'No rules \u2014 start with "Insert example"'],
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
    "lang_unsaved": ["\uC5B8\uC5B4\uB97C \uBC14\uAFB8\uAE30 \uC804\uC5D0 \uBCC0\uACBD\uC744 \uC800\uC7A5\uD558\uAC70\uB098 \uB418\uB3CC\uB9AC\uC138\uC694.", "Save or revert your changes before switching the language."],
    "conn_saved_server_failed": ["\uC5F0\uACB0 \uC124\uC815\uC740 \uC800\uC7A5\uD588\uC9C0\uB9CC \uC11C\uBC84 \uC124\uC815\uC740 \uC800\uC7A5\uD558\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4: {e}", "Connection saved, but the server settings were not: {e}"],
    // progress display (HUD) on the chat screen
    "hud.recalling": ["\uAE30\uC5B5 \uBD88\uB7EC\uC624\uB294 \uC911\u2026", "Recalling memory\u2026"],
    "hud.injected": ["\u2713 \uAE30\uC5B5 \uC8FC\uC785 ({n}\uC790)", "\u2713 Memory injected ({n} chars)"],
    "hud.nothing": ["\u2013 \uAD00\uB828 \uAE30\uC5B5 \uC5C6\uC74C", "\u2013 Nothing relevant"],
    "hud.chat_off": ["\u23FB \uC774 \uCC44\uD305\uC740 NMOS \uAEBC\uC9D0", "\u23FB NMOS is off for this chat"],
    "hud.skipped": ["\u26A0 \uAC74\uB108\uB700: {r}", "\u26A0 Skipped: {r}"],
    "hud.reason.deadline": ["\uC81C\uD55C \uC2DC\uAC04 {s}\uCD08 \uCD08\uACFC \xB7 \uB20C\uB7EC\uC11C \uB298\uB9AC\uAE30", "over the {s} s deadline \xB7 tap to raise"],
    "hud.reason.error": ["\uC0AC\uC774\uB4DC\uCE74 \uC624\uB958", "sidecar error"],
    "hud.extract": ["\uCD94\uCD9C {d}/{n}", "Facts {d}/{n}"],
    "hud.embed": ["\uC784\uBCA0\uB529 {d}/{n}", "Embeddings {d}/{n}"],
    "hud.summarize": ["\uC694\uC57D {n}\uAC1C \uB0A8\uC74C", "summaries to write: {n}"],
    "hud.failed": ["\u26A0 \uC2E4\uD328 {n}", "\u26A0 {n} failed"],
    "hud.done": ["\u2713 \uCC98\uB9AC \uC644\uB8CC", "\u2713 Processing done"],
    "hud.reused": [" \xB7 \uC7AC\uC0AC\uC6A9", " \xB7 reused"],
    "hud.lexical": [" \xB7 \uC5B4\uD718 \uAC80\uC0C9\uB9CC", " \xB7 lexical only"],
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
    "sidecar_error": ["\uC0AC\uC774\uB4DC\uCE74 \uC624\uB958: ", "Sidecar error: "]
  };
  function t(lang, key, vars = {}) {
    const text2 = STRINGS[key][lang === "en" ? 1 : 0];
    return text2.replace(/\{(\w+)\}/g, (m, name) => name in vars ? String(vars[name]) : m);
  }
  var STRING_KEYS = Object.keys(STRINGS);

  // src/manifest.ts
  var HASH_FORMAT_VERSION = 1;
  var SPECIAL_COMMENT = /\{\{specialcomment::[^]*?::\}\}/g;
  function selectedContent(message) {
    const swipes = message?.swipes;
    const id = message?.swipeId;
    if (Array.isArray(swipes) && Number.isInteger(id) && id >= 0 && id < swipes.length) {
      return swipes[id] ?? "";
    }
    return message?.data ?? "";
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
  var bodyKey = (logicalId, revisionHash) => `${logicalId}
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
    entries.forEach((e, i) => index.set(bodyKey(e.host_logical_id, e.revision_hash), i));
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

  // src/prompt.ts
  var PACKET_TAG = '<NarrativeMemory version="0" source="nmos">';
  function contentText(content) {
    if (typeof content === "string") return content;
    if (content == null) return "";
    return JSON.stringify(content);
  }
  function isActive(message) {
    return message.disabled !== true && !message.isComment;
  }
  function latestUserIndex(messages) {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      if (m.role === "user" && isActive(m)) return i;
    }
    return -1;
  }
  function userTurnIndex(prompt, hostMessages) {
    if (!Array.isArray(prompt)) return -1;
    const hostIndex = latestUserIndex(hostMessages);
    if (hostIndex < 0) return -1;
    const expected = cleanText(selectedContent(hostMessages[hostIndex]));
    if (!expected) return -1;
    const anchor = anchorOf(expected, 64);
    for (let i = prompt.length - 1; i >= 0; i -= 1) {
      if (prompt[i]?.role === "assistant") continue;
      const sent = cleanText(contentText(prompt[i]?.content));
      if (sent === expected || sent.includes(anchor)) return i;
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
  function inContextIds(prompt, hostMessages, minAnchor = 16, maxMisses = 3) {
    const texts = prompt.map((m) => cleanText(contentText(m?.content)));
    let pointer = texts.length - 1;
    let boundary = hostMessages.length;
    let misses = 0;
    for (let i = hostMessages.length - 1; i >= 0 && pointer >= 0; i -= 1) {
      const m = hostMessages[i];
      if (!isActive(m)) continue;
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
        boundary = i;
        pointer = found - 1;
        misses = 0;
      } else if (++misses >= maxMisses) {
        break;
      }
    }
    return hostMessages.slice(boundary).map((m) => String(m.chatId ?? "")).filter(Boolean);
  }
  function injectPacket(prompt, packet, position = "before_last_user", turn = -1) {
    if (!packet || hasPacket(prompt)) return prompt;
    const message = { role: "system", content: packet };
    const out = prompt.slice();
    if (position === "end") {
      out.push(message);
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

  // src/core.ts
  var DeadlineError = class extends Error {
  };
  var SUCCESS_TTL_MS = 10 * 6e4;
  var FAILURE_TTL_MS = 3e4;
  var CACHE_LIMIT = 64;
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
    function remember(key, packet, ttl, failed = false, memory = null, vectors = null, canon) {
      cache.set(key, { packet, expires: host.now() + ttl, failed, memory, vectors, canon });
      while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value);
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
      if (result.status === "needs_bodies") {
        const needed = (result.needed_bodies ?? []).map((n) => bodies.get(bodyKey(n.host_logical_id, n.revision_hash)));
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
      return result;
    }
    async function beforeRequest(prompt, mode) {
      const started = host.now();
      const since = epoch;
      let settings = null;
      let key = null;
      let chatId = null;
      let announced = false;
      let failure = null;
      let lateAt = null;
      const late = (at) => {
        lateAt = at;
        if (failure) failure.neededMs = Math.round(at - started);
      };
      try {
        if (mode !== "model" || hasPacket(prompt)) return prompt;
        settings = await within(host.settings(), started + DEFAULT_DEADLINE_MS, "the plugin settings");
        if (!settings.enabled || !settings.sidecarUrl) return prompt;
        const deadline = started + settings.deadlineMs;
        emit({ type: "request-start" });
        announced = true;
        const chat = await within(host.currentChat(), deadline, "the host chat read");
        const messages = Array.isArray(chat?.message) ? chat.message : [];
        const turn = userTurnIndex(prompt, messages);
        if (!chat?.id || turn < 0) {
          emit({ type: "request-abandon" });
          return prompt;
        }
        chatId = chat.id;
        if (settings.offChats?.includes(chat.id)) {
          emit({ type: "request-end", outcome: "chat-off", chars: 0, conversationId: null });
          return prompt;
        }
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
          settings.reservedMemoryTokens
        ])), deadline, "the cache key");
        const canon = await observeCanon(chat, prompt, deadline);
        const canonKey = JSON.stringify([canon?.snapshot?.id ?? null, canon?.held ?? []]);
        const cached = cache.get(key);
        if (cached && cached.expires > host.now() && (cached.failed || cached.canon === canonKey)) {
          const known = conversations.get(chat.id);
          if (canon?.snapshot && known) syncCanon(settings, known, chat.id, canon.snapshot);
          const outcome2 = cached.packet ? "injected" : "nothing-relevant";
          if (!cached.failed) last = {
            at: Date.now(),
            ms: Math.round(host.now() - started),
            packetChars: cached.packet.length,
            packet: cached.packet,
            outcome: outcome2,
            deadlineMs: settings.deadlineMs,
            budgetTokens: settings.reservedMemoryTokens,
            memory: cached.memory ?? null,
            vectors: cached.vectors ?? null
          };
          emit({
            type: "request-end",
            outcome: outcome2,
            chars: cached.packet.length,
            reused: true,
            vectors: cached.vectors ?? null,
            conversationId: conversations.get(chat.id) ?? null
          });
          return injectPacket(prompt, cached.packet, settings.injectPosition, turn);
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
          budget_tokens: settings.reservedMemoryTokens,
          client_timings_ms: { manifest: manifestMs, sync: syncMs, before_retrieve: t2 - started },
          canon_manifest_id: canon?.snapshot?.id ?? null,
          canon_held: canon?.held ?? []
        }, deadline, void 0, late);
        if (canon?.snapshot && synced.conversation_id) syncCanon(settings, synced.conversation_id, chat.id, canon.snapshot);
        const packet = retrieved.freshness === "fresh" ? retrieved.packet.text : "";
        const memory = retrieved.freshness === "fresh" ? retrieved.memory ?? null : null;
        const vectors = retrieved.freshness === "fresh" ? retrieved.vectors ?? null : null;
        if (epoch !== since) throw new Error("memory changed during this request");
        remember(key, packet, SUCCESS_TTL_MS, false, memory, vectors, canonKey);
        host.debug("[NMOS] request done", {
          ms: Math.round(host.now() - started),
          manifestMs: Math.round(manifestMs),
          syncMs: Math.round(syncMs),
          retrieveMs: Math.round(host.now() - t2),
          packetChars: packet.length
        });
        const outcome = packet ? "injected" : "nothing-relevant";
        last = {
          at: Date.now(),
          ms: Math.round(host.now() - started),
          packetChars: packet.length,
          packet,
          outcome,
          deadlineMs: settings.deadlineMs,
          budgetTokens: settings.reservedMemoryTokens,
          memory,
          vectors
        };
        emit({ type: "request-end", outcome, chars: packet.length, vectors, conversationId: synced.conversation_id ?? null });
        return injectPacket(prompt, packet, settings.injectPosition, turn);
      } catch (error) {
        if (key && epoch === since) remember(key, "", FAILURE_TTL_MS, true);
        last = failure = {
          at: Date.now(),
          ms: Math.round(host.now() - started),
          packetChars: 0,
          packet: "",
          outcome: "failed",
          error: error instanceof Error ? error.message : String(error),
          deadlineMs: settings?.deadlineMs ?? 0
        };
        if (lateAt !== null) failure.neededMs = Math.round(lateAt - started);
        if (announced) emit({
          type: "request-end",
          outcome: "failed",
          chars: 0,
          error: last.error,
          deadlineMs: last.deadlineMs,
          conversationId: chatId && conversations.get(chatId) || null
        });
        host.warn("[NMOS] memory skipped for this request (fail open):", error instanceof Error ? error.message : error);
        return prompt;
      }
    }
    function onOutput(arg2) {
      void (async () => {
        const settings = await host.settings();
        if (!settings.enabled || !settings.sidecarUrl || !arg2?.chat?.id || settings.offChats?.includes(arg2.chat.id)) return;
        adviseOnce(settings.language);
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
    async function status() {
      const settings = await host.settings();
      const info = {
        enabled: settings.enabled,
        sidecarUrl: settings.sidecarUrl,
        language: settings.language,
        connected: false,
        last
      };
      try {
        const res = await call(
          settings,
          "/v1/health",
          void 0,
          host.now() + 3e3
        );
        Object.assign(info, {
          connected: true,
          version: res.version,
          features: res.features ?? {},
          pluginExpected: res.plugin?.expected ?? null
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
          vectors: event.vectors
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
        const how = [r.reused ? t(lang, "hud.reused") : "", r.vectors === "fallback" ? t(lang, "hud.lexical") : ""].filter(Boolean).join("");
        return { kind: "ok", text: t(lang, "hud.injected", { n: r.chars }) + how, fraction: null };
      }
      if (r.outcome === "nothing-relevant") return { kind: "muted", text: t(lang, "hud.nothing"), fraction: null };
      if (r.outcome === "chat-off") return { kind: "muted", text: t(lang, "hud.chat_off"), fraction: null };
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
    // Surfaces, darkest to lightest.
    bg: "#0a0b0e",
    sunken: "#0d0e13",
    surface: "#121318",
    raised: "#1a1b22",
    raisedHover: "#23242e",
    // Hairlines on any surface.
    line: "rgba(255,255,255,0.07)",
    lineStrong: "rgba(255,255,255,0.10)",
    lineHover: "rgba(255,255,255,0.16)",
    // Text, strongest to faintest. `textFaint` still passes 4.5:1 on `surface`; `textGhost` is for marks only.
    textStrong: "#f4f4f7",
    text: "#e2e2e8",
    textSoft: "#c0c3d0",
    textMuted: "#9294a0",
    textFaint: "#7c7e8b",
    textGhost: "#5c5e6b",
    // White text on `accent` passes 4.5:1.
    accent: "#4a6af5",
    accentHover: "#3f5ee6",
    link: "#7ca0ff",
    ok: "#4fd18b",
    err: "#f05d5e",
    warn: "#e8ac43"
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
      const icon = await doc.createElement("span");
      await icon.setStyleAttribute(ICON_STYLE);
      await icon.setInnerHTML(NMOS_ICON);
      const text2 = await doc.createElement("span");
      await text2.setStyleAttribute(TEXT_STYLE);
      await line.appendChild(icon);
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
      return { root, line, icon, text: text2, track, fill, listener, last: "" };
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

  // src/budget.ts
  var FIT_CAP = 8e3;
  function budgetAdvice(r, current2) {
    if (!r || r.outcome === "failed" || !r.memory || !(r.memory.cut > 0) || !(r.budgetTokens && r.budgetTokens > 0)) return null;
    const all = typeof r.memory.fits_at === "number";
    const suggest = all ? r.memory.fits_at : FIT_CAP;
    if (suggest <= r.budgetTokens || current2 !== void 0 && current2 >= suggest) return null;
    return { cut: r.memory.cut, offered: r.memory.offered, budget: r.budgetTokens, suggest, all };
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
  var SECTION = /^s-[a-z]{1,20}$/;
  function inspectorApiPath(href) {
    const m = new RegExp(`^/inspector(/c/${UUID}(?:/e/${UUID})?)?(?:[?#]|$)`, "i").exec(href ?? "");
    return m ? `/v1/inspector${m[1] ?? ""}` : null;
  }
  function inspectorConversation(path) {
    const m = new RegExp(`^/v1/inspector/c/(${UUID})(?:/e/${UUID})?$`, "i").exec(path);
    return m ? m[1] : null;
  }
  function inspectorEntity(path) {
    const m = new RegExp(`^/v1/inspector/c/(${UUID})/e/(${UUID})$`, "i").exec(path);
    return m ? { conversation: m[1], entity: m[2] } : null;
  }
  var REPAIR = /^(thread_close|thread_reopen|secret_found_out|secret_keep|fact_retract|fact_correct|fact_lock|fact_restore|undo|alias_join):(-?[0-9a-f-]{1,64})(?::([A-Za-z0-9%._~,-]{1,600}))?$/;
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
  function keepAttribute(name, value) {
    switch (name) {
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
      default:
        return false;
    }
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
    { label: "preset.ollama", url: "http://host.docker.internal:11434/v1" },
    { label: "OpenRouter", url: "https://openrouter.ai/api/v1" },
    { label: "OpenAI", url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
    { label: "Google Gemini", url: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-2.5-flash" },
    { label: "Google Vertex AI", url: VERTEX_URL, model: "google/gemini-3.8-flash" },
    // checked on real Vertex (ADR 0022)
    { label: "preset.custom", url: "custom" }
  ];
  var EMBED_PRESETS = [
    { label: "preset.off", url: "" },
    { label: "preset.ollama", url: "http://host.docker.internal:11434/v1", model: "qwen3-embedding:0.6b" },
    { label: "OpenAI", url: "https://api.openai.com/v1", model: "text-embedding-3-small" },
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
    tune: "tune.title",
    rules: "rules.title"
  };
  var CSS = `
html,body{margin:0;background:${PALETTE.bg}}
.nmos{${paletteVars()}}
.nmos{position:fixed;inset:0;overflow:auto;background:var(--c-bg);font:13.5px/1.6 system-ui,-apple-system,"Noto Sans KR",sans-serif;color:var(--c-text);-webkit-font-smoothing:antialiased}
.nmos *{box-sizing:border-box}
.nmos .wrap{max-width:760px;margin:0 auto;padding:20px 16px 32px}
.nmos header{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.nmos h1{font-size:17px;font-weight:600;letter-spacing:-0.01em;margin:0;flex:1;white-space:nowrap;color:var(--c-text-strong)}
.nmos .tabs{display:flex;gap:6px;border-bottom:1px solid var(--c-line);margin:8px 0 8px}
.nmos .tabs button{background:none;border:0;border-bottom:2px solid transparent;border-radius:0;padding:9px 14px;color:var(--c-text-muted);font-size:13px;font-weight:500;transition:all .15s ease}
.nmos .tabs button:hover:not(:disabled){background:none;border-bottom-color:transparent;color:var(--c-text)}
.nmos .tabs button.on,.nmos .tabs button.on:hover:not(:disabled){color:var(--c-text-strong);border-bottom-color:var(--c-accent)}
.nmos .card{background:var(--c-surface);border:1px solid var(--c-line);border-radius:6px;padding:18px 20px;margin:16px 0}
.nmos h2{font-size:13.5px;font-weight:600;letter-spacing:-0.005em;color:var(--c-text-strong);margin:0 0 4px}
.nmos .sub{color:var(--c-text-muted);font-size:12px;line-height:1.55;margin:0 0 14px}
.nmos label{display:block;font-size:11.5px;font-weight:500;color:var(--c-text-muted);margin:12px 0 5px;letter-spacing:0.02em}
.nmos input,.nmos select,.nmos textarea{width:100%;background:var(--c-sunken);color:var(--c-text);border:1px solid var(--c-line-strong);border-radius:4px;padding:8px 11px;font:inherit;font-size:12.5px;transition:border-color .15s ease}
.nmos input:focus,.nmos select:focus,.nmos textarea:focus{border-color:${alpha("accent", 0.6)};outline:none;box-shadow:0 0 0 2px ${alpha("accent", 0.25)}}
.nmos header select{width:auto;padding:5px 9px;font-size:12px;border-radius:4px}
.nmos textarea{min-height:160px;font-family:ui-monospace,monospace;font-size:12px;line-height:1.6}
.nmos .row{display:flex;gap:12px;flex-wrap:wrap}.nmos .row>*{flex:1;min-width:140px}
.nmos .btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.nmos button{background:var(--c-raised);color:var(--c-text);border:1px solid var(--c-line-strong);border-radius:4px;padding:6px 13px;font:inherit;font-size:12.5px;cursor:pointer;transition:all .15s ease}
.nmos button:hover:not(:disabled){background:var(--c-raised-hover);color:var(--c-text-strong);border-color:var(--c-line-hover)}
.nmos button:focus-visible{outline:2px solid ${alpha("accent", 0.6)};outline-offset:1px}
.nmos button.primary{background:var(--c-accent);border-color:var(--c-accent);color:#fff}
.nmos button.primary:hover:not(:disabled){background:var(--c-accent-hover);border-color:var(--c-accent-hover)}
.nmos button.danger{background:${alpha("err", 0.15)};border-color:${alpha("err", 0.4)};color:var(--c-err)}
.nmos button.danger:hover:not(:disabled){background:${alpha("err", 0.25)};border-color:${alpha("err", 0.55)};color:var(--c-text-strong)}
.nmos button:disabled{opacity:.4;cursor:default}
.nmos .msg{margin-top:10px;font-size:12.5px;white-space:pre-wrap}
.nmos .ok{color:var(--c-ok)}.nmos .err{color:var(--c-err)}.nmos .warn{color:var(--c-warn)}.nmos .muted{color:var(--c-text-muted)}
.nmos .check{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:12.5px;color:var(--c-text-soft)}.nmos .check input{width:auto}
.nmos .preview{margin:8px 0;padding:8px 10px;border-left:3px solid var(--c-line);font-size:12.5px;line-height:1.6}.nmos .preview>b{display:block;margin-bottom:4px}
.nmos .line{display:flex;align-items:baseline;gap:8px;margin:5px 0}
.nmos .dot{flex:none;width:7px;height:7px;border-radius:50%;background:var(--c-text-ghost);transform:translateY(-1px)}
.nmos .dot.ok{background:var(--c-ok)}.nmos .dot.err{background:var(--c-err)}.nmos .dot.warn{background:var(--c-warn)}
.nmos .pills{display:flex;gap:8px;flex-wrap:wrap}
.nmos .pill{border:1px solid var(--c-line-strong);border-radius:4px;padding:3px 10px;font-size:12px;color:var(--c-text-muted)}
.nmos .pill.on{border-color:${alpha("ok", 0.4)};background:${alpha("ok", 0.08)};color:var(--c-ok)}
.nmos .mono{font-family:ui-monospace,monospace;font-size:12px;word-break:break-all}
.nmos.wide>.wrap{max-width:1100px}
.nmos .insp{margin-top:14px}.nmos .insp+.sub{margin-top:18px}
.nmos .insp h1{font-size:16px;font-weight:600;margin:4px 0;color:var(--c-text-strong)}
.nmos .insp h2{margin:22px 0 8px;font-size:13.5px;font-weight:600;color:var(--c-text-strong)}
.nmos .insp .top{display:flex;justify-content:space-between;align-items:baseline;gap:12px}.nmos .insp .top p{margin:0}
.nmos .insp a{color:var(--c-link);text-decoration:none;cursor:pointer}
.nmos .insp a:hover{text-decoration:underline}
.nmos .insp .ref{display:block;font-family:ui-monospace,monospace;font-size:10.5px;color:var(--c-text-faint)}
.nmos .insp .wrap{max-width:none;margin:0;padding:0;overflow-x:auto}
.nmos .insp table{width:100%;border-collapse:collapse;font-size:12.5px}
.nmos .insp th,.nmos .insp td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--c-line);vertical-align:top}
.nmos .insp th{font-weight:500;color:var(--c-text-faint);font-size:11.5px;letter-spacing:0.02em;white-space:nowrap}
.nmos .insp tr:hover td{background:rgba(255,255,255,0.02)}
.nmos .insp .chip{display:inline-block;padding:1px 6px;border-radius:3px;background:var(--c-raised);border:1px solid var(--c-line);font-size:11.5px;color:var(--c-text-soft)}
.nmos .insp span.rp{display:inline-flex;flex-wrap:wrap;align-items:center;gap:5px;margin-left:6px;vertical-align:middle}
.nmos .insp span.rp input,.nmos .insp span.rp select{width:auto;padding:3px 7px;font-size:11.5px;border-radius:3px}
.nmos .insp span.rp input[type=text]{width:12em}.nmos .insp span.rp input.turn{width:7em}
.nmos button.mini{padding:2px 8px;font-size:11.5px;border-radius:3px}
.nmos .inspbar{position:sticky;top:0;z-index:1;background:var(--c-bg);padding:10px 0;margin-top:4px}
.nmos .help{margin:8px 0 0}.nmos .help summary{cursor:pointer;color:var(--c-text-muted)}.nmos .help p{margin:6px 0 0}
.nmos .packet{margin:8px 0 0;max-height:420px;overflow:auto;background:var(--c-sunken);border:1px solid var(--c-line);border-radius:4px;padding:12px;font-family:ui-monospace,monospace;font-size:12px;line-height:1.6;color:var(--c-text-soft);white-space:pre-wrap;word-break:break-word}
.nmos .insp.busy{opacity:.5;transition:opacity .15s}
.nmos .insp details>summary{cursor:pointer;list-style:none}.nmos .insp details>summary::-webkit-details-marker{display:none}
.nmos .insp details>summary h2{display:inline-block}
.nmos .insp details>summary h2::before{content:"\u25B8 ";color:var(--c-text-ghost)}.nmos .insp details[open]>summary h2::before{content:"\u25BE "}
.nmos .insp .n{color:var(--c-text-muted);font-weight:400;font-size:11.5px}
.nmos .insp .toc{font-size:12.5px;line-height:1.9;margin:8px 0}.nmos .insp a.warn{color:var(--c-warn)}
.nmos .insp .who{display:flex;align-items:center;gap:8px;margin:10px 0}.nmos .insp .who select{width:auto;min-width:180px;padding:5px 8px}
.nmos .insp details.meta{font-size:11.5px;margin-top:2px;color:var(--c-text-muted)}.nmos .insp details.meta p{margin:4px 0}
.nmos .bar{position:sticky;bottom:0;background:${alpha("surface", 0.95)};backdrop-filter:blur(12px);border-top:1px solid var(--c-line-strong);padding:12px max(16px,calc((100% - 760px) / 2 + 16px));display:flex;align-items:center;gap:10px;flex-wrap:wrap;z-index:10}
.nmos .bar .text{flex:1;min-width:160px;font-size:12.5px}
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
    wrap.append(
      el("header", {}, el("h1", { text: L("title") }), language, close),
      el("nav", { class: "tabs" }, tabStatus, tabInspector, tabSettings)
    );
    const statusView = el("div");
    const inspectorView = el("div");
    const settingsView = el("div");
    wrap.append(statusView, inspectorView, settingsView);
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
          conn.append(el(
            "div",
            { class: "line warn" },
            el("span", { class: "dot warn" }),
            el("span", { text: L("status.plugin_mismatch", { mine: PLUGIN_BUILD, theirs: s.pluginExpected }) })
          ));
        } else if (s.pluginExpected) {
          conn.append(el("div", { class: "muted", text: L("status.plugin_ok", { b: PLUGIN_BUILD }) }));
        }
      } else {
        conn.append(
          el(
            "div",
            { class: "line" },
            el("span", { class: "dot err" }),
            el("span", { class: "err", text: `${L("status.unreachable")}: ${base}` })
          ),
          el("div", { class: "muted", text: s.error ?? "" }),
          el("p", { class: "sub", text: L("status.fix") })
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
        const what = s.last.outcome === "injected" ? L("outcome.injected", { n: s.last.packetChars }) : s.last.outcome === "nothing-relevant" ? L("outcome.nothing") : L("outcome.failed");
        lastCard.append(
          el("div", { class: "line" }, el("span", { class: `dot ${kind}` }), el("span", { text: what })),
          el("div", { class: "muted", text: `${L("status.ago", { n: Math.round((Date.now() - s.last.at) / 1e3) })} \xB7 ${s.last.ms}ms` })
        );
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
    const rebuildButton = el("button", { text: L("act.rebuild") });
    const deleteButton = el("button", { text: L("act.delete") });
    const exportButton = el("button", { text: L("exp.chat") });
    const actionMsg = el("div", { class: "msg" });
    const actions = el(
      "div",
      {},
      el("div", { class: "btns" }, historyButton, rebuildButton, exportButton, deleteButton),
      el("details", { class: "sub help" }, el("summary", { text: L("act.help") }), el("p", { text: L("act.sub") }))
    );
    const linkCard = el("div", { class: "card", style: "display:none" });
    const modeCard = el("div", { class: "card", style: "display:none" });
    const picked = /* @__PURE__ */ new Set();
    const chosen = /* @__PURE__ */ new Map();
    let closers = /* @__PURE__ */ new Map();
    const bulkClose = el("button");
    const bulkBar = el("div", { class: "btns", style: "display:none" }, bulkClose);
    inspectorView.append(
      el("div", { class: "btns inspbar" }, inspectorBack, inspectorRefresh),
      actions,
      actionMsg,
      bulkBar,
      modeCard,
      linkCard,
      inspectorBody,
      inspectorAddress
    );
    function updateBulk() {
      bulkBar.style.display = picked.size ? "" : "none";
      bulkClose.textContent = L("rp.bulk", { n: picked.size });
    }
    function outcomeOf(item) {
      const c = closers.get(item);
      const outcome = c?.selects[0]?.value ?? c?.first;
      return outcome ? { outcome } : {};
    }
    function repairControls(action) {
      if (action.kind === "thread_close") return closeControls(action);
      const n = action.kind === "fact_correct" ? L(action.extra === "object" ? "rp.field_object" : "rp.field_value") : action.extra ?? "";
      const button = el("button", { class: "mini", text: L(`rp.${action.kind}`, { n }) });
      const spot = el("div");
      button.addEventListener("click", () => {
        if (action.kind === "fact_correct") correctForm(action, button);
        else if (action.kind === "undo" && action.extra === "name_split") void undoSplit(action, button, spot);
        else if (action.kind === "alias_join") void aliasJoin(action, button, spot);
        else void repairNow(action, button);
      });
      return [button, spot];
    }
    function closeControls(action) {
      const item = action.item;
      const choices = closeOutcomes(action.extra);
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
      const field2 = action.extra === "object" ? "object" : "value";
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
      } else if (action.kind === "secret_found_out" || action.kind === "secret_keep") {
        body.character = action.extra;
      }
      button.disabled = true;
      try {
        await deps.api("POST", path, body, 15e3);
        picked.delete(action.item);
        updateBulk();
        say(actionMsg, L(action.kind === "undo" ? "rp.undone" : "rp.done"), "ok");
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
      for (const spot of Array.from(page.querySelectorAll("span.rp[data-repair]"))) {
        const action = repairAction(spot.getAttribute("data-repair"));
        if (action) spot.replaceChildren(...repairControls(action));
      }
      for (const item of Array.from(picked)) if (!closers.has(item)) picked.delete(item);
      updateBulk();
      for (const span of Array.from(page.querySelectorAll("span.ts[title]"))) {
        const shown2 = localTime(span.getAttribute("title") ?? "", lang);
        if (!shown2) continue;
        span.textContent = shown2.text;
        span.setAttribute("title", shown2.title);
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
    function go(path) {
      if (path === inspectorPath) return void showInspector();
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
      if (conversation !== actionConversation) {
        actionConversation = conversation;
        say(actionMsg, "");
        disarm();
        picked.clear();
        updateBulk();
      }
      actions.style.display = conversation ? "" : "none";
      const shownEntity = inspectorEntity(path);
      if (!shownEntity) linkCard.style.display = "none";
      if (!conversation || shownEntity) modeCard.style.display = "none";
      if (again) {
        inspectorBody.classList.add("busy");
      } else {
        shownPath = null;
        inspectorBody.replaceChildren(el("div", { class: "card muted", text: L("insp.loading") }));
      }
      const base = (await deps.getArg("sidecar_url") || "http://127.0.0.1:8790").replace(/\/+$/, "");
      const direct = routeFor(base, await deps.getArg("route")) === "direct";
      inspectorAddress.textContent = direct ? L("insp.browser", { url: `${base}/inspector${lang === "en" ? "?lang=en" : ""}` }) : "";
      try {
        const r = await deps.api("GET", `${path}${lang === "en" ? "?lang=en" : ""}`, void 0, 15e3);
        if (load !== loads) return;
        const page = safeFragment(r.html);
        enhance(page);
        inspectorBody.replaceChildren(page);
        shownPath = path;
        if (keep) restore(keep);
        else root.scrollTop = 0;
        if (shownEntity) void showLinks(shownEntity.conversation, shownEntity.entity, load);
        else if (conversation) void showMode(conversation, load);
      } catch (error) {
        if (load !== loads) return;
        shownPath = null;
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
        msg
      );
      modeCard.style.display = "";
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
    async function showLinks(conversation, entity, load) {
      let entities;
      try {
        entities = await deps.api("GET", `/v1/conversations/${conversation}/entities`, void 0, 15e3);
      } catch {
        entities = [];
      }
      if (load !== loads) return;
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
      const link = event.target instanceof Element ? event.target.closest("a") : null;
      if (!link) return;
      event.preventDefault();
      const href = link.getAttribute("href");
      const section = sectionTarget(href);
      const target = section ? inspectorBody.querySelector(`#${section}`) : null;
      if (target) {
        if (target instanceof HTMLDetailsElement) target.open = true;
        target.scrollIntoView({ block: "start", behavior: "smooth" });
        return;
      }
      const path = inspectorApiPath(href);
      if (path) go(path);
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
    settingsView.append(el(
      "div",
      { class: "card" },
      el("h2", { text: L("conn.title") }),
      el("p", { class: "sub", text: L("conn.sub") }),
      field(L("conn.url"), url),
      el("div", { class: "row" }, field(L("conn.route"), route), field(L("conn.budget"), reserved), field(L("conn.deadline"), deadline)),
      el("div", { class: "check" }, enabled, el("span", { text: L("conn.enabled") })),
      el("p", { class: "sub", text: L("conn.hint") }),
      el("p", { class: "sub", text: L("conn.deadline_hint") })
    ));
    function modelSection(kind, title, sub, presets) {
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
        if (p.url !== "custom") endpoint.value = fillProject(p.url, key.value);
        if (p.model) model.value = p.model;
        if (!p.url) model.value = "";
        say(msg, p.url.includes("{project}") ? L("model.vertex_hint") : "");
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
        test.disabled = true;
        say(msg, L("model.testing"));
        try {
          const r = await deps.api(
            "POST",
            "/v1/config/test",
            { kind, url: endpoint.value.trim(), model: model.value.trim(), api_key: key.value.trim() || void 0 }
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
        el("h2", { text: L(title) }),
        el("p", { class: "sub", text: L(sub) }),
        field(L("model.provider"), preset),
        field(L("model.endpoint"), endpoint),
        field(L("model.model"), model),
        list,
        field(L("model.key"), key),
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
    const llm = modelSection("llm", "llm.title", "llm.sub", LLM_PRESETS);
    const emb = modelSection("embeddings", "emb.title", "emb.sub", EMBED_PRESETS);
    const threshold = el("input", { type: "number", step: 0.05, min: 0.05, max: 1 });
    const minSim = el("input", { type: "number", step: 0.01, min: 0, max: 1 });
    const topK = el("input", { type: "number", min: 0, max: 20 });
    const factsLimit = el("input", { type: "number", min: 0, max: 30 });
    const backfill = el("input", { type: "number", min: 0, max: 5e3 });
    const summaries = el("input", { type: "checkbox" });
    const canonFacts = el("input", { type: "checkbox" });
    settingsView.append(el(
      "div",
      { class: "card" },
      el("h2", { text: L("tune.title") }),
      el("p", { class: "sub", text: L("tune.sub") }),
      el("div", { class: "row" }, field(L("tune.threshold"), threshold), field(L("tune.min_sim"), minSim)),
      el("div", { class: "row" }, field(L("tune.top_k"), topK), field(L("tune.facts"), factsLimit), field(L("tune.backfill"), backfill)),
      el("div", { class: "check" }, summaries, el("span", { text: L("tune.summaries") })),
      el("p", { class: "sub", text: L("tune.summaries_hint") }),
      el("div", { class: "check" }, canonFacts, el("span", { text: L("tune.canon_facts") })),
      el("p", { class: "sub", text: L("tune.canon_facts_hint") })
    ));
    const rules = el("textarea", { spellcheck: "false" });
    const example = el("button", { text: L("rules.example") });
    example.addEventListener("click", () => {
      rules.value = JSON.stringify(PARSER_EXAMPLE, null, 2);
      update();
    });
    settingsView.append(el(
      "div",
      { class: "card" },
      el("h2", { text: L("rules.title") }),
      el("p", { class: "sub", text: L("rules.sub") }),
      rules,
      el("div", { class: "btns" }, example)
    ));
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
      { class: "card" },
      el("h2", { text: L("exp.title") }),
      el("p", { class: "sub", text: L("exp.sub") }),
      el("div", { class: "check" }, exportEmbeddings, el("span", { text: L("exp.embeddings") })),
      el("div", { class: "btns" }, exportAll),
      exportMsg
    ));
    const barText = el("span", { class: "text muted" });
    const revert = el("button", { text: L("revert") });
    const save = el("button", { class: "primary", text: L("save") });
    const bar = el("div", { class: "bar" }, barText, revert, save);
    root.append(bar);
    function values() {
      return {
        conn: { url: url.value, route: route.value, enabled: enabled.checked, reserved: reserved.value, deadline: deadline.value },
        llm: llm.values(),
        emb: emb.values(),
        tune: {
          threshold: threshold.value,
          minSim: minSim.value,
          topK: topK.value,
          facts: factsLimit.value,
          backfill: backfill.value,
          summaries: summaries.checked,
          canonFacts: canonFacts.checked
        },
        rules: rules.value
      };
    }
    let baseline = values();
    let closing = false;
    const dirty = () => dirtySections(baseline, values());
    function update(message) {
      const d = dirty();
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
      hudBox.checked = Number(await deps.getArg("hud")) === 1;
    }
    function fillServer(cfg) {
      llm.fill(cfg.llm);
      emb.fill(cfg.embeddings);
      threshold.value = String(cfg.recall.threshold);
      minSim.value = String(cfg.recall.vector_min_sim);
      topK.value = String(cfg.recall.top_k);
      factsLimit.value = String(cfg.recall.facts_limit);
      backfill.value = String(cfg.extraction.backfill);
      summaries.checked = cfg.extraction.summaries !== false;
      canonFacts.checked = cfg.extraction.canon_facts !== false;
      rules.value = cfg.parsers.source === "ui" ? JSON.stringify(cfg.parsers.rules, null, 2) : "";
      rules.placeholder = cfg.parsers.source === "file" ? L("rules.from_file", { n: cfg.parsers.active_rules }) : L("rules.none");
    }
    async function loadAll() {
      await loadConn();
      try {
        fillServer(await deps.api("GET", "/v1/config", void 0, 5e3));
      } catch {
      }
      baseline = values();
      update();
    }
    async function saveAll() {
      const d = dirty();
      if (!d.length) {
        update({ text: L("no_changes"), kind: "muted" });
        return true;
      }
      save.disabled = true;
      say(barText, L("saving"));
      const v = values();
      if (d.includes("conn")) {
        const args = connArgs(v.conn);
        for (const [k, value] of Object.entries(args)) await deps.setArg(k, value);
        reserved.value = String(args.reserved_memory_tokens);
        deadline.value = String(args.deadline_ms);
        baseline = { ...baseline, conn: values().conn };
      }
      const body = configBody(d, v);
      if (!Object.keys(body).length) {
        update({ text: L("saved"), kind: "ok" });
        return true;
      }
      try {
        const r = await deps.api("PUT", "/v1/config", body);
        fillServer(r);
        baseline = values();
        const parts = [r.queued_jobs ? L("saved_queued", { n: r.queued_jobs }) : L("saved")];
        if (r.queued_jobs) deps.hud.background();
        if (d.includes("rules") && r.parsers.active_rules) parts.push(L("saved_rules", { n: r.parsers.active_rules }));
        update({ text: parts.join(" "), kind: "ok" });
        return true;
      } catch (error) {
        const text2 = errorText(lang, error);
        update({ text: d.includes("conn") ? L("conn_saved_server_failed", { e: text2 }) : text2, kind: "err" });
        return false;
      }
    }
    save.addEventListener("click", () => void saveAll());
    revert.addEventListener("click", () => void loadAll());
    function shut() {
      root.remove();
      current = null;
      void deps.hide();
    }
    close.addEventListener("click", () => {
      if (!dirty().length || closing) return shut();
      closing = true;
      const saveClose = el("button", { class: "primary", text: L("save_and_close") });
      const discard = el("button", { text: L("discard_and_close") });
      const cancel = el("button", { text: L("cancel") });
      const restore2 = () => {
        closing = false;
        bar.replaceChildren(barText, revert, save);
        update();
      };
      saveClose.addEventListener("click", async () => {
        if (await saveAll()) shut();
        else restore2();
      });
      discard.addEventListener("click", shut);
      cancel.addEventListener("click", restore2);
      select("settings");
      bar.replaceChildren(el("span", { class: "text warn", text: L("close_unsaved") }), cancel, discard, saveClose);
    });
    language.addEventListener("change", async () => {
      if (dirty().length) {
        language.value = lang;
        select("settings");
        update({ text: L("lang_unsaved"), kind: "warn" });
        return;
      }
      const next = langOf(language.value);
      await deps.setArg("language", next);
      root.remove();
      current = await render(deps, next, shown);
    });
    function select(next) {
      shown = next;
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
      root.classList.toggle("wide", next === "inspector");
      if (next === "status") void refreshStatus();
      if (next === "inspector") void showInspector();
    }
    tabStatus.addEventListener("click", () => select("status"));
    tabInspector.addEventListener("click", () => select("inspector"));
    tabSettings.addEventListener("click", () => select("settings"));
    document.body.append(root);
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
        offChats: parseChatIds(await arg(CHAT_OFF_ARG))
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
    console.log("[NMOS] adapter loaded", { version: "0.3.0" });
  })().catch((error) => console.error("[NMOS] adapter failed to load", error));
})();
