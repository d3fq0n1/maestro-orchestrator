# Federated WeightHost / WeightNode — Whiteboard

> **Audience.** This is the whiteboard. The thesis is on
> [`ARCHITECTURE.md`](../../ARCHITECTURE.md), the implementation is
> in `maestro/shard_registry.py`, and the mesh-level economics are
> sketched here. Read it as a marker drawing, not a spec.

---

## The Inversion in One Picture

```
                      CONVENTIONAL INFERENCE                                FEDERATED WEIGHTHOST INFERENCE
                                                                       (queries travel to weights, not the reverse)

       ┌────────────────────────────────────┐                        ┌─────────────────────────────────────────────┐
       │       Centralized GPU cluster      │                        │             WeightHost mesh                 │
       │                                    │                        │                                             │
       │   ┌────────────────────────────┐   │                        │    WH-A             WH-B            WH-C    │
       │   │  ALL 70B weights, hot      │   │                        │   ┌────┐           ┌────┐          ┌────┐    │
       │   │  in GPU memory             │   │                        │   │L0─ │ ─────►    │L16 │ ─────►   │L32 │    │
       │   │  $$$ to keep warm          │   │                        │   │L15 │           │L31 │          │L47 │    │
       │   └────────────────────────────┘   │                        │   └────┘           └────┘          └────┘    │
       │             ▲                      │                        │      ▲                                       │
       │             │ every query          │                        │      │                                       │
       └─────────────┼──────────────────────┘                        │      │ pipeline routes the query through     │
                     │                                               │      │ whichever hosts hold the right shards │
       ┌─────────────┴─────────────┐                                 │      │                                       │
       │   request bottleneck      │                                 │      │  add WH-D, WH-E, … capacity grows;    │
       │   weights are scarce      │                                 │      │  any single host can be cheap (Pi5,   │
       │   only one provider       │                                 │      │  laptop GPU, edge node, cloud API).   │
       └───────────────────────────┘                                 │      │  No single host serves the model      │
                                                                     │      │  alone. The mesh does.                │
                                                                     │      │                                       │
                                                                     │  ── queries ──►                              │
                                                                     │                                              │
                                                                     │  Conductor routes a Q to the pipeline of     │
                                                                     │  hosts that already hold the relevant        │
                                                                     │  weights warm; locality + reputation +       │
                                                                     │  latency decide the path.                    │
                                                                     │                                              │
                                                                     └─────────────────────────────────────────────┘
```

**The single sentence.** A 70B model on one machine is a monopoly. A 70B model
sharded across thirty machines is a *protocol*. The price of inference stops
being "how much GPU can you afford" and becomes "how well does your mesh
route."

---

## What's a WeightHost? What's a WeightNode?

The two terms describe the same entity from different angles. There is one
dataclass underneath (`maestro/shard_registry.py:37`), but two framings:

```
            WeightHost                                       WeightNode
            ──────────                                       ──────────
   "the registered persistent           same entity         "the operational inference
    substrate"                       ─────────────►         endpoint, right now, in this
                                                            pipeline, serving this query"

      Fields on the dataclass:                        Implicit at routing time:
        - node_id                                       - which pipeline am I in?
        - shards: [ShardDescriptor]                     - which layers do I serve this hop?
        - capabilities: [str]                           - what's my latency to the next hop?
        - domain_affinity: [str]                        - am I warm?
        - hardware_class                                - is my reputation above probation?
        - reputation_score                              - which Cartridges do I carry pre-loaded?

      WeightHost is what the registry             WeightNode is what the Conductor talks to
      stores. WeightNode is what the              when it builds a pipeline. Same registration,
      Conductor uses.                             different framing.
```

If you find yourself confused: the docs use **WeightHost** as the canonical
noun for the dataclass and the registry contents; they use **WeightNode** when
the operational, in-pipeline role is the point. They refer to the same physical
machine.

---

## Adding Nodes Increases Capacity, Not Strain

This is the most counter-intuitive property of the design, so it gets its own
diagram. The conventional intuition — more nodes = more coordination overhead
= worse — applies to systems where every node must know every other node.
**WeightHost federation is not that kind of system.**

