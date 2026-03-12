.PHONY: up down build logs status clean dev setup update help spawn down-all instances

# Default target
help:
	@echo ""
	@echo "  Maestro-Orchestrator"
	@echo "  ────────────────────────────────────────"
	@echo ""
	@echo "  make setup         First-time setup (build + start + open browser)"
	@echo "  make up            Start the container (detached)"
	@echo "  make down          Stop and remove the container"
	@echo "  make build         Rebuild the Docker image"
	@echo "  make logs          Tail container logs"
	@echo "  make status        Show all running instances and health"
	@echo "  make clean         Stop container and remove volumes"
	@echo "  make update        Pull latest changes and rebuild"
	@echo "  make dev           Start local dev servers (no Docker)"
	@echo ""
	@echo "  Multi-instance:"
	@echo "  make spawn         Spawn one additional Maestro instance"
	@echo "  make spawn N=3     Spawn N additional instances"
	@echo "  make instances N=3 Deploy N fresh instances"
	@echo "  make down-all      Stop all Maestro instances"
	@echo ""

# First-time setup: build, start, wait for healthy, open browser
setup:
	@python3 setup.py || python setup.py

# Start in detached mode
up:
	docker compose up -d --build
	@echo ""
	@echo "  Maestro is starting at http://localhost:8000"
	@echo "  Run 'make logs' to watch output or 'make status' to check health."
	@echo ""

# Stop
down:
	docker compose down

# Rebuild without cache
build:
	docker compose build --no-cache

# Follow logs
logs:
	docker compose logs -f

# Health and container status (all instances)
status:
	@python3 setup.py --status 2>/dev/null || python setup.py --status 2>/dev/null || (docker compose ps && echo "")

# Stop and wipe volumes (sessions, R2 ledger, saved keys)
clean:
	@echo "This will delete all sessions, R2 data, and saved API keys."
	@read -p "  Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	docker compose down -v

# Pull latest changes and rebuild
update:
	@echo "  Pulling latest changes ..."
	git pull origin $$(git rev-parse --abbrev-ref HEAD)
	@echo "  Rebuilding and restarting ..."
	docker compose up -d --build
	@echo ""
	@echo "  Update complete!"
	@echo ""

# Local development (no Docker)
dev:
	@echo "Starting backend on :8000 and frontend on :5173 ..."
	@trap 'kill 0' EXIT; \
		(cd backend && uvicorn main:app --reload --port 8000) & \
		(cd frontend && npm install --silent && npm run dev) & \
		wait

# ── Multi-instance targets ────────────────────────────────────────────

# Spawn additional instance(s) (default N=1)
N ?= 1
spawn:
	@python3 setup.py --spawn $(N) --no-browser || python setup.py --spawn $(N) --no-browser

# Deploy N fresh instances (default N=1)
instances:
	@python3 setup.py --instances $(N) --no-browser || python setup.py --instances $(N) --no-browser

# Stop all running Maestro instances
down-all:
	@python3 setup.py --down || python setup.py --down
