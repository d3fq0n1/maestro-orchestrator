# Deliberation Engine — Maestro-Orchestrator v0.7.1

The Deliberation Engine upgrades the default parallel-collect pattern into an
actual multi-round debate. After all agents return their initial answers, each
agent receives a structured prompt that includes the original question, its own
previous reply, and every peer agent's previous reply — then produces a refined
answer before any analysis runs.

---

## Why deliberation?

In the original pipeline every agent responded independently. Their answers were
compared after the fact via dissent analysis and semantic quorum. Two problems
with that model:

1. **No cross-pollination** — an agent couldn't incorporate a valid point raised
   by a peer model.
2. **Agreement might be shallow** — models could converge without ever having to
   defend or revise their reasoning.

Deliberation solves both. An agent that sees a compelling argument from a peer
can revise. An agent that disagrees can say so explicitly. The downstream
analysis then operates on considered, post-debate positions rather than isolated
first-take answers.

---

## Pipeline position

```
Initial agent responses (parallel)
        │
        ▼
Deliberation Engine  ◄── default on, 1 round
  ├─ Each agent reads all peer responses
  └─ Each agent produces a refined reply
        │
        ▼  (deliberated responses replace initial for all below)
Dissent analysis
NCG drift detection
Semantic quorum aggregation
R2 scoring
```

---

## Configuration

### API (both `/api/ask` and `/api/ask/stream`)

```json
{
  "prompt": "Your question",
  "deliberation_enabled": true,
  "deliberation_rounds": 1
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `deliberation_enabled` | `bool` | `true` | Enable/disable deliberation. Omit to keep the default (on). |
| `deliberation_rounds` | `int` | `1` | Number of deliberation rounds (1–5). Each round costs one additional API call per participating agent. |

Both fields are **optional**. Existing integrations that don't send them will
automatically get `deliberation_enabled=true, deliberation_rounds=1`.

To disable deliberation explicitly:

```json
{ "prompt": "...", "deliberation_enabled": false }
```

### Python API

All orchestration entry points accept the same parameters:

```python
# Async (core engine)
result = await run_orchestration_async(
    prompt=prompt,
    deliberation_enabled=True,   # default
    deliberation_rounds=1,        # default
)

# Sync wrapper
result = run_orchestration(
    prompt,
    deliberation_enabled=True,
    deliberation_rounds=1,
)

# Foundry wrappers (backend/orchestrator_foundry.py)
result = await run_orchestration(prompt, deliberation_enabled=True)
async for event in stream_orchestration(prompt, deliberation_rounds=2):
    ...
```

---

## How the deliberation prompt is constructed

For each agent, the engine builds:

```
ORIGINAL QUESTION:
<user prompt>

YOUR PREVIOUS RESPONSE (<model/vendor name>):
<agent's own answer from the previous round>

RESPONSES FROM OTHER MODELS IN THE COUNCIL:
[<peer model name>]
<peer response>

[<peer model name>]
<peer response>

---
You are now in deliberation. Review what the other models said. Consider
whether they raise valid points you missed, whether you disagree with their
reasoning, or whether a synthesis is warranted. Provide your refined answer
to the original question. Be direct: affirm your position, refine it, or
challenge the peers. Do not simply summarise what others said.
```

Peer agents are identified by their model/vendor display names (e.g.
`GPT-4o`, `Claude Sonnet 4.6`), not internal class names. Only clean
(non-error) peer responses are included — failed agents don't inject noise.

---

## Multi-round deliberation

Setting `deliberation_rounds=2` (or higher) runs the deliberation loop
multiple times. Each round uses the previous round's outputs as input.

```
Round 0: initial responses
Round 1: each agent reads round-0 peer responses → produces round-1 reply
Round 2: each agent reads round-1 peer responses → produces round-2 reply
...
final_responses = last round's outputs
```

**Cost:** `rounds × len(clean_agents)` additional API calls per orchestration
request. One round is sufficient for most use cases.

---

## API response format

Both the batch (`/api/ask`) response and the streaming `done` event include a
`deliberation` field:

```json
{
  "deliberation": {
    "enabled": true,
    "rounds_requested": 1,
    "rounds_completed": 1,
    "agents_participated": ["GPT-4o", "Claude Sonnet 4.6", "Gemini 2.5 Flash", "Llama 3.3 70B"],
    "skipped": false,
    "skip_reason": null
  }
}
```

`skipped` is `true` when fewer than 2 healthy agents were available (the engine
requires at least 2 peers to deliberate). `skip_reason` explains why.

---

## Streaming SSE events

The streaming endpoint (`/api/ask/stream`) emits three new events during the
deliberation stage:

### `deliberation_start`

Emitted immediately before the first deliberation round begins.

```json
{
  "rounds_requested": 1,
  "agents": ["GPT-4o", "Claude Sonnet 4.6", "Gemini 2.5 Flash", "Llama 3.3 70B"]
}
```

### `deliberation_round`

Emitted after each round completes. Contains every participating agent's
deliberated response for that round.

```json
{
  "round_number": 1,
  "responses": {
    "GPT-4o": "Having reviewed Claude's point about X, I'd refine my answer...",
    "Claude Sonnet 4.6": "GPT-4o raises a valid concern, however...",
    "Gemini 2.5 Flash": "I agree with GPT-4o on X but disagree on Y because...",
    "Llama 3.3 70B": "The council is converging around X, which I affirm..."
  }
}
```

### `deliberation_done`

Emitted once all rounds are complete.

```json
{
  "enabled": true,
  "rounds_requested": 1,
  "rounds_completed": 1,
  "agents_participated": ["GPT-4o", "Claude Sonnet 4.6", "Gemini 2.5 Flash", "Llama 3.3 70B"],
  "skipped": false,
  "skip_reason": null
}
```

The `stage` event `{"name": "deliberation", "status": "running"}` is also
emitted at the start of the deliberation phase.

---

## Error handling

- If an agent raises an exception during a deliberation round, that agent keeps
  its response from the previous round. The exception is logged and the pipeline
  continues.
- If fewer than 2 healthy agents are available, deliberation is skipped
  (`skipped: true` in the response). Initial responses are used as-is.
- If `DeliberationEngine.run()` itself raises an unexpected error, the
  orchestrator catches it, logs it, and falls back to the initial responses.
  Deliberation failures are **never** fatal.

---

## Module reference (`maestro/deliberation.py`)

| Class / Function | Description |
|-----------------|-------------|
| `DeliberationEngine(rounds)` | Main engine. Call `await engine.run(prompt, agents, initial_responses)`. |
| `DeliberationEngine.run()` | Executes all deliberation rounds. Returns `DeliberationReport`. |
| `DeliberationReport` | Dataclass: `rounds_requested`, `rounds_completed`, `history`, `final_responses`, `agents_participated`, `skipped`, `skip_reason`. |
| `DeliberationRound` | Dataclass: `round_number`, `responses` (`{agent_name: response_str}`). |
| `_build_deliberation_prompt()` | Constructs the per-agent deliberation prompt from context. |
