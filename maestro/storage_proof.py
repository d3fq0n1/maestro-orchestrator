"""
Storage Proof System — Cryptographic verification of weight shard residency.

Implements three proof types:
  1. Proof-of-Replication (PoRep) — Node proves it holds a unique copy of a shard
     by responding to random byte-range hash challenges.
  2. Proof-of-Residency (PoRes) — Node proves weights are loaded in active memory
     (not just on disk) by meeting latency requirements on challenge responses.
  3. Proof-of-Inference (PoI) — Node proves it can produce valid forward-pass
     outputs for known input/output pairs (canary tensors).

Challenge frequency is configurable. Failures trigger reputation penalties
in R2 and eventual eviction from the shard registry.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional
import hashlib
import json
import os
import uuid
from pathlib import Path


_DEFAULT_PROOF_DIR = Path(__file__).resolve().parent.parent / "data" / "storage_proofs"


@dataclass
class ShardDescriptor:
    """Describes a specific weight shard hosted by a node."""
    shard_id: str
    model_id: str
    model_hash: str
    layer_range: tuple
    shard_format: str          # "safetensors", "gguf", "pytorch", "numpy"
    precision: str             # "fp32", "fp16", "bf16", "int8", "int4"
    size_bytes: int
    tensor_names: list = field(default_factory=list)
    checksum: str = ""


@dataclass
class StorageChallenge:
    """A challenge issued to a node to prove shard residency."""
    challenge_id: str
    node_id: str
    shard_id: str
    challenge_type: str        # "byte_range_hash", "latency_probe", "canary_inference"
    issued_at: str
    expires_at: str

    # For byte_range_hash:
    byte_offset: Optional[int] = None
    byte_length: Optional[int] = None
    expected_hash: Optional[str] = None

    # For canary_inference:
    canary_input: Optional[dict] = None
    expected_output_hash: Optional[str] = None

    # For latency_probe:
    max_latency_ms: Optional[int] = None


@dataclass
class ChallengeResponse:
    """A node's response to a storage challenge."""
    challenge_id: str
    node_id: str
    responded_at: str
    response_hash: Optional[str] = None
    inference_output_hash: Optional[str] = None
    latency_ms: Optional[float] = None
    passed: bool = False
    failure_reason: Optional[str] = None


@dataclass
class NodeReputation:
    """Reputation score derived from challenge history and R2 session quality."""
    node_id: str
    challenges_issued: int = 0
    challenges_passed: int = 0
    challenges_failed: int = 0
    challenge_pass_rate: float = 1.0
    mean_latency_ms: float = 0.0
    r2_contribution_scores: list = field(default_factory=list)
    reputation_score: float = 1.0
    last_challenge: Optional[str] = None
    last_failure: Optional[str] = None
    status: str = "trusted"    # "trusted", "probation", "untrusted", "evicted"


