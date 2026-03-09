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

interface AgentError {
  agent: string;
  code: number | null;
  kind: "auth" | "not_found" | "rate_limit" | "server" | "http" | "timeout" | "connection" | "filtered" | "unknown";
  raw: string;
}

interface OrchestratorResponse {
  responses: Record<string, string>;
  agent_errors?: AgentError[];
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

interface StreamStage {
  name: string;
  status: "running" | "done";
  message?: string;
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

/* ── Error helpers ────────────────────────────────────────────── */

function agentErrorMessage(err: AgentError): { title: string; detail: string; severity: "warn" | "error" } {
  switch (err.kind) {
    case "rate_limit":
      return {
        title: `${err.agent}: Rate limited (429)`,
        detail: "The upstream API is throttling requests. Wait a moment and retry.",
        severity: "warn",
      };
    case "not_found":
      return {
        title: `${err.agent}: Model not found (404)`,
        detail: "The requested model or endpoint does not exist. Check the model name or API configuration.",
        severity: "error",
      };
    case "auth":
      return {
        title: `${err.agent}: Authentication failed${err.code ? ` (${err.code})` : ""}`,
        detail: "The API key is missing or invalid. Open Settings to update it.",
        severity: "error",
      };
    case "server":
      return {
        title: `${err.agent}: Server error (${err.code})`,
        detail: "The upstream API returned a server error. This is usually temporary.",
        severity: "warn",
      };
    case "timeout":
      return {
        title: `${err.agent}: Request timed out`,
        detail: "The upstream API did not respond in time. Try again or increase the timeout.",
        severity: "warn",
      };
    case "connection":
      return {
        title: `${err.agent}: Connection failed`,
        detail: "Could not reach the upstream API. Check your network or the service status.",
        severity: "error",
      };
    case "filtered":
      return {
        title: `${err.agent}: Content filtered`,
        detail: "The upstream API blocked the content due to safety filters.",
        severity: "warn",
      };
    case "http":
      return {
        title: `${err.agent}: HTTP ${err.code}`,
        detail: "An unexpected HTTP error occurred.",
        severity: "warn",
      };
    default:
      return {
        title: `${err.agent}: Failed`,
        detail: err.raw,
        severity: "error",
      };
  }
}

/* ── Components ──────────────────────────────────────────────── */

function AgentWarnings({ errors }: { errors: AgentError[] }) {
  if (!errors.length) return null;

  return (
    <div className="section agent-warnings">
      <h3>
        Agent Issues
        <span className="tag warn-tag">{errors.length} agent{errors.length > 1 ? "s" : ""}</span>
      </h3>
      <p className="muted">
        These agents returned errors and were excluded from metrics to avoid polluting results.
      </p>
      {errors.map((err, i) => {
        const msg = agentErrorMessage(err);
        return (
          <div key={i} className={`agent-warning-item agent-warning-${msg.severity}`}>
            <span className="agent-warning-title">{msg.title}</span>
            <span className="agent-warning-detail">{msg.detail}</span>
          </div>
        );
      })}
    </div>
  );
}

function AgentResponses({ responses, errorAgents }: { responses: Record<string, string>; errorAgents?: Set<string> }) {
  const isError = (agent: string) => errorAgents?.has(agent);

  return (
    <div className="section">
      <h3>Agent Responses</h3>
      {Object.entries(responses).map(([agent, text]) => (
        <div key={agent} className={`agent-card${isError(agent) ? " agent-card-error" : ""}`}>
          <span className="agent-name">{agent}</span>
          {isError(agent) && <span className="tag agent-error-tag">error</span>}
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

function StageIndicator({ stages }: { stages: StreamStage[] }) {
  if (!stages.length) return null;
  return (
    <div className="section stage-indicator">
      {stages.map((s, i) => (
        <span key={i} className={`stage-pill stage-${s.status}`}>
          {s.status === "running" && <span className="stage-spinner" />}
          {s.message || s.name}
        </span>
      ))}
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
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions ?? []);
      }
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

/* ── Update Panel ─────────────────────────────────────────────── */

interface UpdateInfo {
  available: boolean;
  local_commit: string;
  remote_commit: string;
  new_commits: string[];
  branch: string;
  error?: string;
  git_missing?: boolean;
}

function UpdatePanel({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [checking, setChecking] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Remote URL config
  const [remoteUrl, setRemoteUrl] = useState("");
  const [remoteLoaded, setRemoteLoaded] = useState(false);
  const [remoteSaving, setRemoteSaving] = useState(false);
  const [remoteSaved, setRemoteSaved] = useState(false);

  const loadRemote = async () => {
    try {
      const res = await fetch("/api/update/remote");
      if (res.ok) {
        const data = await res.json();
        setRemoteUrl(data.url || "");
        setRemoteLoaded(true);
      }
    } catch { /* ignore */ }
  };

  const saveRemote = async () => {
    setRemoteSaving(true);
    setRemoteSaved(false);
    try {
      const res = await fetch("/api/update/remote", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: remoteUrl.trim() }),
      });
      if (res.ok) {
        setRemoteSaved(true);
        setTimeout(() => setRemoteSaved(false), 2000);
      }
    } catch { /* ignore */ }
    setRemoteSaving(false);
  };

  const checkForUpdates = async () => {
    setChecking(true);
    setError(null);
    setApplied(null);
    try {
      const res = await fetch("/api/update/check");
      if (res.ok) {
        const data: UpdateInfo = await res.json();
        setInfo(data);
        if (data.error) setError(data.error);
      } else {
        setError("Failed to reach update server.");
      }
    } catch {
      setError("Network error checking for updates.");
    }
    setChecking(false);
  };

  useEffect(() => {
    if (visible) {
      loadRemote();
      checkForUpdates();
    }
  }, [visible]);

  const handleApply = async () => {
    setApplying(true);
    setError(null);
    try {
      const res = await fetch("/api/update/apply", { method: "POST" });
      if (res.ok) {
        const result = await res.json();
        if (result.success) {
          setApplied(result.message);
          setInfo(null);
        } else {
          setError(`Update failed: ${result.message}`);
        }
      }
    } catch {
      setError("Network error applying update.");
    }
    setApplying(false);
  };

  if (!visible) return null;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel update-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h2>System Update</h2>
          <div className="settings-header-actions">
            <button
              className="toggle-btn"
              onClick={checkForUpdates}
              disabled={checking}
            >
              {checking ? "Checking..." : "Check again"}
            </button>
            <button className="settings-close" onClick={onClose} aria-label="Close">
              x
            </button>
          </div>
        </div>

        <div className="settings-body">
          {info?.git_missing && (
            <div className="update-result-card update-result-current">
              <p className="update-result-text">Updates not available</p>
              <p className="muted">
                Git is not installed in this environment. Updates require Git on the server.
              </p>
            </div>
          )}

          {error && (
            <div className="update-result-card update-result-error">
              <p className="update-result-text">Unable to check for updates</p>
              <p className="muted">{error}</p>
            </div>
          )}

          {applied && (
            <div className="update-result-card update-result-success">
              <p className="update-result-text">{applied}</p>
              <p className="muted">Restart the server to use the new version.</p>
            </div>
          )}

          {checking && !info && (
            <p className="muted">Checking for updates...</p>
          )}

          {info && !info.git_missing && !info.available && !applied && !error && (
            <div className="update-result-card update-result-current">
              <p className="update-result-text">You're up to date</p>
              <p className="muted">
                Branch: <code>{info.branch}</code> &nbsp; Commit: <code>{info.local_commit}</code>
              </p>
            </div>
          )}

          {info && info.available && (
            <div className="update-result-card update-result-available">
              <p className="update-result-text">
                {info.new_commits.length} new commit{info.new_commits.length !== 1 ? "s" : ""} available
              </p>
              <p className="muted">
                <code>{info.local_commit}</code> &rarr; <code>{info.remote_commit}</code>
                &nbsp; on <code>{info.branch}</code>
              </p>

              {info.new_commits.length > 0 && (
                <div className="update-commit-list">
                  {info.new_commits.slice(0, 20).map((c, i) => (
                    <div key={i} className="update-commit-item"><code>{c}</code></div>
                  ))}
                  {info.new_commits.length > 20 && (
                    <div className="update-commit-item muted">
                      ... and {info.new_commits.length - 20} more
                    </div>
                  )}
                </div>
              )}

              <button
                className="submit-btn update-apply-btn"
                onClick={handleApply}
                disabled={applying}
                style={{ marginTop: "0.75rem" }}
              >
                {applying ? "Updating..." : "Update now"}
              </button>
            </div>
          )}
        </div>

        {remoteLoaded && !info?.git_missing && (
          <div className="update-remote-config">
            <label className="update-remote-label" htmlFor="update-remote-url">
              Remote repository URL
            </label>
            <div className="update-remote-row">
              <input
                id="update-remote-url"
                type="text"
                className="key-input"
                placeholder="https://github.com/user/repo.git"
                value={remoteUrl}
                onChange={(e) => { setRemoteUrl(e.target.value); setRemoteSaved(false); }}
              />
              <button
                className="submit-btn"
                onClick={saveRemote}
                disabled={remoteSaving || !remoteUrl.trim()}
              >
                {remoteSaved ? "Saved" : remoteSaving ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        )}

        <p className="settings-footer">
          Set your repository URL above, then check for updates.
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
  const [updateOpen, setUpdateOpen] = useState(false);

  // Streaming state: the in-progress result being built up from SSE events
  const [streamEntry, setStreamEntry] = useState<Partial<OrchestratorResponse> | null>(null);
  const [streamStages, setStreamStages] = useState<StreamStage[]>([]);

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
    setStreamEntry({ responses: {} });
    setStreamStages([]);

    const currentPrompt = prompt;
    setPrompt("");

    try {
      const res = await fetch("/api/ask/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: currentPrompt }),
      });

      if (!res.ok) {
        const status = res.status;
        let userMessage: string;
        if (status === 404) {
          userMessage = "Endpoint not found (404). The backend may be misconfigured or still starting.";
        } else if (status === 429) {
          userMessage = "Too many requests (429). The server is rate-limiting. Please wait a moment and try again.";
        } else if (status === 401 || status === 403) {
          userMessage = `Authentication error (${status}). Check your API keys in Settings.`;
        } else if (status >= 500) {
          userMessage = `Server error (${status}). The backend encountered an internal error. Check the logs.`;
        } else if (status === 422) {
          userMessage = "Invalid request (422). The prompt may be too long or contain unsupported characters.";
        } else {
          userMessage = `Request failed with HTTP ${status}.`;
        }
        setStreamEntry(null);
        setStreamStages([]);
        setHistory((prev) => [{ responses: {}, error: userMessage }, ...prev]);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        setStreamEntry(null);
        setStreamStages([]);
        setHistory((prev) => [{ responses: {}, error: "Streaming not supported by browser." }, ...prev]);
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Keep the last incomplete line in the buffer
        buffer = lines.pop() || "";

        let eventType = "";
        let dataLines: string[] = [];

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            dataLines.push(line.slice(6));
          } else if (line === "" && eventType && dataLines.length) {
            // End of an SSE message — process it
            try {
              const data = JSON.parse(dataLines.join("\n"));
              handleSSEEvent(eventType, data);
            } catch { /* skip malformed events */ }
            eventType = "";
            dataLines = [];
          }
        }
      }
    } catch (err) {
      let userMessage: string;
      if (err instanceof TypeError && String(err).includes("fetch")) {
        userMessage = "Network error: could not reach the backend. Is the server running?";
      } else {
        userMessage = `Unexpected error: ${String(err)}`;
      }
      setStreamEntry(null);
      setStreamStages([]);
      setHistory((prev) => [{ responses: {}, error: userMessage }, ...prev]);
    } finally {
      setLoading(false);
    }
  };

  const handleSSEEvent = (event: string, data: Record<string, unknown>) => {
    switch (event) {
      case "stage":
        setStreamStages((prev) => {
          // Mark previous running stages as done, add the new one
          const updated = prev.map((s) =>
            s.status === "running" ? { ...s, status: "done" as const } : s,
          );
          return [...updated, {
            name: data.name as string,
            status: "running" as const,
            message: data.message as string | undefined,
          }];
        });
        break;

      case "agent_response":
        setStreamEntry((prev) => ({
          ...prev,
          responses: {
            ...(prev?.responses || {}),
            [data.agent as string]: data.text as string,
          },
        }));
        break;

      case "agents_done":
        setStreamEntry((prev) => ({
          ...prev,
          responses: data.responses as Record<string, string>,
          agent_errors: data.agent_errors as AgentError[],
        }));
        break;

      case "dissent":
        setStreamEntry((prev) => ({ ...prev, dissent: data as unknown as DissentData }));
        break;

      case "ncg":
        setStreamEntry((prev) => ({ ...prev, ncg_benchmark: data as unknown as NcgBenchmark }));
        break;

      case "consensus":
        setStreamEntry((prev) => ({
          ...prev,
          consensus: data.consensus as string,
          confidence: data.confidence as string,
          agreement_ratio: data.agreement_ratio as number,
          quorum_met: data.quorum_met as boolean,
          quorum_threshold: data.quorum_threshold as number,
          note: data.note as string | undefined,
        }));
        break;

      case "r2":
        setStreamEntry((prev) => ({ ...prev, r2: data as unknown as R2Data }));
        break;

      case "done":
        // Finalize: move streaming entry to history
        setStreamStages([]);
        setStreamEntry(null);
        setHistory((prev) => [data as unknown as OrchestratorResponse, ...prev]);
        break;

      case "error":
        setStreamStages([]);
        setStreamEntry(null);
        setHistory((prev) => [{ responses: {}, error: data.error as string }, ...prev]);
        break;
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
        <span className="version">v0.6.0</span>
        <div className="header-actions">
          <button
            className="toggle-btn settings-btn"
            onClick={() => setUpdateOpen(true)}
            title="Check for updates"
          >
            Update
          </button>
          <button
            className="toggle-btn settings-btn"
            onClick={() => setSettingsOpen(true)}
            title="API Key Settings"
          >
            Settings
          </button>
        </div>
      </header>

      <UpdatePanel visible={updateOpen} onClose={() => setUpdateOpen(false)} />
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

      {/* Live streaming result — renders progressively as SSE events arrive */}
      {streamEntry && (
        <div className="result-card result-card-streaming">
          <StageIndicator stages={streamStages} />
          {streamEntry.note && <p className="note-text">{streamEntry.note}</p>}
          {(streamEntry.agent_errors?.length ?? 0) > 0 && (
            <AgentWarnings errors={streamEntry.agent_errors!} />
          )}
          {streamEntry.r2 && <R2Section r2={streamEntry.r2} />}
          {streamEntry.consensus != null && (
            <ConsensusBar data={streamEntry as OrchestratorResponse} />
          )}
          {streamEntry.dissent && <DissentSection dissent={streamEntry.dissent} />}
          {streamEntry.ncg_benchmark && <NcgSection ncg={streamEntry.ncg_benchmark} />}
          {streamEntry.responses && Object.keys(streamEntry.responses).length > 0 && (
            <AgentResponses
              responses={streamEntry.responses}
              errorAgents={new Set((streamEntry.agent_errors ?? []).map((e) => e.agent))}
            />
          )}
        </div>
      )}

      {history.map((entry, idx) => {
        const agentErrors = entry.agent_errors ?? [];
        const errorAgentNames = new Set(agentErrors.map((e) => e.agent));
        return (
          <div key={idx} className="result-card">
            {entry.error ? (
              <p className="error-text">{entry.error}</p>
            ) : (
              <>
                {entry.note && <p className="note-text">{entry.note}</p>}
                {agentErrors.length > 0 && <AgentWarnings errors={agentErrors} />}
                {entry.r2 && <R2Section r2={entry.r2} />}
                <ConsensusBar data={entry} />
                {entry.dissent && <DissentSection dissent={entry.dissent} />}
                {entry.ncg_benchmark && <NcgSection ncg={entry.ncg_benchmark} />}
                <AgentResponses responses={entry.responses} errorAgents={errorAgentNames} />
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
