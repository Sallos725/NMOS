"""Inspector language (Korean default) and host-reported conversation labels."""

from __future__ import annotations

from conftest import make_client
from simchat import SimChat
from test_sidecar_integration import sync


def chat() -> SimChat:
    c = SimChat()
    c.user("안녕")
    c.reply("반가워")
    c.user("다음")
    return c


def sync_named(client, c: SimChat, **names) -> None:
    manifest = {**c.manifest(), **names}
    out = client.post("/v1/sync/reconcile", json=manifest).json()
    if out["status"] == "needs_bodies":
        client.post("/v1/sync/bodies", json={"chat_id": c.id, "bodies": c.bodies(out["needed_bodies"]),
                                             "then_reconcile": manifest})


def test_conversation_labels_follow_host_renames(client):
    c = chat()
    sync_named(client, c, character_name="하나", chat_name="벨로나 등대")
    conv = client.get("/v1/conversations").json()[0]
    assert (conv["host_character_name"], conv["host_chat_name"]) == ("하나", "벨로나 등대")
    assert "하나 · 벨로나 등대" in client.get("/inspector").text
    c.user("계속")
    sync_named(client, c, chat_name="벨로나 등대 2")  # renamed chat; bot name not sent this time
    conv = client.get("/v1/conversations").json()[0]
    assert (conv["host_character_name"], conv["host_chat_name"]) == ("하나", "벨로나 등대 2")
    sync(client, c)  # an older plugin sends no names: the labels stay
    assert client.get("/v1/conversations").json()[0]["host_chat_name"] == "벨로나 등대 2"


def test_labels_are_escaped_and_fall_back_to_the_chat_id(client):
    named, plain = chat(), chat()
    sync_named(client, named, character_name="<img src=x onerror=alert(1)>", chat_name="a & b")
    sync(client, plain)
    page = client.get("/inspector").text
    assert "<img src=x" not in page and "&lt;img src=x onerror=alert(1)&gt; · a &amp; b" in page
    assert plain.id in page
    long = chat()
    too_long = client.post("/v1/sync/reconcile", json={**long.manifest(), "chat_name": "x" * 201})
    assert too_long.status_code == 422


def test_inspector_is_korean_by_default_and_english_on_request(client):
    sync_named(client, chat(), character_name="하나", chat_name="첫 대화")
    ko = client.get("/inspector").text
    assert '<html lang="ko">' in ko and "NMOS 인스펙터" in ko and "사실 커버리지" in ko
    en = client.get("/inspector", params={"lang": "en"}).text
    assert '<html lang="en">' in en and "Facts coverage" in en
    conv_id = client.get("/v1/conversations").json()[0]["id"]
    assert f'href="/inspector/c/{conv_id}?lang=en"' in en  # the language follows the links
    detail = client.get(f"/inspector/c/{conv_id}").text
    assert "<h1>하나 · 첫 대화</h1>" in detail and "현재 메시지 (최신순)" in detail
    assert client.get("/inspector", params={"lang": "xx"}).text.startswith('<!doctype html><html lang="ko">')


def test_coverage_of_a_feature_that_was_never_on_is_not_shown_as_partial(client):
    sync_named(client, chat(), character_name="하나", chat_name="첫 대화")  # no LLM, no embeddings
    page = client.get("/inspector").text
    assert "일부" not in page and "0.0%" not in page


def test_no_parsed_state_shows_an_example_status_window(client):
    sync_named(client, chat(), character_name="하나", chat_name="첫 대화")  # no parser rules configured
    conv_id = client.get("/v1/conversations").json()[0]["id"]
    ko = client.get(f"/inspector/c/{conv_id}").text
    assert "상태창 규칙으로 읽은 값이 없습니다." in ko and "HP: 80/100" in ko
    en = client.get(f"/inspector/c/{conv_id}", params={"lang": "en"}).text
    assert "No parser state." in en and "HP: 80/100" in en


