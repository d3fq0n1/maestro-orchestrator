
from maestro.agents.agent_mock import MockAgent2, MockAgent3
from maestro.aggregator import aggregate_responses
from maestro.ncg import MockHeadlessGenerator, DriftDetector


def run_orchestration(prompt: str, ncg_enabled: bool = True) -> dict:
    """
    Orchestrates multiple agents, aggregates responses, and runs the NCG
    diversity benchmark when enabled.

    Two parallel tracks:
      1. Conversational track — agents respond with their personality/framing
      2. NCG track — headless generator produces unframed baseline content

    The drift detector compares the two tracks to catch silent collapse:
    when all conversational agents agree but have drifted from what an
    unconstrained model would produce.
    """
    agents = {
        "MockAgent2": MockAgent2(),     # Mock with opinionated reasoning
        "MockAgent3": MockAgent3(),     # Mock with historical framing
    }

    # --- Conversational track ---
    responses = []
    named_responses = {}
    for name, agent in agents.items():
        print(f"Querying {name}...")
        response = agent.respond(prompt)
        print(f"{name} responded: {response}")
        responses.append(response)
        named_responses[name] = response

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
            print("WARNING: Silent collapse detected — agents agree but "
                  "drift from headless baseline.")
        print(f"Mean drift from NCG baseline: "
              f"{ncg_drift_report.mean_semantic_distance}")

    # --- Aggregation (now with NCG benchmark data) ---
    print("\nAggregating responses...")
    final_output = aggregate_responses(responses, ncg_drift_report)

    return {
        "responses": responses,
        "final_output": final_output,
    }
