"""Runtime configuration: environment defaults overridden by values saved from the plugin UI.

Only these keys are editable at runtime; everything else (database, bind address, auth) stays in the
environment. API keys are write-only through the API, and a saved key is only ever sent to the host it was
saved for: a connection test or model list for another host goes without it, and moving an endpoint to another
host drops it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import psycopg
from psycopg.types.json import Jsonb

from .config import Settings
from . import vertex
from .llm import ChatModel, Embedder, LLMError, chat_headers
from .parsers import RuleSet, compile_rules, load_rules

EDITABLE: dict[str, type] = {
    "llm_url": str, "llm_model": str, "llm_api_key": str, "llm_json_mode": bool,
    "embed_url": str, "embed_model": str, "embed_api_key": str, "embed_query_instruction": str,
    "embed_timeout_ms": int,  # a slow or remote embedder needs more than the 300 ms default (K34)
    "recall_threshold": float, "vector_min_sim": float, "recall_top_k": int, "facts_limit": int,
    "events_limit": int, "threads_limit": int,
    "extract_backfill": int, "summaries": bool, "canon_facts": bool,
}
SECRET = {"llm_api_key", "embed_api_key"}
KEY_HOSTS = {"llm_api_key": "llm_url", "embed_api_key": "embed_url"}  # each key belongs to its endpoint's host
RANGES = {"recall_threshold": (0.05, 1.0), "vector_min_sim": (0.0, 1.0), "recall_top_k": (0, 20),
          "facts_limit": (0, 30), "events_limit": (0, 30), "threads_limit": (0, 10), "extract_backfill": (0, 5000),
          "embed_timeout_ms": (100, 5000)}
PARSERS_KEY = "parsers"
PRESETS_KEY = "parser_presets"
PARSER_MAX_BYTES = 256_000
PARSER_MAX_RULES = 100


def parser_spec(base: Settings, overrides: dict[str, Any], *, strict: bool = False) -> Any:
    """The original document remains visible even when legacy rules cannot activate."""
    if PARSERS_KEY in overrides:
        return overrides[PARSERS_KEY]
    if base.parsers_file:
        try:
            return json.loads(Path(base.parsers_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            if strict:
                raise ValueError("existing parser file cannot be read; repair it before applying a card") from exc
    return {"rules": []}


def template_errors(rules: Any) -> list[str]:
    if not isinstance(rules, list) or len(rules) > PARSER_MAX_RULES:
        return [f"rules must be a list of at most {PARSER_MAX_RULES} rules"]
    if len(json.dumps(rules, ensure_ascii=False).encode()) > PARSER_MAX_BYTES:
        return [f"rules must be at most {PARSER_MAX_BYTES} bytes"]
    return list(compile_rules({"rules": rules}, template=True).errors)


def preset_errors(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 50:
        return ["presets must be a list of at most 50 presets"]
    if len(json.dumps(value, ensure_ascii=False).encode()) > PARSER_MAX_BYTES:
        return [f"presets must be at most {PARSER_MAX_BYTES} bytes"]
    names: set[str] = set()
    errors: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            errors.append("preset must be an object")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not 0 < len(name.strip()) <= 100 or name != name.strip():
            errors.append("preset name must be 1 to 100 characters without surrounding whitespace")
        elif name in names:
            errors.append(f"duplicate preset name: {name}")
        else:
            names.add(name)
        errors.extend(template_errors(item.get("rules")))
    return errors


def bind_card(spec: Any, card: str, rules: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace one exact display-name binding; template IDs are stable within a card namespace."""
    namespace = "card-" + hashlib.sha256(card.encode()).hexdigest()[:16] + ":"
    bound = []
    for index, rule in enumerate(rules):
        rid = str(rule.get("id") or f"rule{index}")
        # Reapplying an exported binding is idempotent; each slot remains distinct for duplicate template IDs.
        marker = f"{namespace}{index}:"
        bound.append({**rule, "id": rid if rid.startswith(marker) else marker + rid, "card": card})
    if not isinstance(spec, dict) or not isinstance(spec.get("rules"), list):
        raise ValueError("existing parser document is malformed; repair it before applying a card")
    return {**spec, "rules": [r for r in spec["rules"] if not isinstance(r, dict) or r.get("card") != card] + bound}


def lock_config(conn: psycopg.Connection) -> None:
    # Serializes merges even before app_config has a parsers row, and across separate API processes.
    conn.execute("SELECT pg_advisory_xact_lock(73490392)")


