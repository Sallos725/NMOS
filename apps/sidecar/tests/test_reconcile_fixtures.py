"""Reconciliation cases (PHASE-0 table) driven by recorded PocketRisu a14c911 manifests."""

from __future__ import annotations

import pytest

from hostfixtures import chat_id, entries, recorded_manifest_hash
from nmos_sidecar.reconcile import Entry, Plan, apply_ops, plan


def ingest(label: str) -> tuple[list[Entry], str, set, dict]:
    """State after a conversation was first seen at snapshot `label`."""
    manifest = entries(label)
    known = {e.key for e in manifest}
    first = plan(None, None, manifest, known, {})
    assert first.kind == "apply"
    states = {k: "provisional" if manifest[i].role == "char" else "accepted" for i, k in enumerate(first.membership)}
    states.update(first.lifecycle)
    return manifest, first.manifest_hash, known, states


def step(before: str, after: str) -> tuple[Plan, list[Entry], list[Entry], dict]:
    head, head_hash, known, states = ingest(before)
    manifest = entries(after)
    known = known | {e.key for e in manifest}
    for e in manifest:
        states.setdefault(e.key, "provisional" if e.role == "char" else "accepted")
    result = plan(head, head_hash, manifest, known, states)
    if result.kind == "apply":
        assert apply_ops([e.key for e in head], result.ops) == result.membership
    return result, head, manifest, states


def by_id(manifest: list[Entry], prefix: str) -> Entry:
    return next(e for e in manifest if e.host_logical_id.startswith(prefix))


def test_manifest_hash_matches_plugin_spike():
    for label in ("S1-before", "S9-after", "S14-1000-run1"):
        _, head_hash, _, _ = ingest(label)
        assert head_hash == recorded_manifest_hash(label)


def test_no_change_reload_is_noop():
    result, *_ = step("S10-before", "S10-after")
    assert result.kind == "noop"


def test_append_and_acceptance_s1():
    result, head, manifest, states = step("S1-before", "S1-after")
    assert result.kind == "apply"
    assert result.commit_reason is None  # D4: appends do not create commits
    assert [c.kind for c in result.changes] == ["append", "append"]
    previous_tail = head[-1]
    assert previous_tail.role == "char" and states[previous_tail.key] == "provisional"
    assert result.lifecycle[previous_tail.key] == "accepted"
    assert manifest[-1].key not in result.lifecycle or result.lifecycle[manifest[-1].key] == "provisional"


def test_reroll_s2():
    result, head, manifest, _ = step("S2-before", "S2-after")
    assert result.commit_reason == "reroll"
    (change,) = result.changes
    assert change.kind == "reroll"
    assert change.old == head[-1].key and change.new == manifest[-1].key
    assert result.lifecycle[head[-1].key] == "retracted"
    assert result.lineage[manifest[-1].key] == head[-1].key
    assert manifest[-1].swipe_count == 2  # H4: previous reply moves into the new message's swipes


def test_swipe_switch_s3():
    result, head, manifest, _ = step("S3-before", "S3-after")
    assert result.commit_reason == "swipe"
    (change,) = result.changes
    assert change.kind == "swipe" and change.host_logical_id == head[-1].host_logical_id
    assert result.lifecycle[head[-1].key] == "superseded"


def test_continue_with_say_nothing_is_an_append_s4():
    result, _, manifest, _ = step("S4-before", "S4-after")
    assert result.commit_reason is None
    assert [c.kind for c in result.changes] == ["append"]
    assert manifest[-1].role == "char"


def test_continue_extends_in_place_s4b():
    result, head, manifest, _ = step("S4b-before", "S4b-after")
    assert result.commit_reason == "edit"
    (change,) = result.changes
    assert change.kind == "continue"
    assert result.lineage[manifest[-1].key] == head[-1].key
    assert result.lifecycle[head[-1].key] == "superseded"


