"""
Smoke tests for maestro/librarian/verification.py — verify_manifest.

Exercises the V2 single-call API: takes a manifest + body + trust
list + policy, returns a VerificationResult with per-signature
outcomes and a threshold decision. Hash integrity, unknown signers,
malformed sigs, wrong algos, and threshold logic are all covered.
"""

import base64
import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from maestro.librarian.crypto import generate_keypair, sign
from maestro.librarian.scribe import Scribe, ScribeKeyStore
from maestro.librarian.types import (
    CanonicalForm,
    CartridgeKind,
    Manifest,
    Policy,
    Signature,
    TrustedKey,
    TrustList,
)
from maestro.librarian.verification import (
    SignatureResult,
    VerificationResult,
    _verify_one_sig,
    verify_manifest,
)


# ---- helpers ----


def _draft_manifest(**overrides) -> Manifest:
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


def _sign_with_scribe(tmp_path, body=b"the body"):
    """Build a Scribe + keystore and sign a draft manifest with one
    fresh key. Returns (signed_manifest, body, key_id, ScribeKeyStore).
    """
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    s = Scribe(keystore=ks, policy=Policy())
    key_id = ks.add_keypair()
    signed = s.anchor(_draft_manifest(), body, [key_id])
    return signed, body, key_id, ks


def _trust_list_for(ks: ScribeKeyStore, *key_ids) -> TrustList:
    """Build a TrustList containing the given key_ids drawn from
    the keystore.
    """
    keys = {}
    for kid in key_ids:
        keys[kid] = TrustedKey(
            key_id=kid,
            public_key=ks.get_public_pem(kid),
            added_at=datetime.now(timezone.utc).isoformat(),
            added_by_operator_key="sha256:" + "0" * 32,
        )
    return TrustList(keys=keys, operator_signature="")


# ---- happy paths ----


def test_verify_manifest_valid_single_sig_default_threshold(tmp_path):
    signed, body, key_id, ks = _sign_with_scribe(tmp_path)
    trust = _trust_list_for(ks, key_id)
    policy = Policy()  # default threshold = 1

    result = verify_manifest(signed, body, trust, policy)

    assert isinstance(result, VerificationResult)
    assert result.content_hash_ok is True
    assert result.manifest_hash_ok is True
    assert result.threshold_required == 1
    assert result.valid_count == 1
    assert result.threshold_met is True
    assert len(result.valid_signatures) == 1
    assert result.invalid_signatures == []


def test_verify_manifest_threshold_lookup_by_kind(tmp_path):
    signed, body, key_id, ks = _sign_with_scribe(tmp_path)
    trust = _trust_list_for(ks, key_id)
    # statute_text requires 2 sigs, but our manifest is unit_definition
    policy = Policy(min_signatures_by_kind={
        "statute_text": 2,
        "unit_definition": 1,
    })
    result = verify_manifest(signed, body, trust, policy)
    assert result.threshold_required == 1
    assert result.threshold_met is True


def test_verify_manifest_threshold_default_is_one(tmp_path):
    signed, body, key_id, ks = _sign_with_scribe(tmp_path)
    trust = _trust_list_for(ks, key_id)
    policy = Policy()  # no entries
    result = verify_manifest(signed, body, trust, policy)
    assert result.threshold_required == 1


def test_verify_manifest_two_sigs_meets_threshold_two(tmp_path):
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    s = Scribe(keystore=ks, policy=Policy())
    a = ks.add_keypair()
    b = ks.add_keypair()
    signed = s.anchor(_draft_manifest(), b"body", [a, b])
    trust = _trust_list_for(ks, a, b)
    policy = Policy(min_signatures_by_kind={"unit_definition": 2})

    result = verify_manifest(signed, b"body", trust, policy)
    assert result.valid_count == 2
    assert result.threshold_met is True


def test_verify_manifest_one_sig_under_threshold_two(tmp_path):
    signed, body, key_id, ks = _sign_with_scribe(tmp_path)
    trust = _trust_list_for(ks, key_id)
    policy = Policy(min_signatures_by_kind={"unit_definition": 2})

    result = verify_manifest(signed, body, trust, policy)
    assert result.valid_count == 1
    assert result.threshold_required == 2
    assert result.threshold_met is False


# ---- hash-integrity failures ----


def test_verify_manifest_body_tamper_rejects_all_sigs(tmp_path):
    signed, body, key_id, ks = _sign_with_scribe(tmp_path)
    trust = _trust_list_for(ks, key_id)
    policy = Policy()

    result = verify_manifest(signed, b"tampered body", trust, policy)
    assert result.content_hash_ok is False
    assert result.threshold_met is False
    assert result.valid_count == 0
    # Each existing signature is reported invalid with the integrity reason
    assert len(result.invalid_signatures) == 1
    _, reason = result.invalid_signatures[0]
    assert "content_hash" in reason


def test_verify_manifest_field_tamper_rejects_all_sigs(tmp_path):
    signed, body, key_id, ks = _sign_with_scribe(tmp_path)
    trust = _trust_list_for(ks, key_id)
    policy = Policy()

    tampered = replace(signed, domain_tags=["different"])
    result = verify_manifest(tampered, body, trust, policy)
    assert result.manifest_hash_ok is False
    assert result.threshold_met is False
    _, reason = result.invalid_signatures[0]
    assert "manifest_hash" in reason


