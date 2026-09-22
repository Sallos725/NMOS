"""Python canonical JSON / revision hash must match the plugin byte for byte."""

from __future__ import annotations

import json
from pathlib import Path

from nmos_sidecar.canonical import canonical_json, normalize_text, revision_hash, revision_payload

VECTORS = Path(__file__).resolve().parents[3] / "fixtures" / "unit" / "revision-hash-v1.json"


def test_plugin_vectors_match():
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert len(vectors) >= 8
    for vector in vectors:
        content = normalize_text(vector["content"])
        assert canonical_json(revision_payload(vector["metadata"], content)) == vector["canonical"]
        assert revision_hash(vector["metadata"], content) == vector["revision_hash"]
