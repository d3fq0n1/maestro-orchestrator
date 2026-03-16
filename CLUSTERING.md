# Maestro Clustering & Sharding

Maestro can run as a distributed multi-node cluster where a primary orchestrator coordinates multiple shard worker nodes. This document covers the architecture, environment variables, and how to run a local cluster.

## Architecture

```
                ┌─────────────────┐
                │   Orchestrator  │
                │  (coordinator)  │
                │   port 8000     │
                └───┬─────┬───┬──┘
                    │     │   │
             ┌──────┘     │   └──────┐
             ▼            ▼          ▼
        ┌─────────┐ ┌─────────┐ ┌─────────┐
        │ Shard-1 │ │ Shard-2 │ │ Shard-3 │
        │ index=0 │ │ index=1 │ │ index=2 │
        │ :8001   │ │ :8002   │ │ :8003   │
        └────┬────┘ └────┬────┘ └────┬────┘
             │            │          │
             └──────┬─────┴──────────┘
                    ▼
              ┌───────────┐    ┌────────────┐
              │   Redis   │    │  Postgres  │
              │   :6379   │    │   :5432    │
              └───────────┘    └────────────┘
```

**Orchestrator** — Runs the full Maestro Web-UI and API. Routes inference tasks to shard nodes via consistent hashing. Issues storage proof challenges.

**Shard workers** — Run the node_server FastAPI app. Accept tasks that fall within their assigned keyspace. Register themselves with the orchestrator and Redis on startup.

**Redis** — Shared state bus. Tracks task assignments, shard registrations, storage proofs, and cluster health. In cluster mode (TUI instance manager), a dedicated shared Redis container (`maestro-shared-redis`) is started on host port **6399** to avoid collisions with per-stack Redis (default 6379). Per-stack Redis/Postgres services from docker-compose.yml are **not** started in cluster mode — the shared container handles all state. If `REDIS_URL` is not set, the system falls back to in-process state (single-node mode).

**Postgres** — Persistent ledger storage. Optional for local development.

## Environment Variables

### All nodes

| Variable | Description | Default |
|---|---|---|
| `NODE_ROLE` | `orchestrator`, `shard`, or empty (standalone) | empty |
| `NODE_ID` | Unique identifier for this instance | `standalone` |
| `SHARD_COUNT` | Total number of shard nodes | `1` |
| `REDIS_URL` | Redis connection URL | empty |
| `DB_URL` | Postgres connection URL | empty |

### Shard nodes only

| Variable | Description | Default |
|---|---|---|
| `SHARD_INDEX` | 0-based position in the shard ring | `0` |
| `ORCHESTRATOR_URL` | URL of the orchestrator | empty |

### Orchestrator only

The orchestrator uses the same environment variables as the standard Maestro deployment (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `MAESTRO_MODE`, etc).

## Task Routing

Tasks are assigned to shards via consistent hashing:

```python
import hashlib
shard_index = int(hashlib.sha256(task_id.encode()).hexdigest(), 16) % shard_count
```

Each shard owns `1/N` of the task keyspace. A shard node rejects tasks outside its range with HTTP 409, so the orchestrator can re-route if needed.

## Storage Proof Protocol

The orchestrator can issue proof challenges to each shard to verify data integrity:

1. Orchestrator sends `POST /proof/attest` with a `challenge_id` and `nonce`
2. Shard computes `SHA-256(node_id:shard_index:nonce:shard_checksums)`
3. Orchestrator verifies the attestation matches expected state

Use `POST /api/cluster/proof/challenge` on the orchestrator to challenge all shards at once.

## API Endpoints

### Orchestrator cluster API (`/api/cluster/`)

| Method | Path | Description |
|---|---|---|
| GET | `/api/cluster/status` | Cluster overview |
| POST | `/api/cluster/dispatch` | Route a task to the correct shard |
| POST | `/api/cluster/proof/challenge` | Challenge all shards |
| GET | `/api/cluster/health` | Poll health of all shards |
| GET | `/api/cluster/routing/{task_id}` | Preview shard assignment |

### Shard node API (each shard, port 8000)

| Method | Path | Description |
|---|---|---|
| POST | `/task/dispatch` | Receive a dispatched task |
| POST | `/task/result` | Push result to orchestrator |
| POST | `/proof/attest` | Respond to storage proof |
| GET | `/health` | Node health |
| GET | `/cluster/info` | Cluster identity |

## Running the Local Cluster

### TUI Instance Manager (recommended)

The easiest way to build a cluster is through the TUI:

1. Launch the TUI: `python -m maestro.tui`
2. Press `M` to open the Instance manager
3. Press `+` to spawn cluster members

The first spawn creates the **orchestrator** along with shared infrastructure (Docker network + shared Redis on port 6399). Each subsequent `+` press spawns a new **shard worker** that auto-registers with the cluster. If port 6399 is already in use by another process, the spawn will fail with a clear error message — stop the conflicting process before retrying. Every instance receives:

- A human-readable name (e.g. "swift-falcon")
- An auto-assigned shard index
- A container IP on the shared cluster network
- Cluster environment variables so all instances see each other

The **Cluster Dashboard** panel on the main TUI screen shows live health for all instances with spinning BTOP-style indicators — no need to open a modal. It auto-refreshes every 2 seconds, or press `C` to refresh immediately. You can also press `+` on the main screen to spawn a new instance without opening the manager:

```
 Cluster
 #   Name           Role          Port   IP              Health
 ─── ────────────── ──────────── ────── ─────────────── ────────
 1   bold-eagle     orchestrator  8000   172.18.0.2      ✶ ok
 2   swift-fox      shard [0]     8010   172.18.0.3      ✶ ok
 3   calm-owl       shard [1]     8020   172.18.0.4      ✶ ok

 3 node(s), 2 shard(s), 3/3 healthy  |  M:Manage  +:Spawn
```

Press `M` to open the full Instance Manager, where you can press `1-9` to stop a specific instance, `+` to spawn, or `R` to refresh.

### Main screen shortcuts

| Key | Action |
|---|---|
| `+` | Quick-spawn a new cluster instance |
| `C` | Refresh cluster dashboard immediately |
| `M` | Open the Instance Manager modal |

### Full cluster via Docker Compose (5 containers)

```bash
docker compose up --build
```

This starts: Redis, Postgres, orchestrator (port 8000), and 3 shard workers (ports 8001-8003).

### Single-node mode (backwards compatible)

```bash
docker compose up orchestrator
```

Or simply:

```bash
docker compose up --build orchestrator
```

When `NODE_ROLE=orchestrator` but no shard nodes are reachable, the system degrades gracefully. When `SHARD_COUNT=1` and `NODE_ROLE` is unset, it behaves identically to the original single-process architecture.

### Test the cluster

```bash
# Check cluster status
curl http://localhost:8000/api/cluster/status

# Check cluster health (polls all shards)
curl http://localhost:8000/api/cluster/health

# Dispatch a test task
curl -X POST http://localhost:8000/api/cluster/dispatch \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test task", "task_id": "test-123"}'

# Preview routing
curl http://localhost:8000/api/cluster/routing/test-123

# Run storage proof challenge
curl -X POST http://localhost:8000/api/cluster/proof/challenge \
  -H "Content-Type: application/json" \
  -d '{}'

# Check individual shard health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```
