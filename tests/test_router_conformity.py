"""
Smoke tests for maestro/router/conformity.py.

Track B of the items-4-6 cluster (data-blocked deliverables).
Implements + verifies the exponential-decay-weighted conformity
score and the dissenter selection helper. Tuning the decay
constant against real R2 data is still data-blocked; only the
function shape is exercised here.
"""

import math

import pytest

from maestro.router.conformity import (
    ConformitySession,
    ConformityWindow,
    _exponential_weights,
    conformity_score,
    select_dissenter,
)


# ---- helpers ----


def _session(
    agent_pool=("alpha", "beta", "gamma"),
    outliers=(),
    sid: str = "s",
) -> ConformitySession:
    return ConformitySession(
        session_id=sid,
        participated_agents=tuple(agent_pool),
        outlier_agents=tuple(outliers),
    )


# ---- _exponential_weights ----


def test_weights_first_is_one():
    w = _exponential_weights(5, lambda_decay=5.0)
    assert math.isclose(w[0], 1.0, rel_tol=1e-9)


def test_weights_decrease_with_distance():
    w = _exponential_weights(5, lambda_decay=2.0)
    for i in range(len(w) - 1):
        assert w[i] > w[i + 1]


def test_weights_zero_count_returns_empty():
    assert _exponential_weights(0, lambda_decay=5.0) == []


def test_weights_large_lambda_approaches_uniform():
    """As lambda_decay -> infinity, weights flatten toward 1 each
    (the exponentials all approach exp(0) = 1).
    """
    w = _exponential_weights(5, lambda_decay=1e6)
    for v in w:
        assert math.isclose(v, 1.0, rel_tol=1e-3)


# ---- conformity_score basic shapes ----


def test_score_returns_none_when_below_n_min():
    """Default n_min is 5; only 3 sessions of history -> None."""
    sessions = [
        _session(outliers=()) for _ in range(3)
    ]
    assert conformity_score("alpha", sessions) is None


def test_score_returns_none_when_agent_never_participated():
    """An agent who isn't in any session's participated_agents
    has zero history -> None.
    """
    sessions = [
        _session(agent_pool=("beta", "gamma")) for _ in range(10)
    ]
    assert conformity_score("alpha", sessions) is None


def test_score_one_when_agent_always_in_majority():
    """No outlier_agents flag in 10 sessions -> all weight goes
    to "in majority" -> 1.0.
    """
    sessions = [_session(outliers=()) for _ in range(10)]
    assert conformity_score("alpha", sessions) == 1.0


def test_score_zero_when_agent_always_outlier():
    """alpha appears as outlier in every session -> weighted sum
    is 0.0 over a positive total weight -> 0.0.
    """
    sessions = [_session(outliers=("alpha",)) for _ in range(10)]
    assert conformity_score("alpha", sessions) == 0.0


def test_score_in_unit_interval():
    """Mixed history: 5 majority, 5 outlier -> score in [0, 1]."""
    sessions = (
        [_session(outliers=()) for _ in range(5)]
        + [_session(outliers=("alpha",)) for _ in range(5)]
    )
    s = conformity_score("alpha", sessions)
    assert s is not None
    assert 0.0 <= s <= 1.0


def test_score_truncates_to_n_max():
    """With n_max=10 and 25 sessions of history, only the most
    recent 10 contribute. If those 10 are all majority (oldest
    15 are outliers), score is 1.0.
    """
    window = ConformityWindow(n_max=10, n_min=5)
    sessions = (
        [_session(outliers=()) for _ in range(10)]   # most recent 10
        + [_session(outliers=("alpha",)) for _ in range(15)]
    )
    assert conformity_score("alpha", sessions, window) == 1.0


# ---- exponential decay vs flat mean ----


