# Troubleshooting

## Common Issues

### API key errors

Ensure `.env` is configured with valid keys. Copy from `.env.example`:

```bash
cp .env.example .env
```

Required keys (at minimum one):
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `OPENROUTER_API_KEY`

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

- Use `--no-cache` if the frontend build seems stale:
  ```bash
  docker-compose build --no-cache
  ```
- Ensure `.env` exists in the project root

### Rate limit errors

Each API provider has its own rate limits. If an agent returns errors:
- Check your API key is valid and has sufficient quota
- Add delays between batch orchestration rounds if needed
- The system gracefully handles individual agent failures without crashing

---

For architecture details, see [`architecture.md`](./architecture.md).
For quorum logic, see [`quorum_logic.md`](./quorum_logic.md).
