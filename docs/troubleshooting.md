# Troubleshooting

## Common Issues

### API key errors

You need at least one provider key. There are several ways to configure them:

1. **TUI setup wizard** (recommended for terminal users): Launch the TUI (`python -m maestro.tui`) and press `S` to open the setup wizard. It walks through each provider and lets you paste keys directly. On first launch the wizard opens automatically.

2. **Web-UI**: The settings panel opens automatically on first launch in the browser.

3. **`.env` file**: Copy from `.env.example` and fill in your keys:
```bash
cp .env.example .env
```

4. **CLI key tool**: `python -m maestro.cli_keys set openai sk-...`

Required keys (at minimum one):
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `OPENROUTER_API_KEY`

Tips for entering long API keys:
- Copy the key from your provider's dashboard
- In most terminals, paste with right-click or `Ctrl+Shift+V`
- The TUI setup wizard masks input for security
- Keys are saved to `.env` and never leave your machine

### Backend won't start

Verify you have all dependencies installed:

```bash
pip install -r requirements.txt
```

Run with:

```bash
uvicorn backend.main:app --reload --port 8000
```

### Frontend can't reach backend

- Ensure the backend is running on port 8000
- The Vite dev server proxies `/api` requests to the backend automatically (see `frontend/vite.config.ts`)
- CORS is enabled in the FastAPI backend for local development

### Docker build fails

- Use `make build` (or `docker compose build --no-cache`) if the frontend build seems stale
- The `.env` file is optional -- if you have one, ensure it has valid syntax

### Container won't start or isn't healthy

- Check logs: `make logs`
- Check health: `make status`
- The health check polls `GET /api/health` -- if it fails, the backend may not be starting correctly

### Rate limit errors

Each API provider has its own rate limits. If an agent returns errors:
- Check your API key is valid and has sufficient quota
- Add delays between batch orchestration rounds if needed
- The system gracefully handles individual agent failures without crashing

### TUI won't start or looks broken

- Ensure your terminal is at least 80 columns wide and 24 rows tall
- The TUI requires the `textual` package: `pip install textual`
- If single-key shortcuts don't work, make sure the prompt input is **not** focused (press `Escape` to unfocus it, then try the key)
- Press `P` to focus the prompt input when you want to type a query
- If the TUI auto-opens the setup wizard, it means no API keys are configured — paste at least one key to continue

### Redis port conflict when spawning cluster instances

If you see `Bind for 0.0.0.0:6399 failed: port is already allocated` when spawning a shard via the TUI instance manager, it means another process is already using port 6399. Common causes:

1. **A previous `maestro-shared-redis` container wasn't cleaned up.** Run:
   ```bash
   docker rm -f maestro-shared-redis
   ```

2. **Another Redis or service is bound to port 6399.** Identify it with:
   ```bash
   # Linux
   ss -tlnp | grep 6399
   # macOS
   lsof -i :6399
   ```
   Stop the conflicting process, then retry.

3. **A full `docker compose up` was run before using the TUI instance manager.** The per-stack Redis in docker-compose.yml uses `REDIS_PORT` (default 6379), but if `REDIS_PORT=6399` leaked into your environment it will collide. Unset it:
   ```bash
   unset REDIS_PORT
   ```

The TUI instance manager now checks port availability before starting the shared Redis container and will display a clear error if the port is occupied.

### TUI crashes when pressing N (Nodes)

If you see `AttributeError: 'list' object has no attribute '_append'` when pressing `N` to open the Node Details modal, this was a bug where `NodeDetailScreen` stored node data as `self._nodes`, overwriting Textual's internal `_nodes` attribute. Fixed in v7.1.6 — renamed to `self._node_data`.

### TUI crashes with `BadIdentifier` error

If you see an error like `'agent-Claude Sonnet 4.6' is an invalid id`, this was a bug where agent display names containing spaces or dots were used directly as Textual widget IDs. Fixed in v7.1.5 — agent names are now sanitized (spaces and special characters replaced with hyphens) before being used as widget identifiers.

---

For architecture details, see [`architecture.md`](./architecture.md).
For quorum logic, see [`quorum_logic.md`](./quorum_logic.md).
For the full TUI reference, see [`ui-guide.md`](./ui-guide.md).
