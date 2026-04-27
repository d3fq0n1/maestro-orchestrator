"""
Librarian store — filesystem-backed Cartridge storage and lookup.

See docs/architecture/librarian.md §Storage Layout.

Layout (under ``data/librarian/``)::

    store/
      by-hash/{aa}/{manifest_hash}.json       # signed manifest
      by-hash/{aa}/{content_hash}.body        # canonical-form body
      by-id/{cartridge_id}/head               # symlink to head manifest
      by-id/{cartridge_id}/versions/{v}       # symlink to versioned manifest
    revocations/{aa}/{manifest_hash}.json     # also present in by-hash
    pending/{cartridge_id}/{version}/
    review/{cartridge_id}/{version}/magi.json
    federation/peers.json
    federation/gossip.log

The store is the ground truth. ``by-id`` symlinks are mutable
pointers updated atomically on anchor or supersession.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from maestro.librarian.types import (
    CanonicalForm,
    CartridgeKind,
    CartridgeRef,
    Manifest,
    Policy,
    Signature,
    TrustList,
)
from maestro.librarian.verification import VerificationResult, verify_manifest


@dataclass
class LoadResult:
    """Outcome of a Manifest load attempt.

    ``manifest`` is None if load failed; ``reason`` describes why.
    Used to carry revocation / supersession status out of the loader
    without raising.
    """

    manifest: Optional[Manifest]
    reason: str = ""
    revoked: bool = False
    superseded_by: Optional[str] = None


# ---- on-disk serialization ----


def _serialize_manifest(m: Manifest) -> bytes:
    """JSON-serialize a manifest for on-disk storage.

    Round-trippable through ``_deserialize_manifest``. Format is
    indented for human inspection; canonicalization for hashing
    uses a different (compact) form via
    ``addressing.canonicalize_manifest_for_hashing``.
    """
    payload = {
        "cartridge_id": m.cartridge_id,
        "version": m.version,
        "kind": m.kind.value,
        "content_hash": m.content_hash,
        "manifest_hash": m.manifest_hash,
        "canonical_form": m.canonical_form.value,
        "supersedes": list(m.supersedes),
        "revokes": list(m.revokes),
        "domain_tags": list(m.domain_tags),
        "issued_at": m.issued_at,
        "not_before": m.not_before,
        "not_after": m.not_after,
        "signatures": [
            {
                "key_id": s.key_id,
                "algo": s.algo,
                "sig": s.sig,
                "signed_at": s.signed_at,
                "role": s.role,
            }
            for s in m.signatures
        ],
        "metadata": dict(m.metadata),
    }
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def _deserialize_manifest(raw: bytes) -> Manifest:
    """Inverse of ``_serialize_manifest``."""
    data = json.loads(raw.decode("utf-8"))
    return Manifest(
        cartridge_id=data["cartridge_id"],
        version=data["version"],
        kind=CartridgeKind(data["kind"]),
        content_hash=data["content_hash"],
        manifest_hash=data["manifest_hash"],
        canonical_form=CanonicalForm(data["canonical_form"]),
        supersedes=list(data.get("supersedes", [])),
        revokes=list(data.get("revokes", [])),
        domain_tags=list(data.get("domain_tags", [])),
        issued_at=data.get("issued_at", ""),
        not_before=data.get("not_before"),
        not_after=data.get("not_after"),
        signatures=[
            Signature(
                key_id=s["key_id"],
                algo=s["algo"],
                sig=s["sig"],
                signed_at=s["signed_at"],
                role=s.get("role", "scribe"),
            )
            for s in data.get("signatures", [])
        ],
        metadata=dict(data.get("metadata", {})),
    )


# ---- path helpers ----


def _strip_hash_prefix(hash_str: str) -> str:
    """Return the bare hex part of a ``"sha256:<hex>"`` string."""
    if ":" in hash_str:
        return hash_str.split(":", 1)[1]
    return hash_str


def _shard_dir(hash_str: str) -> str:
    """Return the 2-char shard prefix for a hash."""
    return _strip_hash_prefix(hash_str)[:2]


# ---- atomic filesystem helpers ----


def _atomic_write(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically via temp-file + rename.

    Uses ``os.replace`` which is atomic on POSIX. The temp file
    lives in the same directory as ``path`` so the rename stays
    on the same filesystem.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _atomic_symlink(target: str, link_path: Path) -> None:
    """Create or replace a symlink at ``link_path`` pointing at
    ``target`` (a string path, possibly relative). Atomic via
    ``os.replace`` on a temp symlink.
    """
    tmp_name = link_path.name + ".tmp-link"
    tmp = link_path.parent / tmp_name
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    os.symlink(target, tmp)
    os.replace(tmp, link_path)


class Librarian:
    """Owning interface for Tier 1 Cartridges.

    Exposes candidate discovery for the Router (``candidates``),
    exact lookup (``load``), and the commit path that turns a
    Scribe-signed manifest into a live Cartridge (``commit``).

    Instances are long-lived; federation gossip lives in
    ``federation.FederationClient`` and borrows this object through
    composition rather than subclassing.
    """

    def __init__(
        self,
        root_dir: Optional[Path] = None,
        trust_list: Optional[TrustList] = None,
        policy: Optional[Policy] = None,
    ):
        self._root = Path(root_dir) if root_dir is not None else None
        self._trust = trust_list
        self._policy = policy or Policy()

    # ---- read path ----

    def load(self, manifest_hash: str) -> LoadResult:
        """Load a Manifest by hash. Verifies signatures against trusted keys.

        Returns a LoadResult carrying revocation / supersession status.
        Defense-in-depth: even if a malformed manifest reaches the
        store somehow, ``load`` re-runs the full verification before
        admitting. ``manifest=None`` on failure with ``reason`` set.

        Step 5 scope: revocation and supersession status are not yet
        populated (machinery for those lands in a follow-up). The
        ``revoked`` field stays False; ``superseded_by`` stays None.
        """
        if self._root is None:
            return LoadResult(manifest=None, reason="root_dir not set")

        store_root = self._root / "store"
        bare = _strip_hash_prefix(manifest_hash)
        manifest_path = store_root / "by-hash" / _shard_dir(manifest_hash) / f"{bare}.json"

        if not manifest_path.exists():
            return LoadResult(manifest=None, reason="not found")

        try:
            manifest = _deserialize_manifest(manifest_path.read_bytes())
        except Exception as exc:
            return LoadResult(
                manifest=None,
                reason=f"deserialization failed: {type(exc).__name__}: {exc}",
            )

        body_bare = _strip_hash_prefix(manifest.content_hash)
        body_path = (
            store_root / "by-hash" / _shard_dir(manifest.content_hash)
            / f"{body_bare}.body"
        )
        if not body_path.exists():
            return LoadResult(manifest=None, reason="body missing")

        body = body_path.read_bytes()

        if self._trust is None:
            return LoadResult(
                manifest=None,
                reason="trust_list not set; cannot verify signatures",
            )

        result = verify_manifest(manifest, body, self._trust, self._policy)
        if not result.threshold_met:
            return LoadResult(
                manifest=None,
                reason=(
                    f"verification failed: "
                    f"valid_count={result.valid_count}, "
                    f"threshold_required={result.threshold_required}, "
                    f"content_hash_ok={result.content_hash_ok}, "
                    f"manifest_hash_ok={result.manifest_hash_ok}"
                ),
            )
        return LoadResult(manifest=manifest)

    def load_body(self, content_hash: str) -> bytes:
        """Load raw (already canonicalized) body bytes by hash.

        Raises FileNotFoundError if the body is not resident locally.
        """
        if self._root is None:
            raise FileNotFoundError("root_dir not set")
        bare = _strip_hash_prefix(content_hash)
        path = (
            self._root / "store" / "by-hash" / _shard_dir(content_hash)
            / f"{bare}.body"
        )
        if not path.exists():
            raise FileNotFoundError(f"body not found: {path}")
        return path.read_bytes()

    def head(self, cartridge_id: str) -> Optional[Manifest]:
        """Return the head Manifest for ``cartridge_id`` via the
        ``by-id/{cartridge_id}/head`` symlink.

        Returns None if the id is unknown or the head pointer is
        broken. Does not run signature verification — callers that
        require verification should ``load`` by manifest_hash.
        """
        if self._root is None:
            return None
        head_path = self._root / "store" / "by-id" / cartridge_id / "head"
        if not head_path.exists():
            return None
        try:
            return _deserialize_manifest(head_path.read_bytes())
        except Exception:
            return None

    def candidates(
        self,
        query_domains: list,
        kind_filter: Optional[list] = None,
    ) -> list:
        """Return a list[CartridgeRef] for the Router's admission pass.

        Matches on domain_tags (flat + dotted prefix, see context-tiers.md
        §Domain scoping). Applies kind_filter if given. Excludes revoked
        manifests; returns superseded manifests with ``superseded_by``
        populated so the Router can substitute the successor.
        """
        # TODO
        raise NotImplementedError

    # ---- write path ----

    def commit(self, manifest: Manifest, body: bytes) -> Manifest:
        """Atomically move a Scribe-signed manifest + body into the live store.

        Verifies the manifest against the trust list and policy
        threshold (see ``verification.verify_manifest``). On
        threshold-not-met, raises ``PolicyError`` carrying the
        full ``VerificationResult`` (option E1).

        On pass: writes the manifest JSON and body atomically into
        ``by-hash/{aa}/...`` and updates the symlinks at
        ``by-id/{cartridge_id}/head`` and
        ``by-id/{cartridge_id}/versions/{v}``. The symlinks point
        at the manifest JSON via relative paths so the store is
        portable across moves.

        Returns the input manifest unchanged.
        """
        if self._root is None:
            raise ValueError("root_dir is required for commit")
        if self._trust is None:
            raise ValueError("trust_list is required for commit")

        result = verify_manifest(manifest, body, self._trust, self._policy)
        if not result.threshold_met:
            raise PolicyError(verification_result=result)

        store_root = self._root / "store"
        manifest_dir = store_root / "by-hash" / _shard_dir(manifest.manifest_hash)
        body_dir = store_root / "by-hash" / _shard_dir(manifest.content_hash)
        id_dir = store_root / "by-id" / manifest.cartridge_id
        versions_dir = id_dir / "versions"

        manifest_dir.mkdir(parents=True, exist_ok=True)
        body_dir.mkdir(parents=True, exist_ok=True)
        versions_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = manifest_dir / f"{_strip_hash_prefix(manifest.manifest_hash)}.json"
        body_path = body_dir / f"{_strip_hash_prefix(manifest.content_hash)}.body"
        head_path = id_dir / "head"
        version_path = versions_dir / manifest.version

        _atomic_write(manifest_path, _serialize_manifest(manifest))
        _atomic_write(body_path, body)

        head_target = os.path.relpath(manifest_path, head_path.parent)
        version_target = os.path.relpath(manifest_path, version_path.parent)
        _atomic_symlink(head_target, head_path)
        _atomic_symlink(version_target, version_path)

        return manifest

    def preload(self, weight_host_id: str, manifest_hash: str) -> None:
        """Record that a WeightHost has pre-admitted a Cartridge.

        Populates ``WeightHost.loaded_cartridges`` on the registry (see
        shard_registry.py; the new field is declared in
        context-tiers.md §WeightHost capability extensions).
        This method does NOT modify the orchestration runtime; it only
        updates the persisted registry so routing can prefer this host.
        """
        # TODO
        raise NotImplementedError

    # ---- enumeration / graph-layer support ----

    def iter_manifests(self):
        """Iterate every signed Manifest in the live store.

        Used by graph-layer code (``maestro/router/graph.py``) to build
        the known-tag set at construction.
        """
        # TODO
        raise NotImplementedError

    def get_by_slug(self, slug: str):
        """Return the Manifest for a ``CART:<id>@<version>`` slug.

        None if the slug doesn't resolve in this instance.
        """
        # TODO: parse "CART:<id>@<version>" then resolve via
        # by-id/<id>/versions/<version>
        raise NotImplementedError

    def cartridges_with_tag(self, tag: str):
        """Iterate CartridgeRefs whose ``domain_tags`` contain ``tag``.

        Exact match only. Longest-prefix matching is the graph
        layer's responsibility.
        """
        # TODO
        raise NotImplementedError

    def supersedes_slugs(self, slug: str) -> list:
        """Return slugs of Cartridges that ``slug`` supersedes.

        Translates the manifest's ``supersedes`` manifest_hash list
        into slugs of the form ``CART:<id>@<version>``. Phantom hashes
        (target Cartridge missing locally) are silently omitted; the
        graph drops the edge.
        """
        # TODO
        raise NotImplementedError

    def revokes_slugs(self, slug: str) -> list:
        """Return slugs of Cartridges that ``slug`` revokes.

        Translation rules same as ``supersedes_slugs``.
        """
        # TODO
        raise NotImplementedError

    def known_tags(self) -> set:
        """Set of every ``domain_tag`` declared by any current Manifest.

        Used by ``CompositeGraphView`` for longest-prefix anchor
        lookup. Implementations may maintain this as a cached index
        that invalidates on commit.
        """
        # TODO
        raise NotImplementedError


class PolicyError(Exception):
    """Raised when a Librarian operation violates Policy thresholds.

    Carries the full ``VerificationResult`` on
    ``.verification_result`` so callers can branch on what
    specifically failed (threshold_met, content_hash_ok,
    manifest_hash_ok).
    """

    def __init__(self, verification_result: VerificationResult):
        self.verification_result = verification_result
        msg = (
            f"manifest verification failed: "
            f"threshold_required={verification_result.threshold_required}, "
            f"valid_count={verification_result.valid_count}, "
            f"threshold_met={verification_result.threshold_met}, "
            f"content_hash_ok={verification_result.content_hash_ok}, "
            f"manifest_hash_ok={verification_result.manifest_hash_ok}"
        )
        super().__init__(msg)
