"""#13: bounded processing of long messages is recorded and visible; raw evidence stays complete."""

from __future__ import annotations

import pytest

from conftest import make_client
from nmos_sidecar.extraction import TARGET_CHARS
from nmos_sidecar.normtext import NORMALIZER_VERSION
from nmos_sidecar.vectors import CHUNK_CHARS, CHUNKER_VERSION, DOCUMENT_PROFILE, MAX_CHUNKS
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
    assert all(covered[n] < n and covered[n] <= limit == 5_600 for n in (6_000, 10_000, 20_000))  # partial (K13)
    cov = client_all.get(f"/v1/conversations/{conv_id(client_all, chat)}/coverage").json()["embeddings"]
    assert cov["partial"] == 3 and cov["complete"] is False
    page = client_all.get(f"/inspector/c/{conv_id(client_all, chat)}?lang=en").text
    assert "partially embedded 3" in page and "emb full" in page and f"emb {covered[20_000]:,}/20,000" in page


def test_extraction_reports_target_truncation(client_all, migrated, db):
    chat = long_chat()
    sync(client_all, chat)
    drain(migrated)
    # Each long message is the user's part of a turn whose reply is "ok" (ADR 0008: the turn is the target).
    ok = len("ok")
    seen = {r["target_chars"] - ok: r["target_used"] - ok for r in db.execute(
        "SELECT (coverage->>'target_chars')::int AS target_chars, (coverage->>'target_used')::int AS target_used"
        " FROM extraction").fetchall()}
    assert seen[5_000] == 5_000 and seen[6_000] == 6_000  # boundary: exactly TARGET_CHARS is complete
    assert seen[10_000] == seen[20_000] == TARGET_CHARS
    truncated_context = db.execute("SELECT max((coverage->>'context_truncated')::int) AS n FROM extraction"
                                   ).fetchone()["n"]
    assert truncated_context == 3  # three context turns hold at most three of the long messages, each cut
    cov = client_all.get(f"/v1/conversations/{conv_id(client_all, chat)}/coverage").json()["extraction"]
    assert cov["target_truncated"] == 2
    assert "ext 6,000/20,000" in client_all.get(f"/inspector/c/{conv_id(client_all, chat)}?lang=en").text


def test_long_message_raw_evidence_remains_complete(client_all, migrated, db):
    chat = long_chat()
    sync(client_all, chat)
    drain(migrated)
    drain_embeddings(migrated)
    for n, row in members(db).items():
        assert row["content"] == story(n) and len(row["content"]) == n


def test_a_projection_embeds_by_the_cap_its_own_key_records(client_all, migrated, db):
    """ADR 0062: the default projection embeds the 20,000-character message in 8 chunks (its key says `max_chunks` 8,
    as the constant did: the same key as before the setting, so an upgrade re-embeds nothing); a generation whose spec
    says 24 embeds 24 under the same default, and a spec from before the cap was in the key (no `max_chunks`) cuts
    at 8."""
    from nmos_sidecar import generations
    from nmos_sidecar.generations import Generation
    from nmos_sidecar.vectors import process_embed

    chat = long_chat()
    sync(client_all, chat)
    drain_embeddings(migrated)
    rid = members(db)[20_000]["id"]
    active = db.execute("SELECT projection, count(*) AS n, max(text_end) AS covered FROM revision_embedding"
                        " WHERE source_revision_id = %s GROUP BY projection", (rid,)).fetchall()
    assert len(active) == 1 and active[0]["n"] == MAX_CHUNKS == 8 and active[0]["covered"] <= 5_600
    before_the_setting = generations.make("embed", EMB["embed_url"], EMB["embed_model"], normalizer=NORMALIZER_VERSION,
                                          chunker=CHUNKER_VERSION, chunk_chars=CHUNK_CHARS, max_chunks=8,
                                          document_profile=DOCUMENT_PROFILE)
    assert active[0]["projection"] == before_the_setting.key  # the constant's key, as the release before made it
    wide = generations.make("embed", EMB["embed_url"], EMB["embed_model"], normalizer="clean-vtest",
                            chunker="chunk-v1", chunk_chars=CHUNK_CHARS, max_chunks=24, document_profile="plain")
    legacy = Generation(kind="embed", model=EMB["embed_model"], endpoint=wide.endpoint, key="embed-before-the-cap",
                        spec={"kind": "embed", "model": EMB["embed_model"], "chunker": "chunk-v1"})
    for gen, cap in ((wide, 24), (legacy, 8)):
        generations.ensure(db, gen)
        assert process_embed(db, {"payload": {"revision_id": str(rid), "generation": gen.key}},
                             FakeEmbedder(), gen) == "done"
        rows = db.execute("SELECT count(*) AS n, max(text_end) AS covered FROM revision_embedding"
                          " WHERE source_revision_id = %s AND projection = %s", (rid, gen.key)).fetchone()
        assert rows["n"] == cap and cap * (CHUNK_CHARS - 30) <= rows["covered"] <= cap * CHUNK_CHARS, gen.key


def test_a_chunk_cap_under_one_is_refused_at_startup(monkeypatch):
    """A cap of 0 would embed nothing and mark every embed job done (Copilot on #242)."""
    from nmos_sidecar.config import Settings

    with pytest.raises(ValueError, match="NMOS_EMBED_MAX_CHUNKS must be at least 1"):
        Settings(embed_max_chunks=0)
    monkeypatch.setenv("NMOS_EMBED_MAX_CHUNKS", "-3")
    with pytest.raises(ValueError, match="at least 1, not -3"):
        Settings()
    monkeypatch.setenv("NMOS_EMBED_MAX_CHUNKS", "1")
    assert Settings().embed_max_chunks == 1
