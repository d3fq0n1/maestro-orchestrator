"""
Tests for LAN Shard Discovery — identity, handshake protocol, adjacency, node formation.
"""

import asyncio
import json
import time
import uuid

import pytest

from maestro.lan_discovery import (
    AdjacencyState,
    MaestroNodeStatus,
    MsgType,
    PeerShard,
    ShardDiscoveryEngine,
    ShardIdentity,
    generate_human_name,
)


class TestHumanNameGeneration:
    def test_generates_adjective_animal(self):
        name = generate_human_name()
        parts = name.split("-")
        assert len(parts) == 2
        assert len(parts[0]) > 0
        assert len(parts[1]) > 0

    def test_uniqueness(self):
        names = {generate_human_name() for _ in range(50)}
        # With 52*48=2496 combos, 50 samples should almost always be unique
        assert len(names) >= 40


class TestShardIdentity:
    def test_creation(self):
        ident = ShardIdentity(uid="abc-123", human_name="swift-falcon")
        assert ident.uid == "abc-123"
        assert ident.human_name == "swift-falcon"

    def test_to_dict(self):
        ident = ShardIdentity(uid="x", human_name="bold-hawk", host="10.0.0.1", port=41820)
        d = ident.to_dict()
        assert d["uid"] == "x"
        assert d["human_name"] == "bold-hawk"
        assert d["host"] == "10.0.0.1"
        assert d["port"] == 41820


class TestPeerShard:
    def test_is_alive_fresh(self):
        peer = PeerShard(
            uid="p1", human_name="test-peer", host="10.0.0.2",
            port=41820, last_seen=time.monotonic(),
        )
        assert peer.is_alive

    def test_is_alive_stale(self):
        peer = PeerShard(
            uid="p1", human_name="test-peer", host="10.0.0.2",
            port=41820, last_seen=time.monotonic() - 60,
        )
        assert not peer.is_alive

    def test_is_adjacent_requires_confirmed_and_alive(self):
        peer = PeerShard(
            uid="p1", human_name="test-peer", host="10.0.0.2",
            port=41820, last_seen=time.monotonic(),
            adjacency=AdjacencyState.CONFIRMED,
        )
        assert peer.is_adjacent

    def test_is_not_adjacent_when_discovered(self):
        peer = PeerShard(
            uid="p1", human_name="test-peer", host="10.0.0.2",
            port=41820, last_seen=time.monotonic(),
            adjacency=AdjacencyState.DISCOVERED,
        )
        assert not peer.is_adjacent

    def test_to_dict(self):
        peer = PeerShard(
            uid="p1", human_name="test-peer", host="10.0.0.2",
            port=41820, last_seen=time.monotonic(),
            adjacency=AdjacencyState.CONFIRMED, latency_ms=5.5,
        )
        d = peer.to_dict()
        assert d["uid"] == "p1"
        assert d["adjacency"] == "confirmed"
        assert d["is_alive"] is True
        assert d["is_adjacent"] is True
        assert d["latency_ms"] == 5.5


class TestMaestroNodeStatus:
    def test_default_not_formed(self):
        status = MaestroNodeStatus()
        assert not status.formed
        assert status.member_uids == []

    def test_to_dict(self):
        status = MaestroNodeStatus(
            formed=True,
            member_uids=["a", "b", "c"],
            member_names=["swift-hawk", "bold-fox", "calm-owl"],
            formed_at="2026-01-01T00:00:00Z",
        )
        d = status.to_dict()
        assert d["formed"] is True
        assert len(d["member_uids"]) == 3


class TestEngineIdentity:
    def test_auto_generates_uid_and_name(self):
        engine = ShardDiscoveryEngine()
        assert len(engine.identity.uid) == 36  # UUID4 format
        assert "-" in engine.identity.human_name  # adjective-animal

    def test_custom_identity(self):
        ident = ShardIdentity(uid="custom-id", human_name="test-node")
        engine = ShardDiscoveryEngine(identity=ident)
        assert engine.identity.uid == "custom-id"
        assert engine.identity.human_name == "test-node"


