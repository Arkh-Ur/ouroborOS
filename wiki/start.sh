#!/usr/bin/env bash
set -euo pipefail

# start.sh — Launch ouroborOS wiki dev server
# Usage: ./start.sh [options]
#   --port PORT    Port to bind (default: 4321)
#   --host HOST    Host to bind (default: 0.0.0.0)
#   -h, --help     Show this help

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${ASTRO_PORT:-4321}"
HOST="0.0.0.0"

usage() {
    echo "Usage: ./start.sh [--port PORT] [--host HOST] [-h|--help]"
    echo ""
    echo "Launch the ouroborOS wiki dev server (Astro + Starlight)."
    echo ""
    echo "Options:"
    echo "  --port PORT    Port to bind (default: 4321, or ASTRO_PORT env var)"
    echo "  --host HOST    Host to bind (default: 0.0.0.0)"
    echo "  -h, --help     Show this help"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)
            PORT="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if ! command -v node &>/dev/null; then
    echo "Error: node is not installed" >&2
    exit 1
fi

if [[ ! -d "node_modules" ]]; then
    echo "Installing dependencies..."
    npm install
fi

echo "Starting ouroborOS wiki on ${HOST}:${PORT}"
echo "  Local:    http://localhost:${PORT}/"

LAN_IP="$(ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '127.0.0.1' | head -1 || true)"
if [[ -n "$LAN_IP" ]]; then
    echo "  Network:  http://${LAN_IP}:${PORT}/"
fi

echo ""

exec npx astro dev --host "$HOST" --port "$PORT"
