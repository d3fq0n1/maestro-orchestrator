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

import base64
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from maestro.librarian.crypto import (
    generate_keypair as _generate_keypair,
    key_id_from_public_pem as _key_id_from_public_pem,
    sign as _sign_bytes,
)
from maestro.librarian.types import Manifest, Signature, Policy


_DEFAULT_KEYS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "librarian" / "keys"
)
_PRIVATE_FILE_SUFFIX = ".ed25519.pem"
_PUBLIC_FILE_SUFFIX = ".ed25519.pub"
_DIR_MODE = 0o700
_FILE_MODE = 0o600
_POSIX = os.name == "posix"


class KeyStorePermissionError(PermissionError):
    """Raised when the key store directory or a private-key file
    has the wrong filesystem mode (POSIX only).
    """


class ScribeKeyStore:
    """Filesystem-backed Ed25519 key store.

    Layout::

        {keys_dir}/
            {key_id}.ed25519.pem         (private, mode 0600)
            public/
                {key_id}.ed25519.pub     (public)

    Keys are referenced by ``key_id`` — ``"sha256:<32hex>"`` derived
    from the public PEM by ``crypto.key_id_from_public_pem``.

    Mode enforcement (POSIX only): the directory and ``public/``
    subdir must be ``0700``; every private-key file must be
    ``0600``. Loading or signing under wrong modes raises
    ``KeyStorePermissionError``. On non-POSIX platforms the check
    is skipped because the Unix mode model doesn't translate.

    ``add_keypair`` (option L1) generates a fresh keypair on disk
    with correct modes; the public PEM lives at the location the
    librarian.md spec describes for inspection / federation.
    """

    def __init__(self, keys_dir: Optional[Path] = None):
        self._dir = Path(keys_dir) if keys_dir is not None else _DEFAULT_KEYS_DIR
        self._public_dir = self._dir / "public"

    @property
    def keys_dir(self) -> Path:
        return self._dir

    @property
    def public_dir(self) -> Path:
        return self._public_dir

    # ---- mode enforcement ----

    @staticmethod
    def _check_mode(path: Path, expected: int):
        """POSIX-only: raise KeyStorePermissionError if ``path`` has
        a mode other than ``expected``. No-op on non-POSIX.
        """
        if not _POSIX:
            return
        if not path.exists():
            raise FileNotFoundError(f"path not found: {path}")
        actual = stat.S_IMODE(path.stat().st_mode)
        if actual != expected:
            raise KeyStorePermissionError(
                f"{path} mode is 0{actual:o}; expected 0{expected:o}"
            )

    def _ensure_dir_mode(self):
        self._check_mode(self._dir, _DIR_MODE)

    def _ensure_file_mode(self, path: Path):
        self._check_mode(path, _FILE_MODE)

    # ---- generation / addition (option L1) ----

    def add_keypair(self) -> str:
        """Generate a fresh Ed25519 keypair and write it to the store.

        Creates the directory tree on first use with mode 0700 on
        both the keys dir and ``public/``. Refuses to overwrite an
        existing private-key file.

        Returns the new key_id.
        """
        self._dir.mkdir(parents=True, exist_ok=True)
        self._public_dir.mkdir(parents=True, exist_ok=True)
        if _POSIX:
            os.chmod(self._dir, _DIR_MODE)
            os.chmod(self._public_dir, _DIR_MODE)

        priv_pem, pub_pem = _generate_keypair()
        key_id = _key_id_from_public_pem(pub_pem)

        priv_path = self._dir / f"{key_id}{_PRIVATE_FILE_SUFFIX}"
        pub_path = self._public_dir / f"{key_id}{_PUBLIC_FILE_SUFFIX}"

        if priv_path.exists():
            raise FileExistsError(
                f"key {key_id} already exists at {priv_path}"
            )

        # Open with O_EXCL to close the TOCTOU window between the
        # exists check above and the write here.
        priv_fd = os.open(
            str(priv_path),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            _FILE_MODE,
        )
        try:
            os.write(priv_fd, priv_pem)
        finally:
            os.close(priv_fd)
        if _POSIX:
            # Defensive: enforce mode in case umask interfered with
            # the O_CREAT mode argument.
            os.chmod(priv_path, _FILE_MODE)
        pub_path.write_bytes(pub_pem)
        return key_id

    # ---- read path ----

    def list_key_ids(self) -> list:
        """Return key_ids of loadable private keys.

        Validates directory mode before reading. Files whose names
        don't end with the expected suffix are ignored.
        """
        self._ensure_dir_mode()
        out = []
        for path in sorted(self._dir.iterdir()):
            if path.is_dir():
                continue
            name = path.name
            if not name.endswith(_PRIVATE_FILE_SUFFIX):
                continue
            key_id = name[: -len(_PRIVATE_FILE_SUFFIX)]
            out.append(key_id)
        return out

    def get_public_pem(self, key_id: str) -> str:
        """Return the public PEM for ``key_id`` as a UTF-8 string.

        Reads from ``public/``. Raises FileNotFoundError if the
        public key is not present. The public dir's mode is not
        enforced here (only private keys are sensitive).
        """
        path = self._public_dir / f"{key_id}{_PUBLIC_FILE_SUFFIX}"
        if not path.exists():
            raise FileNotFoundError(f"public key not found: {path}")
        return path.read_bytes().decode("utf-8")

    # ---- signing ----

    def sign(self, key_id: str, manifest_hash: str) -> Signature:
        """Sign ``manifest_hash`` with the named private key.

        Returns a Signature dataclass. The raw 64-byte Ed25519
        signature is base64-encoded into ``Signature.sig``.

        Validates directory and file modes before reading the
        private key. ``signed_at`` is the current UTC timestamp
        in ISO 8601.

        Raises:
          KeyStorePermissionError on wrong directory or file mode
                                  (POSIX only)
          FileNotFoundError       if the private key is not in the
                                  store
        """
        self._ensure_dir_mode()
        priv_path = self._dir / f"{key_id}{_PRIVATE_FILE_SUFFIX}"
        if not priv_path.exists():
            raise FileNotFoundError(f"private key not found: {priv_path}")
        self._ensure_file_mode(priv_path)
        priv_pem = priv_path.read_bytes()
        sig_bytes = _sign_bytes(priv_pem, manifest_hash.encode("utf-8"))
        return Signature(
            key_id=key_id,
            algo="ed25519",
            sig=base64.b64encode(sig_bytes).decode("ascii"),
            signed_at=datetime.now(timezone.utc).isoformat(),
            role="scribe",
        )


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