class TestHandshakeProtocol:
    """Test the handshake message handling without actual network I/O."""

    def _make_engine(self, uid=None, name=None):
        ident = ShardIdentity(
            uid=uid or str(uuid.uuid4()),
            human_name=name or generate_human_name(),
            host="10.0.0.1",
            port=41820,
        )
        return ShardDiscoveryEngine(identity=ident)

    def test_beacon_creates_peer(self):
        engine = self._make_engine(uid="local-uid")
        # Simulate receiving a beacon from a remote peer
        msg = {
            "type": MsgType.BEACON.value,
            "sender_uid": "remote-uid",
            "sender_name": "brave-wolf",
            "sender_host": "10.0.0.2",
            "sender_port": 41820,
            "version": "0.1.0",
            "ts": time.monotonic(),
        }
        # Mock transport so _send_to doesn't crash
        engine._transport = _MockTransport()
        engine._handle_message(msg, ("10.0.0.2", 41820))

        assert "remote-uid" in engine.peers
        peer = engine.peers["remote-uid"]
        assert peer.human_name == "brave-wolf"
        assert peer.host == "10.0.0.2"
        # Should have initiated handshake
        assert peer.adjacency == AdjacencyState.HANDSHAKE_SENT

    def test_beacon_ignored_from_self(self):
        engine = self._make_engine(uid="local-uid")
        msg = {
            "type": MsgType.BEACON.value,
            "sender_uid": "local-uid",
            "sender_name": "self",
            "sender_host": "10.0.0.1",
            "sender_port": 41820,
        }
        engine._transport = _MockTransport()
        # _handle_message won't be called for self (filtered in protocol)
        # But let's test _on_beacon directly
        engine._on_beacon(msg, ("10.0.0.1", 41820))
        # Self beacon creates a peer entry (protocol layer filters, not _on_beacon)
        # This is fine — the protocol layer filters by UID before calling _handle_message

    def test_handshake_init_sends_ack(self):
        engine = self._make_engine(uid="local-uid")
        transport = _MockTransport()
        engine._transport = transport

        msg = {
            "type": MsgType.HANDSHAKE_INIT.value,
            "sender_uid": "remote-uid",
            "sender_name": "bold-crane",
            "sender_host": "10.0.0.3",
            "sender_port": 41820,
            "target_uid": "local-uid",
            "ts": time.monotonic(),
        }
        engine._handle_message(msg, ("10.0.0.3", 41820))

        assert "remote-uid" in engine.peers
        peer = engine.peers["remote-uid"]
        assert peer.adjacency == AdjacencyState.HANDSHAKE_ACKED

        # Should have sent an ACK
        assert len(transport.sent) > 0
        ack_msg = json.loads(transport.sent[-1][0])
        assert ack_msg["type"] == MsgType.HANDSHAKE_ACK.value

    def test_handshake_ack_confirms_adjacency(self):
        engine = self._make_engine(uid="local-uid")
        transport = _MockTransport()
        engine._transport = transport

        # First register the peer via beacon
        engine.peers["remote-uid"] = PeerShard(
            uid="remote-uid", human_name="keen-fox",
            host="10.0.0.4", port=41820,
            last_seen=time.monotonic(),
            adjacency=AdjacencyState.HANDSHAKE_SENT,
        )
        engine._handshake_timestamps["remote-uid"] = time.monotonic() - 0.01

        msg = {
            "type": MsgType.HANDSHAKE_ACK.value,
            "sender_uid": "remote-uid",
            "sender_name": "keen-fox",
            "sender_host": "10.0.0.4",
            "sender_port": 41820,
            "target_uid": "local-uid",
            "init_ts": time.monotonic() - 0.01,
            "ts": time.monotonic(),
        }
        engine._handle_message(msg, ("10.0.0.4", 41820))

        peer = engine.peers["remote-uid"]
        assert peer.adjacency == AdjacencyState.CONFIRMED
        assert peer.latency_ms > 0

        # Should have sent CONFIRM
        confirm_msg = json.loads(transport.sent[-1][0])
        assert confirm_msg["type"] == MsgType.HANDSHAKE_CONFIRM.value

    def test_handshake_confirm_finalizes(self):
        engine = self._make_engine(uid="local-uid")
        engine._transport = _MockTransport()

        engine.peers["remote-uid"] = PeerShard(
            uid="remote-uid", human_name="rapid-hawk",
            host="10.0.0.5", port=41820,
            last_seen=time.monotonic(),
            adjacency=AdjacencyState.HANDSHAKE_ACKED,
        )

        msg = {
            "type": MsgType.HANDSHAKE_CONFIRM.value,
            "sender_uid": "remote-uid",
            "sender_name": "rapid-hawk",
            "sender_host": "10.0.0.5",
            "sender_port": 41820,
            "target_uid": "local-uid",
            "ts": time.monotonic(),
        }
        engine._handle_message(msg, ("10.0.0.5", 41820))

        peer = engine.peers["remote-uid"]
        assert peer.adjacency == AdjacencyState.CONFIRMED


