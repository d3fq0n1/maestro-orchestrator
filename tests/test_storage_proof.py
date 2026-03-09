"""
Tests for the Storage Proof Engine — challenge/response, reputation scoring.
"""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from maestro.storage_proof import (
    ShardDescriptor,
    StorageChallenge,
    ChallengeResponse,
    NodeReputation,
    StorageProofEngine,
)


class TestStorageProofEngine:
    def test_issue_byte_range_challenge(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        challenge = engine.issue_challenge("node-1", "shard-a", "byte_range_hash")
        assert challenge.challenge_type == "byte_range_hash"
        assert challenge.node_id == "node-1"
        assert challenge.shard_id == "shard-a"
        assert challenge.byte_offset is not None
        assert challenge.expected_hash is not None

    def test_issue_latency_probe(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        challenge = engine.issue_challenge("node-1", "shard-a", "latency_probe")
        assert challenge.challenge_type == "latency_probe"
        assert challenge.max_latency_ms == engine.DEFAULT_MAX_LATENCY_MS

    def test_issue_canary_inference(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        challenge = engine.issue_challenge("node-1", "shard-a", "canary_inference")
        assert challenge.challenge_type == "canary_inference"
        assert challenge.canary_input is not None

    def test_validate_correct_byte_range_hash(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        challenge = engine.issue_challenge("node-1", "shard-a", "byte_range_hash")

        response = ChallengeResponse(
            challenge_id=challenge.challenge_id,
            node_id="node-1",
            responded_at=datetime.now(timezone.utc).isoformat(),
            response_hash=challenge.expected_hash,
        )
        assert engine.validate_response(response)
        assert response.passed

    def test_validate_wrong_hash_fails(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        challenge = engine.issue_challenge("node-1", "shard-a", "byte_range_hash")

        response = ChallengeResponse(
            challenge_id=challenge.challenge_id,
            node_id="node-1",
            responded_at=datetime.now(timezone.utc).isoformat(),
            response_hash="wrong_hash",
        )
        assert not engine.validate_response(response)
        assert not response.passed
        assert response.failure_reason == "Hash mismatch"

    def test_validate_latency_probe_pass(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        challenge = engine.issue_challenge("node-1", "shard-a", "latency_probe")

        response = ChallengeResponse(
            challenge_id=challenge.challenge_id,
            node_id="node-1",
            responded_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=100.0,
        )
        assert engine.validate_response(response)

    def test_validate_latency_probe_fail(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        challenge = engine.issue_challenge("node-1", "shard-a", "latency_probe")

        response = ChallengeResponse(
            challenge_id=challenge.challenge_id,
            node_id="node-1",
            responded_at=datetime.now(timezone.utc).isoformat(),
            latency_ms=99999.0,
        )
        assert not engine.validate_response(response)

    def test_validate_expired_challenge(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        challenge = engine.issue_challenge("node-1", "shard-a", "byte_range_hash")

        # Respond after expiry
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        response = ChallengeResponse(
            challenge_id=challenge.challenge_id,
            node_id="node-1",
            responded_at=future.isoformat(),
            response_hash=challenge.expected_hash,
        )
        assert not engine.validate_response(response)
        assert "expired" in response.failure_reason.lower()


class TestNodeReputation:
    def test_initial_reputation(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        rep = engine.get_reputation("unknown-node")
        assert rep.reputation_score == 1.0
        assert rep.status == "trusted"

    def test_reputation_increases_with_successes(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        for i in range(5):
            challenge = engine.issue_challenge("node-1", f"shard-{i}", "byte_range_hash")
            response = ChallengeResponse(
                challenge_id=challenge.challenge_id,
                node_id="node-1",
                responded_at=datetime.now(timezone.utc).isoformat(),
                response_hash=challenge.expected_hash,
            )
            engine.validate_response(response)

        rep = engine.get_reputation("node-1")
        assert rep.challenges_passed == 5
        assert rep.challenges_failed == 0
        assert rep.challenge_pass_rate == 1.0
        assert rep.status == "trusted"

    def test_reputation_decreases_with_failures(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        for i in range(10):
            challenge = engine.issue_challenge("node-bad", f"shard-{i}", "byte_range_hash")
            response = ChallengeResponse(
                challenge_id=challenge.challenge_id,
                node_id="node-bad",
                responded_at=datetime.now(timezone.utc).isoformat(),
                response_hash="wrong",
            )
            engine.validate_response(response)

        rep = engine.get_reputation("node-bad")
        assert rep.challenges_failed == 10
        assert rep.challenge_pass_rate == 0.0
        assert rep.reputation_score < 0.5

    def test_eviction_on_low_reputation(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        # Force low reputation
        engine._reputations["node-evict"] = NodeReputation(
            node_id="node-evict",
            reputation_score=0.1,
        )
        assert engine.evict_if_necessary("node-evict")
        assert engine.get_reputation("node-evict").status == "evicted"

    def test_r2_contribution_affects_reputation(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        engine._reputations["node-r2"] = NodeReputation(
            node_id="node-r2",
            challenges_passed=5,
            challenges_failed=0,
            challenge_pass_rate=1.0,
        )
        engine.add_r2_contribution("node-r2", 1.0)
        rep = engine.get_reputation("node-r2")
        assert rep.reputation_score > 0.9

    def test_reputation_persists_to_disk(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        challenge = engine.issue_challenge("node-persist", "shard-1", "byte_range_hash")
        response = ChallengeResponse(
            challenge_id=challenge.challenge_id,
            node_id="node-persist",
            responded_at=datetime.now(timezone.utc).isoformat(),
            response_hash=challenge.expected_hash,
        )
        engine.validate_response(response)

        # Load a new engine from same dir
        engine2 = StorageProofEngine(proof_dir=str(tmp_path))
        rep = engine2.get_reputation("node-persist")
        assert rep.challenges_passed >= 1

    def test_list_reputations(self, tmp_path):
        engine = StorageProofEngine(proof_dir=str(tmp_path))
        engine._reputations["node-a"] = NodeReputation(node_id="node-a")
        engine._reputations["node-b"] = NodeReputation(node_id="node-b")
        reps = engine.list_reputations()
        assert len(reps) == 2
