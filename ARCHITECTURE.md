# Maestro: Orchestrating Persistent AI Infrastructure

## The Thesis

Maestro is a control plane for distributed WeightHosts.

The current AI inference paradigm treats weight-loading as a physical given. It is not. It is a design artifact. Every time a query arrives at a cloud API, the implicit assumption is that weights will be loaded to serve it — or that they are already loaded because a centralized provider keeps them hot. This works for providers who can amortize the cost across millions of users. It does not work for anyone else.

The correct inversion: **route queries to persistent weights, not weights to queries.**

A model's weights are large, static, and expensive to move. A query is small, dynamic, and cheap to route. The engineering conclusion is obvious once stated: weights should stay where they are, and queries should travel to them. Maestro implements this inversion as a mechanical reality in the codebase, not as an aspiration in a roadmap.

## Why This Matters

If inference requires centralized weight hosting, then inference is a monopoly resource. Only organizations that can afford to keep terabytes of weights hot in GPU memory can serve models. Everyone else pays rent.

If inference can be distributed across persistent WeightHosts — commodity machines, edge devices, personal GPUs — then the monopoly breaks. A Raspberry Pi holding layers 0-15 of a 70B model is a legitimate WeightNode if another machine holds layers 16-31. Neither machine could serve the model alone. Together, with a control plane that knows where the weights live and routes queries accordingly, they form a viable inference pipeline.

This is not speculative. The shard registry, pipeline construction, and proof-of-storage systems in this codebase implement it. The gap is between "implemented" and "production-ready at scale," which is an engineering gap, not an architectural one.

## Core Abstractions

### WeightHost

A `WeightHost` is any machine that holds model weight shards persistently and can serve inference requests against them. It replaces the concept of a "storage node" or "backend" — those terms imply interchangeable commodity resources. WeightHosts are not interchangeable. Each one holds specific layers of specific models, and the WeightHost registry must know exactly what lives where.

Every WeightHost declares a capability manifest at registration:

- **`domain_affinity`** — what query types this host handles well (e.g., `["code", "math"]`)
- **`warm`** — whether this host has been recently active (weights are hot in memory)
- **`hardware_class`** — `cloud_api`, `local_gpu`, `edge_node`, or `unknown`
- **`last_active`** — timestamp of last inference activity

This manifest is not metadata. It is the input to the routing function.

### Weight Locality Score

The `weight_locality_score` function computes a routing preference for every query-host pair:

| Priority | Condition | Score |
|----------|-----------|-------|
| 1 | Warm host with matching domain affinity | 1.0 |
| 2 | Warm host, any affinity | 0.75 |
| 3 | Cold host with matching domain affinity | 0.5 |
| 4 | Cold host, any affinity | 0.25 |

This score participates as a named factor in every pipeline construction call, alongside reputation and latency. It is not advisory. It is load-bearing.

### WeightHostRegistry

The registry holds the complete topology of the WeightHost mesh. It constructs inference pipelines by assembling ordered sequences of WeightNodes that together cover all layers of a model. Pipeline construction uses weight locality score as the primary tiebreaker when multiple WeightNodes can serve the same layer range.

The registry also tracks:
- Heartbeats and staleness
- Reputation scores (from the proof-of-storage engine)
- Redundancy maps (which WeightNodes hold which layer ranges)
- Embedding-capable WeightNodes

## Conductor Pipeline

The Conductor sits above the WeightHost layer. It does not care whether an agent's response came from a centralized API or a distributed pipeline of WeightNodes. Both produce a string. The pipeline is:

1. **Parallel agent queries** — all agents (centralized and distributed) queried simultaneously
2. **Deliberation** — each agent reads peer responses and refines its position (configurable rounds)
3. **Dissent analysis** — pairwise semantic distance, outlier detection
4. **NCG baseline** — headless generation to detect silent collapse and RLHF conformity drift
5. **Semantic quorum** — 66% supermajority clustering for consensus
6. **R2 scoring** — session quality grading, improvement signal detection
7. **Ledger indexing** — persistent epistemic record

## Quality Assurance Layers

### MAGI (Meta-Agent Governance and Insight)

