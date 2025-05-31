# Maestro-Orchestrator

**Maestro-Orchestrator** is an AI governance and reasoning framework designed to coordinate multiple large language models (LLMs) into a single collaborative system. This approach fosters diversity of thought and structured dissent among synthetic agents, allowing for richer and more ethical decision-making processes.

---

## 🔍 Project Goals

- Create a decentralized orchestration engine that harmonizes multiple AI models.
- Preserve and integrate structured dissent using a quorum-style mechanism (e.g., 66% agreement).
- Log all reasoning history for transparency, auditability, and meta-analysis.
- Build toward a consensus ledger system for immutably recording reality snapshots.

---

## 🛠️ Current Status (as of May 31, 2025)

- ✅ Core CLI for livefire orchestration is operational.
- ✅ Multi-model support functional (OpenAI, Anthropic/Claude, OpenRouter).
- ✅ Structured logging of session results via rotating JSON logs.
- ⚠️ Prism (Google/Gemini) is temporarily disabled due to API instability.
- ⚠️ Some agents return mock responses until official APIs are reinstated or stabilized.
- 🔄 GitHub push protections enforced due to historical leakage of .env credentials (resolved locally).

---

## 🚧 Limitations

- No true automated quorum synthesis yet; decisions still surfaced manually.
- Prism agent needs reactivation once key issues with model IDs are resolved.
- Agent personalities are static; no meta-learning or reflection implemented.
- Push protection on GitHub restricts ease of iteration due to past credential commits.

---

## 🧪 3WM PoC Note

The "Three Wisemen" proof-of-concept (3WM PoC) was an experimental subproject meant to simulate AI council behavior using whimsical symbolic roles. It served as a personal exploration of orchestration under metaphorical framing. However, **it is not part of the core project architecture** and is retained for historical reference only.

---

## 🔒 Security & Ethics

- Secrets are no longer tracked via Git.
- All agent calls are wrapped in clear environmental variable management.
- Project adheres to transparency-first principles, with clear logging and agent attribution.

---

## 🤝 Contributing

Due to the experimental nature of this repository, contributions are welcome but should follow the orchestration philosophy defined above. Real-world deployments should be vetted for ethical safety and agent behavior bounds.

---

## 📜 License

MIT License

© 2025 defcon


# Maestro Orchestrator

Maestro is a modular orchestration framework designed to manage dissent and decision-making across large language models. It embodies a 66% quorum rule to ensure structured disagreement and avoid monolithic AI alignment.

## Project Goals
- Coordinate multiple intelligent agents
- Maintain structured dissent (Three Wisemen model)
- Enable consensus synthesis through quorum voting
- Build a planetary-scale truth synthesis framework

## Quickstart
1. Clone the repo:
   ```bash
   git clone https://github.com/d3fq0n1/maestro-orchestrator.git
   cd maestro-orchestrator
   ```

2. Run mock orchestration (example CLI coming soon):
   ```bash
   python orchestrator.py --agents 3 --quorum 66
   ```

3. Sync your local repo changes:
   ```powershell
   .\scripts\combosync.ps1
   ```

## Repository Structure

| Folder       | Purpose |
|--------------|---------|
| `docs/`      | Whitepaper, roadmap, vision |
| `scripts/`   | Developer automation scripts |
| `images/`    | System diagrams |
| `README.md`  | This file |
| `orchestrator.py` | CLI entrypoint (planned) |

## Contributing
See `CONTRIBUTING.md` for details.

## License
See `license.md`



## 🎛️ CLI Showcase (Mock Orchestrator)

The `maestro_cli.py` script provides a mock simulation of quorum-based decision-making among named agents.

### Features:
- Multi-round orchestration
- Rotating agent roles (scribe, dissenter, strategist, analyst, arbiter)
- Structured dissent + quorum enforcement (66% default)
- JSON log output + persistent session history
- Ready for future LLM integration (uncommentable stubs)

### Usage:

```bash
# Run default 3-round session with verbose output
python maestro_cli.py --verbose --rounds 3

# Save session logs
python maestro_cli.py --rounds 5 --save-log

# Specify custom agents
python maestro_cli.py --agents Alpha Beta Gamma --rounds 2
```

### Output:
- Logs saved to `scripts/council_session/logs/`
- Persistent history stored in `history/session_log.jsonl`
