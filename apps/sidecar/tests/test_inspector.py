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
