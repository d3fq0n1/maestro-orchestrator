"""
LAN Shard Discovery -- UDP broadcast-based peer discovery for Maestro shards.

Each Maestro session on the same LAN subnet automatically discovers neighbors
via periodic UDP beacons on a well-known port.  Discovered shards perform a
three-phase handshake (ANNOUNCE -> ACK -> CONFIRMED) to form adjacencies.
When 3 shards establish a full mirror, the group is promoted to a Maestro Node.

Protocol overview:
    1. Every shard broadcasts a BEACON datagram every BEACON_INTERVAL seconds
       on the LAN broadcast address (255.255.255.255) at DISCOVERY_PORT.
    2. On receiving a BEACON from an unknown peer, the local shard sends a
       directed HANDSHAKE_INIT to that peer's unicast address.
    3. The peer replies with HANDSHAKE_ACK.
    4. The initiator confirms with HANDSHAKE_CONFIRM, completing the adjacency.
    5. Adjacencies that miss STALE_TIMEOUT seconds of beacons are marked down.

Designed for LAN-only operation.  Public connectivity hooks are a future concern.
"""

import asyncio
import json
import logging
import random
import socket
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger("maestro.lan_discovery")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DISCOVERY_PORT = 41820
BEACON_INTERVAL = 3.0        # seconds between beacon broadcasts
STALE_TIMEOUT = 15.0         # seconds before a peer is considered offline
HANDSHAKE_TIMEOUT = 5.0      # seconds to wait for handshake replies
NODE_QUORUM = 3              # shards needed for a full Maestro Node

# ---------------------------------------------------------------------------
# Human-readable name generator (adjective + animal)
# ---------------------------------------------------------------------------

_ADJECTIVES = [
    "amber", "azure", "bold", "brave", "bright", "calm", "clear", "cool",
    "coral", "crimson", "dark", "dawn", "deep", "dusk", "eager", "fair",
    "fast", "fierce", "firm", "free", "gentle", "gilt", "grand", "gray",
    "green", "iron", "jade", "keen", "light", "lunar", "noble", "onyx",
    "pale", "prime", "quick", "rapid", "ruby", "sage", "sharp", "silver",
    "solar", "stark", "steel", "stone", "swift", "tidal", "true", "vivid",
    "warm", "wild", "wise", "zinc",
]

_ANIMALS = [
    "bear", "crane", "crow", "deer", "dove", "drake", "eagle", "elk",
    "falcon", "finch", "fox", "frog", "goat", "hare", "hawk", "heron",
    "horse", "ibis", "jay", "kite", "lark", "lion", "lynx", "mink",
    "moth", "newt", "orca", "otter", "owl", "panda", "pike", "puma",
    "ram", "raven", "robin", "seal", "shrike", "snake", "stag", "stork",
    "swan", "tiger", "toad", "viper", "whale", "wolf", "wren", "yak",
]


def generate_human_name() -> str:
    """Generate a human-readable name like 'swift-falcon'."""
    return f"{random.choice(_ADJECTIVES)}-{random.choice(_ANIMALS)}"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class AdjacencyState(str, Enum):
    """State of the handshake between two shards."""
    DISCOVERED = "discovered"       # beacon received, no handshake yet
    HANDSHAKE_SENT = "handshake_sent"
    HANDSHAKE_ACKED = "handshake_acked"
    CONFIRMED = "confirmed"         # full bidirectional adjacency
    STALE = "stale"                 # missed beacons, considered offline


class MsgType(str, Enum):
    BEACON = "beacon"
    HANDSHAKE_INIT = "handshake_init"
    HANDSHAKE_ACK = "handshake_ack"
    HANDSHAKE_CONFIRM = "handshake_confirm"


@dataclass
class ShardIdentity:
    """Identity of the local shard on the network."""
    uid: str
    human_name: str
    host: str = ""
    port: int = DISCOVERY_PORT
    started_at: str = ""
    version: str = "0.1.0"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PeerShard:
    """A discovered peer shard on the LAN."""
    uid: str
    human_name: str
    host: str
    port: int
    adjacency: AdjacencyState = AdjacencyState.DISCOVERED
    last_seen: float = 0.0           # monotonic timestamp
    first_seen: float = 0.0
    handshake_initiated_at: float = 0.0
    version: str = ""
    latency_ms: float = 0.0

    @property
    def is_alive(self) -> bool:
        return (time.monotonic() - self.last_seen) < STALE_TIMEOUT

    @property
    def is_adjacent(self) -> bool:
        return self.adjacency == AdjacencyState.CONFIRMED and self.is_alive

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "human_name": self.human_name,
            "host": self.host,
            "port": self.port,
            "adjacency": self.adjacency.value,
            "is_alive": self.is_alive,
            "is_adjacent": self.is_adjacent,
            "last_seen_ago_s": round(time.monotonic() - self.last_seen, 1) if self.last_seen else None,
            "latency_ms": round(self.latency_ms, 2),
            "version": self.version,
        }


