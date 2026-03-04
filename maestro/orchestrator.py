import asyncio
import re

from maestro.agents.mock import MockAgent
from maestro.aggregator import aggregate_responses
from maestro.dissent import DissentAnalyzer
from maestro.ncg import MockHeadlessGenerator, DriftDetector
from maestro.r2 import R2Engine
from maestro.session import SessionLogger, build_session_record


# Patterns that indicate an agent returned an error instead of real content.
# These match the error-string conventions used by all agent implementations.
_ERROR_PATTERN = re.compile(
    r"^\[.+?\] (?:HTTP \d{3}|Timeout|Connection failed|Failed|API Key Missing|Malformed response|Content filtered.*)"
)


def _is_agent_error(response: str) -> bool:
    """Return True if the response string is an agent error sentinel."""
    return bool(_ERROR_PATTERN.match(response))


def _classify_agent_error(agent_name: str, response: str) -> dict:
    """Return a structured error dict for a failed agent response."""
    code_match = re.search(r"HTTP (\d{3})", response)
    if code_match:
        code = int(code_match.group(1))
        return {"agent": agent_name, "code": code, "kind": _http_error_kind(code), "raw": response}
    if "Timeout" in response:
        return {"agent": agent_name, "code": None, "kind": "timeout", "raw": response}
    if "Connection failed" in response:
        return {"agent": agent_name, "code": None, "kind": "connection", "raw": response}
    if "API Key Missing" in response:
        return {"agent": agent_name, "code": None, "kind": "auth", "raw": response}
    if "Content filtered" in response:
        return {"agent": agent_name, "code": None, "kind": "filtered", "raw": response}
    return {"agent": agent_name, "code": None, "kind": "unknown", "raw": response}


def _http_error_kind(code: int) -> str:
    if code == 401 or code == 403:
        return "auth"
    if code == 404:
        return "not_found"
    if code == 429:
        return "rate_limit"
    if 500 <= code < 600:
        return "server"
    return "http"


async def run_orchestration_async(
    prompt: str,
    agents: list = None,
    ncg_enabled: bool = True,
    session_logging: bool = True,
    headless_generator=None,
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

    Args:
        prompt: The user's prompt to orchestrate.
        agents: List of Agent instances. Defaults to mock agents for testing.
        ncg_enabled: Whether to run the NCG headless baseline track.
        session_logging: Whether to persist the session record.
        headless_generator: HeadlessGenerator instance for NCG. When None,
            falls back to MockHeadlessGenerator.

    Error handling:
        - return_exceptions=True on asyncio.gather ensures a single agent
          raising an unhandled exception does not abort the entire pipeline.
          The exception is caught here and converted to an error-string
          response so the analysis pipeline continues with the remaining
          agents' outputs.
        - NCG failures fall back to MockHeadlessGenerator output so the
          drift/collapse track always produces a result.
        - Session persistence failures are logged but do not raise — a
          write error should never fail the user-facing response.
        - R2 indexing failures are logged but non-fatal for the same reason.
    """
    if agents is None:
        agents = [
            MockAgent(name="MockAgent2", response_style="empathic"),
            MockAgent(name="MockAgent3", response_style="historical"),
        ]

    # --- Conversational track ---
    # return_exceptions=True prevents a single agent failure from aborting
    # the gather — each exception is returned as a value and converted to
    # an error-string response so the pipeline continues.
    results = await asyncio.gather(
        *(agent.fetch(prompt) for agent in agents),
        return_exceptions=True,
    )

    named_responses = {}
    agent_errors = []
    for agent, response in zip(agents, results):
        if isinstance(response, BaseException):
            error_msg = f"[{agent.name}] Unhandled exception: {type(response).__name__}: {response}"
            print(error_msg)
            error_resp = f"[{agent.name}] Failed"
            named_responses[agent.name] = error_resp
            agent_errors.append(_classify_agent_error(agent.name, error_resp))
        else:
            print(f"{agent.name} responded: {response}")
            named_responses[agent.name] = response
            if _is_agent_error(response):
                agent_errors.append(_classify_agent_error(agent.name, response))

    # Separate clean (non-error) responses for metrics so errored agents
    # don't pollute dissent analysis, NCG drift, or aggregation scores.
    clean_responses = {
        name: resp for name, resp in named_responses.items()
        if not _is_agent_error(resp)
    }
    responses = list(clean_responses.values()) if clean_responses else list(named_responses.values())

    # --- Dissent analysis (internal agreement between agents) ---
    # Only feed clean responses so error strings don't skew agreement scores.
    dissent_analyzer = DissentAnalyzer()
    dissent_input = clean_responses if clean_responses else named_responses
    dissent_report = dissent_analyzer.analyze(prompt, dissent_input)
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
        try:
            generator = headless_generator or MockHeadlessGenerator()
            ncg_output = generator.generate(prompt)
            print(f"NCG ({generator.model_id}) generated baseline content.")

            detector = DriftDetector()
            ncg_drift_report = detector.analyze(
                prompt=prompt,
                ncg_output=ncg_output,
                conversational_outputs=clean_responses if clean_responses else named_responses,
                internal_agreement=dissent_report.internal_agreement,
            )

            if ncg_drift_report.silent_collapse_detected:
                print("WARNING: Silent collapse detected -- agents agree but "
                      "drift from headless baseline.")
            print(f"Mean drift from NCG baseline: "
                  f"{ncg_drift_report.mean_semantic_distance}")
        except Exception as e:
            print(f"[NCG Error] {type(e).__name__}: {e} -- skipping NCG track")
            ncg_drift_report = None

    # --- Aggregation (now with dissent and NCG data) ---
    print("\nAggregating responses...")
    final_output = aggregate_responses(responses, ncg_drift_report, dissent_report)

    # --- Session persistence ---
    session_id = None
    if session_logging:
        try:
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
        except Exception as e:
            print(f"[Session Logger Error] {type(e).__name__}: {e} -- session not persisted")

    # --- R2 Engine (score, signal, index) ---
    try:
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
    except Exception as e:
        print(f"[R2 Engine Error] {type(e).__name__}: {e} -- R2 data unavailable for this session")
        final_output["r2"] = None

    return {
        "responses": responses,
        "named_responses": named_responses,
        "agent_errors": agent_errors,
        "final_output": final_output,
        "session_id": session_id,
    }


def run_orchestration(prompt: str, ncg_enabled: bool = True, session_logging: bool = True) -> dict:
    """Synchronous wrapper for backward compatibility with tests and CLI."""
    return asyncio.run(run_orchestration_async(
        prompt, ncg_enabled=ncg_enabled, session_logging=session_logging,
    ))
