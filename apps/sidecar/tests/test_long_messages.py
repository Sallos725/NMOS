"""#13: bounded processing of long messages is recorded and visible; raw evidence stays complete."""

from __future__ import annotations

import pytest

from conftest import make_client
from nmos_sidecar.extraction import TARGET_CHARS
from nmos_sidecar.vectors import CHUNK_CHARS, MAX_CHUNKS
from simchat import SimChat
from test_extraction import drain, filler
from test_generations import EMB, LLM, conv_id
from test_sidecar_integration import sync
from test_vectors import FakeEmbedder, drain_embeddings

SIZES = [5_000, 6_000, 10_000, 20_000]


def story(chars: int) -> str:
    """Exactly `chars` characters that normalization leaves unchanged."""
    sentence = "하나는 등대 아래에서 은빛 열쇠를 찾았다. "
    base = (sentence * (chars // len(sentence) + 1))[: chars - 1]
    return (base[:-1] + "다" if base.endswith(" ") else base) + "."


def long_chat() -> SimChat:
    chat = SimChat()
    for n in SIZES:
        chat.user(story(n))
        chat.reply("ok")
    filler(chat, 3)
    return chat


def members(db) -> dict[int, dict]:
    rows = db.execute("SELECT sr.id, sr.content, rt.clean_chars FROM source_revision sr"
                      " JOIN revision_text rt ON rt.source_revision_id = sr.id").fetchall()
    return {r["clean_chars"]: r for r in rows if r["clean_chars"] >= 4_000}


@pytest.fixture
def client_all(migrated):
    with make_client(migrated, embedder=FakeEmbedder(), **LLM, **EMB) as c:
        yield c


def test_embedding_reports_partial_coverage_for_long_message(client_all, migrated, db):
    chat = long_chat()
    sync(client_all, chat)
    drain_embeddings(migrated)
    limit = CHUNK_CHARS * MAX_CHUNKS
    covered = {r["clean_chars"]: r["covered"] for r in db.execute(
        "SELECT rt.clean_chars, max(re.text_end) AS covered FROM revision_embedding re"
        " JOIN revision_text rt ON rt.source_revision_id = re.source_revision_id GROUP BY rt.clean_chars").fetchall()}
    assert covered[5_000] == 5_000  # fits
    assert all(covered[n] < n and covered[n] <= limit for n in (6_000, 10_000, 20_000))
    cov = client_all.get(f"/v1/conversations/{conv_id(client_all, chat)}/coverage").json()["embeddings"]
    assert cov["partial"] == 3 and cov["complete"] is False
    page = client_all.get(f"/inspector/c/{conv_id(client_all, chat)}").text
    assert "partially embedded 3" in page and "emb full" in page and f"emb {covered[20_000]:,}/20,000" in page


def test_extraction_reports_target_truncation(client_all, migrated, db):
    chat = long_chat()
    sync(client_all, chat)
    drain(migrated)
    seen = {r["target_chars"]: r["target_used"] for r in db.execute(
        "SELECT (coverage->>'target_chars')::int AS target_chars, (coverage->>'target_used')::int AS target_used"
        " FROM extraction").fetchall()}
    assert seen[5_000] == 5_000 and seen[6_000] == 6_000  # boundary: exactly TARGET_CHARS is complete
    assert seen[10_000] == seen[20_000] == TARGET_CHARS
    truncated_context = db.execute("SELECT max((coverage->>'context_truncated')::int) AS n FROM extraction"
                                   ).fetchone()["n"]
    assert truncated_context == 3  # a 6-message window holds at most three of the long messages, each cut
    cov = client_all.get(f"/v1/conversations/{conv_id(client_all, chat)}/coverage").json()["extraction"]
    assert cov["target_truncated"] == 2
    assert "ext 6,000/20,000" in client_all.get(f"/inspector/c/{conv_id(client_all, chat)}").text


def test_long_message_raw_evidence_remains_complete(client_all, migrated, db):
    chat = long_chat()
    sync(client_all, chat)
    drain(migrated)
    drain_embeddings(migrated)
    for n, row in members(db).items():
        assert row["content"] == story(n) and len(row["content"]) == n
