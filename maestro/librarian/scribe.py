"""
Scribe — Cartridge signing authority.

The Scribe is a role, not an agent. It holds Ed25519 keys at
``data/librarian/keys/`` and signs manifest_hash values on behalf
of canonization.

See docs/architecture/librarian.md §Attestation.

MAGI proposes; the Scribe signs. The Scribe never auto-reviews
Whirlpool promotions — it consumes the Recommendation written by
MAGI and either signs or refuses.

No code in this file should read or write keys outside
``data/librarian/keys/``. The API-key store at maestro/keyring.py
is a separate concern and must not be imported here.
"""

from pathlib import Path
from typing import Optional

from maestro.librarian.types import Manifest, Signature, Policy


class ScribeKeyStore:
    """Filesystem-backed Ed25519 key store.

    Layout:
        data/librarian/keys/
            {key_id}.ed25519.pem         (private, mode 0600)
            public/{key_id}.ed25519.pub  (public)

    The store refuses to load keys if directory or file modes are
    wrong (see librarian.md §Keys).
    """

    def __init__(self, keys_dir: Optional[Path] = None):
        # TODO: default to <repo>/data/librarian/keys/
        # TODO: validate directory mode is 0700
        self._dir = keys_dir

    def list_key_ids(self) -> list:
        """Return fingerprints of loadable private keys."""
        # TODO
        raise NotImplementedError

    def get_public_pem(self, key_id: str) -> str:
        """Return PEM-encoded public key for ``key_id``."""
        # TODO
        raise NotImplementedError

    def sign(self, key_id: str, manifest_hash: str) -> Signature:
        """Sign a manifest_hash with the named private key.

        Validates mode 0600 before loading. Raises PermissionError on
        mode mismatch.
        """
        # TODO
        raise NotImplementedError


class Scribe:
    """Canonization signer.

    Reads a pending manifest + body from the nomination queue, applies
    the canonical-form serializer, computes hashes, signs the
    manifest_hash, and hands control back to the ``Librarian`` which
    performs the atomic move into the live store.

    The Scribe NEVER runs MAGI review itself. A nomination that has
    no MAGI Recommendation at
    ``data/librarian/review/{id}/{version}/magi.json`` is either
    external (signed by a trusted external key — import flow) or
    held for operator action.
    """

    def __init__(self, keystore: ScribeKeyStore, policy: Policy):
        self._keys = keystore
        self._policy = policy

    def anchor(
        self,
        pending_manifest: Manifest,
        pending_body: bytes,
        signing_key_ids: list,
    ) -> Manifest:
        """Sign and return a finalized Manifest.

        Steps (see librarian.md §Scribe anchoring):
          1. Validate canonical_form is in policy.canonical_form_registry.
          2. Validate kind's min_signatures_by_kind ≤ len(signing_key_ids).
          3. canonicalize_body + compute_content_hash.
          4. Bind content_hash into the manifest.
          5. compute_manifest_hash (excluding manifest_hash + signatures).
          6. Sign manifest_hash with each requested key.
          7. Return finalized Manifest ready for store.commit().

        Raises:
          PolicyError if thresholds not met.
          ValueError  if canonical_form validation fails.
        """
        # TODO
        raise NotImplementedError

    def anchor_revocation(
        self,
        revokes: list,
        signing_key_ids: list,
    ) -> Manifest:
        """Produce a kind=REVOCATION Manifest with empty body.

        See librarian.md §Revocation.
        """
        # TODO
        raise NotImplementedError
