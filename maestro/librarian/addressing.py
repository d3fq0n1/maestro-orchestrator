"""
Content-addressing helpers for Cartridge manifests and bodies.

See docs/architecture/librarian.md §Content Addressing.

All functions here are pure: no filesystem access, no network, no
cryptographic signing. Signing lives in ``scribe.py``; storage in
``store.py``.

Day 1 implementation notes (recorded for honesty):

* Manifest canonicalization uses ``json.dumps(sort_keys=True,
  separators=(',', ':'))`` rather than real RFC 8785. Deterministic
  for the manifest shapes the Librarian produces, but not strict-
  spec compliant for adversarial inputs (RFC 8785 has additional
  rules around number serialization and string escaping). Real
  RFC 8785 is a follow-up.

* Body canonicalization currently lights up only ``bytes/raw``
  (trivial passthrough). ``text/utf8-nfc`` and ``json/rfc8785``
  raise ``NotImplementedError`` so the Librarian refuses to anchor
  a Cartridge whose body needs a not-yet-implemented serializer
  rather than silently produce a non-canonical hash.
"""

import hashlib
import json
from dataclasses import asdict
from typing import Any

from maestro.librarian.types import CanonicalForm, Manifest


_HASH_PREFIX = "sha256:"


# ---- body side ----


def canonicalize_body(body: bytes, form: CanonicalForm) -> bytes:
    """Apply the canonical-form serializer to raw body bytes.

    Used before computing ``content_hash`` so semantically identical
    bodies hash to the same value regardless of author formatting.

    Day 1: only ``BYTES_RAW`` is implemented. The other forms raise
    ``NotImplementedError`` to keep the Librarian honest.
    """
    if form == CanonicalForm.BYTES_RAW:
        return body
    if form == CanonicalForm.TEXT_UTF8_NFC:
        raise NotImplementedError(
            "TEXT_UTF8_NFC canonical form not yet implemented; "
            "use BYTES_RAW or wait for the follow-up that adds "
            "Unicode normalization and LF line-ending handling"
        )
    if form == CanonicalForm.JSON_RFC8785:
        raise NotImplementedError(
            "JSON_RFC8785 canonical form not yet implemented; "
            "use BYTES_RAW or wait for the follow-up that adds "
            "real RFC 8785 number/string serialization"
        )
    raise ValueError(f"unknown canonical form: {form!r}")


def compute_content_hash(body: bytes, form: CanonicalForm) -> str:
    """Return ``"sha256:<hex>"`` over the canonicalized body."""
    canonical = canonicalize_body(body, form)
    digest = hashlib.sha256(canonical).hexdigest()
    return f"{_HASH_PREFIX}{digest}"


def verify_content_hash(body: bytes, form: CanonicalForm, expected: str) -> bool:
    """Return True iff ``compute_content_hash(body, form) == expected``.

    Defensive: mismatched / malformed inputs return False rather
    than raising.
    """
    try:
        return compute_content_hash(body, form) == expected
    except Exception:
        return False


# ---- manifest side ----


def _manifest_to_dict(manifest: Manifest) -> dict:
    """Convert a Manifest to a plain dict suitable for JSON serialization.

    Enum fields are stringified to their ``.value`` so the output is
    JSON-native (no custom encoder needed). The ``signatures`` list
    is converted recursively from Signature dataclasses.
    """
    raw = asdict(manifest)
    # Enums in dataclasses come through as Enum instances; convert to .value
    raw["kind"] = manifest.kind.value
    raw["canonical_form"] = manifest.canonical_form.value
    return raw


def canonicalize_manifest_for_hashing(manifest: Manifest) -> bytes:
    """Serialize a manifest for ``manifest_hash`` computation.

    Elides ``manifest_hash`` and ``signatures`` before serialization.
    This is what Scribes sign.

    Day 1 uses ``json.dumps`` with sorted keys and the most compact
    separators — deterministic for the inputs the Librarian
    produces, but not strict RFC 8785 (see module docstring).
    """
    payload: dict = _manifest_to_dict(manifest)
    payload.pop("manifest_hash", None)
    payload.pop("signatures", None)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def compute_manifest_hash(manifest: Manifest) -> str:
    """Return ``"sha256:<hex>"`` over the canonicalized manifest."""
    canonical = canonicalize_manifest_for_hashing(manifest)
    digest = hashlib.sha256(canonical).hexdigest()
    return f"{_HASH_PREFIX}{digest}"


def verify_manifest_hash(manifest: Manifest) -> bool:
    """Return True iff ``manifest.manifest_hash`` matches its canonical form.

    Defensive: malformed inputs return False rather than raising.
    """
    try:
        return compute_manifest_hash(manifest) == manifest.manifest_hash
    except Exception:
        return False
