# Storage Network — Proof-of-Storage Distributed Inference

**Version:** v7.2.8
**Last Updated:** 2026-03-17
**Maintainer:** defcon

The storage network is Maestro's distributed inference layer. Instead of routing prompts to centralized API endpoints, the ShardAgent constructs inference pipelines across a network of storage nodes, each holding specific weight shards. Compute follows storage — the node that holds the weights runs the forward pass.

---

## Architecture

```
                   StorageNodeRegistry
                         |
              +----------+----------+
              |                     |
       Node A (layers 0-15)  Node B (layers 16-31)
              |                     |
              +----------+----------+
                         |
                         v
                 ShardAgent.fetch(prompt)
                         |
              +----------+----------+
              |                     |
         Tokenize prompt      Build pipeline
              |                     |
              v                     v
         Embed input       [Node A] -> [Node B]
              |                     |
              v                     v
         Forward pass        Forward pass
         (layers 0-15)      (layers 16-31)
              |                     |
              +----------+----------+
                         |
                         v
                   Decode logits
                         |
                         v
                  Response string
                  (same as any agent)
```

The orchestrator sees the ShardAgent as just another agent — it calls `fetch(prompt)` and gets a response string. The distributed pipeline is invisible to the rest of the system.

---

## Core Components

### Storage Node Registry (`maestro/shard_registry.py`)

Topology-aware registry of storage nodes and their weight shards.

**Key capabilities:**
- **Shard-level declarations** — Each node declares which layers of which models it holds
- **Pipeline construction** — Greedy algorithm assembles an ordered sequence of nodes covering all layers, preferring higher reputation then lower latency
- **Redundancy mapping** — Tracks which layer ranges have multiple node holders for failover
- **Embedding node discovery** — Finds nodes with embedding capabilities
- **Heartbeat tracking** — Nodes send periodic heartbeats; stale nodes are pruned
- **Reputation integration** — Node status automatically degrades when reputation drops

```python
from maestro.shard_registry import StorageNodeRegistry, StorageNode

registry = StorageNodeRegistry()

# Register a node
registry.register(StorageNode(
    node_id="gpu-node-1",
    host="192.168.1.100",
    port=8001,
    shards=[{
        "shard_id": "llama-70b-layers-0-15",
        "model_id": "meta-llama/llama-3.3-70b-instruct",
        "layer_range": [0, 15],
        "shard_format": "safetensors",
        "precision": "fp16",
        "size_bytes": 35_000_000_000,
    }],
    capabilities=["inference", "embeddings"],
    total_memory_mb=81920,
))

# Build inference pipeline for a model
pipeline = registry.build_inference_pipeline("meta-llama/llama-3.3-70b-instruct")

# Check redundancy
redundancy = registry.get_redundancy_map("meta-llama/llama-3.3-70b-instruct")
# {"0-15": ["gpu-node-1", "gpu-node-3"], "16-31": ["gpu-node-2"]}

# Prune stale nodes (no heartbeat in 10 minutes)
pruned = registry.prune_stale_nodes(max_age_seconds=600)
```

**StorageNode fields:** `node_id`, `host`, `port`, `status`, `shards`, `capabilities`, `total_memory_mb`, `used_memory_mb`, `mean_latency_ms`, `reputation_score`, `metadata`, `registered_at`, `last_heartbeat`

**Node status values:** `available`, `busy`, `offline`, `probation`, `evicted`

Storage: `data/storage_nodes/`, one JSON file per node.

---

### Storage Proof Engine (`maestro/storage_proof.py`)

Cryptographic verification that nodes actually hold the weight shards they claim. Three proof types:

| Proof Type | What It Proves | Mechanism |
|---|---|---|
| **Proof-of-Replication (PoRep)** | Node holds a unique copy of the shard on disk | Random byte-range hash challenge — node must hash a specific offset/length of the shard file |
| **Proof-of-Residency (PoRes)** | Weights are loaded in active memory (not just on disk) | Latency probe — response must arrive within `max_latency_ms` threshold |
| **Proof-of-Inference (PoI)** | Node can produce valid forward-pass outputs | Canary inference — known input/output pair, node must reproduce the expected output hash |

**Challenge lifecycle:**

