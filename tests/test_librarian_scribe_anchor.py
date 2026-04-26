"""
Smoke tests for maestro/librarian/scribe.py — Scribe.anchor flow.

Covers the multi-Scribe accumulation contract (option Q):

  * First-call branch: compute hashes from body, bind, sign.
  * Subsequent-call branch: recompute hashes, verify, sign more.
  * Double-signing with the same key_id raises (option D1).
  * Body or field tampering between Scribes raises.
  * Empty signing_key_ids raises.

Plus anchor_revocation: produces a kind=REVOCATION manifest with
empty body and the requested revokes list, signed.

Threshold enforcement is NOT exercised here (option C2 + Q):
that's the Librarian's commit-time job, landing in step 5.
"""

import base64
from dataclasses import replace

import pytest

from maestro.librarian.crypto import verify
from maestro.librarian.scribe import Scribe, ScribeKeyStore
from maestro.librarian.types import (
    CanonicalForm,
    CartridgeKind,
    Manifest,
    Policy,
    Signature,
)


# ---- helpers ----


def _draft_manifest(**overrides) -> Manifest:
    """Build a draft (unsigned, placeholder hashes) Manifest the
    caller can hand to Scribe.anchor for the first-call branch.
    """
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


def _make_scribe(tmp_path) -> Scribe:
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    return Scribe(keystore=ks, policy=Policy())


# ---- first-call branch ----


def test_first_call_binds_content_and_manifest_hashes(tmp_path):
    s = _make_scribe(tmp_path)
    key_id = s._keys.add_keypair()

    draft = _draft_manifest()
    body = b"a liter is a liter"
    out = s.anchor(draft, body, [key_id])

    assert out.content_hash.startswith("sha256:")
    assert out.manifest_hash.startswith("sha256:")
    # Content hash is deterministic over the body bytes
    assert len(out.content_hash) == len("sha256:") + 64
    assert len(out.manifest_hash) == len("sha256:") + 64
    # Body bytes themselves are not stored in the manifest
    assert b"liter" not in out.content_hash.encode("utf-8")


def test_first_call_appends_one_signature_per_requested_key(tmp_path):
    s = _make_scribe(tmp_path)
    a = s._keys.add_keypair()
    b_ = s._keys.add_keypair()

    draft = _draft_manifest()
    out = s.anchor(draft, b"body", [a, b_])

    assert len(out.signatures) == 2
    assert {sig.key_id for sig in out.signatures} == {a, b_}
    # All signatures use ed25519 and the scribe role
    for sig in out.signatures:
        assert sig.algo == "ed25519"
        assert sig.role == "scribe"


def test_first_call_signatures_verify(tmp_path):
    s = _make_scribe(tmp_path)
    key_id = s._keys.add_keypair()
    pub_pem = s._keys.get_public_pem(key_id).encode("utf-8")

    draft = _draft_manifest()
    out = s.anchor(draft, b"some body", [key_id])

    sig = out.signatures[0]
    raw_sig = base64.b64decode(sig.sig)
    # The Scribe signs the manifest_hash bytes (UTF-8 encoded)
    assert verify(pub_pem, out.manifest_hash.encode("utf-8"), raw_sig) is True


# ---- subsequent-call branch (multi-Scribe accumulation, Q) ----


def test_two_scribes_accumulate_signatures_in_separate_calls(tmp_path):
    """Models option Q: each Scribe signs in their own call.
    Both signatures end up on the same manifest with hashes
    unchanged.
    """
    ks_a = ScribeKeyStore(keys_dir=tmp_path / "keys-a")
    ks_b = ScribeKeyStore(keys_dir=tmp_path / "keys-b")
    scribe_a = Scribe(keystore=ks_a, policy=Policy())
    scribe_b = Scribe(keystore=ks_b, policy=Policy())
    a_key = ks_a.add_keypair()
    b_key = ks_b.add_keypair()

    draft = _draft_manifest()
    body = b"the body"

    after_a = scribe_a.anchor(draft, body, [a_key])
    assert len(after_a.signatures) == 1

    after_b = scribe_b.anchor(after_a, body, [b_key])
    assert len(after_b.signatures) == 2
    # Hashes are stable across the two anchor calls
    assert after_b.content_hash == after_a.content_hash
    assert after_b.manifest_hash == after_a.manifest_hash
    # Both signatures verify under their respective public keys
    pub_a = ks_a.get_public_pem(a_key).encode("utf-8")
    pub_b = ks_b.get_public_pem(b_key).encode("utf-8")
    msg = after_b.manifest_hash.encode("utf-8")
    sig_a = next(s for s in after_b.signatures if s.key_id == a_key)
    sig_b = next(s for s in after_b.signatures if s.key_id == b_key)
    assert verify(pub_a, msg, base64.b64decode(sig_a.sig)) is True
    assert verify(pub_b, msg, base64.b64decode(sig_b.sig)) is True