def test_score_recent_outlier_lowers_score_more_than_old_outlier():
    """If alpha was an outlier in the most-recent session but
    in majority in all 9 older ones, the score should be LESS
    than if alpha was an outlier in the OLDEST session and
    majority everywhere else (the recent outlier weighs more).
    """
    # Pattern A: outlier most recently, majority for the rest
    sessions_a = (
        [_session(outliers=("alpha",))]
        + [_session(outliers=()) for _ in range(9)]
    )
    # Pattern B: majority recently, outlier in the oldest
    sessions_b = (
        [_session(outliers=()) for _ in range(9)]
        + [_session(outliers=("alpha",))]
    )
    score_a = conformity_score("alpha", sessions_a)
    score_b = conformity_score("alpha", sessions_b)
    assert score_a is not None
    assert score_b is not None
    # The recent outlier hurts more than the old one
    assert score_a < score_b


def test_score_with_large_lambda_approaches_flat_mean():
    """As lambda_decay -> infinity, the weighted mean converges
    to the flat mean. With 10 sessions, 5 majority + 5 outlier,
    flat mean is 0.5; lambda=1e6 should be very close.
    """
    sessions = []
    for i in range(10):
        sessions.append(_session(outliers=("alpha",) if i % 2 == 0 else ()))
    window = ConformityWindow(lambda_decay=1e6, n_min=5)
    score = conformity_score("alpha", sessions, window)
    assert score is not None
    assert math.isclose(score, 0.5, rel_tol=0.01)


def test_score_with_small_lambda_dominated_by_recent():
    """Tiny lambda -> the most recent session dominates. If alpha
    was in the majority in session 0 but outlier in all others,
    the score under tiny lambda should be very close to 1.0.
    """
    sessions = (
        [_session(outliers=())]                       # most recent: majority
        + [_session(outliers=("alpha",)) for _ in range(9)]
    )
    window = ConformityWindow(lambda_decay=0.5, n_min=5)
    score = conformity_score("alpha", sessions, window)
    assert score is not None
    assert score > 0.85


# ---- determinism ----


def test_score_is_deterministic():
    sessions = (
        [_session(outliers=()) for _ in range(7)]
        + [_session(outliers=("alpha",)) for _ in range(3)]
    )
    a = conformity_score("alpha", sessions)
    b = conformity_score("alpha", sessions)
    assert a == b


# ---- skipping non-participation ----


def test_score_skips_sessions_where_agent_did_not_participate():
    """alpha didn't participate in some sessions; those should
    be skipped before windowing. The score reflects only
    sessions alpha participated in.
    """
    sessions = (
        [_session(agent_pool=("beta", "gamma")) for _ in range(20)]
        + [_session(outliers=()) for _ in range(5)]    # alpha here
    )
    # alpha participated in only 5 sessions; that's exactly n_min
    score = conformity_score("alpha", sessions)
    assert score == 1.0


def test_score_n_min_counts_only_participated_sessions():
    """20 sessions where alpha didn't participate + 4 where alpha
    did participate (in majority) = 4 < n_min(5) -> None.
    """
    sessions = (
        [_session(agent_pool=("beta", "gamma")) for _ in range(20)]
        + [_session(outliers=()) for _ in range(4)]
    )
    assert conformity_score("alpha", sessions) is None


# ---- select_dissenter ----


def test_select_dissenter_returns_highest_conformity():
    """Three agents; alpha and beta have high history conformity,
    gamma is always an outlier. Pick the highest.
    """
    # Build sessions where alpha is always majority, beta is in
    # majority 4/5 of the time, gamma always outlier
    sessions = []
    for i in range(10):
        outliers = ["gamma"]
        if i % 5 == 0:
            outliers.append("beta")
        sessions.append(_session(outliers=tuple(outliers)))

    chosen = select_dissenter(
        ["alpha", "beta", "gamma"], sessions,
    )
    assert chosen == "alpha"


