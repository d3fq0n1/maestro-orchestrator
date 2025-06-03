// src/maestroUI.tsx
import React, { useState } from "react";

interface AgentResponses {
  [agent: string]: string;
}

interface HistoryEntry {
  prompt: string;
  responses?: AgentResponses;
  quorum?: {
    consensus: string;
    votes: Record<string, number>;
  };
  error?: string;
}

const agentEmojis: Record<string, string> = {
  Sol: "🧠",
  Aria: "🌱",
  Prism: "🌈",
  TempAgent: "🔮",
};

export default function MaestroUI() {
  const [prompt, setPrompt] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const sendPrompt = async () => {
    if (!prompt.trim()) return;
    setLoading(true);
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });

      if (!res.ok) throw new Error("API returned non-200");

      const data = await res.json();
      setHistory((prev) => [...prev, { prompt, ...data }]);
      setTimeout(() => window.scrollTo(0, document.body.scrollHeight), 100);
    } catch (err) {
      console.error("API call failed:", err);
      setHistory((prev) => [...prev, { prompt, error: "❌ API call failed or server unavailable." }]);
      setTimeout(() => window.scrollTo(0, document.body.scrollHeight), 100);
    } finally {
      setPrompt("");
      setLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-4xl mx-auto text-white min-h-screen bg-zinc-900">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold flex items-center space-x-2">
          <span role="img" aria-label="brain">🧠</span>
          <span>Maestro-Orchestrator</span>
        </h1>
        <button
          className="text-sm border border-zinc-600 px-2 py-1 rounded hover:bg-zinc-800"
          onClick={() => {
            document.documentElement.classList.toggle("dark");
          }}
        >
          Toggle Mode
        </button>
      </div>

      <div className="mb-4">
        <textarea
          className="w-full p-3 border border-zinc-600 rounded-md bg-zinc-800 text-white"
          rows={5}
          placeholder="Ask the council..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={loading}
        />
        <button
          onClick={sendPrompt}
          disabled={loading}
          className="mt-2 px-4 py-2 rounded bg-zinc-700 hover:bg-zinc-600"
        >
          {loading ? "Thinking..." : "Submit"}
        </button>
      </div>

      <div className="space-y-4">
        {history.map((entry, idx) => (
          <div key={idx} className="p-4 border border-zinc-700 rounded bg-zinc-800">
            <p className="text-sm text-zinc-400 mb-2">📝 {entry.prompt}</p>
            {entry.responses ? (
              Object.entries(entry.responses).map(([agent, response]) => {
                const display = response?.trim() ? response : "⚠️ No response received.";
                return (
                  <div key={agent} className="mb-1">
                    <strong>{agentEmojis[agent] || agent}: {agent}</strong> {display}
                  </div>
                );
              })
            ) : (
              <p className="text-red-500 text-sm">{entry.error}</p>
            )}
            {entry.quorum && (
              <div className="text-xs mt-2 italic text-zinc-400">
                🗳️ Quorum: {entry.quorum.consensus || "No consensus"}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
