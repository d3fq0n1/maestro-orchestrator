"""
Librarian type definitions.

Dataclasses mirroring the manifest schema in
docs/architecture/librarian.md. Serialization format is JSON under
RFC 8785 canonicalization (see ``addressing.py``). All types are
immutable once written to the store.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CartridgeKind(str, Enum):
    """Cartridge taxonomy — see librarian.md §Cartridge Taxonomy."""

    UNIT_DEFINITION = "unit_definition"
    STATUTE_TEXT = "statute_text"
    PROTOCOL_SPEC = "protocol_spec"
    SCHEMA = "schema"
    DEFINITION = "definition"
    REFERENCE_DATASET = "reference_dataset"
    REVOCATION = "revocation"


class CanonicalForm(str, Enum):
    """Body canonical-form identifiers — see librarian.md §Content Addressing."""

    JSON_RFC8785 = "json/rfc8785"
    TEXT_UTF8_NFC = "text/utf8-nfc"
    BYTES_RAW = "bytes/raw"


@dataclass(frozen=True)
class Signature:
    """A single Scribe signature over a manifest_hash.

    See librarian.md §Signature record.
    """

    key_id: str              # fingerprint of the signing public key
    algo: str                # "ed25519"
    sig: str                 # base64-encoded signature
    signed_at: str           # ISO8601 UTC
    role: str = "scribe"     # reserved: "supersession-witness", "revocation-witness"


@dataclass(frozen=True)
class Manifest:
    """The signed metadata half of a Cartridge.

    The body is addressed by ``content_hash`` and stored separately
    (see librarian.md §Storage Layout). This manifest is what peers
    gossip and what Routers load.

    Invariants:
      - ``manifest_hash`` is SHA-256 of the RFC 8785 canonicalization of
        this manifest with ``manifest_hash`` and ``signatures`` elided.
      - ``content_hash`` is SHA-256 of the canonical-form body bytes.
      - A correction is a *new* Manifest with ``supersedes=[old_hash]``;
        mutation is never permitted.
    """

    cartridge_id: str                # stable human-readable slug
    version: str                     # monotonic per cartridge_id
    kind: CartridgeKind
    content_hash: str                # "sha256:<hex>"
    manifest_hash: str               # "sha256:<hex>"
    canonical_form: CanonicalForm
    supersedes: list = field(default_factory=list)
    revokes: list = field(default_factory=list)
    domain_tags: list = field(default_factory=list)
    issued_at: str = ""
    not_before: Optional[str] = None
    not_after: Optional[str] = None
    signatures: list = field(default_factory=list)   # list[Signature]
    metadata: dict = field(default_factory=dict)     # unsigned, untrusted


@dataclass(frozen=True)
class CartridgeRef:
    """Compact reference returned by ``Librarian.candidates``.

    Carries the fields the Router needs without requiring the full
    manifest or body bytes to be loaded.
    """

    manifest_hash: str
    content_hash: str
    cartridge_id: str
    version: str
    kind: CartridgeKind
    domain_tags: list
    trust: float                    # see router-distance.md §trust(C)
    revoked: bool = False
    superseded_by: Optional[str] = None


@dataclass(frozen=True)
class TrustedKey:
    """Entry in ``trusted.json`` — a Scribe key this Librarian trusts."""

    key_id: str                      # fingerprint
    public_key: str                  # PEM-encoded
    added_at: str
    added_by_operator_key: str       # fingerprint of the operator key
                                     # that authorized adding this trust


@dataclass
class TrustList:
    """Loaded representation of ``trusted.json``.

    Enforces per-key-id uniqueness and carries the operator signature
    needed to validate the on-disk file.
    """

    keys: dict = field(default_factory=dict)          # {key_id: TrustedKey}
    operator_signature: Optional[str] = None           # over the serialized keys


@dataclass
class Policy:
    """Loaded representation of ``policy.json``.

    Governs threshold signatures, external-import review, and the
    canonical-form registry. See librarian.md §Threshold policy.
    """

    min_signatures_by_kind: dict = field(default_factory=dict)   # {kind: int}
    review_external_imports: bool = False
    import_caps_by_key: dict = field(default_factory=dict)       # {key_id: int/day}
    canonical_form_registry: list = field(default_factory=list)  # list[CanonicalForm]
    operator_key_fingerprint: str = ""                           # signs trusted.json
