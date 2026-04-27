"""
Smoke tests for maestro/librarian/addressing.py — content addressing.

Pure functions; no filesystem.

Day 1 caveats covered:

  * BYTES_RAW is the only body canonical form implemented;
    TEXT_UTF8_NFC and JSON_RFC8785 raise NotImplementedError.
  * Manifest canonicalization uses json.dumps(sort_keys=True,
    separators=(',', ':')) rather than real RFC 8785. Tests verify
    determinism for the inputs the Librarian produces.
"""

import json

import pytest

from maestro.librarian.addressing import (
    canonicalize_body,
    canonicalize_manifest_for_hashing,
    compute_content_hash,
    compute_manifest_hash,
    verify_content_hash,
    verify_manifest_hash,
)
from maestro.librarian.types import (
    CanonicalForm,
    CartridgeKind,
    Manifest,
    Signature,
)


# ---- body canonicalization ----


def test_canonicalize_bytes_raw_passthrough():
    assert canonicalize_body(b"hello world", CanonicalForm.BYTES_RAW) == b"hello world"
    assert canonicalize_body(b"", CanonicalForm.BYTES_RAW) == b""


def test_canonicalize_text_utf8_nfc_not_yet_implemented():
    with pytest.raises(NotImplementedError):
        canonicalize_body(b"abc", CanonicalForm.TEXT_UTF8_NFC)


def test_canonicalize_json_rfc8785_not_yet_implemented():
    with pytest.raises(NotImplementedError):
        canonicalize_body(b"{}", CanonicalForm.JSON_RFC8785)


# ---- content hash ----


def test_content_hash_format_and_determinism():
    h1 = compute_content_hash(b"the body", CanonicalForm.BYTES_RAW)
    h2 = compute_content_hash(b"the body", CanonicalForm.BYTES_RAW)
    assert h1.startswith("sha256:")
    assert len(h1) == len("sha256:") + 64
    assert h1 == h2


def test_content_hash_distinguishes_distinct_bodies():
    a = compute_content_hash(b"alpha", CanonicalForm.BYTES_RAW)
    b = compute_content_hash(b"beta", CanonicalForm.BYTES_RAW)
    assert a != b


def test_verify_content_hash_round_trip():
    body = b"some-canonical-body"
    h = compute_content_hash(body, CanonicalForm.BYTES_RAW)
    assert verify_content_hash(body, CanonicalForm.BYTES_RAW, h) is True
    assert verify_content_hash(b"different", CanonicalForm.BYTES_RAW, h) is False


def test_verify_content_hash_returns_false_on_unknown_form():
    """Defensive: an unknown form yields False rather than raising."""
    h = compute_content_hash(b"x", CanonicalForm.BYTES_RAW)
    # Cast through a fake form value to trigger the ValueError path
    # in canonicalize_body, which verify_content_hash must swallow.
    class _Fake:
        value = "no-such-form"
    assert verify_content_hash(b"x", _Fake(), h) is False


# ---- manifest canonicalization ----


def _sample_manifest(**overrides) -> Manifest:
    """Build a simple Manifest for hashing tests. Caller may override
    any field; defaults are stable so two calls produce equal manifests.
    """
    defaults = dict(
        cartridge_id="si-prefixes",
        version="2024.01.01",
        kind=CartridgeKind.UNIT_DEFINITION,
        content_hash="sha256:" + "a" * 64,
        manifest_hash="sha256:" + "0" * 64,   # placeholder; replaced after compute
        canonical_form=CanonicalForm.BYTES_RAW,
        supersedes=[],
        revokes=[],
        domain_tags=["unit.si"],
        issued_at="2024-01-01T00:00:00Z",
        not_before=None,
        not_after=None,
        signatures=[],
        metadata={},
    )
    defaults.update(overrides)
    return Manifest(**defaults)


def test_canonicalize_manifest_drops_signatures_and_self_hash():
    sig = Signature(
        key_id="sha256:abc",
        algo="ed25519",
        sig="base64sig",
        signed_at="2024-01-01T00:00:00Z",
    )
    m_with = _sample_manifest(signatures=[sig], manifest_hash="sha256:will-differ")
    m_without = _sample_manifest(signatures=[], manifest_hash="sha256:also-different")
    bytes_with = canonicalize_manifest_for_hashing(m_with)
    bytes_without = canonicalize_manifest_for_hashing(m_without)
    # Both must produce identical canonical bytes despite different
    # signatures + manifest_hash fields, because those fields are
    # elided before serialization.
    assert bytes_with == bytes_without


def test_canonicalize_manifest_is_deterministic():
    a = canonicalize_manifest_for_hashing(_sample_manifest())
    b = canonicalize_manifest_for_hashing(_sample_manifest())
    assert a == b


def test_canonicalize_manifest_is_sorted_json():
    """The day-1 canonicalization uses json.dumps(sort_keys=True).
    Verify by parsing back: keys appear in sorted order at every level.
    """
    raw = canonicalize_manifest_for_hashing(_sample_manifest())
    text = raw.decode("utf-8")
    # Round-trip parse to confirm valid JSON
    parsed = json.loads(text)
    assert "cartridge_id" in parsed
    # Sorted keys: walk top-level and ensure they are in sorted order.
    top_keys = list(parsed.keys())
    assert top_keys == sorted(top_keys)


def test_canonicalize_manifest_distinguishes_field_changes():
    a = canonicalize_manifest_for_hashing(_sample_manifest(version="2024.01.01"))
    b = canonicalize_manifest_for_hashing(_sample_manifest(version="2024.06.15"))
    assert a != b


# ---- manifest hash ----


def test_manifest_hash_format_and_determinism():
    h = compute_manifest_hash(_sample_manifest())
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64
    assert compute_manifest_hash(_sample_manifest()) == h


def test_manifest_hash_unaffected_by_signatures_field():
    """Changing only signatures (or manifest_hash itself) must not
    change the computed hash, because both fields are elided.
    """
    sig = Signature(
        key_id="sha256:any",
        algo="ed25519",
        sig="anything",
        signed_at="2024-01-01T00:00:00Z",
    )
    h_unsigned = compute_manifest_hash(_sample_manifest(signatures=[]))
    h_signed = compute_manifest_hash(_sample_manifest(signatures=[sig]))
    assert h_unsigned == h_signed


def test_manifest_hash_changes_with_substantive_field():
    h1 = compute_manifest_hash(_sample_manifest(domain_tags=["a"]))
    h2 = compute_manifest_hash(_sample_manifest(domain_tags=["b"]))
    assert h1 != h2


def test_verify_manifest_hash_round_trip():
    m = _sample_manifest()
    real_hash = compute_manifest_hash(m)
    # Build a manifest whose declared manifest_hash matches
    matching = _sample_manifest(manifest_hash=real_hash)
    assert verify_manifest_hash(matching) is True
    # Build one whose declared hash is wrong
    mismatched = _sample_manifest(manifest_hash="sha256:" + "f" * 64)
    assert verify_manifest_hash(mismatched) is False
