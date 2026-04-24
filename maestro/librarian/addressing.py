"""
Content-addressing helpers for Cartridge manifests and bodies.

See docs/architecture/librarian.md §Content Addressing.

All functions here are pure: no filesystem access, no network, no
cryptographic signing. Signing lives in ``scribe.py``; storage in
``store.py``.
"""

from maestro.librarian.types import CanonicalForm, Manifest


def canonicalize_body(body: bytes, form: CanonicalForm) -> bytes:
    """Apply the canonical-form serializer to raw body bytes.

    Used before computing ``content_hash`` so semantically identical
    bodies hash to the same value regardless of author formatting.

    Raises ValueError if the form is unknown.
    """
    # TODO: dispatch by form:
    #   JSON_RFC8785  -> parse + RFC 8785 re-serialize
    #   TEXT_UTF8_NFC -> NFC normalize + LF line endings + strip BOM
    #   BYTES_RAW     -> return as-is
    raise NotImplementedError


def compute_content_hash(body: bytes, form: CanonicalForm) -> str:
    """Return ``"sha256:<hex>"`` over the canonicalized body."""
    # TODO: canonicalize_body then SHA-256
    raise NotImplementedError


def canonicalize_manifest_for_hashing(manifest: Manifest) -> bytes:
    """Serialize a manifest for ``manifest_hash`` computation.

    Elides ``manifest_hash`` and ``signatures`` before RFC 8785
    canonicalization. This is what Scribes sign.
    """
    # TODO: asdict(manifest) -> remove fields -> rfc8785 serialize
    raise NotImplementedError


def compute_manifest_hash(manifest: Manifest) -> str:
    """Return ``"sha256:<hex>"`` over the canonicalized manifest."""
    # TODO: canonicalize_manifest_for_hashing then SHA-256
    raise NotImplementedError


def verify_content_hash(body: bytes, form: CanonicalForm, expected: str) -> bool:
    """Return True iff ``compute_content_hash(body, form) == expected``."""
    # TODO
    raise NotImplementedError


def verify_manifest_hash(manifest: Manifest) -> bool:
    """Return True iff ``manifest.manifest_hash`` matches its canonical form."""
    # TODO
    raise NotImplementedError
