

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
