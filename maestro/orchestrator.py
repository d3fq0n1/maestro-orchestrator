import asyncio

from maestro.agents.mock import MockAgent
from maestro.aggregator import aggregate_responses
from maestro.ncg import MockHeadlessGenerator, DriftDetector
from maestro.session import SessionLogger, build_session_record


async def run_orchestration_async(
    prompt: str,
    agents: list = None,
    ncg_enabled: bool = True,
    session_logging: bool = True,
) -> dict:
    """
    Orchestrates multiple agents, aggregates responses, and runs the NCG
    diversity benchmark when enabled.

    Two parallel tracks:
      1. Conversational track -- agents respond with their personality/framing
      2. NCG track -- headless generator produces unframed baseline content

    The drift detector compares the two tracks to catch silent collapse:
    when all conversational agents agree but have drifted from what an
    unconstrained model would produce.

    When session_logging is True, the full session is persisted to disk
    for later analysis by dissent analysis and R2.
    """
    if agents is None:
        agents = [
            MockAgent(name="MockAgent2", response_style="empathic"),
            MockAgent(name="MockAgent3", response_style="historical"),
        ]

    # --- Conversational track ---
    results = await asyncio.gather(*(agent.fetch(prompt) for agent in agents))

    named_responses = {}
    for agent, response in zip(agents, results):
        print(f"{agent.name} responded: {response}")
        named_responses[agent.name] = response

    responses = list(named_responses.values())

    # --- NCG track (parallel diversity benchmark) ---
    ncg_drift_report = None
    if ncg_enabled:
        print("\nRunning NCG headless baseline...")
        generator = MockHeadlessGenerator()
        ncg_output = generator.generate(prompt)
        print(f"NCG ({generator.model_id}) generated baseline content.")

        detector = DriftDetector()
        ncg_drift_report = detector.analyze(
            prompt=prompt,
            ncg_output=ncg_output,
            conversational_outputs=named_responses,
        )

        if ncg_drift_report.silent_collapse_detected:
            print("WARNING: Silent collapse detected -- agents agree but "
                  "drift from headless baseline.")
        print(f"Mean drift from NCG baseline: "
              f"{ncg_drift_report.mean_semantic_distance}")

    # --- Aggregation (now with NCG benchmark data) ---
    print("\nAggregating responses...")
    final_output = aggregate_responses(responses, ncg_drift_report)

    # --- Session persistence ---
    session_id = None
    if session_logging:
        logger = SessionLogger()
        record = build_session_record(
            prompt=prompt,
            agent_responses=named_responses,
            final_output=final_output,
            ncg_enabled=ncg_enabled,
            agents_used=[a.name for a in agents],
        )
        logger.save(record)
        session_id = record.session_id
        print(f"Session logged: {session_id}")

    return {
        "responses": responses,
        "final_output": final_output,
        "session_id": session_id,
    }


def run_orchestration(prompt: str, ncg_enabled: bool = True, session_logging: bool = True) -> dict:
    """Synchronous wrapper for backward compatibility with tests and CLI."""
    return asyncio.run(run_orchestration_async(
        prompt, ncg_enabled=ncg_enabled, session_logging=session_logging,
    ))