# ---- per-signature failures ----


def test_unknown_signer_is_invalid(tmp_path):
    signed, body, key_id, ks = _sign_with_scribe(tmp_path)
    trust = TrustList(keys={}, operator_signature="")
    policy = Policy()

    result = verify_manifest(signed, body, trust, policy)
    assert result.valid_count == 0
    assert result.threshold_met is False
    assert len(result.invalid_signatures) == 1
    _, reason = result.invalid_signatures[0]
    assert "unknown signer" in reason


def test_unsupported_algo_is_invalid(tmp_path):
    signed, body, key_id, ks = _sign_with_scribe(tmp_path)
    trust = _trust_list_for(ks, key_id)
    policy = Policy()

    # Replace the algo on the signature
    bad_sig = replace(signed.signatures[0], algo="rsa")
    bad_manifest = replace(signed, signatures=[bad_sig])
    # Recompute manifest_hash since we reshaped (signatures are
    # elided in canonicalization, so this still equals the original)
    result = verify_manifest(bad_manifest, body, trust, policy)
    assert result.valid_count == 0
    _, reason = result.invalid_signatures[0]
    assert "unsupported algo" in reason


def test_malformed_base64_is_invalid(tmp_path):
    signed, body, key_id, ks = _sign_with_scribe(tmp_path)
    trust = _trust_list_for(ks, key_id)
    policy = Policy()

    bad_sig = replace(signed.signatures[0], sig="!!!not-valid-base64!!!")
    bad_manifest = replace(signed, signatures=[bad_sig])
    result = verify_manifest(bad_manifest, body, trust, policy)
    assert result.valid_count == 0
    _, reason = result.invalid_signatures[0]
    assert "base64" in reason


def test_tampered_signature_bits_rejected(tmp_path):
    signed, body, key_id, ks = _sign_with_scribe(tmp_path)
    trust = _trust_list_for(ks, key_id)
    policy = Policy()

    # Flip one bit in the decoded signature, re-encode
    raw = bytearray(base64.b64decode(signed.signatures[0].sig))
    raw[0] ^= 0x01
    bad_sig = replace(
        signed.signatures[0],
        sig=base64.b64encode(bytes(raw)).decode("ascii"),
    )
    bad_manifest = replace(signed, signatures=[bad_sig])
    result = verify_manifest(bad_manifest, body, trust, policy)
    assert result.valid_count == 0
    _, reason = result.invalid_signatures[0]
    assert "does not verify" in reason


# ---- mixed validity ----


def test_one_valid_one_unknown_meets_threshold_one(tmp_path):
    """Two signatures, one valid, one from an untrusted key.
    Default threshold (1) is met.
    """
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    s = Scribe(keystore=ks, policy=Policy())
    a = ks.add_keypair()
    b = ks.add_keypair()
    signed = s.anchor(_draft_manifest(), b"body", [a, b])
    # Only trust 'a' — 'b' becomes unknown
    trust = _trust_list_for(ks, a)
    policy = Policy()

    result = verify_manifest(signed, b"body", trust, policy)
    assert result.valid_count == 1
    assert result.threshold_met is True
    # The b signature is in invalid_signatures with "unknown signer"
    invalid_keys = [sig.key_id for sig, _ in result.invalid_signatures]
    assert b in invalid_keys


def test_one_valid_one_unknown_under_threshold_two(tmp_path):
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    s = Scribe(keystore=ks, policy=Policy())
    a = ks.add_keypair()
    b = ks.add_keypair()
    signed = s.anchor(_draft_manifest(), b"body", [a, b])
    trust = _trust_list_for(ks, a)
    policy = Policy(min_signatures_by_kind={"unit_definition": 2})

    result = verify_manifest(signed, b"body", trust, policy)
    assert result.valid_count == 1
    assert result.threshold_required == 2
    assert result.threshold_met is False


# ---- direct unit test on _verify_one_sig ----


def test_verify_one_sig_happy_path():
    """A directly-constructed signature against a small message."""
    priv, pub = generate_keypair()
    msg = "sha256:" + "a" * 64
    raw_sig = sign(priv, msg.encode("utf-8"))
    fake_key_id = "sha256:" + "f" * 32
    sig = Signature(
        key_id=fake_key_id,
        algo="ed25519",
        sig=base64.b64encode(raw_sig).decode("ascii"),
        signed_at="2024-01-01T00:00:00Z",
    )
    trust = TrustList(
        keys={
            fake_key_id: TrustedKey(
                key_id=fake_key_id,
                public_key=pub.decode("utf-8"),
                added_at="",
                added_by_operator_key="",
            ),
        },
        operator_signature="",
    )
    out = _verify_one_sig(sig, msg, trust)
    assert out.valid is True


# ---- empty manifest (no signatures) ----


def test_no_signatures_under_threshold_one(tmp_path):
    """Hash-consistent manifest with zero signatures: threshold not met."""
    # Build a minimally-hashed manifest by signing then stripping
    signed, body, key_id, ks = _sign_with_scribe(tmp_path)
    no_sigs = replace(signed, signatures=[])
    trust = _trust_list_for(ks, key_id)
    policy = Policy()

    result = verify_manifest(no_sigs, body, trust, policy)
    assert result.valid_count == 0
    assert result.threshold_met is False
    assert result.signatures == ()