```
1. Engine issues challenge → StorageChallenge
2. Challenge sent to node → POST /challenge on node_server
3. Node computes response → ChallengeResponse
4. Engine validates response → pass/fail
5. Reputation updated → NodeReputation
6. Eviction check → status transition if below threshold
```

**Reputation scoring:**

```
reputation_score = 0.7 * challenge_pass_rate + 0.3 * mean_r2_contribution
```

| Score | Status |
|---|---|
| >= 0.7 | `trusted` |
| 0.3 – 0.7 | `probation` |
| < 0.3 | `evicted` |

Evicted nodes are excluded from pipeline construction. Nodes on probation can recover by passing subsequent challenges.

```python
from maestro.storage_proof import StorageProofEngine

engine = StorageProofEngine()

# Issue a challenge
challenge = engine.issue_challenge("gpu-node-1", "llama-70b-layers-0-15", "byte_range_hash")

# Validate a response
passed = engine.validate_response(response)

# Run challenge cycle across all registered nodes
results = engine.run_challenge_cycle(registry)

# Check reputation
rep = engine.get_reputation("gpu-node-1")
# NodeReputation(reputation_score=0.95, status="trusted", ...)

# Record R2 contribution
engine.add_r2_contribution("gpu-node-1", score=0.82)
```

Storage: `data/storage_proofs/reputations.json` for persistent reputation data, plus per-cycle JSON files.

---

### Shard Agent (`maestro/agents/shard.py`)

The ShardAgent implements the same `Agent` base class as GPT-4o, Claude Sonnet 4.6, Gemini 2.5 Flash, and Llama 3.3 70B. It's a drop-in addition to the agent council.

```python
from maestro.agents.shard import ShardAgent

agent = ShardAgent(
    model_id="meta-llama/llama-3.3-70b-instruct",
    registry=registry,
    proof_engine=proof_engine,
    timeout_per_hop=30.0,
    min_reputation=0.5,
)

# Same interface as every other agent
response = await agent.fetch("What are the ethical implications of AGI?")
```

**Pipeline execution:**
1. Query registry for nodes covering all model layers
2. Filter by reputation (min threshold)
3. Forward activation tensors through each pipeline node sequentially
4. Each node runs its shard's layers and passes activations to the next
5. Final node produces output, decoded locally
6. On failure, attempt failover to redundant nodes

**Error handling** follows the agent contract — all failures return typed error strings, never raise:
- `[ShardNet] No storage registry configured`
- `[ShardNet] No storage nodes available for {model_id}`
- `[ShardNet] No trusted nodes available (reputation threshold: {min})`
- `[ShardNet] Pipeline failed at hop {i} (node {node_id}): {error}`

---

### Node Server (`maestro/node_server.py`)

**This is a standalone process** — it does NOT run inside the Maestro backend. Each storage node runs its own instance.

```bash
# Start a storage node
MAESTRO_NODE_ID=gpu-node-1 \
MAESTRO_SHARD_CONFIG=data/node_shards.json \
uvicorn maestro.node_server:app --host 0.0.0.0 --port 8001
```

**Endpoints:**

| Method | Path | Description |
|---|---|---|
| POST | `/infer` | Forward-pass inference on resident shards |
| POST | `/challenge` | Respond to proof-of-storage challenges |
| GET | `/health` | Node health and status |
| POST | `/heartbeat` | Acknowledge liveness |
| GET | `/shards` | List resident weight shards |

**Configuration via environment variables:**
- `MAESTRO_NODE_ID` — Unique node identifier (default: `node-default`)
- `MAESTRO_SHARD_CONFIG` — Path to shard declarations JSON (default: `data/node_shards.json`)
- `MAESTRO_ORCHESTRATOR_URL` — Orchestrator URL for auto-registration and heartbeats (optional)
- `MAESTRO_ADVERTISED_HOST` — Public hostname/IP the orchestrator uses to reach this node (optional)
- `MAESTRO_HEARTBEAT_INTERVAL` — Heartbeat interval in seconds (default: `60`)
- `MAESTRO_NODE_PORT` — Listen port (default: `8001`)

**v0.6.2 features:**
- **Auto-registration** — If `MAESTRO_ORCHESTRATOR_URL` is set, the node automatically registers on startup and sends periodic heartbeats
- **Real byte-range proof challenges** — When shard files exist on disk, the `/challenge` endpoint hashes actual file bytes instead of using deterministic mocks. Falls back to mock hashes for backwards compatibility.

