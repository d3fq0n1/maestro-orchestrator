import React, { useState, useEffect } from "react";

/* ── Type definitions ────────────────────────────────────────── */

interface PairwiseEntry {
  agents: string[];
  distance: number;
}

interface AgentProfile {
  agent: string;
  mean_distance: number;
  is_outlier: boolean;
}

interface DissentData {
  internal_agreement: number;
  dissent_level: string;
  outlier_agents: string[];
  pairwise: PairwiseEntry[];
  agent_profiles: AgentProfile[];
}

interface NcgPerAgent {
  agent: string;
  drift: number;
  compression: number;
  tier: string;
}

interface NcgBenchmark {
  ncg_model: string;
  mean_drift: number;
  max_drift: number;
  silent_collapse: boolean;
  compression_alert: boolean;
  per_agent: NcgPerAgent[];
}

interface R2Data {
  grade: string;
  confidence_score: number;
  flags: string[];
  signal_count: number;
  entry_id: string;
}

interface OrchestratorResponse {
  responses: Record<string, string>;
  session_id?: string;
  consensus?: string;
  confidence?: string;
  agreement_ratio?: number;
  quorum_met?: boolean;
  quorum_threshold?: number;
  dissent?: DissentData;
  ncg_benchmark?: NcgBenchmark;
  r2?: R2Data;
  note?: string;
  error?: string;
}

interface SessionSummary {
  session_id: string;
  timestamp: string;
  prompt: string;
  agent_count: number;
  ncg_enabled: boolean;
  silent_collapse: boolean;
}

/* ── Small helpers ───────────────────────────────────────────── */

function gradeColor(grade: string): string {
  switch (grade) {
    case "strong": return "var(--color-ok)";
    case "acceptable": return "var(--color-warn)";
    case "weak": return "var(--color-err)";
    case "suspicious": return "var(--color-crit)";
    default: return "var(--color-muted)";
  }
}

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

/* ── Components ──────────────────────────────────────────────── */

function AgentResponses({ responses }: { responses: Record<string, string> }) {
  return (
    <div className="section">
      <h3>Agent Responses</h3>
      {Object.entries(responses).map(([agent, text]) => (
        <div key={agent} className="agent-card">
          <span className="agent-name">{agent}</span>
          <p className="agent-text">{text || "(no response)"}</p>
        </div>
      ))}
    </div>
  );
}

function ConsensusBar({ data }: { data: OrchestratorResponse }) {
  const ratio = data.agreement_ratio ?? 0;
  const met = data.quorum_met ?? false;
  const threshold = data.quorum_threshold ?? 0.66;

  return (
    <div className="section">
      <h3>Quorum</h3>
      <div className="bar-track">
        <div
          className="bar-fill"
          style={{
            width: pct(ratio),
            background: met ? "var(--color-ok)" : "var(--color-err)",
          }}
        />
        <div
          className="bar-threshold"
          style={{ left: pct(threshold) }}
          title={`Threshold: ${pct(threshold)}`}
        />
      </div>
      <p className="bar-label">
        Agreement: <strong>{pct(ratio)}</strong>
        {" "}(threshold {pct(threshold)})
        {" "}&mdash;{" "}
        <span style={{ color: met ? "var(--color-ok)" : "var(--color-err)" }}>
          {met ? "Quorum met" : "Quorum not met"}
        </span>
      </p>
      {data.consensus && (
        <p className="consensus-text">{data.consensus}</p>
      )}
    </div>
  );
}