def test_subsequent_call_refuses_body_tamper(tmp_path):
    s = _make_scribe(tmp_path)
    a = s._keys.add_keypair()
    b_ = s._keys.add_keypair()

    after_first = s.anchor(_draft_manifest(), b"original body", [a])
    # Now try to add Scribe B's signature with a TAMPERED body
    with pytest.raises(ValueError, match="content_hash mismatch"):
        s.anchor(after_first, b"tampered body", [b_])


def test_subsequent_call_refuses_field_tamper(tmp_path):
    s = _make_scribe(tmp_path)
    a = s._keys.add_keypair()
    b_ = s._keys.add_keypair()

    after_first = s.anchor(_draft_manifest(), b"body", [a])
    # Tamper with a field that's part of the canonical manifest
    # form: domain_tags. The recomputed manifest_hash will differ.
    tampered = replace(after_first, domain_tags=["unit.imperial"])
    with pytest.raises(ValueError, match="manifest_hash mismatch"):
        s.anchor(tampered, b"body", [b_])


# ---- option D1: double-signing refusal ----


def test_double_sign_with_same_key_id_raises(tmp_path):
    s = _make_scribe(tmp_path)
    key_id = s._keys.add_keypair()

    after_first = s.anchor(_draft_manifest(), b"body", [key_id])
    with pytest.raises(ValueError, match="already signed"):
        s.anchor(after_first, b"body", [key_id])


def test_first_call_with_duplicate_key_in_request_raises(tmp_path):
    """Even on first call, asking to sign with the same key_id
    twice raises — the second signature would land on a manifest
    that already has the first.
    """
    s = _make_scribe(tmp_path)
    key_id = s._keys.add_keypair()

    with pytest.raises(ValueError, match="already signed"):
        s.anchor(_draft_manifest(), b"body", [key_id, key_id])


# ---- guardrails ----


def test_empty_signing_key_ids_raises(tmp_path):
    s = _make_scribe(tmp_path)
    with pytest.raises(ValueError, match="empty"):
        s.anchor(_draft_manifest(), b"body", [])


def test_unimplemented_canonical_form_propagates(tmp_path):
    """anchor doesn't enforce policy.canonical_form_registry (C2),
    but the underlying canonicalize_body raises NotImplementedError
    for forms that haven't been wired up. anchor must propagate.
    """
    s = _make_scribe(tmp_path)
    key_id = s._keys.add_keypair()
    draft = _draft_manifest(canonical_form=CanonicalForm.JSON_RFC8785)
    with pytest.raises(NotImplementedError):
        s.anchor(draft, b"{}", [key_id])


# ---- input immutability ----


def test_anchor_does_not_mutate_input_manifest(tmp_path):
    """The Scribe must not silently mutate the caller's manifest.
    Manifest is frozen but its signatures list is a mutable
    container; verify the input list is untouched.
    """
    s = _make_scribe(tmp_path)
    key_id = s._keys.add_keypair()

    draft = _draft_manifest()
    original_sigs = list(draft.signatures)
    out = s.anchor(draft, b"body", [key_id])

    assert draft.signatures == original_sigs   # input untouched
    assert out is not draft                    # new instance
    assert out.signatures is not draft.signatures


# ---- anchor_revocation ----


def test_anchor_revocation_produces_kind_revocation_manifest(tmp_path):
    s = _make_scribe(tmp_path)
    key_id = s._keys.add_keypair()
    revokes = ["sha256:" + "a" * 64, "sha256:" + "b" * 64]

    out = s.anchor_revocation(revokes=revokes, signing_key_ids=[key_id])

    assert out.kind == CartridgeKind.REVOCATION
    assert out.revokes == revokes
    assert out.canonical_form == CanonicalForm.BYTES_RAW
    # Empty body -> deterministic content_hash for empty bytes
    assert out.content_hash.startswith("sha256:")
    assert len(out.signatures) == 1
    assert out.signatures[0].key_id == key_id


def test_anchor_revocation_default_id_unique_per_call(tmp_path):
    """Default cartridge_id includes a microsecond timestamp; two
    calls produce distinct ids.
    """
    s = _make_scribe(tmp_path)
    key_id = s._keys.add_keypair()
    a = s.anchor_revocation(["sha256:" + "1" * 64], [key_id])
    b = s.anchor_revocation(["sha256:" + "2" * 64], [key_id])
    assert a.cartridge_id != b.cartridge_id


def test_anchor_revocation_empty_revokes_raises(tmp_path):
    s = _make_scribe(tmp_path)
    key_id = s._keys.add_keypair()
    with pytest.raises(ValueError, match="empty"):
        s.anchor_revocation(revokes=[], signing_key_ids=[key_id])


def test_anchor_revocation_accumulates_via_anchor(tmp_path):
    """A revocation manifest can have additional signatures
    appended via anchor() exactly like any other manifest.
    """
    s = _make_scribe(tmp_path)
    a_key = s._keys.add_keypair()
    b_key = s._keys.add_keypair()

    rev = s.anchor_revocation(
        revokes=["sha256:" + "f" * 64],
        signing_key_ids=[a_key],
    )
    assert len(rev.signatures) == 1

    after = s.anchor(rev, b"", [b_key])
    assert len(after.signatures) == 2
    assert {sig.key_id for sig in after.signatures} == {a_key, b_key}
