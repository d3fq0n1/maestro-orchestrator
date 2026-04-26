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
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from maestro.librarian.addressing import (
    compute_content_hash,
    compute_manifest_hash,
)
from maestro.librarian.crypto import (
    generate_keypair as _generate_keypair,
    key_id_from_public_pem as _key_id_from_public_pem,
    sign as _sign_bytes,
)
from maestro.librarian.types import (
    CanonicalForm,
    CartridgeKind,
    Manifest,
    Policy,
    Signature,
)


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
        """Append this Scribe's signatures to a pending manifest.

        Multi-Scribe accumulation flow (option Q from the design
        discussion): each call signs once with the keys this Scribe
        was asked for, returning an updated manifest. Multiple
        Scribes can call ``anchor`` in succession on the same
        logical manifest; the signatures list accumulates.
        Threshold enforcement happens at ``Librarian.commit`` time,
        not here. Canonical-form policy enforcement also happens at
        commit time (option C2): this method computes hashes for
        whatever ``canonical_form`` the manifest declares and
        propagates ``NotImplementedError`` from
        ``addressing.canonicalize_body`` for forms not yet
        implemented.

        Two branches by signature presence on the incoming manifest:

        * **First call** (``signatures == []``): compute
          ``content_hash`` from the body, bind it; compute
          ``manifest_hash`` from the post-bind manifest, bind it;
          sign with each requested key; return.
        * **Subsequent call** (``signatures != []``): recompute
          ``content_hash`` and ``manifest_hash`` and verify they
          still match the values on the incoming manifest. If
          either differs (the body or some other field changed
          between Scribes), raise ``ValueError`` — earlier
          signatures attest to those exact hashes and silently
          updating them would invalidate them.

        Same-key double-signing (option D1): a ``key_id`` already
        present in the manifest's ``signatures`` list raises
        ``ValueError``. Repeated signing by the same key is an
        operator mistake we surface early rather than silently
        dedupe or duplicate.

        Empty ``signing_key_ids``: raises ``ValueError`` (calling
        anchor with no keys to sign is meaningless).

        Returns:
          A new ``Manifest`` (immutable) with the requested
          signatures appended.
        """
        if not signing_key_ids:
            raise ValueError("signing_key_ids is empty; nothing to sign")

        if not pending_manifest.signatures:
            # First-call branch: bind hashes from scratch.
            content_hash = compute_content_hash(
                pending_body, pending_manifest.canonical_form,
            )
            sealed = replace(
                pending_manifest,
                content_hash=content_hash,
                manifest_hash="",   # placeholder; recomputed next
            )
            manifest_hash = compute_manifest_hash(sealed)
            sealed = replace(sealed, manifest_hash=manifest_hash)
        else:
            # Subsequent-call branch: verify hashes still match.
            actual_content_hash = compute_content_hash(
                pending_body, pending_manifest.canonical_form,
            )
            if pending_manifest.content_hash != actual_content_hash:
                raise ValueError(
                    f"content_hash mismatch: incoming "
                    f"{pending_manifest.content_hash!r} != computed "
                    f"{actual_content_hash!r} (body changed since prior "
                    f"signing?)"
                )
            actual_manifest_hash = compute_manifest_hash(pending_manifest)
            if pending_manifest.manifest_hash != actual_manifest_hash:
                raise ValueError(
                    f"manifest_hash mismatch: incoming "
                    f"{pending_manifest.manifest_hash!r} != computed "
                    f"{actual_manifest_hash!r} (manifest fields changed "
                    f"since prior signing?)"
                )
            sealed = pending_manifest

        # D1: refuse double-signing with the same key_id, including
        # duplicates within the request list itself.
        seen: set = {s.key_id for s in sealed.signatures}
        new_signatures = list(sealed.signatures)
        for kid in signing_key_ids:
            if kid in seen:
                raise ValueError(
                    f"key_id {kid!r} has already signed this manifest"
                )
            seen.add(kid)
            new_signatures.append(self._keys.sign(kid, sealed.manifest_hash))

        return replace(sealed, signatures=new_signatures)

    def anchor_revocation(
        self,
        revokes: list,
        signing_key_ids: list,
        cartridge_id: Optional[str] = None,
        version: Optional[str] = None,
        domain_tags: Optional[list] = None,
    ) -> Manifest:
        """Produce a ``kind=REVOCATION`` Manifest with empty body.

        Builds a fresh revocation manifest naming the hashes in
        ``revokes`` and runs it through ``anchor`` to bind hashes
        and append signatures. Subsequent Scribes can attach
        further signatures via ``anchor`` (the resulting manifest
        is just another signed manifest as far as accumulation
        is concerned).

        See librarian.md §Revocation. Body is empty and
        canonical_form is BYTES_RAW; the empty bytes hash is
        deterministic and shared across all revocations of any
        ``cartridge_id`` / ``version``.
        """
        if not revokes:
            raise ValueError("revokes list is empty; nothing to revoke")

        now = datetime.now(timezone.utc)
        cid = cartridge_id or f"revocation-{now.strftime('%Y%m%d%H%M%S%f')}"
        ver = version or "1"

        fresh = Manifest(
            cartridge_id=cid,
            version=ver,
            kind=CartridgeKind.REVOCATION,
            content_hash="",
            manifest_hash="",
            canonical_form=CanonicalForm.BYTES_RAW,
            supersedes=[],
            revokes=list(revokes),
            domain_tags=list(domain_tags or []),
            issued_at=now.isoformat(),
            not_before=None,
            not_after=None,
            signatures=[],
            metadata={},
        )
        return self.anchor(fresh, b"", signing_key_ids)
