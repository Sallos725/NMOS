"""The production base's post-processing rules (PHASE-66 part 5): `revision` 0 for every projection kind that has
one, so its spec has no `revision` field and a test that pins a key the base wrote keeps pinning that key byte for
byte. Imported into such a test module, `base_rules` is autouse there. With the marker each of those keys moves once,
by its `revision` field alone: test_tier3_revision_marker.py pins that."""

from __future__ import annotations

import pytest

from nmos_sidecar import canonfacts, extraction, reveals, summaries

KINDS = (extraction, reveals, summaries, canonfacts)


@pytest.fixture(autouse=True)
def base_rules():
    patch = pytest.MonkeyPatch()  # its own: a test's `monkeypatch.undo()` leaves it in place
    for module in KINDS:
        patch.setattr(module, "REVISION", 0)
    yield
    patch.undo()
