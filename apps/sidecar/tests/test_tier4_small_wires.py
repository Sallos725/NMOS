"""Tests for the small Wave 4 wires: takes_value read folding, canonfacts NUL strip, divergence finale cache key
and held_keys forwarding, person_data condition labels, and views.carry_text belief lines."""

from __future__ import annotations

from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from nmos_sidecar import canonfacts, divergence, facts, notes, views


def test_version_key_and_relation_ignore_value_on_non_value_predicates_but_keep_disguised_as():
    m1 = {"predicate": "member_of", "subject": "하나", "object": "기사단", "value": "정예 단원", "object_type": "organization"}
    m2 = {"predicate": "member_of", "subject": "하나", "object": "기사단", "value": None, "object_type": "organization"}
    assert facts.version_key(m1) == facts.version_key(m2)

    l1 = {"predicate": "located_in", "subject": "하나", "object": "도서관", "value": "2층", "object_type": "place"}
    l2 = {"predicate": "located_in", "subject": "하나", "object": "도서관", "value": None, "object_type": "place"}
    assert facts.relation(l1) == facts.relation(l2)

    d1 = {"predicate": "disguised_as", "subject": "리안", "object": "카이", "value": "용병", "object_type": "character"}
    d2 = {"predicate": "disguised_as", "subject": "리안", "object": "카이", "value": "상인", "object_type": "character"}
    assert facts.relation(d1) != facts.relation(d2)


def test_divergence_cache_key_separates_finale_revisions_and_notes_make_forwards_held_keys_and_finale():
    divergence._CACHE.clear()
    calls: list[str] = []

    def model(system: str, user: str):
        calls.append(user)
        return ({"diverged": [{"key": "lore:active", "subject": "세라", "quote": "세라는 등대에 있다.",
                               "now": "세라는 항구에 있다", "turns": [1], "kind": "location"}]},
                '{"diverged":[]}', {"prompt_tokens": 10, "completion_tokens": 10})

    entries = [
        {"key": "lore:active", "title": "등대", "content": "세라는 등대에 있다.", "metadata": {}},
        {"key": "lore:unseen", "title": "비밀섬", "content": "세라는 비밀섬에 숨어 있다.", "metadata": {}},
    ]
    entities = [{"id": str(uuid4()), "name": "세라", "names": ["세라"], "type": "character"}]
    view = {
        "facts": [{"id": str(uuid4()), "predicate": "located_in", "subject": "세라", "object": "항구",
                   "value": None, "turn": 1, "position": 1, "polarity": "positive"}],
        "entities": entities,
        "secrets": [],
        "threads": [],
        "excluded": [],
        "open_turn": {"turn": 2, "revision": "rev-a", "host_logical_id": "m2"},
    }
    told = {"scenes": [{"summary": {"text": "세라는 등대를 떠나 항구로 갔다.", "first_turn": 0, "last_turn": 1}}], "story": None}
    ask = notes.Ask(sections=("diverged",), chars=2000, secrets=False, model=True)

    r1 = notes.make(ask, view, told, 1, model, "2026-11-25", canon=entries, held_keys={"lore:active"})
    assert r1["sections"][0]["entries"] == 1
    assert r1["sections"][0]["cached"] is False
    assert len(calls) == 1

    # Same finale revision hits the cache
    r2 = notes.make(ask, view, told, 1, model, "2026-11-25", canon=entries, held_keys={"lore:active"})
    assert r2["sections"][0]["cached"] is True
    assert len(calls) == 1

    # New provisional finale revision misses the cache
    view_b = {**view, "open_turn": {"turn": 2, "revision": "rev-b", "host_logical_id": "m2"}}
    r3 = notes.make(ask, view_b, told, 1, model, "2026-11-25", canon=entries, held_keys={"lore:active"})
    assert r3["sections"][0]["cached"] is False
    assert len(calls) == 2


def test_views_carry_text_formats_belief_rows_in_korean_and_english():
    carried = {"kind": "belief", "subject": "하나", "value": "도윤이 배신자라고 믿는다"}
    reg = {"line": "belief", "subject": "Sera", "value": "Kaito is still alive"}
    assert views.carry_text(carried, "ko") == "하나 믿음: 도윤이 배신자라고 믿는다"
    assert views.carry_text(reg, "en") == "Sera believes: Kaito is still alive"


def test_person_data_marks_include_condition_slot_label(migrated: str):
    from test_tier3_read_ontology import Chat, a

    cond = {"scope": "private", "when": "둘만"}
    v21 = Chat(migrated, {"t0": [a("하나", "feels_toward", "도윤", "호감", condition=cond)]}, name="w4-wire-cond")
    with v21.client() as c:
        v21.run(c)
        view = v21.view()
        hana = next(e for e in view["entities"] if e["name"] == "하나")
        r = c.get(f"/v1/views/c/{v21.cid}/person/{hana['id']}", headers={"X-NMOS-Token": "test-token"})
        assert r.status_code == 200
        html = r.json()["html"]
        assert "도윤 → 호감 [둘만]" in html


def test_canonfacts_strips_nul_from_stored_raw_reply(migrated: str):
    from conftest import make_client
    from nmos_sidecar.config import Settings
    from nmos_sidecar.worker import run_once
    from simchat import SimChat
    from test_canon import push
    from test_generations import LLM
    from test_sidecar_integration import sync

    with make_client(migrated, **LLM) as c:
        chat = SimChat("canon-nul-chat")
        chat.user("안녕")
        chat.reply("반가워")
        sync(c, chat)
        desc = "세라는 북부 항구 마을을 지키는 은빛 기사단의 젊은 단장이며, 어릴 적부터 등대지기의 딸로 자라 바다와 검술을 모두 익혔다."
        push(c, chat, {"card:desc": (desc, {})})
        gen = canonfacts.generation(Settings(database_url=migrated, **LLM))
        assert gen is not None
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            raw_with_nul = '{"assertions": []}\x00trailing'
            ran = run_once(
                conn,
                {"canon": (gen.key, lambda _c, j: canonfacts.process(
                    _c, j, lambda _s, _u: ({"assertions": []}, raw_with_nul, {"prompt_tokens": 1, "completion_tokens": 1}),
                    gen))},
            )
            assert ran is True
            saved = conn.execute("SELECT raw->>'reply' AS r FROM extraction WHERE extractor_key = %s",
                                 (gen.key,)).fetchone()
            assert saved is not None and "\x00" not in (saved["r"] or "")
            assert saved["r"] == '{"assertions": []}trailing'
