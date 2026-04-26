"""
Smoke tests for maestro/librarian/scribe.py — ScribeKeyStore.

Filesystem-backed; uses pytest's tmp_path fixture. Mode-enforcement
tests are POSIX-only (skipped on Windows because the Unix mode model
doesn't translate). The ScribeKeyStore itself follows the same rule.
"""

import base64
import os
import stat

import pytest

from maestro.librarian.crypto import verify
from maestro.librarian.scribe import (
    KeyStorePermissionError,
    ScribeKeyStore,
)
from maestro.librarian.types import Signature


_POSIX_ONLY = pytest.mark.skipif(
    os.name != "posix",
    reason="mode enforcement is POSIX-only",
)


# ---- add_keypair ----


def test_add_keypair_creates_directory_tree(tmp_path):
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    key_id = ks.add_keypair()
    assert (tmp_path / "keys").is_dir()
    assert (tmp_path / "keys" / "public").is_dir()
    assert key_id.startswith("sha256:")


def test_add_keypair_writes_private_and_public(tmp_path):
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    key_id = ks.add_keypair()
    priv = tmp_path / "keys" / f"{key_id}.ed25519.pem"
    pub = tmp_path / "keys" / "public" / f"{key_id}.ed25519.pub"
    assert priv.exists()
    assert pub.exists()
    assert b"-----BEGIN PRIVATE KEY-----" in priv.read_bytes()
    assert b"-----BEGIN PUBLIC KEY-----" in pub.read_bytes()


@_POSIX_ONLY
def test_add_keypair_sets_correct_modes(tmp_path):
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    key_id = ks.add_keypair()
    assert stat.S_IMODE((tmp_path / "keys").stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "keys" / "public").stat().st_mode) == 0o700
    priv = tmp_path / "keys" / f"{key_id}.ed25519.pem"
    assert stat.S_IMODE(priv.stat().st_mode) == 0o600


def test_add_keypair_refuses_overwrite(tmp_path, monkeypatch):
    """add_keypair must refuse to overwrite an existing private key.
    Real Ed25519 generation never collides, so we monkeypatch the
    generator to force two add_keypair calls onto the same key_id.
    """
    from maestro.librarian import scribe as scribe_mod
    from maestro.librarian.crypto import generate_keypair as _real

    cached = _real()
    monkeypatch.setattr(scribe_mod, "_generate_keypair", lambda: cached)

    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    key_id = ks.add_keypair()
    # Same monkeypatched generator -> same key_id collision
    with pytest.raises(FileExistsError):
        ks.add_keypair()
    # First key remains intact
    priv = tmp_path / "keys" / f"{key_id}.ed25519.pem"
    assert priv.exists()


# ---- list_key_ids ----


def test_list_key_ids_returns_added_keys(tmp_path):
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    a = ks.add_keypair()
    b = ks.add_keypair()
    ids = ks.list_key_ids()
    assert a in ids
    assert b in ids
    assert ids == sorted(ids)


def test_list_key_ids_ignores_non_matching_files(tmp_path):
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    ks.add_keypair()
    # Drop an unrelated file in the keys dir
    (tmp_path / "keys" / "README.txt").write_text("nothing to see")
    ids = ks.list_key_ids()
    assert all(i.startswith("sha256:") for i in ids)
    assert len(ids) == 1


def test_list_key_ids_skips_subdirectories(tmp_path):
    """The 'public' subdir lives inside keys_dir; iterdir would
    yield it, and a naive impl would try to treat it as a key file.
    Confirm the skip.
    """
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    ks.add_keypair()
    ids = ks.list_key_ids()
    # No id should be the literal "public"
    assert "public" not in ids


# ---- get_public_pem ----


def test_get_public_pem_returns_pem_string(tmp_path):
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    key_id = ks.add_keypair()
    pem = ks.get_public_pem(key_id)
    assert isinstance(pem, str)
    assert pem.startswith("-----BEGIN PUBLIC KEY-----")


def test_get_public_pem_raises_on_unknown_key(tmp_path):
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    ks.add_keypair()  # so dir exists
    with pytest.raises(FileNotFoundError):
        ks.get_public_pem("sha256:" + "f" * 32)


# ---- sign ----


def test_sign_returns_signature_dataclass_with_correct_fields(tmp_path):
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    key_id = ks.add_keypair()
    sig = ks.sign(key_id, "sha256:" + "a" * 64)
    assert isinstance(sig, Signature)
    assert sig.key_id == key_id
    assert sig.algo == "ed25519"
    assert sig.role == "scribe"
    # signed_at is ISO 8601 UTC
    assert sig.signed_at.endswith("+00:00") or sig.signed_at.endswith("Z")
    # base64 sig of a 64-byte Ed25519 signature is 88 chars (with padding)
    raw = base64.b64decode(sig.sig)
    assert len(raw) == 64


def test_sign_produces_signature_that_verifies(tmp_path):
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    key_id = ks.add_keypair()
    manifest_hash = "sha256:" + "b" * 64
    sig = ks.sign(key_id, manifest_hash)
    pub_pem = ks.get_public_pem(key_id).encode("utf-8")
    raw_sig = base64.b64decode(sig.sig)
    assert verify(pub_pem, manifest_hash.encode("utf-8"), raw_sig) is True


def test_sign_raises_on_unknown_key_id(tmp_path):
    ks = ScribeKeyStore(keys_dir=tmp_path / "keys")
    ks.add_keypair()  # so dir exists with correct mode
    with pytest.raises(FileNotFoundError):
        ks.sign("sha256:" + "9" * 32, "sha256:" + "c" * 64)


# ---- mode enforcement ----


@_POSIX_ONLY
def test_list_key_ids_refuses_wrong_dir_mode(tmp_path):
    keys_dir = tmp_path / "keys"
    ks = ScribeKeyStore(keys_dir=keys_dir)
    ks.add_keypair()
    os.chmod(keys_dir, 0o755)
    with pytest.raises(KeyStorePermissionError):
        ks.list_key_ids()


@_POSIX_ONLY
def test_sign_refuses_wrong_dir_mode(tmp_path):
    keys_dir = tmp_path / "keys"
    ks = ScribeKeyStore(keys_dir=keys_dir)
    key_id = ks.add_keypair()
    os.chmod(keys_dir, 0o755)
    with pytest.raises(KeyStorePermissionError):
        ks.sign(key_id, "sha256:" + "d" * 64)


@_POSIX_ONLY
def test_sign_refuses_wrong_file_mode(tmp_path):
    keys_dir = tmp_path / "keys"
    ks = ScribeKeyStore(keys_dir=keys_dir)
    key_id = ks.add_keypair()
    priv_path = keys_dir / f"{key_id}.ed25519.pem"
    os.chmod(priv_path, 0o644)
    with pytest.raises(KeyStorePermissionError):
        ks.sign(key_id, "sha256:" + "e" * 64)


# ---- end-to-end ----


def test_two_keystore_instances_share_disk_state(tmp_path):
    """A Scribe writing keys with one keystore instance should be
    seen by another keystore instance pointed at the same dir.
    Models multi-process operator workflows.
    """
    a = ScribeKeyStore(keys_dir=tmp_path / "keys")
    key_id = a.add_keypair()
    b = ScribeKeyStore(keys_dir=tmp_path / "keys")
    assert key_id in b.list_key_ids()
    pem = b.get_public_pem(key_id)
    assert "BEGIN PUBLIC KEY" in pem
