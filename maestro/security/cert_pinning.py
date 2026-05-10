"""
Certificate pinning for outbound Weight-transport HTTP clients.

Implements SPKI (Subject Public Key Info) pinning: the SHA-256
of a server's SubjectPublicKeyInfo is recorded in a pin store,
and the client refuses to trust a presented certificate unless
its SPKI hash matches one of the pinned values for that hostname.

SPKI pinning (Q-7.1 = a) survives certificate rotation when the
public key is preserved — operators don't have to update pins on
every cert renewal. This is the pattern used by Chrome's HSTS
preload, Apple's App Transport Security, and HPKP (RFC 7469,
deprecated for browsers but still the right idea for outbound
API clients).

Storage format (Q-7.3 = a, plain JSON; signed-pins variant
deferred)::

    {
      "version": 1,
      "pins": [
        {
          "hostname": "api.openai.com",
          "spki_sha256": ["sha256:abc123...", "sha256:def456..."],
          "added_at": "2024-01-01T00:00:00+00:00",
          "notes": "..."
        },
        ...
      ]
    }

Multiple pins per hostname support graceful key rotation (the
backup pin is the next-cert's SPKI, pre-staged before the
rotation).

Threat-model note: the unsigned JSON file is rewritable by an
attacker with filesystem write to ``data/security/``. A signed-
pins variant (parallel to the Cartridge ``trusted.json`` format)
is the natural follow-up; the current file format documents this
gap honestly so a future signing layer is additive.

This module is pure — no network, no httpx, no async. The
``PinnedTransport`` httpx wrapper that consumes ``PinStore``
lives in step 7-2 of this track.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization


_SPKI_PREFIX = "sha256:"


# ---- exceptions ----


class PinVerificationError(Exception):
    """Raised when a presented certificate fails SPKI pin verification.

    Carries the hostname and the SPKI hash that was presented so
    operators can investigate (and decide whether the rotation
    was expected or this is a real attack).
    """

    def __init__(self, hostname: str, presented_spki: str, expected: list):
        self.hostname = hostname
        self.presented_spki = presented_spki
        self.expected = list(expected)
        super().__init__(
            f"SPKI pin verification failed for {hostname!r}: "
            f"presented {presented_spki!r} not in expected {self.expected!r}"
        )


# ---- types ----


@dataclass(frozen=True)
class Pin:
    """One pinned SPKI hash for a hostname.

    Multiple ``Pin`` instances per hostname are supported (graceful
    key rotation: the backup pin is the next-cert's SPKI, staged
    before the actual rotation).
    """

    hostname: str
    spki_sha256: str             # ``"sha256:<hex>"``
    added_at: str = ""           # ISO8601 UTC; informational
    notes: str = ""              # operator-readable context


@dataclass
class PinStore:
    """Hostname-keyed mapping of pinned SPKI hashes.

    The store is mutable for runtime convenience (operators can
    add a pin during cert rotation without reloading); persistence
    happens through ``save_pin_store``.
    """

    pins_by_host: dict = field(default_factory=dict)   # {hostname: list[Pin]}
    metadata: dict = field(default_factory=dict)

    # ---- lookup ----

    def pins_for(self, hostname: str) -> list:
        """Return the list of ``Pin`` objects for ``hostname``,
        or an empty list if the hostname isn't pinned.
        """
        return list(self.pins_by_host.get(hostname, ()))

    def hostnames(self) -> list:
        """All hostnames that have at least one pin."""
        return sorted(self.pins_by_host.keys())

    def is_pinned(self, hostname: str) -> bool:
        """Return True iff ``hostname`` has at least one pin."""
        return hostname in self.pins_by_host and bool(self.pins_by_host[hostname])

    # ---- mutation ----

    def add_pin(self, pin: Pin) -> None:
        """Add a pin to the store. Idempotent: adding the same
        pin twice is a no-op.
        """
        bucket = self.pins_by_host.setdefault(pin.hostname, [])
        if any(p.spki_sha256 == pin.spki_sha256 for p in bucket):
            return
        bucket.append(pin)

    def remove_pin(self, hostname: str, spki_sha256: str) -> bool:
        """Remove a pin. Returns True iff a pin was actually
        removed. The bucket is dropped from the dict when empty.
        """
        bucket = self.pins_by_host.get(hostname)
        if not bucket:
            return False
        filtered = [p for p in bucket if p.spki_sha256 != spki_sha256]
        if len(filtered) == len(bucket):
            return False
        if filtered:
            self.pins_by_host[hostname] = filtered
        else:
            del self.pins_by_host[hostname]
        return True


# ---- SPKI extraction ----


def compute_spki_sha256(cert_bytes: bytes) -> str:
    """Compute the SPKI SHA-256 hash of an X.509 certificate.

    Accepts either DER or PEM. The hash is over the
    ``SubjectPublicKeyInfo`` structure (RFC 5280 §4.1.2.7) so it
    survives certificate rotation as long as the keypair is
    preserved.

    Returns ``"sha256:<64hex>"``.
    """
    if cert_bytes.startswith(b"-----BEGIN"):
        cert = x509.load_pem_x509_certificate(cert_bytes)
    else:
        cert = x509.load_der_x509_certificate(cert_bytes)
    spki_der = cert.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashlib.sha256(spki_der).hexdigest()
    return f"{_SPKI_PREFIX}{digest}"


# ---- verification ----


def verify_pin(
    cert_bytes: bytes,
    hostname: str,
    store: PinStore,
    *,
    require_pin: bool = True,
) -> bool:
    """Verify that a presented certificate's SPKI matches a pin
    for the given hostname.

    Parameters
    ----------
    cert_bytes:
        The presented certificate (DER or PEM).
    hostname:
        The hostname the connection was opened to. Used to look
        up the pin set.
    store:
        The PinStore to consult.
    require_pin:
        When True (default), raises ``PinVerificationError`` if
        the hostname has no pins (fail-closed). When False, an
        un-pinned hostname returns True (fail-open) — useful for
        gradual rollout where only a subset of hostnames have
        pins configured.

    Returns
    -------
    bool
        True iff the SPKI matches. Raises ``PinVerificationError``
        on mismatch (or on missing pin under ``require_pin=True``)
        rather than returning False — the caller almost always
        wants to abort, and an exception forces the failure mode
        rather than relying on return-value checking.
    """
    presented_spki = compute_spki_sha256(cert_bytes)
    pins = store.pins_for(hostname)
    if not pins:
        if require_pin:
            raise PinVerificationError(hostname, presented_spki, expected=[])
        return True
    expected_hashes = [p.spki_sha256 for p in pins]
    if presented_spki not in expected_hashes:
        raise PinVerificationError(hostname, presented_spki, expected=expected_hashes)
    return True


# ---- on-disk format ----


def load_pin_store(path) -> PinStore:
    """Load a PinStore from a JSON file.

    Expected shape::

        {
          "version": 1,
          "pins": [
            {"hostname": "...", "spki_sha256": ["sha256:...", ...],
             "added_at": "...", "notes": "..."},
            ...
          ]
        }

    A pin entry's ``spki_sha256`` field is a list because graceful
    rotation requires storing both the current and the upcoming
    pin under one hostname. Each value in the list yields one
    ``Pin`` instance.
    """
    raw = json.loads(Path(path).read_text())
    if raw.get("version") != 1:
        raise ValueError(
            f"unsupported pin store version: {raw.get('version')!r}"
        )

    store = PinStore(metadata={
        k: v for k, v in raw.items() if k not in ("pins", "version")
    })
    for entry in raw.get("pins", []):
        hostname = entry["hostname"]
        added_at = entry.get("added_at", "")
        notes = entry.get("notes", "")
        for spki_hash in entry.get("spki_sha256", []):
            store.add_pin(Pin(
                hostname=hostname,
                spki_sha256=spki_hash,
                added_at=added_at,
                notes=notes,
            ))
    return store


def save_pin_store(store: PinStore, path) -> None:
    """Save a PinStore to a JSON file.

    Aggregates multiple ``Pin`` instances per hostname into one
    entry with a list-shaped ``spki_sha256`` so the on-disk file
    is compact. Any ``added_at`` / ``notes`` from the first pin
    in the bucket is preserved on the entry; per-pin notes within
    a bucket lose granularity at save time. This is acceptable
    given the stable case (one or two pins per host) and keeps
    the on-disk shape obvious.
    """
    entries = []
    for hostname in sorted(store.pins_by_host.keys()):
        bucket = store.pins_by_host[hostname]
        if not bucket:
            continue
        entries.append({
            "hostname": hostname,
            "spki_sha256": [p.spki_sha256 for p in bucket],
            "added_at": bucket[0].added_at,
            "notes": bucket[0].notes,
        })

    payload = {
        "version": 1,
        "pins": entries,
    }
    payload.update(store.metadata or {})
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True))