def test_select_dissenter_returns_none_when_no_agent_above_floor():
    """Default floor is 0.6. If everyone is below, no dissenter."""
    sessions = []
    for i in range(10):
        # Everyone is an outlier half the time -> conformity ~ 0.5
        outliers = ["alpha", "beta", "gamma"] if i % 2 == 0 else []
        sessions.append(_session(outliers=tuple(outliers)))

    chosen = select_dissenter(["alpha", "beta", "gamma"], sessions)
    assert chosen is None


def test_select_dissenter_returns_none_when_no_history():
    """Agents with no history get a None score and are skipped."""
    sessions = []  # zero sessions
    chosen = select_dissenter(["alpha", "beta", "gamma"], sessions)
    assert chosen is None


def test_select_dissenter_skips_agents_below_floor_keeps_those_above():
    """alpha is conformist; beta is dissident. With both eligible,
    pick alpha; if floor is raised so only alpha qualifies, still
    alpha; if so high that nobody qualifies, None.
    """
    sessions = []
    for _ in range(10):
        # alpha always in majority (high conformity)
        # beta always outlier (low conformity)
        sessions.append(_session(outliers=("beta",)))

    # Default floor (0.6): alpha qualifies
    chosen = select_dissenter(["alpha", "beta"], sessions)
    assert chosen == "alpha"

    # Floor raised to 0.95 still admits alpha (conformity = 1.0)
    high = ConformityWindow(floor=0.95)
    assert select_dissenter(["alpha", "beta"], sessions, high) == "alpha"

    # Floor raised above 1.0: no one qualifies
    impossible = ConformityWindow(floor=1.01)
    assert select_dissenter(["alpha", "beta"], sessions, impossible) is None


def test_select_dissenter_tiebreak_by_name_sort():
    """Two agents tied on conformity -> the lexicographically-
    smallest name wins.
    """
    sessions = [_session(outliers=()) for _ in range(10)]
    # alpha and beta both always in majority -> conformity = 1.0
    chosen = select_dissenter(["beta", "alpha"], sessions)
    assert chosen == "alpha"


def test_select_dissenter_skips_insufficient_history():
    """Agents with insufficient history (None score) are silently
    skipped; eligible agents still selected from.
    """
    # alpha participates in 10 sessions; beta in 2
    base_pool = ("alpha", "beta", "gamma")
    short_pool = ("beta",)
    sessions = (
        [_session(agent_pool=base_pool, outliers=()) for _ in range(10)]
        + [_session(agent_pool=short_pool, outliers=()) for _ in range(2)]
    )
    # alpha has 10 sessions of history, beta has 12 but only 2
    # where beta participated alone -> beta participation count = 12.
    # Both qualify in this contrived test. Adjust to make beta
    # under n_min: only sessions where beta is in agent_pool are
    # counted, and we're using base_pool for 10 of 12. So
    # beta's history is also 12. Both qualify.
    # Refactor: make beta participate in only 3 sessions total.
    sessions = (
        [_session(agent_pool=("alpha",), outliers=()) for _ in range(10)]
        + [_session(agent_pool=("alpha", "beta"), outliers=()) for _ in range(3)]
    )
    # alpha has 13 sessions; beta has 3 (< n_min=5)
    chosen = select_dissenter(["alpha", "beta"], sessions)
    assert chosen == "alpha"   # beta's None score skipped


# ---- ConformityWindow ----


def test_window_defaults_match_spec():
    """Defaults named in distance-dissent.md §Dissenter selection."""
    w = ConformityWindow()
    assert w.n_max == 20
    assert w.n_min == 5
    assert w.floor == 0.6
    # lambda_decay is the new tunable from Track B
    assert w.lambda_decay == 5.0


def test_window_is_frozen():
    w = ConformityWindow()
    with pytest.raises(Exception):
        w.n_max = 100


# ---- ConformitySession ----


def test_session_is_frozen():
    s = ConformitySession(session_id="s1")
    with pytest.raises(Exception):
        s.session_id = "tampered"
