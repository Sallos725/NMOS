"""Runtime configuration: environment defaults overridden by values saved from the plugin UI.

Only these keys are editable at runtime; everything else (database, bind address, auth) stays in the
environment. API keys are write-only through the API.
"""

from __future__ import annotations

import dataclasses
import json
import time
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from .config import Settings
from .llm import ChatModel, Embedder, LLMError
from .parsers import RuleSet, compile_rules, load_rules

EDITABLE: dict[str, type] = {
    "llm_url": str, "llm_model": str, "llm_api_key": str, "llm_json_mode": bool,
    "embed_url": str, "embed_model": str, "embed_api_key": str, "embed_query_instruction": str,
    "recall_threshold": float, "vector_min_sim": float, "recall_top_k": int, "facts_limit": int,
    "extract_backfill": int,
}
SECRET = {"llm_api_key", "embed_api_key"}
RANGES = {"recall_threshold": (0.05, 1.0), "vector_min_sim": (0.0, 1.0), "recall_top_k": (0, 20),
          "facts_limit": (0, 30), "extract_backfill": (0, 5000)}
PARSERS_KEY = "parsers"


def stored(conn: psycopg.Connection) -> dict[str, Any]:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM app_config").fetchall()}


def effective(base: Settings, overrides: dict[str, Any]) -> Settings:
    changes = {k: v for k, v in overrides.items() if k in EDITABLE}
    return dataclasses.replace(base, **changes)


def ruleset(base: Settings, overrides: dict[str, Any]) -> RuleSet:
    if PARSERS_KEY in overrides:
        return compile_rules(overrides[PARSERS_KEY])
    return load_rules(base.parsers_file)


def validate_update(update: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    clean: dict[str, Any] = {}
    errors: list[str] = []
    for key, value in update.items():
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
        try:
            coerced = kind(value) if kind is not bool else bool(value)
        except (TypeError, ValueError):
            errors.append(f"{key}: expected {kind.__name__}")
            continue
        if key in RANGES and not RANGES[key][0] <= coerced <= RANGES[key][1]:
            errors.append(f"{key}: must be between {RANGES[key][0]} and {RANGES[key][1]}")
            continue
        if key.endswith("_url") and coerced and not coerced.startswith(("http://", "https://")):
            errors.append(f"{key}: must start with http:// or https://")
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
        "llm": {"url": settings.llm_url, "model": settings.llm_model, "api_key_set": bool(settings.llm_api_key),
                "json_mode": settings.llm_json_mode},
        "embeddings": {"url": settings.embed_url, "model": settings.embed_model,
                       "api_key_set": bool(settings.embed_api_key),
                       "query_instruction": settings.embed_query_instruction},
        "recall": {"threshold": settings.recall_threshold, "vector_min_sim": settings.vector_min_sim,
                   "top_k": settings.recall_top_k, "facts_limit": settings.facts_limit},
        "extraction": {"backfill": settings.extract_backfill},
        "parsers": {"rules": overrides.get(PARSERS_KEY) if PARSERS_KEY in overrides else None,
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
        return {"ok": False, "ms": round((time.perf_counter() - started) * 1000), "error": str(exc)}


def test_embeddings(url: str, model: str, api_key: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        (vec,) = Embedder(url, model, api_key).embed(["기억 테스트 문장입니다."], timeout_s=60)
        return {"ok": True, "ms": round((time.perf_counter() - started) * 1000), "dimensions": len(vec)}
    except LLMError as exc:
        return {"ok": False, "ms": round((time.perf_counter() - started) * 1000), "error": str(exc)}


def list_models(url: str, api_key: str) -> dict[str, Any]:
    import httpx

    try:
        res = httpx.get(f"{url.rstrip('/')}/models", headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                        timeout=15)
        res.raise_for_status()
        ids = sorted({str(m.get("id")) for m in res.json().get("data", []) if m.get("id")})
        return {"ok": True, "models": ids[:500]}
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        return {"ok": False, "error": str(exc)[:300], "models": []}
