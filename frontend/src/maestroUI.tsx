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
  local_unknown?: boolean;
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
  const [restarting, setRestarting] = useState(false);

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
        setRemoteUrl(data.url || "https://github.com/d3fq0n1/maestro-orchestrator.git");
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

  const handleRestart = async () => {
    setRestarting(true);
    try {
      await fetch("/api/update/restart", { method: "POST" });
    } catch { /* expected — server is shutting down */ }
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

          {applying && (
            <div className="update-result-card update-result-available">
              <p className="update-result-text">Updating...</p>
              <div className="update-progress-bar">
                <div className="update-progress-bar-fill" />
              </div>
            </div>
          )}

          {applied && (
            <div className="update-result-card update-result-success">
              <p className="update-result-text">{applied}</p>
              <p className="muted">Restart the server to use the new version.</p>
              <button
                className="update-restart-btn"
                onClick={handleRestart}
                disabled={restarting}
                style={{ marginTop: "0.75rem" }}
              >
                {restarting ? "Restarting..." : "Restart server"}
              </button>
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

          {info && info.available && !error && (
            <div className="update-result-card update-result-available">
              {info.local_unknown ? (
                <>
                  <p className="update-result-text">Update available</p>
                  <p className="muted">
                    Current version could not be determined. Latest remote
                    is <code>{info.remote_commit}</code> on <code>{info.branch}</code>.
                  </p>
                </>
              ) : (
                <>
                  <p className="update-result-text">
                    {info.new_commits.length} new commit{info.new_commits.length !== 1 ? "s" : ""} available
                  </p>
                  <p className="muted">
                    <code>{info.local_commit}</code> &rarr; <code>{info.remote_commit}</code>
                    &nbsp; on <code>{info.branch}</code>
                  </p>
                </>
              )}

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

        {!info?.git_missing && (
          <p className="settings-footer">
            Set your repository URL above, then check for updates.
          </p>
        )}
      </div>
    </div>
  );
}

/* ── Storage Network Panel ────────────────────────────────────── */

interface StorageNodeInfo {
  node_id: string;
  host: string;
  port: number;
  status: string;
  shards: { model_id?: string; layer_range?: number[]; shard_id?: string }[];
  capabilities: string[];
  reputation_score: number;
  mean_latency_ms: number;
  last_heartbeat: string;
}

interface ShardModel {
  model_id: string;
  total_layers: number;
  layer_coverage: number[][];
  complete: boolean;
  precision: string;
  files: number;
  total_gb: number;
}

interface DownloadStatus {
  status: string;
  model_id?: string;
  error?: string;
  files_downloaded?: number;
  layer_start?: number;
  layer_end?: number;
}

interface NodeContribution {
  node_id: string;
  layer_range: number[];
  reputation: number;
  latency_ms: number;
  status: string;
}

interface NetworkModel {
  model_id: string;
  total_layers: number;
  covered_layers: number;
  coverage_pct: number;
  coverage_ranges: number[][];
  gaps: number[][];
  is_mirror: boolean;
  pipeline_hops: number;
  pipeline: { node_id: string; host: string; port: number }[];
  redundancy_map: Record<string, string[]>;
  node_contributions: NodeContribution[];
}

interface NetworkTopology {
  node_count: number;
  model_count: number;
  nodes: (StorageNodeInfo & { reputation_status: string; shard_count: number })[];
  models: NetworkModel[];
}

function nodeStatusColor(status: string): string {
  switch (status) {
    case "available": return "var(--color-ok)";
    case "busy": return "var(--color-warn)";
    case "probation": return "var(--color-warn)";
    case "offline": return "var(--color-muted)";
    case "evicted": return "var(--color-err)";
    default: return "var(--color-muted)";
  }
}

function CommandSnippet({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(command).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="command-snippet">
      <code className="command-snippet-text">{command}</code>
      <button
        className="command-snippet-copy"
        onClick={handleCopy}
        title="Copy to clipboard"
      >
        {copied ? "Copied!" : "Copy"}
      </button>
    </div>
  );
}

function StoragePanel({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const [tab, setTab] = useState<"nodes" | "shards" | "shard-map" | "network">("network");

  // Nodes tab state
  const [nodes, setNodes] = useState<StorageNodeInfo[]>([]);
  const [nodesLoading, setNodesLoading] = useState(false);
  const [challengeResult, setChallengeResult] = useState<string | null>(null);

  // Shards tab state
  const [models, setModels] = useState<ShardModel[]>([]);
  const [shardsLoading, setShardsLoading] = useState(false);
  const [diskUsage, setDiskUsage] = useState<{ total_gb: number; total_files: number } | null>(null);
  const [verifyResults, setVerifyResults] = useState<Record<string, { passed: string[]; failed: string[]; missing: string[] }>>({});
  const [verifying, setVerifying] = useState<Record<string, boolean>>({});

  // Download form state
  const [dlModelId, setDlModelId] = useState("");
  const [dlLayers, setDlLayers] = useState("");
  const [dlToken, setDlToken] = useState("");
  const [dlStatus, setDlStatus] = useState<DownloadStatus | null>(null);
  const [dlPolling, setDlPolling] = useState(false);

  // Generate config state
  const [configModel, setConfigModel] = useState("");
  const [configResult, setConfigResult] = useState<string | null>(null);

  // Network topology state
  const [topology, setTopology] = useState<NetworkTopology | null>(null);
  const [topoLoading, setTopoLoading] = useState(false);

  const loadTopology = async () => {
    setTopoLoading(true);
    try {
      const res = await fetch("/api/storage/network/topology");
      if (res.ok) {
        const data: NetworkTopology = await res.json();
        setTopology(data);
      }
    } catch { /* ignore */ }
    setTopoLoading(false);
  };

  const loadNodes = async () => {
    setNodesLoading(true);
    try {
      const res = await fetch("/api/storage/nodes");
      if (res.ok) {
        const data = await res.json();
        setNodes(data.nodes ?? []);
      }
    } catch { /* ignore */ }
    setNodesLoading(false);
  };

  const loadModels = async () => {
    setShardsLoading(true);
    try {
      const [modelsRes, usageRes] = await Promise.all([
        fetch("/api/storage/shards/models"),
        fetch("/api/storage/shards/disk-usage"),
      ]);
      if (modelsRes.ok) {
        const data = await modelsRes.json();
        setModels(data.models ?? []);
      }
      if (usageRes.ok) {
        const data = await usageRes.json();
        setDiskUsage(data);
      }
    } catch { /* ignore */ }
    setShardsLoading(false);
  };

  useEffect(() => {
    if (visible) {
      if (tab === "nodes") loadNodes();
      else if (tab === "shards") loadModels();
      else if (tab === "network" || tab === "shard-map") loadTopology();
    }
  }, [visible, tab]);

  const triggerChallenge = async (nodeId: string) => {
    setChallengeResult(null);
    try {
      const res = await fetch(`/api/storage/challenge/${nodeId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ challenge_type: "byte_range_hash" }),
      });
      if (res.ok) {
        const data = await res.json();
        setChallengeResult(`Challenge ${data.challenge_id.slice(0, 8)}... issued to ${nodeId}`);
      }
    } catch {
      setChallengeResult("Failed to issue challenge.");
    }
  };

  const removeNode = async (nodeId: string) => {
    try {
      await fetch(`/api/storage/nodes/${nodeId}`, { method: "DELETE" });
      await loadNodes();
    } catch { /* ignore */ }
  };

  const startDownload = async () => {
    if (!dlModelId.trim()) return;
    let layerStart = 0;
    let layerEnd = -1;
    if (dlLayers.trim()) {
      const parts = dlLayers.split("-");
      layerStart = parseInt(parts[0]) || 0;
      layerEnd = parts.length > 1 ? parseInt(parts[1]) || -1 : layerStart;
    }
    try {
      const res = await fetch("/api/storage/shards/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model_id: dlModelId.trim(),
          layer_start: layerStart,
          layer_end: layerEnd,
          token: dlToken.trim(),
        }),
      });
      if (res.ok) {
        setDlStatus({ status: "starting", model_id: dlModelId.trim() });
        setDlPolling(true);
      }
    } catch {
      setDlStatus({ status: "error", error: "Network error." });
    }
  };

  // Poll download status
  useEffect(() => {
    if (!dlPolling || !dlModelId.trim()) return;
    const modelId = dlModelId.trim();
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/storage/shards/download-status/${encodeURIComponent(modelId)}`);
        if (res.ok) {
          const data: DownloadStatus = await res.json();
          setDlStatus(data);
          if (data.status === "complete" || data.status === "error" || data.status === "idle") {
            setDlPolling(false);
            if (data.status === "complete") {
              loadModels();
              // Clear the download status on the backend
              fetch(`/api/storage/shards/download-status/${encodeURIComponent(modelId)}`, { method: "DELETE" });
            }
          }
        }
      } catch { /* ignore */ }
    }, 2000);
    return () => clearInterval(interval);
  }, [dlPolling, dlModelId]);

  const handleVerify = async (modelId: string) => {
    setVerifying((p) => ({ ...p, [modelId]: true }));
    try {
      const res = await fetch(`/api/storage/shards/verify/${encodeURIComponent(modelId)}`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setVerifyResults((p) => ({ ...p, [modelId]: data }));
      }
    } catch { /* ignore */ }
    setVerifying((p) => ({ ...p, [modelId]: false }));
  };

  const handleRemoveModel = async (modelId: string) => {
    try {
      await fetch(`/api/storage/shards/${encodeURIComponent(modelId)}`, { method: "DELETE" });
      await loadModels();
    } catch { /* ignore */ }
  };

  const handleGenerateConfig = async (modelId: string) => {
    setConfigResult(null);
    try {
      const res = await fetch("/api/storage/shards/generate-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: modelId }),
      });
      if (res.ok) {
        const data = await res.json();
        setConfigResult(`Generated ${data.shard_count} shard(s) to ${data.output_path}`);
      }
    } catch {
      setConfigResult("Failed to generate config.");
    }
  };

  if (!visible) return null;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel storage-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h2>Storage Network</h2>
          <div className="settings-header-actions">
            <button className="settings-close" onClick={onClose} aria-label="Close">
              x
            </button>
          </div>
        </div>

        {/* Tab bar */}
        <div className="storage-tabs">
          <button
            className={`storage-tab${tab === "network" ? " storage-tab-active" : ""}`}
            onClick={() => setTab("network")}
          >
            Network
          </button>
          <button
            className={`storage-tab${tab === "shard-map" ? " storage-tab-active" : ""}`}
            onClick={() => setTab("shard-map")}
          >
            Shard Map
          </button>
          <button
            className={`storage-tab${tab === "nodes" ? " storage-tab-active" : ""}`}
            onClick={() => setTab("nodes")}
          >
            Nodes
          </button>
          <button
            className={`storage-tab${tab === "shards" ? " storage-tab-active" : ""}`}
            onClick={() => setTab("shards")}
          >
            Shards
          </button>
        </div>

        <div className="settings-body">

          {/* ── Network tab — topology, mirrors, neighbors ── */}
          {tab === "network" && (
            <>
              <div className="storage-tab-header">
                <span className="muted">
                  {topology ? `${topology.node_count} node${topology.node_count !== 1 ? "s" : ""}, ${topology.model_count} model${topology.model_count !== 1 ? "s" : ""}` : "Loading..."}
                </span>
                <button className="toggle-btn" onClick={loadTopology} disabled={topoLoading}>
                  {topoLoading ? "Loading..." : "Refresh"}
                </button>
              </div>

              {topology && topology.models.length === 0 && topology.nodes.length === 0 && (
                <div className="storage-empty">
                  <p className="muted">No storage nodes or models in the network.</p>
                  <CommandSnippet command={`python -m maestro.node_cli start --orchestrator ${window.location.origin}`} />
                </div>
              )}

              {/* Per-model mirror status */}
              {topology?.models.map((model) => (
                <div key={model.model_id} className="storage-network-model">
                  <div className="storage-model-header">
                    <span className="storage-model-id" title={model.model_id}>{model.model_id}</span>
                    <span
                      className="tag"
                      style={{
                        background: model.is_mirror ? "var(--color-ok)" : model.coverage_pct > 0 ? "var(--color-warn)" : "var(--color-muted)",
                        color: model.is_mirror ? "#fff" : model.coverage_pct > 0 ? "#000" : "#fff",
                      }}
                    >
                      {model.is_mirror ? "FULL MIRROR" : `${model.coverage_pct}% coverage`}
                    </span>
                  </div>

                  {/* Layer coverage bar */}
                  <div className="shard-layer-bar-container">
                    <div className="shard-layer-bar">
                      {model.total_layers > 0 && model.node_contributions.map((nc, i) => {
                        const left = (nc.layer_range[0] / model.total_layers) * 100;
                        const width = ((nc.layer_range[1] - nc.layer_range[0] + 1) / model.total_layers) * 100;
                        const hue = (i * 137) % 360;
                        return (
                          <div
                            key={`${nc.node_id}-${i}`}
                            className="shard-layer-segment"
                            style={{
                              left: `${left}%`,
                              width: `${width}%`,
                              background: `hsla(${hue}, 65%, 55%, 0.8)`,
                            }}
                            title={`${nc.node_id}: layers ${nc.layer_range[0]}-${nc.layer_range[1]}`}
                          />
                        );
                      })}
                    </div>
                    <div className="shard-layer-labels">
                      <span>L0</span>
                      <span>L{model.total_layers > 0 ? model.total_layers - 1 : 0}</span>
                    </div>
                  </div>

                  {/* Gaps warning */}
                  {model.gaps.length > 0 && (
                    <p className="storage-gaps-warning">
                      Missing layers: {model.gaps.map(g => g[0] === g[1] ? `${g[0]}` : `${g[0]}-${g[1]}`).join(", ")}
                    </p>
                  )}

                  {/* Pipeline */}
                  {model.pipeline.length > 0 && (
                    <div className="shard-pipeline">
                      <span className="muted" style={{ fontSize: "0.78rem" }}>Pipeline: </span>
                      {model.pipeline.map((hop, i) => (
                        <span key={hop.node_id} className="shard-pipeline-hop">
                          {i > 0 && <span className="shard-pipeline-arrow">&rarr;</span>}
                          <span className="storage-shard-pill">{hop.node_id}</span>
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Neighbor nodes contributing to this model */}
                  <div className="shard-neighbors">
                    <span className="muted" style={{ fontSize: "0.78rem" }}>
                      Neighbor nodes ({model.node_contributions.length}):
                    </span>
                    {model.node_contributions.map((nc) => (
                      <div key={nc.node_id} className="shard-neighbor-row">
                        <span className="storage-shard-pill" style={{ minWidth: "auto" }}>
                          {nc.node_id}
                        </span>
                        <span className="muted" style={{ fontSize: "0.75rem" }}>
                          L{nc.layer_range[0]}-{nc.layer_range[1]}
                        </span>
                        <span style={{ fontSize: "0.75rem", color: nc.reputation >= 0.7 ? "var(--color-ok)" : nc.reputation >= 0.3 ? "var(--color-warn)" : "var(--color-err)" }}>
                          {(nc.reputation * 100).toFixed(0)}% rep
                        </span>
                        <span className="muted" style={{ fontSize: "0.75rem" }}>
                          {nc.latency_ms.toFixed(0)}ms
                        </span>
                        <span
                          className="tag"
                          style={{
                            background: nodeStatusColor(nc.status),
                            fontSize: "0.6rem",
                            padding: "0.1rem 0.3rem",
                          }}
                        >
                          {nc.status}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* Redundancy map */}
                  {Object.keys(model.redundancy_map).length > 0 && (
                    <div className="shard-redundancy">
                      <span className="muted" style={{ fontSize: "0.78rem" }}>Redundancy:</span>
                      {Object.entries(model.redundancy_map).map(([range, nodeIds]) => (
                        <div key={range} className="shard-redundancy-row">
                          <span className="mono" style={{ fontSize: "0.75rem" }}>L{range}</span>
                          <span style={{ fontSize: "0.75rem", color: nodeIds.length >= 2 ? "var(--color-ok)" : "var(--color-warn)" }}>
                            {nodeIds.length}x
                          </span>
                          <span className="muted" style={{ fontSize: "0.72rem" }}>
                            {nodeIds.join(", ")}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </>
          )}

          {/* ── Shard Map tab — visual grid of nodes x layers ── */}
          {tab === "shard-map" && (
            <>
              <div className="storage-tab-header">
                <span className="muted">
                  {topology ? `Shard distribution across ${topology.node_count} node${topology.node_count !== 1 ? "s" : ""}` : "Loading..."}
                </span>
                <button className="toggle-btn" onClick={loadTopology} disabled={topoLoading}>
                  {topoLoading ? "Loading..." : "Refresh"}
                </button>
              </div>

              {topology && topology.models.length === 0 && (
                <div className="storage-empty">
                  <p className="muted">No models with shards in the network.</p>
                </div>
              )}

              {topology?.models.map((model) => {
                // Build a grid: rows = nodes, columns = layer blocks
                const blockSize = Math.max(1, Math.ceil(model.total_layers / 32));
                const blockCount = Math.ceil(model.total_layers / blockSize);

                // Map which nodes cover which blocks
                const nodeBlocks: Record<string, Set<number>> = {};
                model.node_contributions.forEach((nc) => {
                  if (!nodeBlocks[nc.node_id]) nodeBlocks[nc.node_id] = new Set();
                  for (let l = nc.layer_range[0]; l <= nc.layer_range[1]; l++) {
                    nodeBlocks[nc.node_id].add(Math.floor(l / blockSize));
                  }
                });
                const nodeIds = Object.keys(nodeBlocks);

                return (
                  <div key={model.model_id} className="shard-map-model">
                    <div className="storage-model-header">
                      <span className="storage-model-id" title={model.model_id}>{model.model_id}</span>
                      <span
                        className="tag"
                        style={{
                          background: model.is_mirror ? "var(--color-ok)" : "var(--color-warn)",
                          color: model.is_mirror ? "#fff" : "#000",
                        }}
                      >
                        {model.is_mirror ? "MIRROR" : `${model.coverage_pct}%`}
                      </span>
                    </div>

                    {/* Layer index header */}
                    <div className="shard-map-grid">
                      <div className="shard-map-row shard-map-header-row">
                        <span className="shard-map-label"></span>
                        <div className="shard-map-cells">
                          {Array.from({ length: blockCount }, (_, b) => (
                            <span
                              key={b}
                              className="shard-map-cell shard-map-cell-header"
                              title={`Layers ${b * blockSize}-${Math.min((b + 1) * blockSize - 1, model.total_layers - 1)}`}
                            >
                              {b % Math.max(1, Math.floor(blockCount / 8)) === 0 ? b * blockSize : ""}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* One row per node */}
                      {nodeIds.map((nodeId, ni) => {
                        const blocks = nodeBlocks[nodeId];
                        const hue = (ni * 137) % 360;
                        return (
                          <div key={nodeId} className="shard-map-row">
                            <span className="shard-map-label" title={nodeId}>
                              {nodeId.length > 12 ? nodeId.slice(0, 12) + "..." : nodeId}
                            </span>
                            <div className="shard-map-cells">
                              {Array.from({ length: blockCount }, (_, b) => (
                                <span
                                  key={b}
                                  className={`shard-map-cell ${blocks.has(b) ? "shard-map-cell-active" : "shard-map-cell-empty"}`}
                                  style={blocks.has(b) ? { background: `hsla(${hue}, 65%, 55%, 0.8)` } : undefined}
                                  title={blocks.has(b) ? `${nodeId}: L${b * blockSize}-${Math.min((b + 1) * blockSize - 1, model.total_layers - 1)}` : `empty`}
                                />
                              ))}
                            </div>
                          </div>
                        );
                      })}

                      {/* Network coverage row (aggregate) */}
                      <div className="shard-map-row shard-map-aggregate-row">
                        <span className="shard-map-label" style={{ fontWeight: 700 }}>Network</span>
                        <div className="shard-map-cells">
                          {Array.from({ length: blockCount }, (_, b) => {
                            const coveredNodes = nodeIds.filter(n => nodeBlocks[n].has(b)).length;
                            return (
                              <span
                                key={b}
                                className={`shard-map-cell ${coveredNodes > 0 ? "shard-map-cell-covered" : "shard-map-cell-gap"}`}
                                style={coveredNodes > 0 ? {
                                  background: coveredNodes >= 2 ? "var(--color-ok)" : "var(--color-warn)",
                                  opacity: Math.min(1, 0.4 + coveredNodes * 0.2),
                                } : undefined}
                                title={coveredNodes > 0 ? `${coveredNodes}x redundancy` : "gap — no coverage"}
                              />
                            );
                          })}
                        </div>
                      </div>
                    </div>

                    {/* Legend */}
                    <div className="shard-map-legend">
                      <span className="muted" style={{ fontSize: "0.72rem" }}>
                        {model.total_layers} layers, {blockSize > 1 ? `${blockSize} layers/block` : "1:1"}
                      </span>
                      <span style={{ fontSize: "0.72rem" }}>
                        <span className="shard-map-legend-dot" style={{ background: "var(--color-ok)" }} /> 2x+ redundancy
                        <span className="shard-map-legend-dot" style={{ background: "var(--color-warn)", marginLeft: "0.5rem" }} /> 1x
                        <span className="shard-map-legend-dot" style={{ background: "var(--color-err)", marginLeft: "0.5rem" }} /> gap
                      </span>
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* ── Nodes tab ── */}
          {tab === "nodes" && (
            <>
              <div className="storage-tab-header">
                <span className="muted">{nodes.length} node{nodes.length !== 1 ? "s" : ""} registered</span>
                <button className="toggle-btn" onClick={loadNodes} disabled={nodesLoading}>
                  {nodesLoading ? "Loading..." : "Refresh"}
                </button>
              </div>

              {challengeResult && (
                <p className="storage-challenge-result">{challengeResult}</p>
              )}

              {nodes.length === 0 && !nodesLoading && (
                <div className="storage-empty">
                  <p className="muted">No storage nodes registered.</p>
                  <CommandSnippet command={`python -m maestro.node_cli start --orchestrator ${window.location.origin}`} />
                </div>
              )}

              {nodes.map((node) => (
                <div key={node.node_id} className="storage-node-card">
                  <div className="storage-node-header">
                    <span className="storage-node-id" title={node.node_id}>{node.node_id}</span>
                    <span
                      className="tag"
                      style={{ background: nodeStatusColor(node.status) }}
                    >
                      {node.status}
                    </span>
                    <span className="storage-node-host" title={`${node.host}:${node.port}`}>
                      {node.host}:{node.port}
                    </span>
                  </div>

                  <div className="storage-node-stats">
                    <span>
                      Reputation: <strong>{(node.reputation_score * 100).toFixed(0)}%</strong>
                    </span>
                    <span>
                      Latency: <strong>{node.mean_latency_ms.toFixed(0)}ms</strong>
                    </span>
                    <span>
                      Shards: <strong>{node.shards.length}</strong>
                    </span>
                  </div>

                  {node.shards.length > 0 && (
                    <div className="storage-node-shards">
                      {node.shards.map((s, i) => (
                        <span key={i} className="storage-shard-pill">
                          {s.model_id?.split("/").pop() || "unknown"}
                          {s.layer_range && s.layer_range.length >= 2 && (
                            <> L{s.layer_range[0]}-{s.layer_range[1]}</>
                          )}
                        </span>
                      ))}
                    </div>
                  )}

                  {node.last_heartbeat && (
                    <p className="storage-node-heartbeat">
                      Last heartbeat: {new Date(node.last_heartbeat).toLocaleString()}
                    </p>
                  )}

                  <div className="storage-node-actions">
                    <button className="toggle-btn" onClick={() => triggerChallenge(node.node_id)}>
                      Challenge
                    </button>
                    <button
                      className="toggle-btn key-btn-danger"
                      onClick={() => removeNode(node.node_id)}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </>
          )}

          {/* ── Shards tab ── */}
          {tab === "shards" && (
            <>
              {/* Download form */}
              <div className="storage-download-form">
                <h3>Download Shards</h3>
                <div className="storage-download-row">
                  <input
                    type="text"
                    className="key-input"
                    placeholder="Model ID (e.g. meta-llama/Llama-3.3-70B-Instruct)"
                    value={dlModelId}
                    onChange={(e) => setDlModelId(e.target.value)}
                  />
                </div>
                <div className="storage-download-row">
                  <input
                    type="text"
                    className="key-input"
                    placeholder="Layers (e.g. 0-15, blank for all)"
                    value={dlLayers}
                    onChange={(e) => setDlLayers(e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <input
                    type="password"
                    className="key-input"
                    placeholder="HF Token (optional)"
                    value={dlToken}
                    onChange={(e) => setDlToken(e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <button
                    className="submit-btn"
                    onClick={startDownload}
                    disabled={!dlModelId.trim() || dlPolling}
                    style={{ marginTop: 0 }}
                  >
                    {dlPolling ? "Downloading..." : "Download"}
                  </button>
                </div>

                {dlStatus && (
                  <div className={`storage-dl-status storage-dl-${dlStatus.status}`}>
                    {dlStatus.status === "downloading" && (
                      <>
                        <span className="stage-spinner" /> Downloading {dlStatus.model_id}
                        {dlStatus.layer_start !== undefined && dlStatus.layer_end !== undefined && dlStatus.layer_end !== -1 && (
                          <> (layers {dlStatus.layer_start}-{dlStatus.layer_end})</>
                        )}
                        ...
                      </>
                    )}
                    {dlStatus.status === "starting" && (
                      <><span className="stage-spinner" /> Starting download...</>
                    )}
                    {dlStatus.status === "complete" && (
                      <>Download complete: {dlStatus.files_downloaded} file(s)</>
                    )}
                    {dlStatus.status === "error" && (
                      <>Download failed: {dlStatus.error}</>
                    )}
                  </div>
                )}
              </div>

              {/* Disk usage */}
              <div className="storage-tab-header">
                <span className="muted">
                  {models.length} model{models.length !== 1 ? "s" : ""}
                  {diskUsage && <> &mdash; {diskUsage.total_gb} GB total</>}
                </span>
                <button className="toggle-btn" onClick={loadModels} disabled={shardsLoading}>
                  {shardsLoading ? "Loading..." : "Refresh"}
                </button>
              </div>

              {models.length === 0 && !shardsLoading && (
                <div className="storage-empty">
                  <p className="muted">No local shards. Use the download form above or the CLI.</p>
                </div>
              )}

              {models.map((m) => (
                <div key={m.model_id} className="storage-model-card">
                  <div className="storage-model-header">
                    <span className="storage-model-id" title={m.model_id}>{m.model_id}</span>
                    <span
                      className="tag"
                      style={{ background: m.complete ? "var(--color-ok)" : "var(--color-warn)", color: m.complete ? "#fff" : "#000" }}
                    >
                      {m.complete ? "complete" : "partial"}
                    </span>
                  </div>

                  <div className="storage-model-stats">
                    <span>Layers: <strong>{m.total_layers}</strong></span>
                    <span>Coverage: <strong>{m.layer_coverage.map(r => `${r[0]}-${r[1]}`).join(", ")}</strong></span>
                    <span>Precision: <strong>{m.precision}</strong></span>
                    <span>Files: <strong>{m.files}</strong></span>
                    <span>Size: <strong>{m.total_gb} GB</strong></span>
                  </div>

                  {verifyResults[m.model_id] && (
                    <div className="storage-verify-results">
                      {verifyResults[m.model_id].passed.length > 0 && (
                        <span style={{ color: "var(--color-ok)", fontSize: "0.78rem" }}>
                          {verifyResults[m.model_id].passed.length} passed
                        </span>
                      )}
                      {verifyResults[m.model_id].failed.length > 0 && (
                        <span style={{ color: "var(--color-err)", fontSize: "0.78rem" }}>
                          {verifyResults[m.model_id].failed.length} failed
                        </span>
                      )}
                      {verifyResults[m.model_id].missing.length > 0 && (
                        <span style={{ color: "var(--color-warn)", fontSize: "0.78rem" }}>
                          {verifyResults[m.model_id].missing.length} missing
                        </span>
                      )}
                    </div>
                  )}

                  {configResult && configModel === m.model_id && (
                    <p className="storage-config-result">{configResult}</p>
                  )}

                  <div className="storage-model-actions">
                    <button
                      className="toggle-btn"
                      onClick={() => handleVerify(m.model_id)}
                      disabled={verifying[m.model_id]}
                    >
                      {verifying[m.model_id] ? "Verifying..." : "Verify"}
                    </button>
                    <button
                      className="toggle-btn"
                      onClick={() => { setConfigModel(m.model_id); handleGenerateConfig(m.model_id); }}
                    >
                      Generate Config
                    </button>
                    <button
                      className="toggle-btn key-btn-danger"
                      onClick={() => handleRemoveModel(m.model_id)}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>

        <p className="settings-footer">
          {tab === "network"
            ? "Neighbor nodes sharing shards form mirrors when full layer coverage is achieved."
            : tab === "shard-map"
            ? "Visual grid of which nodes hold which layer blocks. Green = redundant, yellow = single copy."
            : tab === "nodes"
            ? "Nodes auto-register when started with --orchestrator."
            : "Download shards from HuggingFace, then generate a node config to start serving."}
        </p>
      </div>
    </div>
  );
}

/* ── Dependency Health Panel ──────────────────────────────────── */

interface DepCheck {
  name: string;
  category: string;
  severity: "ok" | "warn" | "error";
  message: string;
  hint: string;
}

interface DepReport {
  healthy: boolean;
  total: number;
  ok: number;
  warnings: number;
  errors: number;
  checks: DepCheck[];
}

function severityIcon(s: string): string {
  switch (s) {
    case "ok": return "\u2714";
    case "warn": return "\u26a0";
    case "error": return "\u2718";
    default: return "?";
  }
}

function severityColor(s: string): string {
  switch (s) {
    case "ok": return "var(--color-ok)";
    case "warn": return "var(--color-warn)";
    case "error": return "var(--color-err)";
    default: return "var(--color-muted)";
  }
}

const CATEGORY_LABELS: Record<string, string> = {
  runtime: "Runtime",
  python: "Python Packages",
  system: "System Tools",
  api_key: "API Keys",
};

function DependencyPanel({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const [report, setReport] = useState<DepReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/health/dependencies");
      if (res.ok) {
        setReport(await res.json());
      } else {
        setError(`Server returned ${res.status}`);
      }
    } catch {
      setError("Could not reach the backend.");
    }
    setLoading(false);
  };

  useEffect(() => {
    if (visible) loadReport();
  }, [visible]);

  if (!visible) return null;

  const categories = ["runtime", "python", "system", "api_key"];

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h2>Dependency Health</h2>
          <div className="settings-header-actions">
            <button className="toggle-btn" onClick={loadReport} disabled={loading}>
              {loading ? "Checking..." : "Re-check"}
            </button>
            <button className="settings-close" onClick={onClose} aria-label="Close">
              x
            </button>
          </div>
        </div>

        <div className="settings-body">
          {error && (
            <div className="agent-warning-item agent-warning-error">
              <span className="agent-warning-title">Check failed</span>
              <span className="agent-warning-detail">{error}</span>
            </div>
          )}

          {loading && !report && <p className="muted">Running dependency checks...</p>}

          {report && (
            <>
              {/* Summary */}
              <div
                className="dep-summary"
                style={{
                  padding: "0.75rem 1rem",
                  borderRadius: "6px",
                  marginBottom: "1rem",
                  background: report.healthy
                    ? "rgba(76, 175, 80, 0.1)"
                    : "rgba(244, 67, 54, 0.1)",
                  border: `1px solid ${report.healthy ? "var(--color-ok)" : "var(--color-err)"}`,
                }}
              >
                <p style={{ margin: 0, fontWeight: 600, color: report.healthy ? "var(--color-ok)" : "var(--color-err)" }}>
                  {report.healthy
                    ? `All clear \u2014 ${report.ok} passed, ${report.warnings} warning(s)`
                    : `Issues found \u2014 ${report.errors} error(s), ${report.warnings} warning(s), ${report.ok} ok`}
                </p>
              </div>

              {/* Checks grouped by category */}
              {categories.map((cat) => {
                const items = report.checks.filter((c) => c.category === cat);
                if (!items.length) return null;
                return (
                  <div key={cat} className="dep-category" style={{ marginBottom: "1rem" }}>
                    <h3 style={{ margin: "0 0 0.4rem 0", fontSize: "0.9rem" }}>
                      {CATEGORY_LABELS[cat] || cat}
                    </h3>
                    {items.map((c, i) => (
                      <div
                        key={i}
                        className="dep-check-row"
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          padding: "0.3rem 0.5rem",
                          borderLeft: `3px solid ${severityColor(c.severity)}`,
                          marginBottom: "0.3rem",
                          background: c.severity === "error"
                            ? "rgba(244, 67, 54, 0.05)"
                            : c.severity === "warn"
                            ? "rgba(255, 152, 0, 0.05)"
                            : "transparent",
                        }}
                      >
                        <span style={{ fontSize: "0.85rem" }}>
                          <span style={{ color: severityColor(c.severity), marginRight: "0.4rem" }}>
                            {severityIcon(c.severity)}
                          </span>
                          {c.message}
                        </span>
                        {c.hint && (
                          <span className="muted" style={{ fontSize: "0.78rem", marginLeft: "1.4rem" }}>
                            {c.hint}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                );
              })}
            </>
          )}
        </div>

        <p className="settings-footer">
          Checks Python packages, system tools, API keys, and runtime environment.
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
  const [storageOpen, setStorageOpen] = useState(false);
  const [depsOpen, setDepsOpen] = useState(false);

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
        <span className="version">v0.7.2</span>
        <div className="header-actions">
          <button
            className="toggle-btn settings-btn"
            onClick={() => setDepsOpen(true)}
            title="Dependency Health Check"
          >
            Health
          </button>
          <button
            className="toggle-btn settings-btn"
            onClick={() => setStorageOpen(true)}
            title="Storage Network"
          >
            Storage
          </button>
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

      <DependencyPanel visible={depsOpen} onClose={() => setDepsOpen(false)} />
      <StoragePanel visible={storageOpen} onClose={() => setStorageOpen(false)} />
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
