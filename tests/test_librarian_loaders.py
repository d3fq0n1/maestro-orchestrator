"""
Smoke tests for maestro/librarian/loaders.py — Policy + TrustList.

Trust list loading verifies an operator signature against the
operator PEM stored in policy.json. Round-trip: save → load
returns the same logical content. Tampering at the trust-list
file level raises TrustListVerificationError.
"""

import base64
import json
from datetime import datetime, timezone

import pytest

from maestro.librarian.crypto import (
    generate_keypair,
    key_id_from_public_pem,
)
from maestro.librarian.loaders import (
    TrustListVerificationError,
    load_policy,
    load_trust_list,
    read_operator_pem,
    save_policy,
    save_trust_list,
)
from maestro.librarian.types import (
    Policy,
    TrustList,
    TrustedKey,
)


# ---- helpers ----


def _operator_keypair():
    priv, pub = generate_keypair()
    return priv, pub.decode("utf-8"), key_id_from_public_pem(pub)


def _make_policy(operator_fp: str = "") -> Policy:
    return Policy(
        min_signatures_by_kind={"statute_text": 2, "unit_definition": 1},
        review_external_imports=True,
        import_caps_by_key={"sha256:abc": 5},
        canonical_form_registry=["bytes/raw"],
        operator_key_fingerprint=operator_fp,
    )


def _make_trust_list(*entries: TrustedKey) -> TrustList:
    return TrustList(
        keys={e.key_id: e for e in entries},
        operator_signature="",
    )


def _trusted_key(key_id: str) -> TrustedKey:
    return TrustedKey(
        key_id=key_id,
        public_key="-----BEGIN PUBLIC KEY-----\nDUMMY\n-----END PUBLIC KEY-----\n",
        added_at=datetime.now(timezone.utc).isoformat(),
        added_by_operator_key="sha256:" + "0" * 32,
    )


# ---- Policy round-trip ----


def test_policy_round_trip(tmp_path):
    p = _make_policy(operator_fp="sha256:" + "a" * 32)
    path = tmp_path / "policy.json"
    save_policy(p, path, operator_key_pem="-----BEGIN PUBLIC KEY-----\nFOO\n-----END PUBLIC KEY-----\n")
    loaded = load_policy(path)

    assert loaded.min_signatures_by_kind == p.min_signatures_by_kind
    assert loaded.review_external_imports is True
    assert loaded.import_caps_by_key == {"sha256:abc": 5}
    assert loaded.canonical_form_registry == ["bytes/raw"]
    assert loaded.operator_key_fingerprint == p.operator_key_fingerprint