def test_inspector_handles_active_extractor_without_eligible_turns(migrated):
    with make_client(migrated, llm_url="http://fake-llm/v1", llm_model="fake") as client:
        pending = SimChat()
        pending.user("아직 답변이 없는 메시지")
        sync_named(client, pending, character_name="하나", chat_name="대기 중")
        conv_id = client.get("/v1/conversations").json()[0]["id"]
        coverage = client.get(f"/v1/conversations/{conv_id}/coverage").json()["extraction"]

        assert set(coverage) == {"generation"}
        detail = client.get(f"/v1/inspector/c/{conv_id}")
        assert detail.status_code == 200
        assert '<span class="muted">—</span>' in detail.json()["html"]


def test_inspector_links_keep_token_and_language(migrated):
    with make_client(migrated) as c:
        sync_named(c, chat(), character_name="하나", chat_name="첫 대화")
        conv_id = c.get("/v1/conversations").json()[0]["id"]
        del c.headers["Authorization"]
        page = c.get("/inspector", params={"token": "test-token", "lang": "en"}).text
        assert f'href="/inspector/c/{conv_id}?token=test-token&lang=en"' in page
        assert 'href="/inspector?token=test-token">한국어</a>' in page


def test_container_entrypoint_builds_the_app(monkeypatch, migrated):
    """The image runs `uvicorn nmos_sidecar.api:app_factory --factory`; tests otherwise use create_app."""
    from nmos_sidecar.api import app_factory

    monkeypatch.setenv("NMOS_DATABASE_URL", migrated)
    assert app_factory().title == "NMOS sidecar"


def test_embedded_inspector_is_the_same_page_without_the_frame(client):
    """The plugin panel shows the inspector in place (H15): body only, no language switch, still escaped."""
    sync_named(client, chat(), character_name="<b>하나</b>", chat_name="첫 대화")
    conv_id = client.get("/v1/conversations").json()[0]["id"]
    listing = client.get("/v1/inspector", params={"lang": "en"}).json()["html"]
    assert not listing.startswith("<!doctype") and "<style>" not in listing and "English" not in listing
    assert "Facts coverage" in listing and f'href="/inspector/c/{conv_id}?lang=en"' in listing
    assert "&lt;b&gt;하나&lt;/b&gt;" in listing and "<b>하나</b>" not in listing
    detail = client.get(f"/v1/inspector/c/{conv_id}").json()["html"]
    assert detail.startswith('<div class="top"><p><a href="/inspector">← 대화 목록</a></p></div>')
    assert "현재 메시지 (최신순)" in detail
    assert client.get("/v1/inspector/c/00000000-0000-0000-0000-000000000000").status_code == 404


def test_embedded_inspector_requires_the_token(migrated):
    with make_client(migrated) as c:
        del c.headers["Authorization"]
        assert c.get("/v1/inspector").status_code == 401


def test_detail_lists_turns_and_counts_changes_per_commit(client):
    c = SimChat()
    for i in range(4):
        c.user(f"줄 {i}")
        c.reply(f"답 {i}")
    c.user("마지막")
    sync(client, c)
    c.messages = c.messages[:3]  # "delete all below": six messages at once
    sync(client, c)
    cid = client.get("/v1/conversations").json()[0]["id"]
    page = client.get(f"/inspector/c/{cid}?lang=en").text
    assert "delete ×6" in page
    assert "<th>#</th><th>Turn</th>" in page


def story_client(migrated, lines):
    """A client whose chat was extracted by the deterministic stub (tests/memeval.py)."""
    from memeval import stub_extractor
    from test_extraction import drain
    from test_generations import LLM

    c = SimChat()
    for line in lines:
        c.user(line)
        c.reply("Noted.")
    c.user("next")
    client = make_client(migrated, **LLM)
    return client, c, lambda: drain(migrated, stub_extractor)