function DissentSection({ dissent }: { dissent: DissentData }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="section">
      <h3>
        Dissent Analysis
        <span
          className="tag"
          style={{ background: dissent.dissent_level === "high" ? "var(--color-err)" : "var(--color-muted)" }}
        >
          {dissent.dissent_level}
        </span>
      </h3>
      <p>Internal agreement: <strong>{pct(dissent.internal_agreement)}</strong></p>
      {dissent.outlier_agents.length > 0 && (
        <p className="warn-text">Outlier agents: {dissent.outlier_agents.join(", ")}</p>
      )}
      <button className="toggle-btn" onClick={() => setExpanded(!expanded)}>
        {expanded ? "Hide details" : "Show pairwise distances"}
      </button>
      {expanded && (
        <table className="data-table">
          <thead>
            <tr><th>Pair</th><th>Distance</th></tr>
          </thead>
          <tbody>
            {dissent.pairwise.map((p, i) => (
              <tr key={i}>
                <td>{p.agents.join(" / ")}</td>
                <td>{p.distance.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function NcgSection({ ncg }: { ncg: NcgBenchmark }) {
  return (
    <div className={`section ${ncg.silent_collapse ? "alert-border" : ""}`}>
      <h3>
        NCG Benchmark
        {ncg.silent_collapse && <span className="tag crit-tag">Silent Collapse</span>}
        {ncg.compression_alert && <span className="tag warn-tag">Compression</span>}
      </h3>
      <p>Model: <code>{ncg.ncg_model}</code></p>
      <p>Mean drift: <strong>{ncg.mean_drift.toFixed(4)}</strong> | Max drift: {ncg.max_drift.toFixed(4)}</p>
      <table className="data-table">
        <thead>
          <tr><th>Agent</th><th>Drift</th><th>Compression</th><th>Tier</th></tr>
        </thead>
        <tbody>
          {ncg.per_agent.map((a) => (
            <tr key={a.agent}>
              <td>{a.agent}</td>
              <td>{a.drift.toFixed(4)}</td>
              <td>{a.compression.toFixed(2)}</td>
              <td>{a.tier}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function R2Section({ r2 }: { r2: R2Data }) {
  return (
    <div className="section">
      <h3>
        R2 Engine
        <span className="tag" style={{ background: gradeColor(r2.grade) }}>
          {r2.grade}
        </span>
      </h3>
      <p>Confidence: <strong>{(r2.confidence_score * 100).toFixed(1)}%</strong></p>
      {r2.flags.length > 0 && (
        <ul className="flag-list">
          {r2.flags.map((f, i) => <li key={i}>{f}</li>)}
        </ul>
      )}
      {r2.signal_count > 0 && (
        <p className="signal-count">{r2.signal_count} improvement signal(s) raised</p>
      )}
    </div>
  );
}

function SessionHistory() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [visible, setVisible] = useState(false);

  const loadSessions = async () => {
    try {
      const res = await fetch("/api/sessions");
      if (res.ok) setSessions(await res.json());
    } catch { /* ignore */ }
  };

  useEffect(() => {
    if (visible) loadSessions();
  }, [visible]);

  return (
    <div className="section">
      <button className="toggle-btn" onClick={() => setVisible(!visible)}>
        {visible ? "Hide session history" : "Show session history"}
      </button>
      {visible && (
        sessions.length === 0
          ? <p className="muted">No sessions recorded yet.</p>
          : <table className="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Prompt</th>
                  <th>Agents</th>
                  <th>NCG</th>
                  <th>Collapse</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.session_id}>
                    <td className="mono">{new Date(s.timestamp).toLocaleString()}</td>
                    <td>{s.prompt}</td>
                    <td>{s.agent_count}</td>
                    <td>{s.ncg_enabled ? "Yes" : "No"}</td>
                    <td style={{ color: s.silent_collapse ? "var(--color-crit)" : "inherit" }}>
                      {s.silent_collapse ? "Yes" : "No"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
      )}
    </div>
  );
}

/* ── Main ────────────────────────────────────────────────────── */

export default function MaestroUI() {
  const [prompt, setPrompt] = useState("");
  const [history, setHistory] = useState<OrchestratorResponse[]>([]);
  const [loading, setLoading] = useState(false);

  const sendPrompt = async () => {
    if (!prompt.trim() || loading) return;
    setLoading(true);
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: OrchestratorResponse = await res.json();
      setHistory((prev) => [data, ...prev]);
    } catch (err) {
      setHistory((prev) => [{ responses: {}, error: String(err) }, ...prev]);
    } finally {
      setPrompt("");
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendPrompt();
    }
  };

  return (
    <div className="maestro-root">
      <header className="maestro-header">
        <h1>Maestro-Orchestrator</h1>
        <span className="version">v0.3</span>
      </header>

      <div className="prompt-area">
        <textarea
          rows={3}
          placeholder="Ask the council..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <button onClick={sendPrompt} disabled={loading} className="submit-btn">
          {loading ? "Thinking..." : "Submit"}
        </button>
      </div>

      <SessionHistory />

      {history.map((entry, idx) => (
        <div key={idx} className="result-card">
          {entry.error ? (
            <p className="error-text">{entry.error}</p>
          ) : (
            <>
              {entry.note && <p className="note-text">{entry.note}</p>}
              {entry.r2 && <R2Section r2={entry.r2} />}
              <ConsensusBar data={entry} />
              {entry.dissent && <DissentSection dissent={entry.dissent} />}
              {entry.ncg_benchmark && <NcgSection ncg={entry.ncg_benchmark} />}
              <AgentResponses responses={entry.responses} />
            </>
          )}
        </div>
      ))}
    </div>
  );
}