@pytest.mark.parametrize("scenario,prefix,role", [("S5", "f3c47d86", "user"), ("S6", "a3f81796", "char")])
def test_edit_old_message(scenario, prefix, role):
    result, head, manifest, _ = step(f"{scenario}-before", f"{scenario}-after")
    assert result.commit_reason == "edit"
    (change,) = result.changes
    assert change.kind == "edit" and change.host_logical_id.startswith(prefix)
    assert by_id(manifest, prefix).role == role
    assert result.lifecycle[by_id(head, prefix).key] == "superseded"


def test_delete_middle_s7():
    result, head, _, _ = step("S7-before", "S7-after")
    assert result.commit_reason == "delete"
    (change,) = result.changes
    assert change.kind == "delete" and change.host_logical_id.startswith("5e2370a0")
    assert by_id(head, "5e2370a0").key not in result.membership


@pytest.mark.parametrize("scenario,prefix,value", [("S8", "6fcccbc7", True), ("S8b", "f3c47d86", "allBefore")])
def test_disable(scenario, prefix, value):
    result, _, manifest, _ = step(f"{scenario}-before", f"{scenario}-after")
    assert result.commit_reason == "disable"
    (change,) = result.changes
    assert change.kind == "disable" and change.host_logical_id.startswith(prefix)
    assert by_id(manifest, prefix).disabled == value


def test_branch_is_new_conversation_with_origin_s9():
    manifest = entries("S9-after")
    result = plan(None, None, manifest, {e.key for e in manifest}, {})
    assert result.commit_reason == "branch"
    assert result.branch == {
        "chat_ref": chat_id("S9-before"),
        "chat_name": "New Chat 2",
        "message_ref": "a3f81796-18cc-42fd-9306-78371f3e68a1",
    }


def test_import_is_new_conversation_s10():
    manifest = entries("S10-imported")
    result = plan(None, None, manifest, {e.key for e in manifest}, {})
    assert result.commit_reason == "import"
    assert result.branch is None
    assert chat_id("S10-imported") != chat_id("S10-before")


def test_large_divergence():
    # Recorded manifests of two different chats offered as the same conversation: every id unknown.
    result, *_ = step("S1-after", "S9-after")
    assert result.commit_reason == "reconciliation"
    assert result.ops[0]["op"] == "set"


def test_unknown_revisions_need_bodies():
    head, head_hash, known, states = ingest("S1-before")
    result = plan(head, head_hash, entries("S1-after"), known, states)
    assert result.kind == "needs_bodies"
    assert [k[0][:8] for k in result.needed] == ["fda7d327", "9fc87c88"]


def test_retry_resend_is_noop():
    result, head, manifest, states = step("S2-before", "S2-after")
    again = plan(manifest, result.manifest_hash, manifest, {e.key for e in head + manifest}, states)
    assert again.kind == "noop"


def test_mixed_changes_keep_fine_grained_ops():
    # Recorded S5 (edit) and S7 (delete) happened between two requests: one commit, not a full reset.
    head, head_hash, known, states = ingest("S5-before")
    manifest = [e for e in entries("S7-after")]
    known |= {e.key for e in manifest}
    for e in manifest:
        states.setdefault(e.key, "accepted")
    result = plan(head, head_hash, manifest, known, states)
    assert result.commit_reason == "reconciliation"
    assert {c.kind for c in result.changes} >= {"edit", "delete"}
    assert all(op["op"] != "set" for op in result.ops)
    assert apply_ops([e.key for e in head], result.ops) == result.membership


def test_live_reroll_retracts_tail_before_regeneration():
    # Recorded S2 beforeRequest saw 7 host messages: the host removed the tail reply before the
    # request ran, so the manifest NMOS receives is S2-before minus its tail.
    head, head_hash, known, states = ingest("S2-before")
    result = plan(head, head_hash, head[:-1], known, states)
    assert result.commit_reason == "reroll"
    (change,) = result.changes
    assert change.kind == "reroll" and change.old == head[-1].key
    assert result.lifecycle[head[-1].key] == "retracted"
    assert result.membership == [e.key for e in head[:-1]]


def test_deleting_a_middle_accepted_message_does_not_retract_it():
    result, head, _, states = step("S7-before", "S7-after")
    removed = next(c for c in result.changes if c.kind == "delete")
    assert states[removed.old] == "accepted" and removed.old not in result.lifecycle