```
   ADDING A NODE TO A CONVENTIONAL CLUSTER             ADDING A NODE TO THE WEIGHTHOST MESH
   ─────────────────────────────────────                ─────────────────────────────────────

   Before:                                              Before:
       3 GPU hosts × hot 70B weights                       3 WeightHosts × layer ranges {0-15, 16-31, 32-47}
       = 3× memory cost                                    = pipeline capacity: 1×
       = 3× redundancy                                     = covered range: layers 0-47 of one model
       = 1× capacity (one model)
                                                         After adding WH-D (layers 32-47, second machine
   After adding GPU host #4:                            holding the SAME range):
       4 GPU hosts × hot 70B weights                       4 WeightHosts × covering {0-15, 16-31, 32-47×2}
       = 4× memory cost                                    = pipeline capacity: 2× for layers 32-47
       = 4× redundancy (some)                              = redundancy on the busiest range
       = 1× capacity (still one model;                     = covered range: same (layers 0-47)
         everyone holds the same weights)                  = MAGI can fail one over without dropping
                                                             throughput
   Coordination cost: low (single load balancer)
   Marginal capacity per node added: capacity ÷ N      Coordination cost: low (registry advertises;
   Failure of one node: 1/N degradation                  the Conductor reads)
                                                       Marginal capacity per node added: ADDITIVE
                                                         on whatever layer range the new node holds
                                                       Failure of one node: pipeline reroutes through
                                                         the redundancy map; the mesh stays up.

                                                       After adding WH-E (layers 48-63 of model B):
                                                           5 WeightHosts × covering {layers 0-47 of A,
                                                                                      layers 48-63 of B}
                                                           = the mesh now serves TWO models
                                                           = no host had to load anything new; WH-E
                                                             simply brought new layers along

       MARGINAL ADDED CAPACITY                             MARGINAL ADDED CAPACITY
       per new host:                                       per new host:
                                                              + redundancy on existing shards
                  ──┐                                     OR
                  ↓ │                                       + coverage of a new shard
                    │                                     OR
              ┌─────┘                                       + capacity for a new model entirely
              │
       (linear; capacity is fixed                          (additive AND compositional; each new
        regardless of N)                                    host brings its specific layers along)
```

**Why this works.** Conventional GPU clusters scale by replicating the same
hot weights across more hosts. Adding a host buys you redundancy, not new
capability. WeightHost federation scales by **sharding** — each new host
brings *its specific layer range* along, and the registry composes hosts into
pipelines that together cover whichever model the query needs.

Every node is a new ingredient in the mesh's recipe book, not a duplicate
copy of the chef.

---

## Why This Beats Dynamically Loading Weights into RAM

A natural alternative: keep weights on disk, load them into GPU/RAM
on-demand per query. Spotify-for-models. This idea sounds attractive
until you do the math.

```
                            DYNAMIC LOAD                          PERSISTENT WEIGHTHOSTS
                            ────────────                          ──────────────────────

      Per-query timing:        ms                                       ms
                          ┌─────────┐                              ┌─────────┐
                          │ network │ ←  fetch shard from S3        │ network │ ←  query → pipeline
                          │  3000+  │                               │  10-100 │
                          ├─────────┤                               ├─────────┤
                          │  load   │ ←  PCIe transfer, GPU place   │  warm   │ ←  weights already
                          │  2000+  │                               │  hit    │     hot in memory
                          ├─────────┤                               │   ~0    │
                          │ infer   │                               ├─────────┤
                          │   ~200  │                               │ infer   │
                          ├─────────┤                               │   ~200  │
                          │ release │ ←  if memory pressure         └─────────┘
                          │   ~50   │
                          └─────────┘
                          ≈ 5000+ ms per query                     ≈ 200-300 ms per query

      Cost structure:
        - cold-start tax on EVERY query                              - cold-start tax once
                                                                       (at host startup or first
        - PCIe / network is the bottleneck                             query); steady-state is
          ALWAYS                                                       network + inference only
        - GPU memory is "rented" briefly so you                      - GPU memory is "owned"
          burn cycles on swapping rather than                          by the host; cycles go
          on inference                                                 to inference
        - your hot path crosses two storage tiers                    - hot path is one tier
          (disk → memory)                                              (GPU memory)
        - thrashing under concurrent load: every                     - the warmth signal in the
          new query competes for memory bandwidth                      capability manifest tells
          with the previous one's load                                 the Conductor which hosts
                                                                       to prefer; cold hosts get
                                                                       fewer queries by design

      Energy:
        - load + release + load + release …                          - amortized: load once,
        - the GPU is hot but mostly busy moving                        serve many queries; the
          bytes, not computing                                         GPU is hot AND useful

      Scaling story:
        - bottlenecked by storage I/O bandwidth                      - bottlenecked by the slowest
        - adding more GPUs doesn't help if the                         WeightHost in your pipeline,
          shared backing store is saturated                            which is fixable by adding
                                                                       a faster replica there

      The "elastic" promise:
        - load any model on any host on demand!                      - hosts advertise what they
          (in practice: 5+ second cold starts                         hold; the mesh composes
          per model swap)                                            them per-query (instantaneous
                                                                       routing on warm hosts)
```

**The fundamental error of the dynamic-load model.** It treats weights as if
they were cache content — fetch on demand, evict when memory's tight. But
weights aren't cache content; they're the *machine itself*. You don't fetch a
CPU's instruction decoder on demand. You wire it in once and run it forever.

A WeightHost is a machine wired for the layers it holds. Adding a host is
adding a machine to the cluster. Removing a host is taking one away. Loading
weights dynamically is a permanent compromise on every query, and the
arithmetic shows it: a 5-second cold start on every request is a 25× latency
penalty compared to a warm pipeline, paid forever.

---

## The Routing Loop, with Locality

This is the actual decision logic at the registry level. The Conductor calls
`route_query(model_id, query_domains)`; the registry returns an ordered
pipeline of hosts.

