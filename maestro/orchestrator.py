import asyncio
import json
import re
from typing import AsyncGenerator, TYPE_CHECKING

from maestro.agents.mock import MockAgent
from maestro.aggregator import aggregate_responses
from maestro.dissent import DissentAnalyzer
from maestro.ncg import MockHeadlessGenerator, DriftDetector
from maestro.r2 import R2Engine
from maestro.session import SessionLogger, build_session_record

if TYPE_CHECKING:
    from maestro.plugins.manager import ModManager


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
    mod_manager: 'ModManager' = None,
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

    # --- Pre-orchestration hook ---
    if mod_manager:
        hook_ctx = await mod_manager.run_hooks("pre_orchestration", {
            "prompt": prompt, "agents": agents,
        })
        prompt = hook_ctx.get("prompt", prompt)
        agents = hook_ctx.get("agents", agents)

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

    # --- Post-agent-response hooks ---
    if mod_manager:
        for agent, response in zip(agents, results):
            resp_str = named_responses.get(agent.name, "")
            await mod_manager.run_hooks("post_agent_response", {
                "agent_name": agent.name, "response": resp_str, "prompt": prompt,
            })

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

    # --- Pre-aggregation hook ---
    if mod_manager:
        hook_ctx = await mod_manager.run_hooks("pre_aggregation", {
            "responses": responses, "dissent_report": dissent_report,
        })
        responses = hook_ctx.get("responses", responses)

    # --- Aggregation (now with dissent and NCG data) ---
    print("\nAggregating responses...")
    final_output = aggregate_responses(responses, ncg_drift_report, dissent_report)

    # --- Post-aggregation hook ---
    if mod_manager:
        await mod_manager.run_hooks("post_aggregation", {"final_output": final_output})

    # --- Pre-session-save hook ---
    if mod_manager:
        await mod_manager.run_hooks("pre_session_save", {
            "prompt": prompt, "named_responses": named_responses,
            "final_output": final_output,
        })

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

    # --- Post-session-save hook ---
    if mod_manager:
        await mod_manager.run_hooks("post_session_save", {"session_id": session_id})

    # --- Pre-R2-scoring hook ---
    if mod_manager:
        await mod_manager.run_hooks("pre_r2_scoring", {
            "dissent_report": dissent_report, "drift_report": ncg_drift_report,
        })

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
        # --- Post-R2-scoring hook ---
        if mod_manager:
            await mod_manager.run_hooks("post_r2_scoring", {
                "r2_score": final_output["r2"], "r2_signals": r2_signals,
            })
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