---

### Shard Utilities (`maestro/shard_utils.py`)

Low-level tools for working with safetensors weight files:

- **Header parsing** — Read safetensors metadata without loading tensor data
- **Layer mapping** — Extract layer indices from tensor names (supports Llama, GPT-2, BERT, GGUF conventions)
- **Byte-range hashing** — SHA-256 of arbitrary byte ranges (core primitive for PoRep challenges)
- **Shard descriptors** — Build `ShardDescriptor` objects from actual files on disk
- **Directory scanning** — Find and index all safetensors files in a directory

```python
from maestro.shard_utils import (
    read_safetensors_header,
    get_layer_range_from_file,
    hash_byte_range,
    build_shard_descriptor,
    scan_shard_directory,
)

# Parse header without loading tensor data
header = read_safetensors_header("model-00001-of-00004.safetensors")

# What layers does this file cover?
start, end = get_layer_range_from_file("model-00001-of-00004.safetensors")

# Hash bytes at offset 1024, length 4096 (for proof challenges)
h = hash_byte_range("model-00001-of-00004.safetensors", offset=1024, length=4096)
```

---

### Shard Manager (`maestro/shard_manager.py`)

High-level manager for downloading and organizing weight shards:

- **Download from HuggingFace** — Fetch specific safetensors files for a model, with smart layer-range filtering using the model's index file
- **Manifest generation** — Scan local files and build an index of layer coverage, checksums, and precision
- **Node config generation** — Produce the `node_shards.json` config that the node server reads
- **Integrity verification** — Verify all local shards against stored checksums
- **Inventory** — List models, report disk usage, clean up

```python
from maestro.shard_manager import ShardManager

manager = ShardManager()

# Download layers 0-15 of Llama 3.3 70B
manager.download_model_shards(
    model_id="meta-llama/Llama-3.3-70B-Instruct",
    layer_start=0,
    layer_end=15,
    token="hf_...",
)

# Generate node config
config = manager.generate_shard_config(
    "meta-llama/Llama-3.3-70B-Instruct",
    output_path="data/node_shards.json",
)

# Verify integrity
results = manager.verify_all("meta-llama/Llama-3.3-70B-Instruct")
```

Storage layout:
```
data/shards/
  meta-llama__Llama-3.3-70B-Instruct/
    model-00001-of-00004.safetensors
    model-00002-of-00004.safetensors
    manifest.json
```

---

### Node CLI (`maestro/node_cli.py`)

Command-line interface for node operators:

```bash
# Download shards and generate config
python -m maestro.node_cli setup --model meta-llama/Llama-3.3-70B-Instruct --layers 0-15

# Start the node server with auto-registration
python -m maestro.node_cli start --port 8001 --orchestrator http://maestro-host:8080

# Show local shard inventory
python -m maestro.node_cli status

# Verify shard integrity
python -m maestro.node_cli verify --model meta-llama/Llama-3.3-70B-Instruct

# Show what the node would serve
python -m maestro.node_cli shards
```

| Command | Description |
|---|---|
| `setup` | Download model shards from HuggingFace and generate node config |
| `start` | Start the node server (with optional auto-registration) |
| `status` | Show local shard inventory across all models |
| `verify` | Verify shard integrity against manifest checksums |
| `shards` | Show the node's shard config (what it would serve) |

---

## R2 Integration

The storage network integrates with R2 at two levels:

1. **Node contribution scoring** — R2 tracks per-node session quality via `score_node_contribution()`. These scores feed into the reputation formula (30% weight).

2. **Node signal detection** — R2 detects `node_degradation` and `proof_failure` signals, which feed into MAGI for cross-session analysis of storage network health.

---

## REST API

### Network Management