```
                    ┌──────────────────────────────────────────────────────┐
                    │  query Q                                             │
                    │  (text, embedding, derived query_domains)            │
                    └──────────────────┬───────────────────────────────────┘
                                       │
                                       ▼
        ┌──────────────────────────────────────────────────────────────────┐
        │  WeightHostRegistry.route_query(model_id, query_domains)         │
        │                                                                  │
        │   For each host that holds a shard of model_id:                  │
        │     score = weight_locality_score(host, query_domains)           │
        │                                                                  │
        │       priority   condition                          score        │
        │       ────────   ─────────                          ─────        │
        │       1          warm  +  matching domain_affinity   1.00        │
        │       2          warm  +  any domain_affinity        0.75        │
        │       3          cold  +  matching domain_affinity   0.50        │
        │       4          cold  +  any domain_affinity        0.25        │
        │                                                                  │
        │   Greedy pipeline construction:                                  │
        │     - sort candidates by (start_layer, -locality, -reputation,   │
        │                            -latency)                             │
        │     - walk forward; at each step pick the candidate that         │
        │       covers the current layer and extends furthest, weighted    │
        │       by locality + reputation + latency                         │
        │     - bail if a layer range has no live coverage                 │
        └─────────────────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                       pipeline = [ WH-A(0-15), WH-D(16-31), WH-C(32-47) ]
                                              │
                                              │ queries flow:
                                              ▼
                       ┌──────┐   activations   ┌──────┐   activations   ┌──────┐
                       │ WH-A │ ─────────────►  │ WH-D │ ─────────────►  │ WH-C │
                       │ L0-  │                 │ L16- │                 │ L32- │
                       │ L15  │                 │ L31  │                 │ L47  │
                       └──────┘                 └──────┘                 └──────┘
                          ▲
                          │
                          │ on host failure mid-pipeline:
                          │
                          │   - the redundancy map already lists WH-A'(0-15)
                          │   - the Conductor reroutes the failed shard's hop
                          │   - the rest of the pipeline keeps its state
                          │   - StorageProofEngine kicks the failed host into
                          │     probation
                          │
                          ▼
```

The point of the locality score isn't to maximize cache hits abstractly —
it's to **prefer hosts whose weights are warm AND whose declared domain
matches the query**, because those two together mean the next token comes out
fast and from a host that's good at this kind of query.

---

## What MAGI Sees (the closing-the-loop view)

The mesh isn't fire-and-forget; MAGI observes the R2 ledger and writes
recommendations that affect future routing. Compressing the long-term view:

```
   ┌─────────────────────────────────────────────────────────────────────────┐
   │                                                                         │
   │           sessions across time, scored by R2                            │
   │   ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ── ──     │
   │                                                                         │
   │   for each WeightHost:                                                  │
   │       reputation drifts                                                 │
   │       domain_affinity learns (was it actually good at "law"?)           │
   │       warmth pattern emerges                                            │
   │                                                                         │
   │   MAGI reads the ledger:                                                │
   │       - WH-D has gone cold for 48 hours -> deprioritize routing         │
   │       - WH-A consistently in majority on "code" -> raise its            │
   │         domain_affinity weight                                          │
   │       - pipeline {WH-A, WH-D, WH-C} reports silent_collapse → 5         │
   │         times -> route through redundant {WH-A, WH-D', WH-C'}           │
   │       - WH-E reputation dropped to 0.4 -> probation, then evict         │
   │                                                                         │
   │   These recommendations don't reshape the architecture; they tune       │
   │   the routing function. The mesh stays the mesh.                        │
   │                                                                         │
   └─────────────────────────────────────────────────────────────────────────┘
```

---

## The Insight, Compressed

| Property of conventional inference | Property of federated WeightHost mesh |
|---|---|
| Weights are large and immovable | Weights are large and immovable |
| Queries are small and routable | Queries are small and routable |
| Therefore: load weights into ONE place; route queries to that place | Therefore: pin weights to MANY places; route queries to wherever the weights already are |
| Adding hosts = duplicating one machine | Adding hosts = adding new machines (different layer ranges) |
| Capacity is bottlenecked by GPU memory | Capacity is bottlenecked by *aggregate* mesh memory |
| Cost scales with the largest possible model | Cost scales with each host's portion of each model |
| Failure of "the cluster" = total outage | Failure of one host = pipeline reroutes |
| Edge devices can't participate | A Raspberry Pi 5 holding layers 0-15 is a legitimate WeightHost |

The thesis isn't "distributed is good." It's:

> **A model's weights are large, static, and expensive to move. A query is
> small, dynamic, and cheap to route. The engineering conclusion is obvious
> once stated.**

Maestro is the control plane that makes that obvious conclusion mechanically
real.

---

## See Also

- [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md) — the prose thesis
- [`../../ROADMAP.md`](../../ROADMAP.md) — the staged delivery, including
  the MaestrOS substrate
- [`../storage-network.md`](../storage-network.md) — proof-of-storage and
  reputation
- [`../../maestro/shard_registry.py`](../../maestro/shard_registry.py) — the
  `WeightHost` dataclass and routing implementation
- [`context-tiers.md`](./context-tiers.md) — how Cartridges, Whirlpool, and
  Weight priors sit *on top of* the WeightHost mesh
