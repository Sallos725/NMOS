"""The local replay must fail closed on corrupt caches and restore hooks on failure."""
from argparse import Namespace
from pathlib import Path
import hashlib
import json

import pytest

import eval_recall_candidate as E
import check_recall_candidate as G
from nmos_sidecar import audit, retrieval


@pytest.mark.parametrize("vector", [[1.0], [float("nan")] * 4096, [0.0] * 4096])
def test_corrupt_cached_vector_cannot_silently_change_search(tmp_path, monkeypatch, vector):
    identity = {"text": "synthetic question", "model": E.MODEL, "endpoint": E.URL}
    E.write(tmp_path / "query-vectors" / (E.digest(identity) + ".json"),
            {"identity": identity, "vector": vector})
    embedder = E.CachedLocalEmbedder(tmp_path, False)
    def forbidden_call(*args, **kwargs):
        pytest.fail("cache-only replay called a model")
    monkeypatch.setattr(embedder.model, "embed", forbidden_call)
    with pytest.raises(ValueError):
        embedder.embed([identity["text"]], 1)


def test_missing_cache_cannot_call_a_model(tmp_path, monkeypatch):
    embedder = E.CachedLocalEmbedder(tmp_path, False)
    def forbidden_call(*args, **kwargs):
        pytest.fail("cache-only replay called a model")
    monkeypatch.setattr(embedder.model, "embed", forbidden_call)
    with pytest.raises(ValueError, match="missing frozen"):
        embedder.embed(["synthetic question"], 1)


def test_failed_replay_restores_all_hooks_and_requests_read_only(tmp_path, monkeypatch):
    before = audit.gather, retrieval.fuse, retrieval.grown_excerpt
    def disconnected(*args, **kwargs):
        assert kwargs["options"] == "-c default_transaction_read_only=on"
        assert (audit.gather, retrieval.fuse, retrieval.grown_excerpt) != before
        raise RuntimeError("synthetic disconnected database")
    monkeypatch.setattr(E.psycopg, "connect", disconnected)
    monkeypatch.chdir(Path(E.__file__).resolve().parents[1])
    cases = tmp_path / "cases.json"
    cases.write_text("[]")
    args = Namespace(cases=cases, out=tmp_path / "private", label="test", db="unused",
                     candidate=True, allow_local_embeddings=False)
    with pytest.raises(RuntimeError, match="synthetic disconnected"):
        E.run(args)
    assert (audit.gather, retrieval.fuse, retrieval.grown_excerpt) == before


def test_gate_rejects_prompt_window_change_even_when_denominator_is_same(tmp_path):
    case = {"name": "synthetic", "gold": ["target"], "forbidden": []}
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps([case]))
    E.write(tmp_path / "protocol.json", {
        "cases_sha256": hashlib.sha256(cases.read_bytes()).hexdigest(),
        "scorer_sha256": hashlib.sha256(Path(G.E.__file__).read_bytes()).hexdigest(), "budget": 4000,
    })
    for label, text in (("baseline", "missing"), ("candidate", "target")):
        E.write(tmp_path / label / "source.json", {"synthetic": "same-hash"})
        E.write(tmp_path / label / "cases/synthetic.json", {
            "case": case, "window": "", "result": G.E.score(case, text, ""),
            "packet": {"text": text, "tokens": 10, "vectors": "on", "policy": "packet-v10", "keywords": "on"},
        })
    assert G.verify(tmp_path, "candidate", cases)["pass"]
    path = tmp_path / "candidate/cases/synthetic.json"
    record = json.loads(path.read_text())
    record["window"] = "changed context without an answer"
    E.write(path, record)
    with pytest.raises(ValueError, match="prompt window changed"):
        G.verify(tmp_path, "candidate", cases)
