# Setup Guide

For complete setup instructions, see:

- [Quickstart](./quickstart.md) -- minimal steps to get running
- [Deployment Guide](./deployment.md) -- local, Docker, and production deployment
- [Architecture](./architecture.md) -- system architecture and data flow

## Quick Reference

### Docker (Recommended)

```bash
make setup
```

This builds the container, waits for the health check, and opens your browser. No `.env` needed -- configure keys in the Web-UI.

After initial setup: `make up` / `make down` / `make logs` / `make status`

### Local Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your API keys
make dev               # starts backend + frontend together
```

Application (UI + API): `http://localhost:8000`
