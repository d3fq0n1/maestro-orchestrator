"""
Smoke tests for maestro/security/cert_pinning.py.

Item 7 step 1. Generates real X.509 certificates in-memory
(via the cryptography library that's already a project dep) so
the SPKI math is exercised against actual cert structures
rather than synthetic byte strings.
"""

import datetime
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from maestro.security.cert_pinning import (
    Pin,
    PinStore,
    PinVerificationError,
    compute_spki_sha256,
    load_pin_store,
    save_pin_store,
    verify_pin,
)


# ---- fixtures ----


def _make_cert(common_name: str = "example.com") -> tuple:
    """Generate an RSA keypair + self-signed X.509 cert.
    Returns (cert_pem_bytes, cert_der_bytes, private_key).
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(private_key=key, algorithm=hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM)
    der = cert.public_bytes(serialization.Encoding.DER)
    return pem, der, key


def _rotate_cert_same_key(key, common_name: str = "example.com") -> tuple:
    """Generate a NEW cert (new serial, new validity window) using
    the SAME public key. Same SPKI -> same pin survives rotation.
    """
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now + datetime.timedelta(days=400))
        .not_valid_after(now + datetime.timedelta(days=765))
        .sign(private_key=key, algorithm=hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


# ---- compute_spki_sha256 ----


def test_compute_spki_sha256_format():
    pem, _, _ = _make_cert()
    spki = compute_spki_sha256(pem)
    assert spki.startswith("sha256:")
    hex_part = spki[len("sha256:"):]
    assert len(hex_part) == 64
    assert all(c in "0123456789abcdef" for c in hex_part)


def test_compute_spki_sha256_deterministic_for_same_cert():
    pem, _, _ = _make_cert()
    a = compute_spki_sha256(pem)
    b = compute_spki_sha256(pem)
    assert a == b


def test_compute_spki_sha256_pem_and_der_match():
    pem, der, _ = _make_cert()
    assert compute_spki_sha256(pem) == compute_spki_sha256(der)


def test_compute_spki_sha256_distinct_certs_have_distinct_hashes():
    pem_a, _, _ = _make_cert("alpha.example")
    pem_b, _, _ = _make_cert("beta.example")
    assert compute_spki_sha256(pem_a) != compute_spki_sha256(pem_b)


def test_compute_spki_sha256_survives_cert_rotation():
    """Same keypair, new cert (different serial, new validity).
    SPKI hash MUST be identical. This is the central property
    that makes SPKI pinning operationally usable.
    """
    pem_a, _, key = _make_cert()
    pem_b = _rotate_cert_same_key(key)
    assert compute_spki_sha256(pem_a) == compute_spki_sha256(pem_b)


# ---- PinStore ----


def test_empty_pin_store_has_no_hostnames():
    store = PinStore()
    assert store.hostnames() == []
    assert not store.is_pinned("anything.test")
    assert store.pins_for("anything.test") == []


def test_add_pin_appears_in_hostname_lookup():
    store = PinStore()
    pin = Pin("api.example", "sha256:" + "a" * 64)
    store.add_pin(pin)
    assert store.is_pinned("api.example")
    assert store.pins_for("api.example") == [pin]
    assert "api.example" in store.hostnames()


def test_add_pin_idempotent():
    store = PinStore()
    pin = Pin("api.example", "sha256:" + "a" * 64)
    store.add_pin(pin)
    store.add_pin(pin)  # second add is a no-op
    assert len(store.pins_for("api.example")) == 1


def test_add_multiple_pins_for_same_hostname():
    store = PinStore()
    a = Pin("api.example", "sha256:" + "a" * 64)
    b = Pin("api.example", "sha256:" + "b" * 64)
    store.add_pin(a)
    store.add_pin(b)
    assert len(store.pins_for("api.example")) == 2


def test_remove_pin():
    store = PinStore()
    spki = "sha256:" + "a" * 64
    store.add_pin(Pin("api.example", spki))
    assert store.remove_pin("api.example", spki) is True
    assert not store.is_pinned("api.example")


def test_remove_pin_unknown_returns_false():
    store = PinStore()
    assert store.remove_pin("nope.example", "sha256:abc") is False


def test_remove_pin_keeps_other_pins_for_same_hostname():
    store = PinStore()
    a = Pin("api.example", "sha256:" + "a" * 64)
    b = Pin("api.example", "sha256:" + "b" * 64)
    store.add_pin(a)
    store.add_pin(b)
    store.remove_pin("api.example", a.spki_sha256)
    assert store.pins_for("api.example") == [b]


# ---- verify_pin ----


def test_verify_pin_passes_when_spki_matches():
    pem, _, _ = _make_cert()
    spki = compute_spki_sha256(pem)
    store = PinStore()
    store.add_pin(Pin("example.com", spki))
    assert verify_pin(pem, "example.com", store) is True


def test_verify_pin_passes_after_cert_rotation_same_key():
    """The whole point of SPKI pinning: rotate the cert without
    rotating the key, and the pin still validates.
    """
    pem_old, _, key = _make_cert()
    pem_new = _rotate_cert_same_key(key)
    spki = compute_spki_sha256(pem_old)
    store = PinStore()
    store.add_pin(Pin("example.com", spki))
    assert verify_pin(pem_new, "example.com", store) is True


def test_verify_pin_raises_on_mismatch():
    pem, _, _ = _make_cert("a.example")
    other_pem, _, _ = _make_cert("b.example")
    other_spki = compute_spki_sha256(other_pem)
    store = PinStore()
    store.add_pin(Pin("a.example", other_spki))   # wrong pin pre-staged
    with pytest.raises(PinVerificationError) as exc_info:
        verify_pin(pem, "a.example", store)
    assert exc_info.value.hostname == "a.example"
    assert exc_info.value.expected == [other_spki]


def test_verify_pin_raises_on_missing_pin_when_required():
    pem, _, _ = _make_cert()
    store = PinStore()  # empty
    with pytest.raises(PinVerificationError):
        verify_pin(pem, "unknown.example", store, require_pin=True)


def test_verify_pin_passes_on_missing_pin_when_not_required():
    """fail-open mode for partial rollout."""
    pem, _, _ = _make_cert()
    store = PinStore()
    assert verify_pin(pem, "unknown.example", store, require_pin=False) is True


def test_verify_pin_works_with_multiple_pins_for_one_host():
    """Graceful rotation: store carries old + new pin; either
    matches.
    """
    pem_a, _, key_a = _make_cert("api.example")
    pem_b, _, key_b = _make_cert("api.example")
    spki_a = compute_spki_sha256(pem_a)
    spki_b = compute_spki_sha256(pem_b)
    store = PinStore()
    store.add_pin(Pin("api.example", spki_a))
    store.add_pin(Pin("api.example", spki_b))
    # Either cert validates
    assert verify_pin(pem_a, "api.example", store) is True
    assert verify_pin(pem_b, "api.example", store) is True


def test_verify_pin_error_carries_presented_and_expected():
    pem, _, _ = _make_cert()
    presented_spki = compute_spki_sha256(pem)
    expected_spki = "sha256:" + "f" * 64
    store = PinStore()
    store.add_pin(Pin("api.example", expected_spki))
    with pytest.raises(PinVerificationError) as exc_info:
        verify_pin(pem, "api.example", store)
    err = exc_info.value
    assert err.presented_spki == presented_spki
    assert err.expected == [expected_spki]


# ---- load / save round-trip ----


def test_save_and_load_round_trip(tmp_path):
    store = PinStore()
    store.add_pin(Pin(
        hostname="api.openai.com",
        spki_sha256="sha256:" + "a" * 64,
        added_at="2024-01-01T00:00:00+00:00",
        notes="initial",
    ))
    store.add_pin(Pin(
        hostname="api.openai.com",
        spki_sha256="sha256:" + "b" * 64,
    ))
    store.add_pin(Pin(
        hostname="api.anthropic.com",
        spki_sha256="sha256:" + "c" * 64,
    ))
    path = tmp_path / "pins.json"
    save_pin_store(store, path)

    loaded = load_pin_store(path)
    assert sorted(loaded.hostnames()) == [
        "api.anthropic.com", "api.openai.com",
    ]
    assert len(loaded.pins_for("api.openai.com")) == 2
    pin_hashes = {p.spki_sha256 for p in loaded.pins_for("api.openai.com")}
    assert "sha256:" + "a" * 64 in pin_hashes
    assert "sha256:" + "b" * 64 in pin_hashes


def test_load_pin_store_rejects_unknown_version(tmp_path):
    path = tmp_path / "pins.json"
    path.write_text(json.dumps({"version": 99, "pins": []}))
    with pytest.raises(ValueError, match="version"):
        load_pin_store(path)


def test_load_pin_store_handles_empty_file(tmp_path):
    path = tmp_path / "pins.json"
    path.write_text(json.dumps({"version": 1, "pins": []}))
    store = load_pin_store(path)
    assert store.hostnames() == []


def test_save_pin_store_drops_empty_buckets(tmp_path):
    """Hostnames whose buckets become empty after remove_pin
    should not appear in the saved JSON.
    """
    store = PinStore()
    spki = "sha256:" + "a" * 64
    store.add_pin(Pin("api.example", spki))
    store.remove_pin("api.example", spki)
    # hostname now empty
    path = tmp_path / "pins.json"
    save_pin_store(store, path)
    raw = json.loads(path.read_text())
    assert raw["pins"] == []


def test_save_pin_store_writes_version_marker(tmp_path):
    store = PinStore()
    store.add_pin(Pin("h", "sha256:" + "0" * 64))
    path = tmp_path / "pins.json"
    save_pin_store(store, path)
    raw = json.loads(path.read_text())
    assert raw["version"] == 1


# ---- end-to-end: real cert -> pin -> verify ----


def test_e2e_real_cert_pin_workflow(tmp_path):
    """Full workflow: generate cert, derive pin, save store,
    reload, present cert, verify.
    """
    pem, _, _ = _make_cert("example.com")
    spki = compute_spki_sha256(pem)

    store = PinStore()
    store.add_pin(Pin("example.com", spki, added_at="2024-01-01T00:00:00+00:00"))
    save_pin_store(store, tmp_path / "pins.json")

    reloaded = load_pin_store(tmp_path / "pins.json")
    assert verify_pin(pem, "example.com", reloaded) is True