@dataclass
class MaestroNodeStatus:
    """Status of the local Maestro Node (3-shard quorum group)."""
    formed: bool = False
    member_uids: list = field(default_factory=list)
    member_names: list = field(default_factory=list)
    formed_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Discovery protocol handler
# ---------------------------------------------------------------------------

class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """Asyncio UDP protocol for beacon broadcast and handshake exchange."""

    def __init__(self, engine: "ShardDiscoveryEngine"):
        self._engine = engine
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        try:
            msg = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        # Ignore our own messages
        sender_uid = msg.get("sender_uid", "")
        if sender_uid == self._engine.identity.uid:
            return
        asyncio.get_event_loop().call_soon_threadsafe(
            self._engine._handle_message, msg, addr
        )

    def error_received(self, exc: Exception) -> None:
        logger.debug("Discovery UDP error: %s", exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        logger.debug("Discovery UDP connection lost: %s", exc)


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class ShardDiscoveryEngine:
    """
    Manages LAN-based shard discovery, handshakes, and adjacency tracking.

    Lifecycle:
        engine = ShardDiscoveryEngine()
        await engine.start()
        ...
        await engine.stop()

    Query state:
        engine.peers           -> dict of uid -> PeerShard
        engine.adjacent_peers  -> list of confirmed, alive peers
        engine.node_status     -> MaestroNodeStatus
        engine.snapshot()      -> full JSON-serializable status dict
    """

    def __init__(
        self,
        port: int = DISCOVERY_PORT,
        beacon_interval: float = BEACON_INTERVAL,
        node_quorum: int = NODE_QUORUM,
        identity: Optional[ShardIdentity] = None,
    ):
        self.port = port
        self.beacon_interval = beacon_interval
        self.node_quorum = node_quorum
        self.identity = identity or ShardIdentity(
            uid=str(uuid.uuid4()),
            human_name=generate_human_name(),
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.peers: dict[str, PeerShard] = {}
        self.node_status = MaestroNodeStatus()

        self._transport: Optional[asyncio.DatagramTransport] = None
        self._protocol: Optional[_DiscoveryProtocol] = None
        self._beacon_task: Optional[asyncio.Task] = None
        self._prune_task: Optional[asyncio.Task] = None
        self._running = False
        self._handshake_timestamps: dict[str, float] = {}  # uid -> send time

    # -- Lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Start beacon broadcasting and listening."""
        if self._running:
            return
        self._running = True

        loop = asyncio.get_running_loop()

        # Detect local IP for identity
        self.identity.host = self._detect_lan_ip()
        self.identity.port = self.port

        # Create UDP socket with broadcast capability
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass  # SO_REUSEPORT not available on all platforms
        sock.setblocking(False)
        sock.bind(("", self.port))

        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: _DiscoveryProtocol(self),
            sock=sock,
        )

        self._beacon_task = asyncio.create_task(self._beacon_loop())
        self._prune_task = asyncio.create_task(self._prune_loop())

        logger.info(
            "Shard discovery started: %s (%s) on port %d",
            self.identity.human_name, self.identity.uid[:8], self.port,
        )

    async def stop(self) -> None:
        """Stop discovery and clean up."""
        self._running = False
        if self._beacon_task:
            self._beacon_task.cancel()
            try:
                await self._beacon_task
            except asyncio.CancelledError:
                pass
        if self._prune_task:
            self._prune_task.cancel()
            try:
                await self._prune_task
            except asyncio.CancelledError:
                pass
        if self._transport:
            self._transport.close()
        logger.info("Shard discovery stopped: %s", self.identity.human_name)

    # -- Beacon loop ---------------------------------------------------------

    async def _beacon_loop(self) -> None:
        """Periodically broadcast presence beacon."""
        while self._running:
            try:
                self._send_beacon()
            except Exception as e:
                logger.debug("Beacon send error: %s", e)
            await asyncio.sleep(self.beacon_interval)

    def _send_beacon(self) -> None:
        """Broadcast a BEACON datagram to the LAN."""
        msg = {
            "type": MsgType.BEACON.value,
            "sender_uid": self.identity.uid,
            "sender_name": self.identity.human_name,
            "sender_host": self.identity.host,
            "sender_port": self.identity.port,
            "version": self.identity.version,
            "ts": time.monotonic(),
        }
        data = json.dumps(msg).encode("utf-8")
        if self._transport:
            self._transport.sendto(data, ("255.255.255.255", self.port))

    # -- Prune loop ----------------------------------------------------------

    async def _prune_loop(self) -> None:
        """Periodically mark stale peers."""
        while self._running:
            await asyncio.sleep(STALE_TIMEOUT / 2)
            now = time.monotonic()
            for peer in self.peers.values():
                if peer.adjacency != AdjacencyState.STALE and not peer.is_alive:
                    logger.info(
                        "Peer gone stale: %s (%s)",
                        peer.human_name, peer.uid[:8],
                    )
                    peer.adjacency = AdjacencyState.STALE
            self._evaluate_node_status()

    # -- Message handling ----------------------------------------------------

    def _handle_message(self, msg: dict, addr: tuple) -> None:
        """Route an incoming message to the appropriate handler."""
        msg_type = msg.get("type", "")
        if msg_type == MsgType.BEACON.value:
            self._on_beacon(msg, addr)
        elif msg_type == MsgType.HANDSHAKE_INIT.value:
            self._on_handshake_init(msg, addr)
        elif msg_type == MsgType.HANDSHAKE_ACK.value:
            self._on_handshake_ack(msg, addr)
        elif msg_type == MsgType.HANDSHAKE_CONFIRM.value:
            self._on_handshake_confirm(msg, addr)

    def _on_beacon(self, msg: dict, addr: tuple) -> None:
        """Handle an incoming BEACON: register peer, maybe start handshake."""
        uid = msg["sender_uid"]
        now = time.monotonic()

        if uid in self.peers:
            peer = self.peers[uid]
            peer.last_seen = now
            peer.host = msg.get("sender_host", addr[0])
            peer.port = msg.get("sender_port", DISCOVERY_PORT)
            peer.version = msg.get("version", "")
            # If peer was stale and came back, re-initiate handshake
            if peer.adjacency == AdjacencyState.STALE:
                logger.info(
                    "Peer returned: %s (%s)", peer.human_name, peer.uid[:8]
                )
                peer.adjacency = AdjacencyState.DISCOVERED
                self._initiate_handshake(peer)
        else:
            peer = PeerShard(
                uid=uid,
                human_name=msg.get("sender_name", "unknown"),
                host=msg.get("sender_host", addr[0]),
                port=msg.get("sender_port", DISCOVERY_PORT),
                last_seen=now,
                first_seen=now,
                version=msg.get("version", ""),
            )
            self.peers[uid] = peer
            logger.info(
                "Discovered peer: %s (%s) at %s:%d",
                peer.human_name, uid[:8], peer.host, peer.port,
            )
            self._initiate_handshake(peer)

    def _initiate_handshake(self, peer: PeerShard) -> None:
        """Send HANDSHAKE_INIT to a discovered peer."""
        msg = {
            "type": MsgType.HANDSHAKE_INIT.value,
            "sender_uid": self.identity.uid,
            "sender_name": self.identity.human_name,
            "sender_host": self.identity.host,
            "sender_port": self.identity.port,
            "target_uid": peer.uid,
            "ts": time.monotonic(),
        }
        self._send_to(msg, peer.host, peer.port)
        peer.adjacency = AdjacencyState.HANDSHAKE_SENT
        peer.handshake_initiated_at = time.monotonic()
        self._handshake_timestamps[peer.uid] = time.monotonic()
        logger.debug("Handshake INIT sent to %s", peer.human_name)

    def _on_handshake_init(self, msg: dict, addr: tuple) -> None:
        """Received HANDSHAKE_INIT: reply with ACK."""
        uid = msg["sender_uid"]
        # Ensure peer is tracked
        if uid not in self.peers:
            self.peers[uid] = PeerShard(
                uid=uid,
                human_name=msg.get("sender_name", "unknown"),
                host=msg.get("sender_host", addr[0]),
                port=msg.get("sender_port", DISCOVERY_PORT),
                last_seen=time.monotonic(),
                first_seen=time.monotonic(),
            )
        peer = self.peers[uid]
        peer.last_seen = time.monotonic()

        ack = {
            "type": MsgType.HANDSHAKE_ACK.value,
            "sender_uid": self.identity.uid,
            "sender_name": self.identity.human_name,
            "sender_host": self.identity.host,
            "sender_port": self.identity.port,
            "target_uid": uid,
            "init_ts": msg.get("ts", 0),
            "ts": time.monotonic(),
        }
        self._send_to(ack, peer.host, peer.port)
        peer.adjacency = AdjacencyState.HANDSHAKE_ACKED
        logger.debug("Handshake ACK sent to %s", peer.human_name)

    def _on_handshake_ack(self, msg: dict, addr: tuple) -> None:
        """Received HANDSHAKE_ACK: send CONFIRM, complete adjacency."""
        uid = msg["sender_uid"]
        if uid not in self.peers:
            return
        peer = self.peers[uid]
        peer.last_seen = time.monotonic()

        # Compute round-trip latency from handshake
        init_ts = self._handshake_timestamps.get(uid)
        if init_ts:
            peer.latency_ms = (time.monotonic() - init_ts) * 1000

        confirm = {
            "type": MsgType.HANDSHAKE_CONFIRM.value,
            "sender_uid": self.identity.uid,
            "sender_name": self.identity.human_name,
            "sender_host": self.identity.host,
            "sender_port": self.identity.port,
            "target_uid": uid,
            "ts": time.monotonic(),
        }
        self._send_to(confirm, peer.host, peer.port)
        peer.adjacency = AdjacencyState.CONFIRMED
        logger.info(
            "Adjacency CONFIRMED with %s (%s) latency=%.1fms",
            peer.human_name, uid[:8], peer.latency_ms,
        )
        self._evaluate_node_status()

    def _on_handshake_confirm(self, msg: dict, addr: tuple) -> None:
        """Received HANDSHAKE_CONFIRM: finalize adjacency on our side too."""
        uid = msg["sender_uid"]
        if uid not in self.peers:
            return
        peer = self.peers[uid]
        peer.last_seen = time.monotonic()
        peer.adjacency = AdjacencyState.CONFIRMED
        logger.info(
            "Adjacency CONFIRMED (via confirm) with %s (%s)",
            peer.human_name, uid[:8],
        )
        self._evaluate_node_status()

    # -- Node status evaluation ----------------------------------------------

    def _evaluate_node_status(self) -> None:
        """Check if we have enough adjacent shards to form a Maestro Node."""
        adjacent = self.adjacent_peers
        total_members = len(adjacent) + 1  # include self

        was_formed = self.node_status.formed

        if total_members >= self.node_quorum:
            if not self.node_status.formed:
                member_uids = [self.identity.uid] + [p.uid for p in adjacent]
                member_names = [self.identity.human_name] + [p.human_name for p in adjacent]
                self.node_status = MaestroNodeStatus(
                    formed=True,
                    member_uids=member_uids[:self.node_quorum],
                    member_names=member_names[:self.node_quorum],
                    formed_at=datetime.now(timezone.utc).isoformat(),
                )
                logger.info(
                    "MAESTRO NODE FORMED: %s",
                    ", ".join(self.node_status.member_names),
                )
        else:
            if self.node_status.formed:
                logger.warning(
                    "Maestro Node DISSOLVED: only %d/%d shards adjacent",
                    total_members, self.node_quorum,
                )
                self.node_status = MaestroNodeStatus(formed=False)

    # -- Transport helpers ---------------------------------------------------

    def _send_to(self, msg: dict, host: str, port: int) -> None:
        """Send a JSON datagram to a specific host:port."""
        if not self._transport:
            return
        data = json.dumps(msg).encode("utf-8")
        self._transport.sendto(data, (host, port))

    @staticmethod
    def _detect_lan_ip() -> str:
        """Detect the LAN IP address of this machine."""
        try:
            # Connect to a non-routable address to determine our LAN interface
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    # -- Public query methods ------------------------------------------------

    @property
    def adjacent_peers(self) -> list[PeerShard]:
        """Return all confirmed, alive peers."""
        return [p for p in self.peers.values() if p.is_adjacent]

    @property
    def alive_peers(self) -> list[PeerShard]:
        """Return all peers that are still sending beacons."""
        return [p for p in self.peers.values() if p.is_alive]

    def snapshot(self) -> dict:
        """Full JSON-serializable status snapshot for UI/API consumption."""
        adjacent = self.adjacent_peers
        alive = self.alive_peers
        return {
            "identity": self.identity.to_dict(),
            "peers": {uid: p.to_dict() for uid, p in self.peers.items()},
            "peer_count": len(self.peers),
            "alive_count": len(alive),
            "adjacent_count": len(adjacent),
            "node_status": self.node_status.to_dict(),
            "is_maestro_node": self.node_status.formed,
        }

    def peer_summary(self) -> list[dict]:
        """Compact list of peers for TUI display."""
        result = []
        for peer in sorted(self.peers.values(), key=lambda p: p.first_seen):
            result.append({
                "uid_short": peer.uid[:8],
                "name": peer.human_name,
                "host": peer.host,
                "adjacency": peer.adjacency.value,
                "alive": peer.is_alive,
                "adjacent": peer.is_adjacent,
                "latency_ms": round(peer.latency_ms, 1),
            })
        return result
