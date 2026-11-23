"""PHASE-60 S6 (ADR 0085): `api.view_of` reads the chat's carry link in force for panel and Inspector views.

Stub extractor only; synthetic names 세라, 카이토, 하나, 유나, 도현, 유찬."""

from __future__ import annotations

from typing import Any

import pytest

from conftest import make_client
from nmos_sidecar import api, facts
from simchat import SimChat
from test_extraction import drain as drain_extract
from test_generations import conv_id
from test_phase60_carry_take import ON, _build_source_chat, _fact, _stub_extract
from test_sidecar_integration import sync

SOURCE_LABELS = {"character_name": "세라", "chat_name": "항구의 밤", "persona_name": "도현"}
TARGET_TURN_0 = "유찬은 아침 항구 광장에 도착했고 건강한 상태다."


def _stub_both(system: str, user: str) -> tuple[dict, str, dict]:
    ans, raw, used = _stub_extract(system, user)
    target = user.split("TARGET turn", 1)[-1]
    if TARGET_TURN_0 in target:
        rows = list(ans.get("assertions") or [])
        rows += [
            _fact("유찬", "located_in", None, "항구 광장", "place", evidence="항구 광장에 도착했고"),
            _fact("유찬", "has_status", "건강함", evidence="건강한 상태다"),
        ]
        return {"assertions": rows}, raw, used
    return ans, raw, used


def _setup(c, migrated: str) -> tuple[str, str]:
    src_sim = _build_source_chat(4)
    sync(c, src_sim, **SOURCE_LABELS)

    tgt_sim = SimChat("tgt-view-chat")
    tgt_sim.user("새 이야기를 시작한다.")
    tgt_sim.reply(TARGET_TURN_0)
    tgt_sim.user("둘러보자.")
    sync(c, tgt_sim, character_name="세라", chat_name="새 이야기", persona_name="유찬")

    drain_extract(migrated, _stub_both)
    return conv_id(c, src_sim), conv_id(c, tgt_sim)


def test_continue_link_shows_carried_facts_and_unlink_restores_byte_identical_json(migrated: str) -> None:
    """With any packet policy (here the default packet-v19), a linked target's `/facts` (and related views) carries
    the link's rows flagged `carried`; removing the link returns byte-identical JSON to before linking."""
    with make_client(migrated, **ON) as c:
        src, tgt = _setup(c, migrated)

        before_facts = c.get(f"/v1/conversations/{tgt}/facts")
        before_history = c.get(f"/v1/conversations/{tgt}/facts", params={"history": True})
        before_entities = c.get(f"/v1/conversations/{tgt}/entities")
        before_threads = c.get(f"/v1/conversations/{tgt}/threads")
        assert before_facts.status_code == 200
        assert before_facts.json()  # target has its own extracted facts
        assert all("carried" not in f and "carried_from" not in f for f in before_facts.json())

        made = c.post(f"/v1/conversations/{tgt}/carry",
                      json={"source_conversation_id": src, "mode": "continue"}).json()["link"]
        link_id = made["id"]

        linked_facts = c.get(f"/v1/conversations/{tgt}/facts")
        assert linked_facts.status_code == 200
        rows = linked_facts.json()
        carried_rows = [f for f in rows if f.get("carried") == link_id]
        own_rows = [f for f in rows if "carried" not in f]
        assert carried_rows
        assert own_rows
        assert any(f["subject"] == "세라" and f["predicate"] == "located_in" and f["object"] == "등대"
                   for f in carried_rows)
        assert any(f["subject"] == "하나" and f["predicate"] == "located_in" and f["object"] == "항구 시장"
                   for f in carried_rows)
        for f in carried_rows:
            assert f["turn"] == -1
            assert f["carried_from"]["conversation"] == src
        assert any(f["predicate"] == "has_status" and f["value"] == "건강함" for f in own_rows)

        entities = c.get(f"/v1/conversations/{tgt}/entities").json()
        assert any(e["name"] == "하나" for e in entities)
        threads = c.get(f"/v1/conversations/{tgt}/threads").json()
        assert any("등대 열쇠" in (t.get("text") or "") for t in threads)
        assert c.get(f"/inspector/c/{tgt}").status_code == 200

        assert c.delete(f"/v1/conversations/{tgt}/carry").status_code == 200
        assert c.get(f"/v1/conversations/{tgt}/facts").content == before_facts.content
        assert c.get(f"/v1/conversations/{tgt}/facts", params={"history": True}).content == before_history.content
        assert c.get(f"/v1/conversations/{tgt}/entities").content == before_entities.content
        assert c.get(f"/v1/conversations/{tgt}/threads").content == before_threads.content


def test_unlinked_chat_makes_identical_memory_view_call_and_regression_keeps_flags(
    migrated: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unlinked chat calls `memory_view` with no `carried` argument and has no `carried`/`regression` keys;
    a linked chat passes `carried` and keeps the view's `carried` and `regression` keys (regression rows stay out of
    `/facts`)."""
    calls: list[tuple[dict[str, Any], set[str], dict[str, Any] | None, int]] = []
    real_memory_view = facts.memory_view

    def spy_memory_view(*args: Any, **kwargs: Any) -> dict[str, Any]:
        out = real_memory_view(*args, **kwargs)
        calls.append((dict(kwargs), set(out.keys()), out.get("carried"), len(out.get("regression") or ())))
        return out

    monkeypatch.setattr(api, "memory_view", spy_memory_view)

    with make_client(migrated, **ON) as c:
        src, tgt = _setup(c, migrated)

        # Unlinked target: identical call without `carried`, no `carried`/`regression` keys on the view.
        calls.clear()
        unlinked_tgt_bytes = c.get(f"/v1/conversations/{tgt}/facts").content
        assert len(calls) == 1
        kw, keys, carried_meta, reg_count = calls[0]
        assert "carried" not in kw
        assert "carried" not in keys and "regression" not in keys
        assert carried_meta is None and reg_count == 0

        # Source chat (unlinked) snapshot before linking the target.
        unlinked_src_bytes = c.get(f"/v1/conversations/{src}/facts").content

        # Regression link: `view_of` passes `carried`, view holds `carried` + `regression`, `/facts` unchanged.
        made = c.post(f"/v1/conversations/{tgt}/carry",
                      json={"source_conversation_id": src, "mode": "regression", "entity_names": ["세라"]}).json()["link"]
        calls.clear()
        reg_res = c.get(f"/v1/conversations/{tgt}/facts")
        assert reg_res.status_code == 200
        assert reg_res.content == unlinked_tgt_bytes  # regression never alters current facts
        assert len(calls) == 1
        kw, keys, carried_meta, reg_count = calls[0]
        assert "carried" in kw and kw["carried"] is not None
        assert "carried" in keys and "regression" in keys
        assert carried_meta is not None and carried_meta["link"] == made["id"] and carried_meta["mode"] == "regression"
        assert reg_count > 0

        # Linking tgt does not affect the unlinked source's answer (byte-identical JSON).
        calls.clear()
        assert c.get(f"/v1/conversations/{src}/facts").content == unlinked_src_bytes
        assert len(calls) == 1 and "carried" not in calls[0][0]
        assert "carried" not in calls[0][1] and "regression" not in calls[0][1]
