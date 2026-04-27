"""
End-to-end integration test for the Scribe threshold-signature track.

Demonstrates the full multi-Scribe flow from key generation through
commit and load:

  1. Operator generates an operator keypair.
  2. Three Scribes (A, B, C) each generate their own keypair.
  3. Trust list is built with all three Scribe public keys, signed
     by the operator, persisted via save_trust_list.
  4. Policy declares min_signatures_by_kind["unit_definition"] = 2
     (2-of-3 threshold), persisted via save_policy.
  5. Trust list and policy are loaded fresh from disk.
  6. Scribe A signs a draft manifest -> commit fails (threshold).
  7. Scribe B accumulates a signature -> commit succeeds.
  8. Library round-trips: load(manifest_hash) returns the exact
     manifest that was committed, signatures still verify, hashes
     still match.
  9. On-disk layout invariants: by-hash/{aa}/{manifest}.json,
     by-hash/{bb}/{content}.body, by-id/{id}/head ->
     manifest, by-id/{id}/versions/{v} -> manifest.

Plus negative tests:

  * Committing the manifest with only one signature against a
    threshold of 2 raises PolicyError with the VerificationResult
    attached.
  * On-disk tamper of the body bytes is detected by load() and
    the manifest is refused.
  * On-disk tamper of the manifest JSON is detected by load().
"""

import base64
import json
import os
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from maestro.librarian.crypto import (
    generate_keypair,
    key_id_from_public_pem,
    verify,
)
from maestro.librarian.loaders import (
    load_policy,
    load_trust_list,
    save_policy,
    save_trust_list,
)
from maestro.librarian.scribe import Scribe, ScribeKeyStore
from maestro.librarian.store import (
    Librarian,
    LoadResult,
    PolicyError,
)
from maestro.librarian.types import (
    CanonicalForm,
    CartridgeKind,
    Manifest,
    Policy,
    TrustedKey,
    TrustList,
)


# ---- end-to-end fixture ----


def _build_world(tmp_path, threshold: int = 2):
    """Set up an operator, three Scribes, signed trust list, policy
    on disk, and a fresh Librarian instance.

    Returns a dict with all the pieces a test needs.
    """
    # Operator keypair (out-of-band; not in any Scribe keystore)
    op_priv, op_pub_bytes = generate_keypair()
    op_pub = op_pub_bytes.decode("utf-8")
    op_fp = key_id_from_public_pem(op_pub_bytes)

    # Three Scribes, each with their own keystore
    ks_a = ScribeKeyStore(keys_dir=tmp_path / "scribe-a")
    ks_b = ScribeKeyStore(keys_dir=tmp_path / "scribe-b")
    ks_c = ScribeKeyStore(keys_dir=tmp_path / "scribe-c")
    a_key = ks_a.add_keypair()
    b_key = ks_b.add_keypair()
    c_key = ks_c.add_keypair()

    scribe_a = Scribe(keystore=ks_a, policy=Policy())
    scribe_b = Scribe(keystore=ks_b, policy=Policy())
    scribe_c = Scribe(keystore=ks_c, policy=Policy())

    # Build + persist policy and trust list
    policy_path = tmp_path / "policy.json"
    trust_path = tmp_path / "trusted.json"

    policy = Policy(
        min_signatures_by_kind={"unit_definition": threshold},
        review_external_imports=False,
        import_caps_by_key={},
        canonical_form_registry=["bytes/raw"],
        operator_key_fingerprint=op_fp,
    )
    save_policy(policy, policy_path, operator_key_pem=op_pub)

    now = datetime.now(timezone.utc).isoformat()
    trust = TrustList(
        keys={
            a_key: TrustedKey(a_key, ks_a.get_public_pem(a_key), now, op_fp),
            b_key: TrustedKey(b_key, ks_b.get_public_pem(b_key), now, op_fp),
            c_key: TrustedKey(c_key, ks_c.get_public_pem(c_key), now, op_fp),
        },
        operator_signature="",
    )
    save_trust_list(trust, trust_path, op_priv)

    # Fresh load from disk simulates a real deployment booting up
    loaded_policy = load_policy(policy_path)
    loaded_trust = load_trust_list(trust_path, policy_path)

    librarian = Librarian(
        root_dir=tmp_path / "librarian",
        trust_list=loaded_trust,
        policy=loaded_policy,
    )

    return {
        "op_priv": op_priv,
        "op_pub": op_pub,
        "op_fp": op_fp,
        "scribe_a": scribe_a,
        "scribe_b": scribe_b,
        "scribe_c": scribe_c,
        "a_key": a_key,
        "b_key": b_key,
        "c_key": c_key,
        "ks_a": ks_a,
        "ks_b": ks_b,
        "ks_c": ks_c,
        "policy": loaded_policy,
        "trust": loaded_trust,
        "librarian": librarian,
        "tmp_path": tmp_path,
    }


