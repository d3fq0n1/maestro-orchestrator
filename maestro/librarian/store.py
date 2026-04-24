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

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from maestro.librarian.types import (
    CartridgeRef,
    Manifest,
    Policy,
    TrustList,
)


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
        # TODO: default root to <repo>/data/librarian/
        self._root = root_dir
        self._trust = trust_list
        self._policy = policy

    # ---- read path ----

    def load(self, manifest_hash: str) -> LoadResult:
        """Load a Manifest by hash. Verifies signatures against trusted keys.

        Returns a LoadResult carrying revocation / supersession status.
        A revoked manifest is returned with ``revoked=True`` but the
        caller must refuse to admit it (the Router does this).
        """
        # TODO
        raise NotImplementedError

    def load_body(self, content_hash: str) -> bytes:
        """Load raw (already canonicalized) body bytes by hash.

        Raises FileNotFoundError if the body is not resident locally.
        """
        # TODO
        raise NotImplementedError

    def head(self, cartridge_id: str) -> Optional[Manifest]:
        """Return the head (most recent) Manifest for ``cartridge_id``.

        None if the id is unknown.
        """
        # TODO: resolve by-id/{cartridge_id}/head symlink
        raise NotImplementedError

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

        Precondition: manifest_hash verifies, content_hash verifies,
        every signature in signatures is present in trust_list.

        Postcondition: by-hash entries exist; by-id/{id}/head points at
        this manifest; by-id/{id}/versions/{v} points at this manifest.

        Raises PolicyError if min_signatures_by_kind not met.
        """
        # TODO
        raise NotImplementedError

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


class PolicyError(Exception):
    """Raised when a Librarian operation violates ``Policy`` thresholds."""
