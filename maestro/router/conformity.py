"""
Conformity score — exponential-decay-weighted measure of how
often an agent has landed in the majority cluster across recent
R2 sessions. Used by the Router's forced-rotation dissenter
selection (see docs/architecture/distance-dissent.md §Dissenter
selection).

The score is the input to ``select_dissenter``: pick the agent
whose recent R2 history shows the strongest correlation with
the session majority — i.e. the most conformist Weight by
measurement. The Router's forced-rotation mechanism then admits
moderate-distance context to that agent on this session, so its
priors are perturbed without fabricating disagreement.

Track B of the items-4-6 cluster (data-blocked deliverables).
Replaces the flat-mean conformity formulation in the spec with
exponential decay so recent sessions count more — the spec's
``distance-dissent.md`` Open Questions explicitly named this as
the natural extension once pre-admit data accumulates.

Tuning the decay constant ``lambda_decay`` against real R2 data
remains the data-blocked piece. The function shape is implemented;
operators can override defaults via ``ConformityWindow`` until
trend data informs better values.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Optional


@dataclass(frozen=True)
class ConformitySession:
    """Compact record of one session's facts for conformity scoring.

    Decouples the helper from the full ``R2LedgerEntry`` schema —
    the R2 ledger reader extracts the two fields conformity cares
    about (``participated_agents``, ``outlier_agents``) and hands
    over a list of these.

    An agent is "in the majority cluster" for a session iff it
    appears in ``participated_agents`` and is NOT in
    ``outlier_agents``.
    """

    session_id: str
    participated_agents: tuple = ()
    outlier_agents: tuple = ()


@dataclass(frozen=True)
class ConformityWindow:
    """Window + curve parameters for conformity scoring.

    Defaults align with the values named in distance-dissent.md
    §Dissenter selection. ``lambda_decay`` is the new tunable
    introduced by Track B; lower values weight recent sessions
    more aggressively.

    n_max:
        Maximum number of recent sessions to consider. Older
        sessions beyond ``n_max`` are ignored regardless of
        weight.
    n_min:
        Minimum sessions required before returning a score.
        Below this, ``conformity_score`` returns None (neutral).
        Forced rotation does not apply to agents with too-short
        history.
    lambda_decay:
        Curve constant for ``weight(i) = exp(-i / lambda_decay)``.
        i = 0 is the most-recent session, i = n-1 is the oldest.
        Large lambda_decay -> weights flatten toward the
        flat-mean limit. Small lambda_decay -> recent sessions
        dominate. Default 5.0 is moderate.
    floor:
        ``select_dissenter`` only returns an agent whose
        conformity is at least this floor. When no agent
        crosses, the council already has adequate natural
        dissent and forced rotation does not engage.
    """

    n_max: int = 20
    n_min: int = 5
    lambda_decay: float = 5.0
    floor: float = 0.6


def _exponential_weights(n: int, lambda_decay: float) -> list:
    """Return ``n`` weights ``[exp(0), exp(-1/lambda), ...,
    exp(-(n-1)/lambda)]``. Pure helper; no normalization here.
    """
    if n <= 0:
        return []
    return [exp(-i / lambda_decay) for i in range(n)]


def conformity_score(
    agent_name: str,
    sessions: list,
    window: Optional[ConformityWindow] = None,
) -> Optional[float]:
    """Weighted conformity score for ``agent_name`` over recent sessions.

    Parameters
    ----------
    agent_name:
        The agent we're scoring.
    sessions:
        List of ``ConformitySession``, **most recent first**. The
        caller is responsible for ordering. Sessions in which
        ``agent_name`` did not participate are skipped before
        windowing.
    window:
        Optional ``ConformityWindow`` overriding the defaults.

    Returns
    -------
    float in ``[0, 1]`` or None
        ``None`` when fewer than ``window.n_min`` sessions of
        history exist for this agent. Otherwise a weighted
        fraction in ``[0, 1]`` with 1.0 = "always in the
        majority" and 0.0 = "always an outlier."

    Implementation notes
    --------------------
    * The flat mean is the limit as ``lambda_decay -> infinity``;
      tests verify this property.
    * Sessions are first filtered to those the agent participated
      in, then truncated to ``window.n_max``. The exponential
      weights are computed over the truncated relevant list, so
      ``i = 0`` is always the agent's most-recent participation.
    """
    w = window or ConformityWindow()

    relevant = [s for s in sessions if agent_name in s.participated_agents]
    relevant = relevant[: w.n_max]

    if len(relevant) < w.n_min:
        return None

    weights = _exponential_weights(len(relevant), w.lambda_decay)
    total_weight = sum(weights)
    if total_weight == 0.0:
        # Degenerate: ``lambda_decay`` was so small every weight
        # underflowed. Treat as "no signal" rather than divide-by-zero.
        return None

    weighted_sum = 0.0
    for weight, session in zip(weights, relevant):
        in_majority = agent_name not in session.outlier_agents
        weighted_sum += weight * (1.0 if in_majority else 0.0)

    return weighted_sum / total_weight


def select_dissenter(
    agent_names: list,
    sessions: list,
    window: Optional[ConformityWindow] = None,
) -> Optional[str]:
    """Return the per-session dissenter, or None if no agent crosses
    the conformity floor.

    Selection rule (distance-dissent.md §Dissenter selection):
      1. Compute ``conformity_score`` for each candidate.
      2. Drop agents below ``window.floor`` (council has enough
         natural dissent).
      3. Drop agents with ``None`` score (insufficient history;
         forced rotation doesn't apply).
      4. Return ``argmax(conformity)``. Ties broken by name sort
         (ascending) for determinism. The spec also calls for an
         "oldest forced-rotation session" tiebreak, which requires
         a separate rotation log not yet implemented; deferred.

    Returns
    -------
    str or None
        The chosen dissenter's name, or None when no agent is
        eligible.
    """
    w = window or ConformityWindow()
    candidates = []
    for agent in agent_names:
        score = conformity_score(agent, sessions, w)
        if score is None:
            continue
        if score < w.floor:
            continue
        candidates.append((score, agent))

    if not candidates:
        return None

    # Highest score first; ties broken by lexicographic agent name
    candidates.sort(key=lambda pair: (-pair[0], pair[1]))
    return candidates[0][1]