def _draft(**overrides) -> Manifest:
    defaults = dict(
        cartridge_id="si-prefixes",
        version="2024.01.01",
        kind=CartridgeKind.UNIT_DEFINITION,
        content_hash="",
        manifest_hash="",
        canonical_form=CanonicalForm.BYTES_RAW,
        supersedes=[],
        revokes=[],
        domain_tags=["unit.si"],
        issued_at="2024-01-01T00:00:00+00:00",
        not_before=None,
        not_after=None,
        signatures=[],
        metadata={},
    )
    defaults.update(overrides)
    return Manifest(**defaults)


# ---- happy path ----


def test_threshold_met_after_two_scribes(tmp_path):
    """Sign with A only -> commit fails. Add B's signature -> commit
    succeeds. Verify on-disk layout and load round-trip.
    """
    w = _build_world(tmp_path, threshold=2)
    body = b"a liter is a liter"

    after_a = w["scribe_a"].anchor(_draft(), body, [w["a_key"]])
    with pytest.raises(PolicyError) as exc_info:
        w["librarian"].commit(after_a, body)
    err = exc_info.value
    assert err.verification_result.threshold_required == 2
    assert err.verification_result.valid_count == 1
    assert err.verification_result.threshold_met is False

    # Accumulate B's signature and retry
    after_b = w["scribe_b"].anchor(after_a, body, [w["b_key"]])
    committed = w["librarian"].commit(after_b, body)
    assert committed is after_b

    # On-disk layout
    store_root = tmp_path / "librarian" / "store"
    bare_manifest_hash = committed.manifest_hash.split(":", 1)[1]
    bare_content_hash = committed.content_hash.split(":", 1)[1]
    manifest_file = (
        store_root / "by-hash" / bare_manifest_hash[:2]
        / f"{bare_manifest_hash}.json"
    )
    body_file = (
        store_root / "by-hash" / bare_content_hash[:2]
        / f"{bare_content_hash}.body"
    )
    head_link = store_root / "by-id" / "si-prefixes" / "head"
    version_link = store_root / "by-id" / "si-prefixes" / "versions" / "2024.01.01"

    assert manifest_file.is_file()
    assert body_file.is_file()
    assert body_file.read_bytes() == body
    assert head_link.is_symlink()
    assert version_link.is_symlink()
    # Both symlinks resolve to the same manifest file
    assert head_link.resolve() == manifest_file.resolve()
    assert version_link.resolve() == manifest_file.resolve()


def test_load_round_trip_preserves_manifest(tmp_path):
    """After commit, load() returns an equal Manifest."""
    w = _build_world(tmp_path, threshold=2)
    body = b"a liter is a liter"
    after_a = w["scribe_a"].anchor(_draft(), body, [w["a_key"]])
    after_b = w["scribe_b"].anchor(after_a, body, [w["b_key"]])
    committed = w["librarian"].commit(after_b, body)

    result = w["librarian"].load(committed.manifest_hash)
    assert isinstance(result, LoadResult)
    assert result.manifest is not None
    assert result.reason == ""
    assert result.manifest == committed