MAGI reads the R2 ledger and session history to detect cross-session patterns. It produces structured recommendations for system-level changes. MAGI never auto-applies changes. It observes, analyzes, and proposes. Humans decide.

MAGI serves the thesis by ensuring that the distributed inference pipeline produces outputs of comparable or superior quality to centralized alternatives. If WeightHosts degrade, MAGI detects it.

### Quorum and Dissent

The 66% quorum threshold and 33% dissent preservation are mechanisms for epistemic integrity. Agreement is not automatically good. Dissent is not automatically bad. The system records both and lets downstream consumers decide what to trust.

These thresholds are retained as-is.

### NCG (Novel Content Generation)

The headless baseline detects when all agents converge on the same answer not because the answer is correct, but because RLHF training pushed them toward conformity. This is a real failure mode. NCG catches it by comparing agent outputs against an unconstrained generation baseline.

### InjectionGuard and Rollback

The self-improvement pipeline can propose and apply code changes to the running system. The InjectionGuard enforces safety rails: category whitelists, bounds enforcement, rate limiting, smoke tests. Every injection is paired with a rollback snapshot. If quality degrades, the system reverts automatically.

These safety systems are retained as-is.

## Proof-of-Storage

WeightHosts must prove they hold the weights they claim. The `StorageProofEngine` issues three types of challenges:

- **Proof-of-Replication** — byte-range hash of a specific offset in a shard file
- **Proof-of-Residency** — latency probe (you can only respond fast if the data is local)
- **Proof-of-Inference** — canary inference producing a deterministic output

Reputation scores combine challenge pass rates with R2 contribution metrics. WeightNodes below 0.3 reputation are evicted. WeightNodes below 0.7 are on probation. This is the trust layer that makes distributed inference viable — you cannot participate in the mesh without proving you hold real weights.

## R2 Epistemic Ledger

Every Conductor session is scored and indexed into a persistent ledger. The R2 engine grades sessions (strong, acceptable, weak, suspicious), detects improvement signals, and provides the data substrate for MAGI's cross-session analysis.

The ledger is retained as-is.

## Self-Improvement Engine

The rapid recursion loop (MAGI analysis -> code introspection -> optimization proposals -> MAGI_VIR sandbox validation -> promote/reject -> optional injection) is disabled by default behind the `MAESTRO_AUTO_INJECT` environment variable. When enabled, it allows the system to tune its own thresholds and parameters under human supervision.

Retained as-is.

## Long-Term Substrate: telOS

Maestro's WeightHost/WeightNode abstraction was designed independently but is architecturally convergent with telOS. In telOS, the vector database *is* the address space — there is no process table, no file hierarchy, no PID namespace. Resources are located by semantic proximity to intent vectors, not by path or numeric identifier.

Under this model:
- A **WeightHost** becomes a vector-addressed node in the telOS address space, located by its capability signature
- A **WeightNode** is a resolved inference endpoint, reachable via intent query rather than TCP socket
- The quorum layer becomes a semantic consensus operation over the vector substrate, not a network vote over HTTP
- The R2 epistemic ledger maps naturally to an append-only vector index with time-weighted decay

This is not vaporware architectural speculation. It is the intended end state of the infrastructure Blake is currently building, and every design decision in Maestro should be evaluated against whether it survives the Python→Rust→telOS transition with minimal refactor cost.

---

## Design Decisions Follow From the Thesis

Every architectural choice in Maestro derives from the core inversion:

- **WeightHost over generic "backend"** — because the abstraction must encode what a host holds, not just that it exists
- **WeightNode over generic "node"** — because each inference node holds specific layers and participates in specific pipelines
- **Capability manifests** — because routing requires knowing domain affinity and warmth state, not just availability
- **Locality-aware routing** — because the whole point is to route queries to where weights already live
- **Pipeline construction** — because a single WeightNode rarely holds a complete model; inference requires composing WeightNodes
- **Proof-of-storage** — because distributed trust requires cryptographic verification, not just heartbeats
- **MAGI and R2** — because quality must be measured continuously to prove that distributed inference works

The implementation is incomplete. The direction is not ambiguous.
