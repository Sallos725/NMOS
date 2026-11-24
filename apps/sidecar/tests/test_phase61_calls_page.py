"""PHASE-61 S6 (ADR 0089): the browser Inspector's "Model calls" page (KO "모델 호출"): the summary of the last hour and
the last 200 calls, in both languages, every value escaped; the Inspector's first page links it. Synthetic names only."""

from __future__ import annotations

import psycopg

from conftest import make_client
from test_phase61_calls_read import log_row

HOSTILE_ERROR = 'HTTP 400: <script>alert("세라")</script> & "quotes"'
HOSTILE_MODEL = "<img src=x onerror=alert(1)>model"


def test_the_inspector_page_escapes_every_value_in_both_languages(migrated):
    with psycopg.connect(migrated, autocommit=True) as conn:
        log_row(conn, "http", 400, model=HOSTILE_MODEL, error=HOSTILE_ERROR, endpoint="http://x/<b>v1</b>")
        log_row(conn, usage={"calls": 1, "input": 1200, "output": 34}, kind="summarize")
    with make_client(migrated) as c:
        for lang, title, kind in (("ko", "모델 호출", "요약"), ("en", "Model calls", "summary")):
            html = c.get("/inspector/calls", params={"lang": lang}).text
            assert title in html and kind in html and "1200 / 34" in html
            for tag in ("<script>alert", "<img src", "<b>v1"):
                assert tag not in html
            assert "&lt;script&gt;alert" in html and "&lt;img src=x" in html
            embed = c.get("/v1/inspector/calls", params={"lang": lang}).json()["html"]
            assert title in embed and "<html" not in embed and "<img src" not in embed
        # the Inspector's first page links it, in the browser only
        assert 'href="/inspector/calls' in c.get("/inspector").text
        assert "/inspector/calls" not in c.get("/v1/inspector").json()["html"]
        del c.headers["Authorization"]
        assert c.get("/inspector/calls").status_code == 401 and c.get("/v1/inspector/calls").status_code == 401


def test_the_page_with_no_call_says_so(migrated):
    with make_client(migrated) as c:
        assert "No model call is logged." in c.get("/inspector/calls", params={"lang": "en"}).text
