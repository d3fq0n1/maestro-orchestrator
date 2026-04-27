"""
Librarian federation — gossip over lan_discovery + HTTP fetch.

See docs/architecture/librarian.md §Federation Protocol.

Layered on ``maestro/lan_discovery.py`` for peer discovery (adds a
new ``librarian`` service advertisement type) and plain HTTP for
content fetch. No DHT, no libp2p. Trust is per-key, not per-peer:
a Cartridge served by any peer is admitted only if its signatures
verify against the local trusted.json.

This module is a scaffold. No network code is written yet.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from maestro.librarian.store import Librarian


@dataclass
class PeerRecord:
    """A federation peer (operator-configured or LAN-discovered)."""

    url: str                          # https://peer.example/librarian
    discovered_via: str               # "lan" | "operator"
    last_seen: str = ""
    last_gossip_seq: int = 0
    status: str = "active"            # "active" | "probation" | "banned"
    pubkey_fingerprints: list = field(default_factory=list)   # known Scribe keys


@dataclass
class AdvertisementEntry:
    """One item in an advertise payload."""

    manifest_hash: str
    kind: str
    version: str


class FederationClient:
    """Gossip + fetch client for peer Librarians.

    The client runs gossip cycles on a tunable interval (default 60s).
    Each cycle: advertise recent hashes → receive diff → fetch missing
    manifests → verify signatures → fetch bodies → verify content
    hashes → commit via local Librarian.

    Revocations are priority-propagated: every cycle re-advertises
    every revocation until acknowledged by the peer.
    """

    def __init__(
        self,
        librarian: Librarian,
        peers_path: Optional[Path] = None,
        interval_seconds: int = 60,
    ):
        self._librarian = librarian
        self._peers_path = peers_path
        self._interval = interval_seconds

    # ---- peer management ----

    def load_peers(self) -> list:
        """Load peers from data/librarian/federation/peers.json."""
        # TODO
        raise NotImplementedError

    def add_peer(self, url: str, discovered_via: str = "operator") -> PeerRecord:
        """Add an operator-configured peer. Duplicate URLs deduplicate."""
        # TODO
        raise NotImplementedError

    def remove_peer(self, url: str) -> bool:
        """Remove a peer. Returns False if the peer was unknown."""
        # TODO
        raise NotImplementedError

    # ---- gossip cycle ----

    async def run_cycle(self, peer: PeerRecord) -> dict:
        """Run one gossip cycle with a single peer.

        Returns a summary dict with counts of advertised / fetched /
        verified / rejected hashes for logging.
        """
        # TODO
        raise NotImplementedError

    def build_advertisement(self, max_recent: int = 64) -> list:
        """Build the advertise payload: recent hashes + all revocations."""
        # TODO
        raise NotImplementedError

    async def fetch_manifest(self, peer: PeerRecord, manifest_hash: str):
        """HTTP GET a manifest from a peer and verify its signatures.

        Returns a verified Manifest, or None on verification failure.
        """
        # TODO
        raise NotImplementedError

    async def fetch_body(self, peer: PeerRecord, content_hash: str) -> bytes:
        """HTTP GET a body from a peer and verify its content_hash."""
        # TODO
        raise NotImplementedError

    # ---- event log ----

    def log_event(self, event_type: str, detail: dict) -> None:
        """Append to data/librarian/federation/gossip.log."""
        # TODO
        raise NotImplementedError
