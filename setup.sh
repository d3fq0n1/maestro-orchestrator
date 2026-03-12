#!/usr/bin/env bash
# ──────────────────────────────────────────────
# Maestro-Orchestrator — One-command setup
# ──────────────────────────────────────────────
set -euo pipefail

PORT="${MAESTRO_PORT:-8000}"
URL="http://localhost:$PORT"
COMPOSE="docker compose"

# Fall back to docker-compose (v1) if docker compose (v2) is missing
if ! $COMPOSE version &>/dev/null; then
    COMPOSE="docker-compose"
fi

# ── Pre-flight checks ──────────────────────────
check_deps() {
    local missing=()
    command -v docker &>/dev/null || missing+=("docker")
    $COMPOSE version &>/dev/null || missing+=("docker compose")

    if [ ${#missing[@]} -gt 0 ]; then
        echo "Error: missing required tools: ${missing[*]}"
        echo "Install Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi
}

# ── Open browser (cross-platform) ──────────────
open_browser() {
    local url="$1"
    if command -v xdg-open &>/dev/null; then
        xdg-open "$url" 2>/dev/null &
    elif command -v open &>/dev/null; then
        open "$url" &
    elif command -v start &>/dev/null; then
        start "$url" &
    else
        echo "  Open your browser to: $url"
        return
    fi
    echo "  Browser opened to $url"
}

# ── Wait for the health endpoint ────────────────
wait_for_healthy() {
    local retries=30
    local delay=2
    echo -n "  Waiting for Maestro to start "
    for i in $(seq 1 $retries); do
        if curl -sf "$URL/api/health" >/dev/null 2>&1; then
            echo " ready!"
            return 0
        fi
        echo -n "."
        sleep "$delay"
    done
    echo ""
    echo "  Warning: Maestro did not respond within $((retries * delay))s."
    echo "  Check logs with: make logs"
    return 1
}

# ── Main ────────────────────────────────────────
main() {
    echo ""
    echo "  ╔══════════════════════════════════════╗"
    echo "  ║    Maestro-Orchestrator Setup        ║"
    echo "  ╚══════════════════════════════════════╝"
    echo ""

    check_deps

    # Ensure .env exists so docker-compose doesn't error on a missing env_file.
    touch .env

    echo "  Stopping any existing containers ..."
    $COMPOSE down --remove-orphans 2>/dev/null || true

    # Kill leftover processes from prior Maestro sessions holding the port.
    if command -v lsof &>/dev/null; then
        local pids
        pids=$(lsof -ti :"$PORT" 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo "  Killing leftover processes on port $PORT (PIDs: $pids) ..."
            echo "$pids" | xargs kill -9 2>/dev/null || true
            sleep 1
        fi
    elif command -v ss &>/dev/null; then
        local pids
        pids=$(ss -tlnp "sport = :$PORT" 2>/dev/null | grep -oP 'pid=\K[0-9]+' || true)
        if [ -n "$pids" ]; then
            echo "  Killing leftover processes on port $PORT (PIDs: $pids) ..."
            echo "$pids" | xargs kill -9 2>/dev/null || true
            sleep 1
        fi
    fi

    # Stop stale Docker containers (from manual runs) holding the port.
    local stale
    stale=$(docker ps -q --filter "publish=$PORT" 2>/dev/null || true)
    if [ -n "$stale" ]; then
        echo "  Stopping stale Docker containers on port $PORT ..."
        echo "$stale" | xargs docker rm -f 2>/dev/null || true
    fi

    echo "  Building and starting containers ..."
    $COMPOSE up -d --build

    echo ""
    if wait_for_healthy; then
        open_browser "$URL"
    fi

    echo ""
    echo "  Maestro is running at $URL"
    echo ""
    echo "  Useful commands:"
    echo "    make logs     Tail container logs"
    echo "    make status   Check container health"
    echo "    make down     Stop all containers"
    echo ""
}

main "$@"