STORY = ("Hana has the letter.", "Hana is in the library.", "Hana keeps a secret from Kaito: the map is fake.",
         'Kaito says: "I am a knight."', "Hana burns the letter.", "Hana has the letter.")


def character_links(page: str, conv: str) -> dict[str, str]:
    import re
    return {name: eid for eid, name in re.findall(rf'href="/inspector/c/{conv}/e/([0-9a-f-]{{36}})[^"]*">([^<]+)</a>', page)}


def test_detail_has_a_table_of_contents_and_collapsible_sections(migrated):
    client, c, drain = story_client(migrated, STORY)
    with client:
        sync(client, c)
        drain()
        conv = client.get("/v1/conversations").json()[0]["id"]
        page = client.get(f"/inspector/c/{conv}").text
        # Counts in the contents and the section headings; a conflict is flagged.
        assert '<p class="toc">' in page and '<a href="#s-conflicts" class="warn">충돌 <span class="n">1</span></a>' in page
        assert '<details id="s-facts" open><summary><h2>현재 사실 <span class="n">' in page
        # Conflicts come before the facts they are about; bulky logs start folded.
        assert page.index('id="s-conflicts"') < page.index('id="s-facts"')
        for folded in ("members", "commits", "retrievals"):
            assert f'<details id="s-{folded}"><summary>' in page
        # Internal ids are behind a fold of their own, not in the heading area.
        assert '<details class="meta"><summary class="muted">식별자</summary>' in page


def test_detail_labels_are_readable_and_keep_the_raw_value(migrated):
    client, c, drain = story_client(migrated, STORY)
    with client:
        sync(client, c)
        drain()
        assert client.post("/v1/retrieve", json={"chat_id": c.id, "query": "letter", "budget_tokens": 500}).status_code == 200
        conv = client.get("/v1/conversations").json()[0]["id"]
        page = client.get(f"/inspector/c/{conv}").text
        assert '<span class="chip" title="located_in">위치</span>' in page
        assert '<span class="chip" title="accepted">확정</span>' in page
        assert '<span class="chip" title="import">가져오기</span>' in page or 'title="reconciliation">동기화' in page
        # Timestamps are UTC with the exact instant kept for the panel to show in local time.
        assert '<span class="ts" title="' in page and ' UTC</span>' in page
        en = client.get(f"/inspector/c/{conv}?lang=en").text
        assert '<span class="chip" title="located_in">located in</span>' in en


def test_character_view_gathers_what_concerns_one_character(migrated):
    client, c, drain = story_client(migrated, STORY)
    with client:
        sync(client, c)
        drain()
        conv = client.get("/v1/conversations").json()[0]["id"]
        page = client.get(f"/inspector/c/{conv}").text
        assert '<p class="who"><span class="muted">캐릭터</span> <b>전체</b>' in page
        who = character_links(page, conv)
        assert {"Hana", "Kaito"} <= set(who) and "letter" not in who  # characters only

        hana = client.get(f"/inspector/c/{conv}/e/{who['Hana']}").text
        assert "<h1>Hana</h1>" in hana and "<b>Hana</b>" in hana  # selected in the picker
        assert f'<a href="/inspector/c/{conv}">전체</a>' in hana
        assert 'id="s-held"' in hana and "Hana 보유" in hana  # the letter, with its timeline
        assert 'id="s-conflicts"' in hana  # held after it burned
        assert 'id="s-about"' in hana and "library" in hana
        # What Hana knows is listed once, under what she knows, not again among the facts about her.
        assert '<h2>아는 것 <span class="n">1</span>' in hana and hana.count("the map is fake") == 1
        assert '<h2>이 인물에 대한 사실 <span class="n">1</span>' in hana
        assert "id=\"s-members\"" not in hana and "id=\"s-commits\"" not in hana
        assert "knight" not in hana  # Kaito's claim is about Kaito

        kaito = client.get(f"/inspector/c/{conv}/e/{who['Kaito']}?lang=en").text
        assert 'id="s-claims"' in kaito and "knight" in kaito
        assert 'id="s-hidden"' in kaito and "the map is fake" in kaito  # kept from Kaito
        assert "library" not in kaito and 'id="s-held"' not in kaito

        embedded = client.get(f"/v1/inspector/c/{conv}/e/{who['Kaito']}").json()["html"]
        assert not embedded.startswith("<!doctype") and "knight" in embedded
        # A character that no longer resolves (memory rebuilt) is a page, not an error.
        gone = client.get(f"/inspector/c/{conv}/e/00000000-0000-0000-0000-000000000000")
        assert gone.status_code == 200 and "이 인물을 찾을 수 없습니다" in gone.text
        assert client.get(f"/inspector/c/00000000-0000-0000-0000-000000000000/e/{who['Kaito']}").status_code == 404


