"""
Crypto primitives for the Librarian — Ed25519 sign / verify / keygen.

This module is the *only* place in maestro/librarian/ that imports
``cryptography``. Every other module routes its signing and
verification through these helpers.

Functions are pure (no filesystem, no global state). Persistence
lives in ``scribe.ScribeKeyStore``; verification policy lives in
the trust-list and policy loaders.

Algorithm: Ed25519. Public and private keys are exchanged as PEM-
encoded byte strings — the Scribe key store on disk is PEM, the
``trusted.json`` entries are PEM, and the wire format used by
federation is PEM. ``Signature.algo`` is ``"ed25519"`` for every
signature this module produces.

Key id format: ``"sha256:<32hex>"`` derived from the SHA-256 of
the raw public-key bytes (32 bytes for Ed25519). Truncating to 32
hex characters keeps the key id eyeball-friendly while remaining
collision-resistant for the operator-set sizes the Librarian is
designed for. The full hash is recoverable by re-computing.
"""

from __future__ import annotations

import hashlib
from typing import Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


KEY_ID_PREFIX = "sha256:"
KEY_ID_HEX_LEN = 32   # truncated SHA-256, sufficient for Librarian operator sets


def generate_keypair() -> Tuple[bytes, bytes]:
    """Generate a fresh Ed25519 keypair.

    Returns ``(private_pem, public_pem)``. The private key is in
    PKCS#8 / PEM form with no encryption (the Librarian relies on
    filesystem mode 0600 in ``ScribeKeyStore`` for at-rest
    protection; an encrypted-key option is a follow-up).
    """
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def key_id_from_public_pem(public_pem: bytes) -> str:
    """Derive the canonical key id for a public PEM.

    Format: ``"sha256:<32hex>"``. Deterministic — re-deriving the
    id from the same PEM always yields the same string.
    """
    public_key = serialization.load_pem_public_key(public_pem)
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    digest = hashlib.sha256(raw).hexdigest()
    return f"{KEY_ID_PREFIX}{digest[:KEY_ID_HEX_LEN]}"


def sign(private_pem: bytes, message: bytes) -> bytes:
    """Sign ``message`` with the Ed25519 private key in ``private_pem``.

    Returns the raw signature bytes (64 bytes for Ed25519). The
    Librarian wraps this in a base64 string when serializing into
    a manifest; this primitive returns raw bytes so the wrapper
    layer owns the encoding choice.
    """
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError(
            "private_pem does not decode to an Ed25519 private key"
        )
    return private_key.sign(message)


def verify(public_pem: bytes, message: bytes, signature: bytes) -> bool:
    """Verify ``signature`` against ``message`` under ``public_pem``.

    Returns ``True`` iff the signature is valid. Returns ``False``
    on any verification failure — tampered message, tampered
    signature, wrong key, malformed inputs. Does not raise; the
    Librarian's commit path counts valid signatures and a False
    is just one signature that doesn't count.
    """
    try:
        public_key = serialization.load_pem_public_key(public_pem)
    except Exception:
        return False
    if not isinstance(public_key, Ed25519PublicKey):
        return False
    try:
        public_key.verify(signature, message)
    except InvalidSignature:
        return False
    except Exception:
        return False
    return True
