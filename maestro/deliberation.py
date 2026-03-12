"""
Deliberation Engine — Maestro-Orchestrator v7.1.6

After collecting initial responses from all agents, the deliberation engine
feeds each agent's response back into the pool so every agent can read what
its peers said and produce a refined, informed reply.  This turns the default
parallel-collect pattern into an actual multi-round debate.

Pipeline position:
    Initial agent responses
        └─► Deliberation (rounds 1..N, default enabled)
                └─► Deliberated responses feed into dissent, NCG, aggregation

Each deliberation round constructs a per-agent prompt that contains:
  - The original user question
  - The agent's own previous reply
  - Every peer agent's previous reply (by model/vendor name)

The agent is then asked to affirm, refine, or challenge its position in light
of what its peers said.  Only clean (non-error) peer responses are included
so failed agents don't inject noise into the deliberation context.

Usage
-----
    from maestro.deliberation import DeliberationEngine

    engine = DeliberationEngine(rounds=1)
    report = await engine.run(
        prompt=user_prompt,
        agents=agent_list,
        initial_responses=named_responses,   # {agent.name: response_str}
    )
    # report.final_responses replaces named_responses for downstream analysis
    # report.history contains every round's responses

The engine is non-fatal: if any agent raises during deliberation, that agent
keeps its previous-round response and the pipeline continues.
"""

