"""
Smoke tests for maestro/librarian/crypto.py — Ed25519 primitives.

Pure crypto; no filesystem touched. Persistence and signing flow
land in later steps of the Scribe threshold-signature track.
"""

import pytest

from maestro.librarian.crypto import (
    KEY_ID_PREFIX,
    KEY_ID_HEX_LEN,
    generate_keypair,
    key_id_from_public_pem,
    sign,
    verify,
)


# ---- keypair generation ----


def test_generate_keypair_returns_two_pem_strings():
    private_pem, public_pem = generate_keypair()
    assert isinstance(private_pem, bytes)
    assert isinstance(public_pem, bytes)
    assert b"-----BEGIN PRIVATE KEY-----" in private_pem
    assert b"-----BEGIN PUBLIC KEY-----" in public_pem


def test_generate_keypair_produces_distinct_keys():
    a_priv, a_pub = generate_keypair()
    b_priv, b_pub = generate_keypair()
    assert a_priv != b_priv
    assert a_pub != b_pub


# ---- key id derivation ----


def test_key_id_format_is_sha256_prefix_plus_hex():
    _, pub_pem = generate_keypair()
    key_id = key_id_from_public_pem(pub_pem)
    assert key_id.startswith(KEY_ID_PREFIX)
    hex_part = key_id[len(KEY_ID_PREFIX):]
    assert len(hex_part) == KEY_ID_HEX_LEN
    assert all(c in "0123456789abcdef" for c in hex_part)


def test_key_id_is_deterministic():
    _, pub_pem = generate_keypair()
    a = key_id_from_public_pem(pub_pem)
    b = key_id_from_public_pem(pub_pem)
    assert a == b


def test_key_id_distinct_for_distinct_keys():
    _, pub_a = generate_keypair()
    _, pub_b = generate_keypair()
    assert key_id_from_public_pem(pub_a) != key_id_from_public_pem(pub_b)


# ---- sign / verify round trip ----


def test_sign_verify_round_trip():
    priv_pem, pub_pem = generate_keypair()
    message = b"sha256:abcdef0123456789"
    signature = sign(priv_pem, message)
    assert isinstance(signature, bytes)
    assert len(signature) == 64    # Ed25519 signature length
    assert verify(pub_pem, message, signature) is True


def test_signature_is_deterministic_for_same_message():
    """Ed25519 signatures are deterministic per RFC 8032: signing the
    same message twice with the same key produces the same bytes.
    """
    priv_pem, _ = generate_keypair()
    msg = b"deterministic-payload"
    sig_a = sign(priv_pem, msg)
    sig_b = sign(priv_pem, msg)
    assert sig_a == sig_b


def test_verify_rejects_tampered_message():
    priv_pem, pub_pem = generate_keypair()
    sig = sign(priv_pem, b"original message")
    assert verify(pub_pem, b"original messagE", sig) is False


def test_verify_rejects_tampered_signature():
    priv_pem, pub_pem = generate_keypair()
    sig = bytearray(sign(priv_pem, b"payload"))
    sig[0] ^= 0x01     # flip a bit
    assert verify(pub_pem, b"payload", bytes(sig)) is False


def test_verify_rejects_wrong_key():
    priv_a, _ = generate_keypair()
    _, pub_b = generate_keypair()
    sig = sign(priv_a, b"payload")
    assert verify(pub_b, b"payload", sig) is False


def test_verify_returns_false_on_malformed_inputs():
    """Defensive: garbage inputs must not raise; the Librarian's
    commit path counts valid sigs and a False is just one that
    doesn't count.
    """
    assert verify(b"not a pem", b"msg", b"sig") is False
    assert verify(b"", b"msg", b"sig") is False
    priv, pub = generate_keypair()
    assert verify(pub, b"msg", b"") is False
    assert verify(pub, b"msg", b"\x00" * 64) is False


def test_sign_rejects_non_ed25519_private_key():
    """Sanity: feeding a non-Ed25519 PEM into sign() raises rather
    than silently producing a different-algorithm signature.
    """
    # An obviously-wrong PEM blob
    with pytest.raises(Exception):
        sign(b"-----BEGIN PRIVATE KEY-----\ngarbage\n-----END PRIVATE KEY-----", b"msg")