def test_load_signatures_still_verify(tmp_path):
    """The signatures on a loaded manifest verify against the
    public PEMs from the trust list.
    """
    w = _build_world(tmp_path, threshold=2)
    body = b"the body"
    after_a = w["scribe_a"].anchor(_draft(), body, [w["a_key"]])
    after_b = w["scribe_b"].anchor(after_a, body, [w["b_key"]])
    committed = w["librarian"].commit(after_b, body)

    loaded = w["librarian"].load(committed.manifest_hash).manifest
    msg = loaded.manifest_hash.encode("utf-8")
    for sig in loaded.signatures:
        trusted = w["trust"].keys[sig.key_id]
        raw = base64.b64decode(sig.sig)
        assert verify(trusted.public_key.encode("utf-8"), msg, raw) is True


def test_load_body_round_trip(tmp_path):
    w = _build_world(tmp_path, threshold=2)
    body = b"binary body bytes"
    m = w["scribe_a"].anchor(_draft(), body, [w["a_key"]])
    m = w["scribe_b"].anchor(m, body, [w["b_key"]])
    committed = w["librarian"].commit(m, body)

    assert w["librarian"].load_body(committed.content_hash) == body


def test_head_returns_committed_manifest(tmp_path):
    w = _build_world(tmp_path, threshold=2)
    body = b"x"
    m = w["scribe_a"].anchor(_draft(), body, [w["a_key"]])
    m = w["scribe_b"].anchor(m, body, [w["b_key"]])
    committed = w["librarian"].commit(m, body)

    head = w["librarian"].head("si-prefixes")
    assert head == committed


# ---- threshold variations ----


def test_threshold_one_succeeds_with_one_scribe(tmp_path):
    w = _build_world(tmp_path, threshold=1)
    body = b"single-sig body"
    m = w["scribe_a"].anchor(_draft(), body, [w["a_key"]])
    committed = w["librarian"].commit(m, body)
    loaded = w["librarian"].load(committed.manifest_hash).manifest
    assert loaded == committed


def test_threshold_three_requires_all_three(tmp_path):
    w = _build_world(tmp_path, threshold=3)
    body = b"triple-sig body"
    m = w["scribe_a"].anchor(_draft(), body, [w["a_key"]])
    with pytest.raises(PolicyError):
        w["librarian"].commit(m, body)
    m = w["scribe_b"].anchor(m, body, [w["b_key"]])
    with pytest.raises(PolicyError):
        w["librarian"].commit(m, body)
    m = w["scribe_c"].anchor(m, body, [w["c_key"]])
    committed = w["librarian"].commit(m, body)
    assert len(committed.signatures) == 3


# ---- detection at load time ----


def test_load_detects_body_tamper(tmp_path):
    """Mutate the body file on disk; load() must refuse the manifest."""
    w = _build_world(tmp_path, threshold=2)
    body = b"original body"
    m = w["scribe_a"].anchor(_draft(), body, [w["a_key"]])
    m = w["scribe_b"].anchor(m, body, [w["b_key"]])
    committed = w["librarian"].commit(m, body)

    # Tamper
    bare = committed.content_hash.split(":", 1)[1]
    body_file = (
        tmp_path / "librarian" / "store" / "by-hash" / bare[:2]
        / f"{bare}.body"
    )
    body_file.write_bytes(b"tampered body")

    result = w["librarian"].load(committed.manifest_hash)
    assert result.manifest is None
    assert "verification failed" in result.reason
    assert "content_hash_ok=False" in result.reason


