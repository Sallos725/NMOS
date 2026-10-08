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
    # PHASE-39 Q1: block rules: the text between start and end is split by this string instead of by lines, so a
    # one-line status bar ("[Status:a=1|b=2]", "☆ [A: 1 | B: 2]") is read field by field.
    separator: str | None = None
    # PHASE-39 Q2: the rule reads only the chats of this card (the conversation's character name), exactly.
    card: str | None = None
    # PHASE-39 Q4: keys whose changes without a cause in the reply are flagged ("Needs attention"); reading is unchanged.
    watch: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RuleSet:
    rules: tuple[Rule, ...]
    version: str
    errors: tuple[str, ...] = ()


EMPTY = RuleSet(rules=(), version="none")


WATCH_MAX = 40  # watched keys per rule


def _watch_ok(watch: Any) -> bool:
    return (isinstance(watch, list) and len(watch) <= WATCH_MAX
            and all(isinstance(k, str) and 0 < len(k.strip()) <= 60 for k in watch))


def _version_spec(spec: Any) -> Any:
    """The rules as reading depends on them: a valid `watch` changes what is flagged, not what is read (PHASE-39 Q4), so
    it keeps the rules' version and the stored observations. One that is not valid leaves its rule out, so it counts:
    the rule is read again once it is fixed."""
    if not isinstance(spec, dict) or not isinstance(spec.get("rules"), list):
        return spec
    return {**spec, "rules": [{k: v for k, v in r.items() if k != "watch"}
                              if isinstance(r, dict) and _watch_ok(r.get("watch", [])) else r for r in spec["rules"]]}


def compile_rules(spec: Any) -> RuleSet:
    raw = json.dumps(_version_spec(spec), sort_keys=True, ensure_ascii=False)
    items = spec.get("rules", []) if isinstance(spec, dict) else []
    rules: list[Rule] = []
    errors: list[str] = []
    for i, item in enumerate(items):
        rid = str(item.get("id") or f"rule{i}")
        try:
            kind = item.get("kind")
            card = item.get("card")
            if card is not None and (not isinstance(card, str) or not card.strip()):
                raise ValueError("card must be a character name")
            watch = item.get("watch", [])
            if not _watch_ok(watch):
                raise ValueError(f"watch must be a list of at most {WATCH_MAX} keys")
            common = {"id": rid, "kind": kind, "prefix": str(item.get("prefix", "")),
                      "role": item.get("role"), "character": item.get("character"), "card": card,
                      "watch": frozenset(k.strip() for k in watch)}
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
                start = re.compile(item["start"], re.MULTILINE)
                if start.search("") is not None:  # it would start a block everywhere (PHASE-39: a hung sync)
                    raise ValueError("start must not match empty text")
                separator = item.get("separator")
                if separator is not None and (not isinstance(separator, str) or not 1 <= len(separator) <= 8):
                    raise ValueError("separator must be a string of 1 to 8 characters")
                rules.append(Rule(start=start,
                                  end=re.compile(item["end"], re.MULTILINE), entity_line=entity_line,
                                  separator=separator, **common))
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


def _past(pos: int, end: int) -> int:
    """Where the next block search starts: after this block, and always further than the last search (a start and an
    end that match empty text, as a lookahead does, would otherwise search the same place forever)."""
    return end if end > pos else pos + 1


def needs_card(ruleset: RuleSet) -> bool:
    return any(rule.card for rule in ruleset.rules)


def watched(ruleset: RuleSet) -> dict[str, frozenset[str]]:
    """Each rule's watched keys (PHASE-39 Q4), for the rules that have some."""
    return {rule.id: rule.watch for rule in ruleset.rules if rule.watch}


def _applies(rule: Rule, role: str | None, character: str | None, card: str | None) -> bool:
    return not ((rule.role and rule.role != role) or (rule.character and rule.character != character)
                or (rule.card and rule.card != card))


def prose(ruleset: RuleSet, content: str, role: str | None, character: str | None, card: str | None = None) -> str:
    """The message without what the rules read: each regex match and each block from its start to its end mark
    (PHASE-39 Q4: whether the story itself says what a bar changed)."""
    spans: list[tuple[int, int]] = []
    for rule in ruleset.rules:
        if not _applies(rule, role, character, card):
            continue
        if rule.kind == "regex" and rule.pattern:
            spans += [m.span() for m in rule.pattern.finditer(content)]
        elif rule.kind == "block" and rule.start and rule.end:
            pos = 0
            while (s := rule.start.search(content, pos)) is not None:
                e = rule.end.search(content, s.end())
                spans.append((s.start(), e.end() if e else len(content)))
                pos = _past(pos, e.end() if e else len(content))
    out, at = [], 0
    for a, b in sorted(spans):
        if a > at:
            out.append(content[at:a])
        at = max(at, b)
    out.append(content[at:])
    return "".join(out)


def parse(ruleset: RuleSet, content: str, role: str | None, character: str | None,
          card: str | None = None) -> list[tuple[str, str, str]]:
    """(rule_id, key, value) pairs found in one message. Later matches of a key win. `card`: the chat's character
    name, for rules bound to one card.

    Keys are "<entity>.<key>" when a rule captures an entity (sim bots: one card, many characters)."""
    out: dict[str, tuple[str, str, str]] = {}
    for rule in ruleset.rules:
        if not _applies(rule, role, character, card):
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
                for line in (block.split(rule.separator) if rule.separator else block.splitlines()):
                    line = _clean(line.replace("\n", " ") if rule.separator else line)
                    if rule.entity_line and (em := rule.entity_line.fullmatch(line.strip())):
                        entity = em.group("entity")
                        continue
                    m = KV_LINE.match(line)
                    if m:
                        k = _key(rule, m.group("key").strip(), entity)
                        out[k] = (rule.id, k, m.group("value").strip()[:MAX_VALUE])
                pos = _past(pos, e.end() if e else len(content))
    return list(out.values())