def test_character_view_escapes_names(migrated):
    client, c, drain = story_client(migrated, ("Hana has the <b>letter</b>.", "X<i> is in the library."))
    with client:
        sync(client, c)
        drain()
        conv = client.get("/v1/conversations").json()[0]["id"]
        page = client.get(f"/inspector/c/{conv}").text
        assert "<i>" not in page and "<b>letter" not in page


PROMISES = ('Hana says to Kaito: "I promise to meet you at the lighthouse."',
            'Hana says to Yui: "I promise to return the book."', "Hana kept the promise to return the book.",
            "Ren kept the promise to feed the cat.", "Hana betrayed Kaito.", "Hana did chore 1.")


def test_inspector_shows_promises_unmatched_resolutions_and_salience(migrated):
    """PHASE-7 step 5: threads with status, resolutions that closed nothing, event salience."""
    client, c, drain = story_client(migrated, PROMISES)
    with client:
        sync(client, c)
        drain()
        conv = client.get("/v1/conversations").json()[0]["id"]
        page = client.get(f"/inspector/c/{conv}").text
        assert '<a href="#s-threads">약속 <span class="n">2</span></a>' in page
        assert page.index('id="s-threads"') < page.index('id="s-facts"')
        assert '<span class="chip" title="open">열림</span>' in page and '<span class="chip" title="kept">지킴</span>' in page
        assert "Hana fulfilled: return the book" in page  # what closed it
        assert 'id="s-unmatched"' in page and "feed the cat" in page  # Ren has no such promise
        assert '<span class="chip" title="major">중요</span>' in page
        assert '<span class="chip" title="minor">사소</span>' in page
        who = character_links(page, conv)
        yui = client.get(f"/inspector/c/{conv}/e/{who['Yui']}?lang=en").text
        assert 'id="s-threads"' in yui and "return the book" in yui and "lighthouse" not in yui


def test_inspector_shows_participants_and_what_a_character_takes_part_in(migrated):
    """PHASE-8 step 4: a participants column, and "Takes part in" on the character page, including a
    character who is only ever a participant."""
    client, c, drain = story_client(migrated, ("Kaito is in the harbor.", "Hana betrayed Kaito.", "Hana betrayed Mina."))
    with client:
        sync(client, c)
        drain()
        conv = client.get("/v1/conversations").json()[0]["id"]
        page = client.get(f"/inspector/c/{conv}?lang=en").text
        assert "<th>With</th>" in page
        who = character_links(page, conv)
        assert {"Hana", "Kaito", "Mina"} <= set(who)  # Mina is only a participant
        kaito = client.get(f"/inspector/c/{conv}/e/{who['Kaito']}?lang=en").text
        assert 'id="s-takes_part"' in kaito and "betrayed Kaito" in kaito and "betrayed Mina" not in kaito
        mina = client.get(f"/inspector/c/{conv}/e/{who['Mina']}").text
        assert 'id="s-takes_part"' in mina and "betrayed Mina" in mina
        hana = client.get(f"/inspector/c/{conv}/e/{who['Hana']}").text
        assert 'id="s-takes_part"' not in hana  # her own events are "about" her, not "takes part"