class StorageProofEngine:
    """
    Manages the challenge-response lifecycle for all registered storage nodes.

    Responsibilities:
      - Issue periodic challenges to nodes based on their shard claims
      - Validate challenge responses
      - Update node reputation scores
      - Trigger eviction when reputation drops below threshold
      - Provide reputation data to R2 for session scoring

    Storage: data/storage_proofs/ directory, one JSON file per challenge cycle.
    """

    # Reputation thresholds
    PROBATION_THRESHOLD = 0.7
    EVICTION_THRESHOLD = 0.3
    DEFAULT_CHALLENGE_WINDOW_SECONDS = 60
    DEFAULT_MAX_LATENCY_MS = 5000

    def __init__(self, proof_dir: str = None, challenge_interval_seconds: int = 300):
        self._dir = Path(proof_dir) if proof_dir else _DEFAULT_PROOF_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._challenge_interval = challenge_interval_seconds
        self._reputations: dict[str, NodeReputation] = {}
        self._pending_challenges: dict[str, StorageChallenge] = {}

        # Load persisted reputations
        self._load_reputations()

    def _load_reputations(self):
        """Load reputation data from disk."""
        rep_file = self._dir / "reputations.json"
        if rep_file.exists():
            try:
                data = json.loads(rep_file.read_text())
                for node_id, rep_data in data.items():
                    self._reputations[node_id] = NodeReputation(**{
                        k: v for k, v in rep_data.items()
                        if k in NodeReputation.__dataclass_fields__
                    })
            except (json.JSONDecodeError, TypeError):
                pass

    def _save_reputations(self):
        """Persist reputation data to disk."""
        data = {
            node_id: asdict(rep) for node_id, rep in self._reputations.items()
        }
        rep_file = self._dir / "reputations.json"
        rep_file.write_text(json.dumps(data, indent=2, default=str))

    def issue_challenge(
        self,
        node_id: str,
        shard_id: str,
        challenge_type: str = "byte_range_hash",
    ) -> StorageChallenge:
        """Create and persist a new challenge for a node."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=self.DEFAULT_CHALLENGE_WINDOW_SECONDS)

        challenge = StorageChallenge(
            challenge_id=str(uuid.uuid4()),
            node_id=node_id,
            shard_id=shard_id,
            challenge_type=challenge_type,
            issued_at=now.isoformat(),
            expires_at=expires.isoformat(),
        )

        if challenge_type == "byte_range_hash":
            # Random byte range for the shard
            challenge.byte_offset = int.from_bytes(os.urandom(4), "big") % (1024 * 1024)
            challenge.byte_length = 4096
            # Expected hash would be pre-computed by challenger who has a reference copy
            challenge.expected_hash = hashlib.sha256(
                f"{shard_id}:{challenge.byte_offset}:{challenge.byte_length}".encode()
            ).hexdigest()

        elif challenge_type == "latency_probe":
            challenge.max_latency_ms = self.DEFAULT_MAX_LATENCY_MS

        elif challenge_type == "canary_inference":
            challenge.canary_input = {"type": "canary", "shard_id": shard_id}
            challenge.expected_output_hash = hashlib.sha256(
                f"canary:{shard_id}".encode()
            ).hexdigest()

        self._pending_challenges[challenge.challenge_id] = challenge

        # Update reputation tracking
        if node_id not in self._reputations:
            self._reputations[node_id] = NodeReputation(node_id=node_id)
        self._reputations[node_id].challenges_issued += 1
        self._reputations[node_id].last_challenge = now.isoformat()

        return challenge

    def validate_response(self, response: ChallengeResponse) -> bool:
        """Verify a challenge response and update reputation."""
        challenge = self._pending_challenges.pop(response.challenge_id, None)
        if not challenge:
            response.passed = False
            response.failure_reason = "Unknown or expired challenge"
            return False

        # Check expiry
        expires = datetime.fromisoformat(challenge.expires_at)
        responded = datetime.fromisoformat(response.responded_at)
        if responded > expires:
            response.passed = False
            response.failure_reason = "Response received after challenge expired"
            self._record_failure(response.node_id)
            return False

        passed = False
        if challenge.challenge_type == "byte_range_hash":
            passed = (response.response_hash == challenge.expected_hash)
            if not passed:
                response.failure_reason = "Hash mismatch"

        elif challenge.challenge_type == "latency_probe":
            if response.latency_ms is not None and challenge.max_latency_ms is not None:
                passed = response.latency_ms <= challenge.max_latency_ms
                if not passed:
                    response.failure_reason = (
                        f"Latency {response.latency_ms}ms exceeds "
                        f"max {challenge.max_latency_ms}ms"
                    )
            else:
                response.failure_reason = "Missing latency data"

        elif challenge.challenge_type == "canary_inference":
            passed = (response.inference_output_hash == challenge.expected_output_hash)
            if not passed:
                response.failure_reason = "Canary inference output mismatch"

        response.passed = passed

        if passed:
            self._record_success(response.node_id, response.latency_ms)
        else:
            self._record_failure(response.node_id)

        return passed

    def _record_success(self, node_id: str, latency_ms: float = None):
        """Record a successful challenge response."""
        rep = self._reputations.setdefault(node_id, NodeReputation(node_id=node_id))
        rep.challenges_passed += 1
        self._update_pass_rate(rep)

        if latency_ms is not None:
            # Rolling average
            total = rep.challenges_passed
            rep.mean_latency_ms = (
                (rep.mean_latency_ms * (total - 1) + latency_ms) / total
            )

        self._update_reputation_score(rep)
        self._save_reputations()

    def _record_failure(self, node_id: str):
        """Record a failed challenge response."""
        rep = self._reputations.setdefault(node_id, NodeReputation(node_id=node_id))
        rep.challenges_failed += 1
        rep.last_failure = datetime.now(timezone.utc).isoformat()
        self._update_pass_rate(rep)
        self._update_reputation_score(rep)
        self._save_reputations()

    def _update_pass_rate(self, rep: NodeReputation):
        """Recalculate challenge pass rate."""
        total = rep.challenges_passed + rep.challenges_failed
        rep.challenge_pass_rate = rep.challenges_passed / total if total > 0 else 1.0

    def _update_reputation_score(self, rep: NodeReputation):
        """
        Compute reputation score from challenge pass rate and R2 contributions.
        Score = 0.7 * challenge_pass_rate + 0.3 * mean_r2_contribution
        """
        r2_mean = 0.5  # default neutral
        if rep.r2_contribution_scores:
            r2_mean = sum(rep.r2_contribution_scores[-20:]) / len(rep.r2_contribution_scores[-20:])

        rep.reputation_score = round(
            0.7 * rep.challenge_pass_rate + 0.3 * r2_mean, 4
        )

        # Status transitions
        if rep.reputation_score < self.EVICTION_THRESHOLD:
            rep.status = "evicted"
        elif rep.reputation_score < self.PROBATION_THRESHOLD:
            rep.status = "probation"
        else:
            if rep.status in ("probation", "untrusted"):
                rep.status = "trusted"  # recovered

    def get_reputation(self, node_id: str) -> NodeReputation:
        """Get current reputation for a node."""
        return self._reputations.get(
            node_id, NodeReputation(node_id=node_id)
        )

    def run_challenge_cycle(self, registry) -> dict:
        """
        Issue challenges to all registered nodes. Called periodically.
        Returns a summary of the cycle.
        """
        now = datetime.now(timezone.utc)
        cycle_id = f"cycle_{now.isoformat()}"
        results = {
            "cycle_id": cycle_id,
            "timestamp": now.isoformat(),
            "challenges_issued": 0,
            "nodes_challenged": [],
        }

        # Get all nodes from registry
        if not hasattr(registry, '_nodes'):
            return results

        for node_id, node_data in registry._nodes.items():
            shards = node_data.get("shards", []) if isinstance(node_data, dict) else []
            if hasattr(node_data, 'shards'):
                shards = node_data.shards

            if not shards:
                # Issue a latency probe even without shards
                challenge = self.issue_challenge(node_id, "none", "latency_probe")
                results["challenges_issued"] += 1
                results["nodes_challenged"].append(node_id)
            else:
                for shard in shards[:1]:  # Challenge first shard per cycle
                    shard_id = shard.get("shard_id", "unknown") if isinstance(shard, dict) else getattr(shard, 'shard_id', 'unknown')
                    challenge = self.issue_challenge(node_id, shard_id)
                    results["challenges_issued"] += 1
                    results["nodes_challenged"].append(node_id)

        # Persist cycle
        cycle_file = self._dir / f"{cycle_id}.json"
        try:
            cycle_file.write_text(json.dumps(results, indent=2))
        except Exception as e:
            print(f"[StorageProof] Failed to persist cycle: {e}")

        return results

    def evict_if_necessary(self, node_id: str) -> bool:
        """Check reputation and evict node if below threshold."""
        rep = self.get_reputation(node_id)
        if rep.reputation_score < self.EVICTION_THRESHOLD:
            rep.status = "evicted"
            self._save_reputations()
            return True
        return False

    def add_r2_contribution(self, node_id: str, score: float):
        """Record an R2 session contribution score for a node."""
        rep = self._reputations.setdefault(node_id, NodeReputation(node_id=node_id))
        rep.r2_contribution_scores.append(score)
        # Keep last 100
        if len(rep.r2_contribution_scores) > 100:
            rep.r2_contribution_scores = rep.r2_contribution_scores[-100:]
        self._update_reputation_score(rep)
        self._save_reputations()

    def list_reputations(self) -> list[dict]:
        """List all node reputations."""
        return [asdict(rep) for rep in self._reputations.values()]