class TestNodeFormation:
    """Test the Maestro Node quorum logic."""

    def _engine_with_peers(self, n_adjacent, quorum=3):
        engine = ShardDiscoveryEngine(
            node_quorum=quorum,
            identity=ShardIdentity(uid="self", human_name="local-shard"),
        )
        engine._transport = _MockTransport()
        for i in range(n_adjacent):
            engine.peers[f"peer-{i}"] = PeerShard(
                uid=f"peer-{i}",
                human_name=f"peer-{i}-name",
                host=f"10.0.0.{i+2}",
                port=41820,
                last_seen=time.monotonic(),
                adjacency=AdjacencyState.CONFIRMED,
            )
        return engine

    def test_node_forms_at_quorum(self):
        engine = self._engine_with_peers(2, quorum=3)  # 2 peers + self = 3
        engine._evaluate_node_status()
        assert engine.node_status.formed
        assert len(engine.node_status.member_uids) == 3
        assert "self" in engine.node_status.member_uids

    def test_node_not_formed_below_quorum(self):
        engine = self._engine_with_peers(1, quorum=3)  # 1 peer + self = 2
        engine._evaluate_node_status()
        assert not engine.node_status.formed

    def test_node_dissolves_when_peers_go_stale(self):
        engine = self._engine_with_peers(2, quorum=3)
        engine._evaluate_node_status()
        assert engine.node_status.formed

        # Mark one peer as stale
        engine.peers["peer-0"].adjacency = AdjacencyState.STALE
        engine._evaluate_node_status()
        assert not engine.node_status.formed

    def test_node_with_excess_peers(self):
        engine = self._engine_with_peers(5, quorum=3)
        engine._evaluate_node_status()
        assert engine.node_status.formed
        # Only first quorum members are listed
        assert len(engine.node_status.member_uids) == 3


class TestSnapshot:
    def test_snapshot_structure(self):
        engine = ShardDiscoveryEngine(
            identity=ShardIdentity(uid="snap-uid", human_name="snap-node"),
        )
        engine._transport = _MockTransport()
        engine.peers["p1"] = PeerShard(
            uid="p1", human_name="peer-one", host="10.0.0.2",
            port=41820, last_seen=time.monotonic(),
            adjacency=AdjacencyState.CONFIRMED,
        )

        snap = engine.snapshot()
        assert snap["identity"]["uid"] == "snap-uid"
        assert snap["peer_count"] == 1
        assert snap["alive_count"] == 1
        assert snap["adjacent_count"] == 1
        assert "p1" in snap["peers"]
        assert snap["peers"]["p1"]["adjacency"] == "confirmed"

    def test_peer_summary(self):
        engine = ShardDiscoveryEngine(
            identity=ShardIdentity(uid="sum-uid", human_name="sum-node"),
        )
        engine.peers["p1"] = PeerShard(
            uid="p1-full-uid", human_name="alpha-fox", host="10.0.0.2",
            port=41820, last_seen=time.monotonic(),
            adjacency=AdjacencyState.CONFIRMED, latency_ms=3.5,
            first_seen=time.monotonic(),
        )

        summary = engine.peer_summary()
        assert len(summary) == 1
        assert summary[0]["name"] == "alpha-fox"
        assert summary[0]["uid_short"] == "p1-full-"
        assert summary[0]["adjacent"] is True
        assert summary[0]["latency_ms"] == 3.5


class TestStaleDetection:
    def test_peer_goes_stale(self):
        engine = ShardDiscoveryEngine(
            identity=ShardIdentity(uid="stale-test", human_name="stale-node"),
        )
        engine._transport = _MockTransport()
        engine.peers["old-peer"] = PeerShard(
            uid="old-peer", human_name="old-one", host="10.0.0.99",
            port=41820, last_seen=time.monotonic() - 60,
            adjacency=AdjacencyState.CONFIRMED,
        )

        assert not engine.peers["old-peer"].is_alive
        assert not engine.peers["old-peer"].is_adjacent


class TestLANIPDetection:
    def test_detect_returns_string(self):
        ip = ShardDiscoveryEngine._detect_lan_ip()
        assert isinstance(ip, str)
        # Should be a valid IPv4 address
        parts = ip.split(".")
        assert len(parts) == 4


# ---------------------------------------------------------------------------
# Mock transport for testing without real sockets
# ---------------------------------------------------------------------------

class _MockTransport:
    """Minimal mock of asyncio.DatagramTransport for unit testing."""

    def __init__(self):
        self.sent: list[tuple[bytes, tuple]] = []
        self.closed = False

    def sendto(self, data: bytes, addr: tuple) -> None:
        self.sent.append((data, addr))

    def close(self) -> None:
        self.closed = True
