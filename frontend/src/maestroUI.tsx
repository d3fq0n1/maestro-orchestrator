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

interface KeyInfo {
  provider: string;
  label: string;
  env_var: string;
  configured: boolean;
  masked_value: string;
  signup_url?: string;
  valid?: boolean | null;
  error?: string | null;
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

/* ── API Key Settings ─────────────────────────────────────────── */

function ApiKeySettings({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const [keys, setKeys] = useState<KeyInfo[]>([]);
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [validating, setValidating] = useState<Record<string, boolean>>({});
  const [showRaw, setShowRaw] = useState<Record<string, boolean>>({});

  const loadKeys = async () => {
    try {
      const res = await fetch("/api/keys");
      if (res.ok) {
        const data = await res.json();
        setKeys(data.keys);
      }
    } catch { /* ignore */ }
  };

  useEffect(() => {
    if (visible) loadKeys();
  }, [visible]);

  const handleSave = async (provider: string) => {
    const value = editing[provider];
    if (!value?.trim()) return;
    setSaving((p) => ({ ...p, [provider]: true }));
    try {
      const res = await fetch(`/api/keys/${provider}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value: value.trim() }),
      });
      if (res.ok) {
        setEditing((p) => ({ ...p, [provider]: "" }));
        await loadKeys();
      }
    } catch { /* ignore */ }
    setSaving((p) => ({ ...p, [provider]: false }));
  };

  const handleRemove = async (provider: string) => {
    try {
      const res = await fetch(`/api/keys/${provider}`, { method: "DELETE" });
      if (res.ok) await loadKeys();
    } catch { /* ignore */ }
  };

  const handleValidate = async (provider: string) => {
    setValidating((p) => ({ ...p, [provider]: true }));
    try {
      const res = await fetch(`/api/keys/${provider}/validate`, { method: "POST" });
      if (res.ok) {
        const result: KeyInfo = await res.json();
        setKeys((prev) =>
          prev.map((k) => (k.provider === provider ? { ...k, valid: result.valid, error: result.error } : k))
        );
      }
    } catch { /* ignore */ }
    setValidating((p) => ({ ...p, [provider]: false }));
  };

  const handleValidateAll = async () => {
    const allProviders = keys.map((k) => k.provider);
    allProviders.forEach((p) => setValidating((prev) => ({ ...prev, [p]: true })));
    try {
      const res = await fetch("/api/keys/validate", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setKeys(data.keys);
      }
    } catch { /* ignore */ }
    allProviders.forEach((p) => setValidating((prev) => ({ ...prev, [p]: false })));
  };

  if (!visible) return null;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h2>API Keys</h2>
          <div className="settings-header-actions">
            <button className="toggle-btn" onClick={handleValidateAll}>
              Validate All
            </button>
            <button className="settings-close" onClick={onClose} aria-label="Close">
              x
            </button>
          </div>
        </div>

        <div className="settings-body">
          {keys.map((k) => (
            <div key={k.provider} className="key-row">
              <div className="key-row-header">
                <span className="key-label">{k.label}</span>
                {k.signup_url && (
                  <a className="key-signup-link" href={k.signup_url} target="_blank" rel="noopener noreferrer">
                    Get a key
                  </a>
                )}
                <span className="key-env-var">{k.env_var}</span>
                <span
                  className={`key-status ${k.configured ? (k.valid === true ? "status-valid" : k.valid === false ? "status-invalid" : "status-configured") : "status-missing"}`}
                >
                  {k.configured
                    ? k.valid === true
                      ? "valid"
                      : k.valid === false
                        ? "invalid"
                        : "configured"
                    : "missing"}
                </span>
              </div>

              {k.configured && (
                <div className="key-current">
                  <code>{showRaw[k.provider] ? "(stored securely)" : k.masked_value}</code>
                  <div className="key-actions">
                    <button
                      className="toggle-btn key-btn"
                      onClick={() => handleValidate(k.provider)}
                      disabled={validating[k.provider]}
                    >
                      {validating[k.provider] ? "..." : "Test"}
                    </button>
                    <button
                      className="toggle-btn key-btn key-btn-danger"
                      onClick={() => handleRemove(k.provider)}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              )}

              {k.valid === false && k.error && (
                <p className="key-error">{k.error}</p>
              )}

              <div className="key-input-row">
                <input
                  type={showRaw[k.provider] ? "text" : "password"}
                  className="key-input"
                  placeholder={k.configured ? "Replace key..." : "Paste API key..."}
                  value={editing[k.provider] || ""}
                  onChange={(e) => setEditing((p) => ({ ...p, [k.provider]: e.target.value }))}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSave(k.provider);
                  }}
                />
                <button
                  className="toggle-btn key-btn"
                  onClick={() => setShowRaw((p) => ({ ...p, [k.provider]: !p[k.provider] }))}
                  title="Toggle visibility"
                >
                  {showRaw[k.provider] ? "Hide" : "Show"}
                </button>
                <button
                  className="submit-btn key-save-btn"
                  onClick={() => handleSave(k.provider)}
                  disabled={!editing[k.provider]?.trim() || saving[k.provider]}
                >
                  {saving[k.provider] ? "..." : "Save"}
                </button>
              </div>
            </div>
          ))}
        </div>

        <p className="settings-footer">
          Keys are saved to the .env file and take effect immediately.
        </p>
      </div>
    </div>
  );
}

/* ── Main ────────────────────────────────────────────────────── */

export default function MaestroUI() {
  const [prompt, setPrompt] = useState("");
  const [history, setHistory] = useState<OrchestratorResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Auto-open the settings panel on first load when no keys are configured.
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/keys");
        if (res.ok) {
          const data = await res.json();
          if (!data.any_configured) setSettingsOpen(true);
        }
      } catch { /* ignore */ }
    })();
  }, []);

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
        <button
          className="toggle-btn settings-btn"
          onClick={() => setSettingsOpen(true)}
          title="API Key Settings"
        >
          Settings
        </button>
      </header>

      <ApiKeySettings visible={settingsOpen} onClose={() => setSettingsOpen(false)} />

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
