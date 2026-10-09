"""PHASE-33 Q7: the source-turn page. A turn's text with the words its facts were checked against, what the active
generation made of it, the packet lines that came from it, and links to it from every turn cell."""

from __future__ import annotations

from test_packet_ledger import ask, db, full, story  # noqa: F401  (`full` is a fixture)


def _conv(client) -> str:
    return client.get("/v1/conversations").json()[0]["id"]


def _turn_of(url: str, words: str) -> int:
    with db(url) as conn:
        return conn.execute(
            "SELECT am.turn FROM active_membership am JOIN source_revision sr ON sr.id = am.source_revision_id"
            " JOIN conversation c ON c.head_commit_id = am.commit_id WHERE sr.content LIKE %s", (f"%{words}%",)
        ).fetchone()["turn"]


def test_a_turn_shows_its_text_its_facts_and_the_lines_that_used_it(full):
    client, url = full
    chat = story(client, url)  # "Hana has the map." is one turn; the stub extractor makes a fact of it
    out = ask(client, chat, "Hana, where is the map?")
    assert "map" in out["packet"]["text"]
    conv, turn = _conv(client), _turn_of(url, "Hana has the map.")
    page = client.get(f"/inspector/c/{conv}/t/{turn}").text
    assert f"<h1>턴 {turn}</h1>" in page
    assert '<b class="hl">' in page and "Hana has the map" in page  # the evidence in bold
    assert "has the map" in page.split('id="s-made"')[1].split("</details>")[0]  # the fact it made
    assert "현재" in page  # its outcome
    used = page.split('id="s-used"')[1].split("</details>")[0]
    assert "has the map" in used or "Hana has the map" in used  # the request above placed a line from it
    assert f'href="/inspector/c/{conv}/t/{turn - 1}"' in page and f'href="/inspector/c/{conv}/t/{turn + 1}"' in page


def test_turn_cells_lead_to_their_turn_and_keep_token_and_language(full):
    client, url = full
    story(client, url)
    conv, turn = _conv(client), _turn_of(url, "Hana has the map.")
    del client.headers["Authorization"]
    detail = client.get(f"/inspector/c/{conv}", params={"token": "test-token", "lang": "en"}).text
    assert f'href="/inspector/c/{conv}/t/{turn}?token=test-token&amp;lang=en"' in detail \
        or f'href="/inspector/c/{conv}/t/{turn}?token=test-token&lang=en"' in detail
    page = client.get(f"/inspector/c/{conv}/t/{turn}", params={"token": "test-token", "lang": "en"}).text
    assert f"<h1>Turn {turn}</h1>" in page and f'href="/inspector/c/{conv}?token=test-token&lang=en"' in page
    assert client.get(f"/inspector/c/{conv}/t/{turn}").status_code == 401


def test_the_panel_gets_the_body_and_a_turn_not_on_the_head_says_so(full):
    client, url = full
    story(client, url)
    conv = _conv(client)
    body = client.get(f"/v1/inspector/c/{conv}/t/1").json()["html"]
    assert not body.startswith("<!doctype") and "<style>" not in body and "한국어" not in body
    assert "이 턴은 지금 헤드에 없습니다." in client.get(f"/inspector/c/{conv}/t/999").text
    assert client.get("/inspector/c/00000000-0000-0000-0000-000000000000/t/1").status_code == 404


def test_the_text_is_escaped():
    from nmos_sidecar.inspector import _marked

    assert _marked("<script>x</script> Hana has the map.", ["Hana has the map."]) == (
        '&lt;script&gt;x&lt;/script&gt; <b class="hl">Hana has the map.</b>')
    assert _marked("a\nb", []) == "a<br>b"
    assert _marked("the map, the map", ["the map", "map, the"]) == '<b class="hl">the map, the map</b>'  # merged


def test_an_elided_evidence_quote_is_found_piece_by_piece():
    from nmos_sidecar.inspector import _marked

    text = "류진은 서랍을 열었다. 상자 안에는 먹이 있었다. 그는 붓 한 자루를 골라 건넸다."
    marked = _marked(text, ["류진은 서랍을 열었다. … 붓 한 자루를 골라 건넸다."])
    assert marked == ('<b class="hl">류진은 서랍을 열었다.</b> 상자 안에는 먹이 있었다. 그는 '
                      '<b class="hl">붓 한 자루를 골라 건넸다.</b>')