def test_load_policy_missing_fields_default(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text("{}")
    loaded = load_policy(path)

    assert loaded.min_signatures_by_kind == {}
    assert loaded.review_external_imports is False
    assert loaded.import_caps_by_key == {}
    assert loaded.canonical_form_registry == []
    assert loaded.operator_key_fingerprint == ""


def test_read_operator_pem(tmp_path):
    path = tmp_path / "policy.json"
    save_policy(_make_policy(), path, operator_key_pem="THE-PEM")
    assert read_operator_pem(path) == "THE-PEM"


# ---- TrustList round-trip ----


def test_trust_list_round_trip(tmp_path):
    op_priv, op_pub, op_fp = _operator_keypair()
    save_policy(_make_policy(operator_fp=op_fp), tmp_path / "policy.json", operator_key_pem=op_pub)

    tk = _trusted_key("sha256:" + "1" * 32)
    tl = _make_trust_list(tk)
    save_trust_list(tl, tmp_path / "trusted.json", op_priv)

    loaded = load_trust_list(tmp_path / "trusted.json", tmp_path / "policy.json")
    assert "sha256:" + "1" * 32 in loaded.keys
    assert loaded.keys["sha256:" + "1" * 32].public_key == tk.public_key
    assert loaded.operator_signature != ""   # non-empty after save


def test_save_trust_list_updates_in_memory_signature(tmp_path):
    op_priv, op_pub, op_fp = _operator_keypair()
    save_policy(_make_policy(operator_fp=op_fp), tmp_path / "policy.json", operator_key_pem=op_pub)

    tl = _make_trust_list(_trusted_key("sha256:" + "2" * 32))
    assert tl.operator_signature == ""
    save_trust_list(tl, tmp_path / "trusted.json", op_priv)
    assert tl.operator_signature != ""


def test_trust_list_signature_covers_keys(tmp_path):
    """Re-saving with a different keys set produces a different
    operator signature.
    """
    op_priv, op_pub, op_fp = _operator_keypair()
    save_policy(_make_policy(operator_fp=op_fp), tmp_path / "policy.json", operator_key_pem=op_pub)

    tl_a = _make_trust_list(_trusted_key("sha256:" + "a" * 32))
    save_trust_list(tl_a, tmp_path / "trusted_a.json", op_priv)

    tl_b = _make_trust_list(
        _trusted_key("sha256:" + "a" * 32),
        _trusted_key("sha256:" + "b" * 32),
    )
    save_trust_list(tl_b, tmp_path / "trusted_b.json", op_priv)

    assert tl_a.operator_signature != tl_b.operator_signature


# ---- TrustList tampering rejection (C-3 mitigation) ----


def test_load_trust_list_rejects_tampered_keys(tmp_path):
    """Mutate the trusted.json after save; verify load raises."""
    op_priv, op_pub, op_fp = _operator_keypair()
    save_policy(_make_policy(operator_fp=op_fp), tmp_path / "policy.json", operator_key_pem=op_pub)

    tl = _make_trust_list(_trusted_key("sha256:" + "3" * 32))
    save_trust_list(tl, tmp_path / "trusted.json", op_priv)

    # Mutate the file to add a malicious key WITHOUT re-signing
    data = json.loads((tmp_path / "trusted.json").read_text())
    data["keys"].append({
        "key_id": "sha256:" + "evil" * 8,
        "public_key": "EVIL",
        "added_at": "",
        "added_by_operator_key": "",
    })
    (tmp_path / "trusted.json").write_text(json.dumps(data))

    with pytest.raises(TrustListVerificationError):
        load_trust_list(tmp_path / "trusted.json", tmp_path / "policy.json")


def test_load_trust_list_rejects_corrupted_signature(tmp_path):
    op_priv, op_pub, op_fp = _operator_keypair()
    save_policy(_make_policy(operator_fp=op_fp), tmp_path / "policy.json", operator_key_pem=op_pub)

    tl = _make_trust_list(_trusted_key("sha256:" + "4" * 32))
    save_trust_list(tl, tmp_path / "trusted.json", op_priv)

    # Corrupt the operator_signature
    data = json.loads((tmp_path / "trusted.json").read_text())
    raw = bytearray(base64.b64decode(data["operator_signature"]))
    raw[0] ^= 0x01
    data["operator_signature"] = base64.b64encode(bytes(raw)).decode("ascii")
    (tmp_path / "trusted.json").write_text(json.dumps(data))

    with pytest.raises(TrustListVerificationError):
        load_trust_list(tmp_path / "trusted.json", tmp_path / "policy.json")


def test_load_trust_list_rejects_wrong_operator_key(tmp_path):
    """A trusted.json signed by operator A cannot be verified
    against operator B's PEM in policy.json.
    """
    a_priv, a_pub, a_fp = _operator_keypair()
    b_priv, b_pub, b_fp = _operator_keypair()
    # Save policy.json with B's PEM
    save_policy(_make_policy(operator_fp=b_fp), tmp_path / "policy.json", operator_key_pem=b_pub)
    # But sign trusted.json with A's key
    tl = _make_trust_list(_trusted_key("sha256:" + "5" * 32))
    save_trust_list(tl, tmp_path / "trusted.json", a_priv)

    with pytest.raises(TrustListVerificationError):
        load_trust_list(tmp_path / "trusted.json", tmp_path / "policy.json")


def test_load_trust_list_missing_operator_pem_raises(tmp_path):
    save_policy(_make_policy(), tmp_path / "policy.json", operator_key_pem="")
    # Even if trusted.json is empty/non-existent, the policy check
    # fires first
    (tmp_path / "trusted.json").write_text(
        json.dumps({"keys": [], "operator_signature": "AAAA"})
    )
    with pytest.raises(TrustListVerificationError, match="operator_key_pem"):
        load_trust_list(tmp_path / "trusted.json", tmp_path / "policy.json")


def test_load_trust_list_missing_operator_signature_raises(tmp_path):
    op_priv, op_pub, op_fp = _operator_keypair()
    save_policy(_make_policy(operator_fp=op_fp), tmp_path / "policy.json", operator_key_pem=op_pub)
    (tmp_path / "trusted.json").write_text(json.dumps({"keys": []}))
    with pytest.raises(TrustListVerificationError, match="operator_signature"):
        load_trust_list(tmp_path / "trusted.json", tmp_path / "policy.json")


def test_load_trust_list_empty_keys_round_trip(tmp_path):
    """An empty trust list is still a legitimate signed object."""
    op_priv, op_pub, op_fp = _operator_keypair()
    save_policy(_make_policy(operator_fp=op_fp), tmp_path / "policy.json", operator_key_pem=op_pub)

    tl = _make_trust_list()  # zero entries
    save_trust_list(tl, tmp_path / "trusted.json", op_priv)

    loaded = load_trust_list(tmp_path / "trusted.json", tmp_path / "policy.json")
    assert loaded.keys == {}
    assert loaded.operator_signature != ""
