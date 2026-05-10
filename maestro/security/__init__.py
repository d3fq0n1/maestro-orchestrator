"""
maestro.security — security primitives for outbound and inbound
trust enforcement.

Currently exposes certificate pinning (item 7 of the open work
list, addressing certificate pinning on Weight transports). The
threat model documents this as a hardening item that protects
against compromised CAs, hostile resolvers, or active MITM on
the path to Weight provider APIs.

See ``cert_pinning.py``.
"""

from maestro.security.cert_pinning import (
    Pin,
    PinStore,
    PinVerificationError,
    compute_spki_sha256,
    load_pin_store,
    save_pin_store,
    verify_pin,
)

__all__ = [
    "Pin",
    "PinStore",
    "PinVerificationError",
    "compute_spki_sha256",
    "load_pin_store",
    "save_pin_store",
    "verify_pin",
]
