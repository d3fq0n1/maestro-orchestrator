import asyncio

from maestro.agents.mock import MockAgent
from maestro.aggregator import aggregate_responses
from maestro.dissent import DissentAnalyzer
from maestro.ncg import MockHeadlessGenerator, DriftDetector
from maestro.r2 import R2Engine
from maestro.session import SessionLogger, build_session_record


async def run_orchestration_async(
    prompt: str,
    agents: list = None,
    ncg_enabled: bool = True,
    session_logging: bool = True,
) -> dict:
    """
    Orchestrates multiple agents, aggregates responses, and runs the
    full analysis pipeline.

    Pipeline after the conversational track:
      1. Dissent analysis -- measures internal agreement between agents
      2. NCG track -- headless baseline for drift/collapse detection
      3. Aggregation -- synthesizes responses with dissent and NCG data
      4. R2 Engine -- scores the session, detects improvement signals,
         and indexes the consensus node into the ledger

    The dissent analyzer produces an internal_agreement score that feeds
    into NCG's silent collapse detector. R2 then synthesizes all signals
    into a quality grade and structured improvement recommendations that
    MAGI will consume for the rapid recursion loop.
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

    # --- Dissent analysis (internal agreement between agents) ---
    dissent_analyzer = DissentAnalyzer()
    dissent_report = dissent_analyzer.analyze(prompt, named_responses)
    print(f"\nDissent level: {dissent_report.dissent_level} "
          f"(agreement: {dissent_report.internal_agreement})")
    if dissent_report.outlier_agents:
        print(f"Outlier agents: {', '.join(dissent_report.outlier_agents)}")

    # --- NCG track (parallel diversity benchmark) ---
    # Now feeds internal_agreement from dissent analysis into the drift
    # detector so it can detect silent collapse.
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
            internal_agreement=dissent_report.internal_agreement,
        )

        if ncg_drift_report.silent_collapse_detected:
            print("WARNING: Silent collapse detected -- agents agree but "
                  "drift from headless baseline.")
        print(f"Mean drift from NCG baseline: "
              f"{ncg_drift_report.mean_semantic_distance}")

    # --- Aggregation (now with dissent and NCG data) ---
    print("\nAggregating responses...")
    final_output = aggregate_responses(responses, ncg_drift_report, dissent_report)

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

    # --- R2 Engine (score, signal, index) ---
    r2 = R2Engine()
    r2_score = r2.score_session(
        dissent_report=dissent_report,
        drift_report=ncg_drift_report,
        quorum_confidence=final_output.get("confidence", "Low"),
    )
    r2_signals = r2.detect_signals(r2_score, dissent_report, ncg_drift_report)
    r2_entry = r2.index(
        session_id=session_id,
        prompt=prompt,
        consensus=final_output.get("consensus", ""),
        agents_agreed=[a.name for a in agents],
        score=r2_score,
        improvement_signals=r2_signals,
        dissent_report=dissent_report,
        drift_report=ncg_drift_report,
    )

    print(f"R2 grade: {r2_score.grade} (confidence: {r2_score.confidence_score})")
    if r2_score.flags:
        for flag in r2_score.flags:
            print(f"  R2 flag: {flag}")
    if r2_signals:
        print(f"  R2 signals: {len(r2_signals)} improvement recommendation(s)")

    # Attach R2 summary to final output
    final_output["r2"] = {
        "grade": r2_score.grade,
        "confidence_score": r2_score.confidence_score,
        "flags": r2_score.flags,
        "signal_count": len(r2_signals),
        "entry_id": r2_entry.entry_id,
    }

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
