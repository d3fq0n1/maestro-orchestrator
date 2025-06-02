# Council Session Runner

This module runs multi-round council deliberations with configurable agent count, roles, and quorum rules. Logs are saved for each round in JSON format and analyzed for dissent.

## Features

- Dynamic quorum and voting logic
- Role rotation across rounds
- Persistence of full agent prompts and responses
- Automatic markdown generation for session summaries
- Modular structure allows integration with CLI or web frontend

## Usage

Run directly:

```bash
python scripts/council_session/run_council_session.py
```

Logs will be stored in `scripts/council_session/logs/` and summaries appear in `docs/`.

### Notes

- Requires `.env` for API keys
- Currently hardcoded agents: Sol, Aria, OpenRouter
- Will integrate with MAGI and R2 Engine in future roadmap