import asyncio
import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Error-sentinel detection (mirrors the pattern in maestro/orchestrator.py
# but defined locally to avoid a circular import)
# ---------------------------------------------------------------------------
_ERROR_PATTERN = re.compile(
    r"^\[.+?\] (?:HTTP \d{3}|Timeout|Connection failed|Failed|API Key Missing"
    r"|Malformed response|Content filtered.*)"
)


def _is_agent_error(response: str) -> bool:
    """Return True if the response string is an agent error sentinel."""
    return bool(_ERROR_PATTERN.match(response))


@dataclass
class DeliberationRound:
    """One round of deliberation — initial or subsequent."""

    round_number: int
    # agent model/vendor name → response text
    responses: dict = field(default_factory=dict)


@dataclass
class DeliberationReport:
    """Full record of the deliberation process for a single orchestration run."""

    rounds_requested: int
    rounds_completed: int
    # Round 0 = initial responses, rounds 1..N = deliberation
    history: list = field(default_factory=list)
    # The final responses to use for downstream analysis (last round)
    final_responses: dict = field(default_factory=dict)
    # Agents that participated in at least one deliberation round
    agents_participated: list = field(default_factory=list)
    # Whether deliberation was skipped (e.g. only one clean agent)
    skipped: bool = False
    skip_reason: str = ""


def _build_deliberation_prompt(
    original_prompt: str,
    agent_name: str,
    own_response: str,
    peer_responses: dict,
    round_number: int,
) -> str:
    """
    Construct the prompt that asks an agent to deliberate on its peers' replies.

    Parameters
    ----------
    original_prompt:  The user's original question.
    agent_name:       This agent's display name (model/vendor name).
    own_response:     This agent's response from the previous round.
    peer_responses:   {peer_name: peer_response} for every *other* agent
                      that returned a clean (non-error) response.
    round_number:     The deliberation round being constructed (1-indexed).
    """
    peer_block_lines = []
    for peer_name, peer_resp in peer_responses.items():
        peer_block_lines.append(f"[{peer_name}]\n{peer_resp}")
    peer_block = "\n\n".join(peer_block_lines)

    round_label = f"Round {round_number} deliberation" if round_number > 1 else "deliberation"

    return (
        f"ORIGINAL QUESTION:\n{original_prompt}\n\n"
        f"YOUR PREVIOUS RESPONSE ({agent_name}):\n{own_response}\n\n"
        f"RESPONSES FROM OTHER MODELS IN THE COUNCIL:\n{peer_block}\n\n"
        f"---\n"
        f"You are now in {round_label}. Review what the other models said. "
        f"Consider whether they raise valid points you missed, whether you "
        f"disagree with their reasoning, or whether a synthesis is warranted. "
        f"Provide your refined answer to the original question. "
        f"Be direct: affirm your position, refine it, or challenge the peers. "
        f"Do not simply summarise what others said."
    )


class DeliberationEngine:
    """
    Runs one or more rounds of cross-agent deliberation.

    Parameters
    ----------
    rounds : int
        Number of deliberation rounds (default 1).  Each round costs one
        additional API call per agent.  Values above 3 are unusual.
    """

    def __init__(self, rounds: int = 1):
        if rounds < 1:
            raise ValueError(f"rounds must be >= 1, got {rounds}")
        self.rounds = rounds

    async def run(
        self,
        prompt: str,
        agents: list,
        initial_responses: dict,
    ) -> DeliberationReport:
        """
        Execute the deliberation loop.

        Parameters
        ----------
        prompt:             The original user prompt.
        agents:             The list of Agent instances in the council.
        initial_responses:  {agent.name: response_str} from the initial fetch.

        Returns
        -------
        DeliberationReport
        """
        # Build a lookup from name → agent instance for quick access
        agent_by_name = {a.name: a for a in agents}

        # Identify clean agents (those that didn't error in the initial round)
        clean_names = [
            name for name, resp in initial_responses.items()
            if not _is_agent_error(resp)
        ]

        report = DeliberationReport(
            rounds_requested=self.rounds,
            rounds_completed=0,
        )

        # Seed history with round 0 (the initial responses)
        report.history.append(
            DeliberationRound(round_number=0, responses=dict(initial_responses))
        )

        if len(clean_names) < 2:
            # Cannot deliberate with fewer than 2 healthy agents
            report.final_responses = dict(initial_responses)
            report.skipped = True
            report.skip_reason = (
                f"Only {len(clean_names)} clean agent(s) available; "
                "deliberation requires at least 2."
            )
            print(f"[Deliberation] Skipped — {report.skip_reason}")
            return report

        # current_responses tracks the latest round's outputs (starts at initial)
        current_responses = dict(initial_responses)

        for round_num in range(1, self.rounds + 1):
            print(f"[Deliberation] Round {round_num}/{self.rounds} — "
                  f"querying {len(clean_names)} agent(s)...")

            round_responses = dict(current_responses)  # copy; update as results arrive

            async def _deliberate_one(name: str) -> tuple[str, str]:
                """Run one agent's deliberation turn; return (name, response)."""
                agent = agent_by_name.get(name)
                if agent is None:
                    return name, current_responses.get(name, "")

                own_resp = current_responses.get(name, "")

                # Peers = all other clean agents from this round
                peers = {
                    n: current_responses[n]
                    for n in clean_names
                    if n != name and not _is_agent_error(current_responses.get(n, ""))
                }

                delib_prompt = _build_deliberation_prompt(
                    original_prompt=prompt,
                    agent_name=name,
                    own_response=own_resp,
                    peer_responses=peers,
                    round_number=round_num,
                )

                try:
                    result = await agent.fetch(delib_prompt)
                    print(f"[Deliberation R{round_num}] {name} responded.")
                    return name, result
                except Exception as exc:
                    print(
                        f"[Deliberation R{round_num}] {name} raised "
                        f"{type(exc).__name__}: {exc} — keeping previous response."
                    )
                    return name, own_resp

            # Run all clean agents concurrently for this round
            tasks = [_deliberate_one(name) for name in clean_names]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for item in results:
                if isinstance(item, BaseException):
                    print(f"[Deliberation R{round_num}] Gather exception: {item}")
                    continue
                name, response = item
                round_responses[name] = response

            report.history.append(
                DeliberationRound(round_number=round_num, responses=dict(round_responses))
            )
            report.rounds_completed += 1
            current_responses = round_responses

        report.final_responses = dict(current_responses)
        report.agents_participated = list(clean_names)
        print(
            f"[Deliberation] Complete — {report.rounds_completed} round(s), "
            f"{len(report.agents_participated)} agent(s) participated."
        )
        return report