def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Events message."""
    payload = json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def run_orchestration_stream(
    prompt: str,
    agents: list = None,
    ncg_enabled: bool = True,
    session_logging: bool = True,
    headless_generator=None,
    mod_manager: 'ModManager' = None,
) -> AsyncGenerator[str, None]:
    """
    Streaming version of run_orchestration_async. Yields SSE events as each
    pipeline stage completes so the frontend can render progressively.

    Events emitted:
        stage       - Pipeline stage update (name + status)
        agents_done - All agent responses collected
        dissent     - Dissent analysis complete
        ncg         - NCG benchmark complete
        consensus   - Aggregation complete (quorum, confidence, consensus text)
        r2          - R2 scoring complete
        done        - Final complete response (same shape as the POST endpoint)
        error       - An error occurred
    """
    if agents is None:
        agents = [
            MockAgent(name="MockAgent2", response_style="empathic"),
            MockAgent(name="MockAgent3", response_style="historical"),
        ]

    try:
        # --- Pre-orchestration hook ---
        if mod_manager:
            hook_ctx = await mod_manager.run_hooks("pre_orchestration", {
                "prompt": prompt, "agents": agents,
            })
            prompt = hook_ctx.get("prompt", prompt)
            agents = hook_ctx.get("agents", agents)

        # --- Stage: Gathering agent responses ---
        yield _sse_event("stage", {"name": "agents", "status": "running",
                                   "message": f"Querying {len(agents)} agents..."})

        # Fire off all agents and yield each one as it completes
        named_responses = {}
        agent_errors = []
        task_to_agent = {
            asyncio.ensure_future(agent.fetch(prompt)): agent
            for agent in agents
        }
        pending_tasks = set(task_to_agent.keys())

        while pending_tasks:
            done, pending_tasks = await asyncio.wait(
                pending_tasks, return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                agent = task_to_agent[task]
                try:
                    response = task.result()
                except BaseException as exc:
                    error_msg = f"[{agent.name}] Unhandled exception: {type(exc).__name__}: {exc}"
                    print(error_msg)
                    response = f"[{agent.name}] Failed"
                    agent_errors.append(_classify_agent_error(agent.name, response))

                named_responses[agent.name] = response
                if isinstance(response, str) and _is_agent_error(response):
                    if not any(e["agent"] == agent.name for e in agent_errors):
                        agent_errors.append(_classify_agent_error(agent.name, response))

                print(f"{agent.name} responded: {response}")
                yield _sse_event("agent_response", {
                    "agent": agent.name,
                    "text": response,
                    "is_error": _is_agent_error(response) if isinstance(response, str) else False,
                    "agents_done": len(named_responses),
                    "agents_total": len(agents),
                })

        # Separate clean responses
        clean_responses = {
            name: resp for name, resp in named_responses.items()
            if not _is_agent_error(resp)
        }
        responses = list(clean_responses.values()) if clean_responses else list(named_responses.values())

        yield _sse_event("agents_done", {
            "responses": named_responses,
            "agent_errors": agent_errors,
        })

        # --- Post-agent-response hooks ---
        if mod_manager:
            for aname, aresp in named_responses.items():
                await mod_manager.run_hooks("post_agent_response", {
                    "agent_name": aname, "response": aresp, "prompt": prompt,
                })

        # --- Stage: Dissent analysis ---
        yield _sse_event("stage", {"name": "dissent", "status": "running",
                                   "message": "Analyzing dissent..."})

        dissent_analyzer = DissentAnalyzer()
        dissent_input = clean_responses if clean_responses else named_responses
        dissent_report = dissent_analyzer.analyze(prompt, dissent_input)

        dissent_data = {
            "internal_agreement": dissent_report.internal_agreement,
            "dissent_level": dissent_report.dissent_level,
            "outlier_agents": dissent_report.outlier_agents,
            "pairwise": [
                {"agents": [p.agent_a, p.agent_b], "distance": p.distance}
                for p in dissent_report.pairwise
            ],
            "agent_profiles": [
                {"agent": p.agent_name, "mean_distance": p.mean_distance_to_others, "is_outlier": p.is_outlier}
                for p in dissent_report.agent_profiles
            ],
        }
        yield _sse_event("dissent", dissent_data)

        # --- Stage: NCG benchmark ---
        ncg_drift_report = None
        ncg_data = None
        if ncg_enabled:
            yield _sse_event("stage", {"name": "ncg", "status": "running",
                                       "message": "Running NCG headless baseline..."})
            try:
                generator = headless_generator or MockHeadlessGenerator()
                ncg_output = generator.generate(prompt)
                detector = DriftDetector()
                ncg_drift_report = detector.analyze(
                    prompt=prompt,
                    ncg_output=ncg_output,
                    conversational_outputs=clean_responses if clean_responses else named_responses,
                    internal_agreement=dissent_report.internal_agreement,
                )
                ncg_data = {
                    "ncg_model": ncg_drift_report.ncg_model,
                    "mean_drift": ncg_drift_report.mean_semantic_distance,
                    "max_drift": ncg_drift_report.max_semantic_distance,
                    "silent_collapse": ncg_drift_report.silent_collapse_detected,
                    "compression_alert": ncg_drift_report.compression_alert,
                    "per_agent": [
                        {"agent": sig.agent_name, "drift": sig.semantic_distance,
                         "compression": sig.compression_ratio, "tier": sig.analysis_tier}
                        for sig in ncg_drift_report.agent_signals
                    ],
                }
                yield _sse_event("ncg", ncg_data)
            except Exception as e:
                print(f"[NCG Error] {type(e).__name__}: {e} -- skipping NCG track")

        # --- Pre-aggregation hook ---
        if mod_manager:
            hook_ctx = await mod_manager.run_hooks("pre_aggregation", {
                "responses": responses, "dissent_report": dissent_report,
            })
            responses = hook_ctx.get("responses", responses)

        # --- Stage: Aggregation ---
        yield _sse_event("stage", {"name": "consensus", "status": "running",
                                   "message": "Synthesizing consensus..."})

        final_output = aggregate_responses(responses, ncg_drift_report, dissent_report)

        yield _sse_event("consensus", {
            "consensus": final_output.get("consensus"),
            "confidence": final_output.get("confidence"),
            "agreement_ratio": final_output.get("agreement_ratio"),
            "quorum_met": final_output.get("quorum_met"),
            "quorum_threshold": final_output.get("quorum_threshold"),
            "note": final_output.get("note"),
        })

        # --- Post-aggregation hook ---
        if mod_manager:
            await mod_manager.run_hooks("post_aggregation", {"final_output": final_output})

        # --- Pre-session-save hook ---
        if mod_manager:
            await mod_manager.run_hooks("pre_session_save", {
                "prompt": prompt, "named_responses": named_responses,
                "final_output": final_output,
            })

        # --- Stage: Session persistence ---
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
            except Exception as e:
                print(f"[Session Logger Error] {type(e).__name__}: {e}")

        # --- Post-session-save hook ---
        if mod_manager:
            await mod_manager.run_hooks("post_session_save", {"session_id": session_id})

        # --- Pre-R2-scoring hook ---
        if mod_manager:
            await mod_manager.run_hooks("pre_r2_scoring", {
                "dissent_report": dissent_report, "drift_report": ncg_drift_report,
            })

        # --- Stage: R2 scoring ---
        yield _sse_event("stage", {"name": "r2", "status": "running",
                                   "message": "Scoring with R2 engine..."})
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

            r2_data = {
                "grade": r2_score.grade,
                "confidence_score": r2_score.confidence_score,
                "flags": r2_score.flags,
                "signal_count": len(r2_signals),
                "entry_id": r2_entry.entry_id,
            }
            final_output["r2"] = r2_data
            yield _sse_event("r2", r2_data)

            # --- Post-R2-scoring hook ---
            if mod_manager:
                await mod_manager.run_hooks("post_r2_scoring", {
                    "r2_score": r2_data, "r2_signals": r2_signals,
                })
        except Exception as e:
            print(f"[R2 Engine Error] {type(e).__name__}: {e}")
            final_output["r2"] = None

        # --- Done: emit complete response ---
        yield _sse_event("done", {
            "responses": named_responses,
            "agent_errors": agent_errors,
            "session_id": session_id,
            "consensus": final_output.get("consensus"),
            "confidence": final_output.get("confidence"),
            "agreement_ratio": final_output.get("agreement_ratio"),
            "quorum_met": final_output.get("quorum_met"),
            "quorum_threshold": final_output.get("quorum_threshold"),
            "dissent": dissent_data,
            "ncg_benchmark": ncg_data,
            "r2": final_output.get("r2"),
            "note": final_output.get("note"),
        })

    except Exception as e:
        print(f"[Stream Error] {type(e).__name__}: {e}")
        yield _sse_event("error", {"error": f"{type(e).__name__}: {str(e)}"})