| Method | Path | Description |
|---|---|---|
| POST | `/api/storage/nodes/register` | Register a storage node |
| DELETE | `/api/storage/nodes/{node_id}` | Unregister a node |
| GET | `/api/storage/nodes` | List all nodes with status and reputation |
| GET | `/api/storage/nodes/{node_id}` | Detailed node info with reputation breakdown |
| POST | `/api/storage/challenge/{node_id}` | Trigger a proof challenge |
| GET | `/api/storage/pipeline/{model_id}` | View the current inference pipeline for a model |
| GET | `/api/storage/redundancy/{model_id}` | Redundancy map (which nodes hold which layers) |
| GET | `/api/storage/reputation` | All node reputations |
| GET | `/api/storage/network/topology` | Full network topology with coverage, mirrors, and neighbor nodes |

### Shard Management

| Method | Path | Description |
|---|---|---|
| GET | `/api/storage/shards/models` | List all models with local shards |
| GET | `/api/storage/shards/status/{model_id}` | Detailed shard status for a model |
| POST | `/api/storage/shards/download` | Start downloading shards (background) |
| GET | `/api/storage/shards/download-status/{model_id}` | Check download progress |
| DELETE | `/api/storage/shards/download-status/{model_id}` | Clear download status |
| POST | `/api/storage/shards/verify/{model_id}` | Verify shard integrity |
| GET | `/api/storage/shards/disk-usage` | Disk usage for all shards |
| DELETE | `/api/storage/shards/{model_id}` | Remove all shards for a model |
| POST | `/api/storage/shards/generate-config` | Generate node_shards.json from local shards |

---

## CLI Commands

| Command | Description |
|---|---|
| `/nodes` | List all registered storage nodes with status |
| `/challenge` | Trigger a proof-of-storage challenge cycle |

---

## Data Storage

```
data/storage_nodes/
  {node_id}.json              — Persisted node registration
data/storage_proofs/
  reputations.json            — All node reputation data
  cycle_{timestamp}.json      — Challenge cycle records
data/shards/
  {model_id_safe}/
    *.safetensors             — Downloaded weight shard files
    manifest.json             — Shard index (layers, checksums, precision)
data/node_shards.json         — Node server shard config (what this node serves)
```

All data is human-readable JSON. No databases.

---

## Design Principles

1. **Compute follows storage** — The node that holds the weights runs the forward pass. No weight transfer at inference time.
2. **Cryptographic trust** — Nodes prove they hold what they claim through challenge-response verification. Trust is earned, not assumed.
3. **Reputation is earned** — 70% challenge history + 30% R2 session quality. Nodes that fail proofs or degrade session quality lose reputation and get evicted.
4. **Fail-open** — A storage node failure triggers failover to a redundant node. If no redundant node exists, the ShardAgent returns a typed error string — the orchestration pipeline continues with the remaining agents.
5. **Pipeline transparency** — The orchestrator doesn't know or care that inference happened across a distributed network. It just sees another agent response.

---

## LAN Shard Discovery

Maestro includes a **UDP beacon-based LAN discovery** system (`maestro/lan_discovery.py`) that lets shards on the same local network find each other automatically.

### How It Works

1. Each shard broadcasts a UDP beacon on the local network at a regular interval
2. Discovered peers go through a handshake protocol: `discovered` → `handshake_sent` → `handshake_acked` → `confirmed` (adjacent)
3. When 3 or more adjacent shards are confirmed, a **Maestro Node** is automatically formed
4. Stale peers (no heartbeat received within the timeout) are marked as `stale`/offline

### Monitoring

- **TUI**: The LAN Discovery panel shows local identity, Maestro Node formation status, and live peer adjacency indicators (spinning green asterisks for adjacent peers, red for offline)
- **TUI command**: Press `N` for node details, or type `/shards` in the prompt for a detailed snapshot
- **CLI**: Type `/nodes` to see registered storage nodes

### States

| State | Description |
|-------|-------------|
| `discovered` | Peer beacon received, no handshake yet |
| `handshake_sent` | Handshake request sent to peer |
| `handshake_acked` | Peer acknowledged the handshake |
| `confirmed` | Peer is adjacent and communicating |
| `stale` | No recent heartbeat — peer may be offline |

---

## See Also

- [`agents.md`](./agents.md) — Agent layer (ShardAgent is listed alongside other agents)
- [`mod-manager.md`](./mod-manager.md) — Plugin system (ShardAgent can be installed as a plugin)
- [`r2-engine.md`](./r2-engine.md) — R2 Engine (node contribution scoring)
- [`architecture.md`](./architecture.md) — System architecture overview
