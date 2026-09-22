"""Deterministic state parsers (D10). Rules come from a JSON file; parsing is pure and cheap."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("nmos.parsers")

KV_LINE = re.compile(r"^\s*[-*•·]?\s*(?P<key>[^:：=|｜\n]{1,60}?)\s*[:：=|｜]\s*(?P<value>.+?)\s*$")
MAX_VALUE = 500


@dataclass(frozen=True)
class Rule:
    id: str
    kind: str  # "regex" | "block"
    pattern: re.Pattern[str] | None = None
    start: re.Pattern[str] | None = None
    end: re.Pattern[str] | None = None
    key: str | None = None
    prefix: str = ""
    role: str | None = None
    character: str | None = None
    entity_line: re.Pattern[str] | None = None  # block rules: a line like "[하나]" switches the entity


@dataclass(frozen=True)
class RuleSet:
    rules: tuple[Rule, ...]
    version: str
    errors: tuple[str, ...] = ()


EMPTY = RuleSet(rules=(), version="none")


def compile_rules(spec: Any) -> RuleSet:
    raw = json.dumps(spec, sort_keys=True, ensure_ascii=False)
    items = spec.get("rules", []) if isinstance(spec, dict) else []
    rules: list[Rule] = []
    errors: list[str] = []
    for i, item in enumerate(items):
        rid = str(item.get("id") or f"rule{i}")
        try:
            kind = item.get("kind")
            common = {"id": rid, "kind": kind, "prefix": str(item.get("prefix", "")),
                      "role": item.get("role"), "character": item.get("character")}
            if kind == "regex":
                pattern = re.compile(item["pattern"], re.MULTILINE)
                names = set(pattern.groupindex)
                if "value" not in names or ("key" not in names and not item.get("key")):
                    raise ValueError("regex rule needs a 'value' group and a 'key' group or key field")
                rules.append(Rule(pattern=pattern, key=item.get("key"), **common))
            elif kind == "block":
                entity_line = re.compile(item["entity_line"]) if item.get("entity_line") else None
                if entity_line is not None and "entity" not in entity_line.groupindex:
                    raise ValueError("entity_line needs an 'entity' group")
                rules.append(Rule(start=re.compile(item["start"], re.MULTILINE),
                                  end=re.compile(item["end"], re.MULTILINE), entity_line=entity_line, **common))
            else:
                raise ValueError(f"unknown kind {kind!r}")
        except (KeyError, ValueError, re.error) as exc:
            errors.append(f"{rid}: {exc}")
    version = hashlib.sha256(raw.encode()).hexdigest()[:16] if rules else "none"
    return RuleSet(rules=tuple(rules), version=version, errors=tuple(errors))


def load_rules(path: str | None) -> RuleSet:
    if not path:
        return EMPTY
    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("parser rules %s not loaded: %s", path, exc)
        return RuleSet(rules=(), version="none", errors=(str(exc),))
    ruleset = compile_rules(spec)
    for error in ruleset.errors:
        log.error("parser rule skipped: %s", error)
    log.info("loaded %d parser rules (version %s)", len(ruleset.rules), ruleset.version)
    return ruleset


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()[:MAX_VALUE]


def _key(rule: Rule, key: str, entity: str | None) -> str:
    key = rule.prefix + _clean(key)
    entity = _clean(entity or "")
    return f"{entity}.{key}" if entity else key


def parse(ruleset: RuleSet, content: str, role: str | None, character: str | None) -> list[tuple[str, str, str]]:
    """(rule_id, key, value) pairs found in one message. Later matches of a key win.

    Keys are "<entity>.<key>" when a rule captures an entity (sim bots: one card, many characters)."""
    out: dict[str, tuple[str, str, str]] = {}
    for rule in ruleset.rules:
        if rule.role and rule.role != role:
            continue
        if rule.character and rule.character != character:
            continue
        if rule.kind == "regex" and rule.pattern:
            for m in rule.pattern.finditer(content):
                key = rule.key or m.group("key")
                value = m.group("value")
                if key and value is not None:
                    k = _key(rule, key, m.groupdict().get("entity"))
                    out[k] = (rule.id, k, _clean(value))
        elif rule.kind == "block" and rule.start and rule.end:
            pos = 0
            while (s := rule.start.search(content, pos)) is not None:
                e = rule.end.search(content, s.end())
                block = content[s.end(): e.start() if e else len(content)]
                entity = s.groupdict().get("entity")
                for line in block.splitlines():
                    line = _clean(line)
                    if rule.entity_line and (em := rule.entity_line.fullmatch(line.strip())):
                        entity = em.group("entity")
                        continue
                    m = KV_LINE.match(line)
                    if m:
                        k = _key(rule, m.group("key").strip(), entity)
                        out[k] = (rule.id, k, m.group("value").strip()[:MAX_VALUE])
                pos = e.end() if e else len(content)
    return list(out.values())
