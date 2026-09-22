"""#12: the supported manifest size is explicit (docs/perf/scale.md)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nmos_sidecar.models import MAX_MANIFEST_MESSAGES, ReconcileRequest


def manifest(n: int) -> dict:
    entry = {"host_logical_id": "m", "revision_hash": "0" * 64, "role": "user"}
    return {"chat_id": "c", "messages": [entry] * n}


def test_measured_25k_tier_is_accepted_and_the_limit_is_explicit():
    assert MAX_MANIFEST_MESSAGES >= 25_000
    assert len(ReconcileRequest.model_validate(manifest(25_000)).messages) == 25_000
    with pytest.raises(ValidationError):
        ReconcileRequest.model_validate(manifest(MAX_MANIFEST_MESSAGES + 1))
