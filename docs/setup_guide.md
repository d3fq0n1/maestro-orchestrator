# Setup Guide

For complete setup instructions, see:

- [Quickstart](./quickstart.md) -- minimal steps to get running
- [Deployment Guide](./deployment.md) -- local, Docker, and production deployment
- [Architecture](./architecture.md) -- system architecture and data flow

## Quick Reference

### Docker (Recommended)

```bash
python setup.py          # works on Windows, macOS, and Linux
```

On macOS/Linux you can also use `make setup`.

This builds the container, waits for the health check, and opens your browser. No `.env` needed -- configure keys in the Web-UI.

After initial setup: `docker compose up -d` / `docker compose down` / `docker compose logs -f` (or use the equivalent `make` shortcuts on macOS/Linux).

### Local Development

```bash
python -m venv venv
source venv/bin/activate        # macOS/Linux
# .\venv\Scripts\activate       # Windows (PowerShell)
pip install -r requirements.txt
cp .env.example .env            # add your API keys
python setup.py --dev           # starts backend + frontend together
```

Application (UI + API): `http://localhost:8000`