def stored(conn: psycopg.Connection) -> dict[str, Any]:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM app_config").fetchall()}


def effective(base: Settings, overrides: dict[str, Any]) -> Settings:
    changes = {k: v for k, v in overrides.items() if k in EDITABLE}
    return dataclasses.replace(base, **changes)


def origin(url: str) -> str:
    """The host an API key belongs to: scheme, host name and port of an endpoint URL."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    return f"{scheme}://{(parts.hostname or '').lower()}:{port or {'http': 80, 'https': 443}.get(scheme)}"


def saved_key_for(url: str, saved_url: str, saved_key: str) -> str:
    """The saved key when `url` is on the host it was saved for (or empty: the saved endpoint), else none."""
    return saved_key if not url or origin(url) == origin(saved_url) else ""


def withheld_note(saved_url: str) -> str:
    return f" (the saved API key is only sent to {origin(saved_url)}; enter the key to use it with this host)"


def keys_follow_hosts(base: Settings, overrides: dict[str, Any], clean: dict[str, Any]) -> dict[str, Any]:
    """`clean` with each saved API key dropped when the update moves its endpoint to another host without a
    new key; the environment's key comes back when the endpoint returns to the environment's host."""
    merged = dict(overrides)
    for key, value in clean.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    before, after = effective(base, overrides), effective(base, merged)
    out = dict(clean)
    for key, url in KEY_HOSTS.items():
        host = origin(getattr(after, url))
        if key in clean or host == origin(getattr(before, url)):
            continue
        if host == origin(getattr(base, url)):
            if key in merged:
                out[key] = None  # back on the environment's host: its key applies again
        elif getattr(after, key):
            out[key] = ""
    return out


def ruleset(base: Settings, overrides: dict[str, Any]) -> RuleSet:
    if PARSERS_KEY in overrides:
        return compile_rules(overrides[PARSERS_KEY])
    return load_rules(base.parsers_file)


_TYPE_NAMES = {bool: "a JSON boolean", int: "an integer", float: "a number", str: "a string"}


def _typed(kind: type, value: Any) -> Any:
    """The value as `kind` when its JSON type already is `kind` (an integral number counts as an
    integer, any number as a float), else None. No truthiness or string parsing (#19)."""
    if kind is bool:
        return value if isinstance(value, bool) else None
    if isinstance(value, bool):
        return None  # bool is an int subclass: true is not 1 here
    if kind is int:
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value if isinstance(value, int) else None
    if kind is float:
        return float(value) if isinstance(value, (int, float)) else None
    return value if isinstance(value, str) else None


def validate_update(update: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    clean: dict[str, Any] = {}
    errors: list[str] = []
    for key, value in update.items():
        if key == PRESETS_KEY:
            errors.extend(f"parser_presets: {e}" for e in preset_errors(value))
            clean[key] = value
            continue
        if key == PARSERS_KEY:
            if value is None:
                clean[key] = None
                continue
            spec = value
            if isinstance(value, str):
                try:
                    spec = json.loads(value) if value.strip() else {"rules": []}
                except json.JSONDecodeError as exc:
                    errors.append(f"parsers: invalid JSON ({exc})")
                    continue
            rs = compile_rules(spec)
            errors += [f"parsers: {e}" for e in rs.errors]
            clean[key] = spec
            continue
        kind = EDITABLE.get(key)
        if kind is None:
            errors.append(f"{key}: not editable")
            continue
        if value is None:
            clean[key] = None  # reset to the environment default
            continue
        coerced = _typed(kind, value)
        if coerced is None:
            errors.append(f"{key}: expected {_TYPE_NAMES[kind]}, got {type(value).__name__} {value!r:.40}")
            continue
        if key in RANGES and not RANGES[key][0] <= coerced <= RANGES[key][1]:
            errors.append(f"{key}: must be between {RANGES[key][0]} and {RANGES[key][1]}")
            continue
        if key.endswith("_url") and coerced and not coerced.startswith(("http://", "https://")):
            errors.append(f"{key}: must start with http:// or https://")
            continue
        if key.endswith("_url") and "{project}" in coerced:
            errors.append(f"{key}: replace {{project}} with your Google Cloud project ID")
            continue
        if key == "llm_api_key":
            try:
                vertex.check_key(coerced)
            except vertex.VertexAuthError as exc:
                errors.append(f"{key}: {exc}")
                continue
        if key == "embed_api_key" and coerced.strip().startswith("{"):
            errors.append(f"{key}: service-account JSON keys are supported for the extraction LLM only")
            continue
        clean[key] = coerced.strip() if isinstance(coerced, str) else coerced
    return clean, errors


def save(conn: psycopg.Connection, clean: dict[str, Any]) -> None:
    for key, value in clean.items():
        if value is None:
            conn.execute("DELETE FROM app_config WHERE key = %s", (key,))
        else:
            conn.execute(
                "INSERT INTO app_config (key, value, updated_at) VALUES (%s, %s, now())"
                " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                (key, Jsonb(value)),
            )


def public_view(settings: Settings, overrides: dict[str, Any], rules: RuleSet) -> dict[str, Any]:
    """Settings as the UI sees them. Secrets are reported as set/unset only."""
    return {
        "install": settings.install or None,  # `bundle` from the portable launcher: the panel's Ollama address
        "llm": {"url": settings.llm_url, "model": settings.llm_model, "api_key_set": bool(settings.llm_api_key),
                "json_mode": settings.llm_json_mode},
        "embeddings": {"url": settings.embed_url, "model": settings.embed_model,
                       "api_key_set": bool(settings.embed_api_key),
                       "query_instruction": settings.embed_query_instruction},
        "recall": {"threshold": settings.recall_threshold, "vector_min_sim": settings.vector_min_sim,
                   "embed_timeout_ms": settings.embed_timeout_ms,
                   "top_k": settings.recall_top_k, "facts_limit": settings.facts_limit,
                   "events_limit": settings.events_limit,
                   "threads_limit": settings.threads_limit},
        "extraction": {"backfill": settings.extract_backfill, "summaries": settings.summaries,
                       "canon_facts": settings.canon_facts},
        "parsers": {"rules": overrides.get(PARSERS_KEY) if PARSERS_KEY in overrides else None,
                    "spec": parser_spec(settings, overrides), "presets": overrides.get(PRESETS_KEY, []),
                    "source": "ui" if PARSERS_KEY in overrides else ("file" if settings.parsers_file else "none"),
                    "active_rules": len(rules.rules), "errors": list(rules.errors)},
        "overridden": sorted(overrides),
    }


def test_llm(url: str, model: str, api_key: str, json_mode: bool) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        parsed, _ = ChatModel(url, model, api_key, timeout_s=60, json_mode=json_mode).complete_json(
            "Reply with JSON only.", 'Return exactly {"ok": true, "language": "<the language of: 안녕하세요>"}')
        return {"ok": bool(parsed.get("ok")), "ms": round((time.perf_counter() - started) * 1000), "reply": parsed}
    except LLMError as exc:
        error = str(exc)
        if "aiplatform.endpoints.predict" in error:  # Vertex: enabling the APIs does not grant this (ADR 0022)
            error = ("Vertex refused: the service account in this key needs the Vertex AI User role "
                     "(roles/aiplatform.user) on its project; enabling the APIs is not enough. " + error)
        return {"ok": False, "ms": round((time.perf_counter() - started) * 1000), "error": error}


def test_embeddings(url: str, model: str, api_key: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        (vec,) = Embedder(url, model, api_key).embed(["기억 테스트 문장입니다."], timeout_s=60)
        return {"ok": True, "ms": round((time.perf_counter() - started) * 1000), "dimensions": len(vec)}
    except LLMError as exc:
        return {"ok": False, "ms": round((time.perf_counter() - started) * 1000), "error": str(exc)}


def list_models(url: str, api_key: str, kind: str = "llm") -> dict[str, Any]:
    import httpx

    try:
        info = vertex.service_account_info(api_key) if kind == "llm" else None
        if info is not None and vertex.catalog_target(url):  # Vertex has no `/models` (ADR 0022 amendment 1)
            return {"ok": True, "models": vertex.list_models(info, url)[:500]}
        headers = chat_headers(api_key) if kind == "llm" else ({"Authorization": f"Bearer {api_key}"} if api_key else {})
        res = httpx.get(f"{url.rstrip('/')}/models", headers=headers, timeout=15)
        res.raise_for_status()
        ids = sorted({str(m.get("id")) for m in res.json().get("data", []) if m.get("id")})
        return {"ok": True, "models": ids[:500]}
    except (LLMError, vertex.VertexAuthError) as exc:
        return {"ok": False, "error": str(exc)[:300], "models": []}
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        return {"ok": False, "error": str(exc)[:300], "models": []}