def test_load_detects_manifest_tamper(tmp_path):
    """Mutate the manifest JSON on disk; load() must refuse."""
    w = _build_world(tmp_path, threshold=2)
    body = b"the body"
    m = w["scribe_a"].anchor(_draft(), body, [w["a_key"]])
    m = w["scribe_b"].anchor(m, body, [w["b_key"]])
    committed = w["librarian"].commit(m, body)

    # Tamper: change a substantive field in the on-disk JSON.
    bare = committed.manifest_hash.split(":", 1)[1]
    manifest_file = (
        tmp_path / "librarian" / "store" / "by-hash" / bare[:2]
        / f"{bare}.json"
    )
    data = json.loads(manifest_file.read_text())
    data["domain_tags"] = ["malicious"]
    manifest_file.write_text(json.dumps(data, indent=2, sort_keys=True))

    result = w["librarian"].load(committed.manifest_hash)
    assert result.manifest is None
    assert "manifest_hash_ok=False" in result.reason


def test_load_returns_not_found_for_unknown_hash(tmp_path):
    w = _build_world(tmp_path, threshold=2)
    fake = "sha256:" + "f" * 64
    result = w["librarian"].load(fake)
    assert result.manifest is None
    assert result.reason == "not found"


# ---- E1 invariants ----


def test_policy_error_carries_verification_result(tmp_path):
    """The PolicyError raised on threshold-not-met carries the
    full VerificationResult so callers can branch on which check
    failed.
    """
    w = _build_world(tmp_path, threshold=2)
    body = b"body"
    m = w["scribe_a"].anchor(_draft(), body, [w["a_key"]])
    with pytest.raises(PolicyError) as exc_info:
        w["librarian"].commit(m, body)

    res = exc_info.value.verification_result
    # The single signature was valid, but threshold not met
    assert res.valid_count == 1
    assert res.threshold_required == 2
    assert res.threshold_met is False
    assert res.content_hash_ok is True
    assert res.manifest_hash_ok is True


# ---- supersession ----


def test_supersession_updates_head_symlink(tmp_path):
    """Commit v1 then v2 (with supersedes pointing at v1).
    head/ updates to v2 atomically; v1's manifest file remains in
    by-hash/.
    """
    w = _build_world(tmp_path, threshold=2)
    body_v1 = b"body v1"
    m1 = w["scribe_a"].anchor(_draft(version="v1"), body_v1, [w["a_key"]])
    m1 = w["scribe_b"].anchor(m1, body_v1, [w["b_key"]])
    c1 = w["librarian"].commit(m1, body_v1)

    body_v2 = b"body v2"
    draft_v2 = _draft(version="v2", supersedes=[c1.manifest_hash])
    m2 = w["scribe_a"].anchor(draft_v2, body_v2, [w["a_key"]])
    m2 = w["scribe_b"].anchor(m2, body_v2, [w["b_key"]])
    c2 = w["librarian"].commit(m2, body_v2)

    head = w["librarian"].head("si-prefixes")
    assert head == c2

    # Both versions are loadable by hash
    r1 = w["librarian"].load(c1.manifest_hash)
    r2 = w["librarian"].load(c2.manifest_hash)
    assert r1.manifest == c1
    assert r2.manifest == c2

    # Both version symlinks resolve correctly
    v1_link = tmp_path / "librarian" / "store" / "by-id" / "si-prefixes" / "versions" / "v1"
    v2_link = tmp_path / "librarian" / "store" / "by-id" / "si-prefixes" / "versions" / "v2"
    assert v1_link.is_symlink()
    assert v2_link.is_symlink()
    assert v1_link.resolve() != v2_link.resolve()


# ---- guardrails ----


def test_commit_without_root_raises(tmp_path):
    w = _build_world(tmp_path, threshold=1)
    bad = Librarian(root_dir=None, trust_list=w["trust"], policy=w["policy"])
    body = b"x"
    m = w["scribe_a"].anchor(_draft(), body, [w["a_key"]])
    with pytest.raises(ValueError, match="root_dir"):
        bad.commit(m, body)


def test_commit_without_trust_list_raises(tmp_path):
    bad = Librarian(root_dir=tmp_path / "lib", trust_list=None, policy=Policy())
    fake_manifest = _draft(
        content_hash="sha256:" + "0" * 64,
        manifest_hash="sha256:" + "0" * 64,
    )
    with pytest.raises(ValueError, match="trust_list"):
        bad.commit(fake_manifest, b"body")
