#!/usr/bin/env bash
# Run the private voice-demo website (Spec 3 + Spec 1 submit endpoint).
#
# Usage:
#   SITE_TOKEN=secret ./run_site.sh [--host 127.0.0.1] [--port 8000]
#
# Env overrides: HOST, PORT, SITE_TOKEN, STORAGE_ROOT, DB_PATH, MAX_UPLOAD_MB.
# Binds localhost only (SITE-NF-001); all routes except /healthz require the
# shared token (SITE-B-001):  Authorization: Bearer $SITE_TOKEN
set -euo pipefail

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: SITE_TOKEN=secret $0 [--host 127.0.0.1] [--port 8000]"
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ "${SITE_TOKEN:-change-me}" == "change-me" ]]; then
  echo "WARNING: SITE_TOKEN is unset (using insecure default 'change-me')." >&2
  echo "Set a secret:  SITE_TOKEN=\$(python -c 'import secrets;print(secrets.token_hex(16))') $0" >&2
fi

export STORAGE_ROOT="${STORAGE_ROOT:-storage}"
export DB_PATH="${DB_PATH:-$STORAGE_ROOT/app.db}"
mkdir -p "$STORAGE_ROOT"

if ! python -c "import fastapi, uvicorn" 2>/dev/null; then
  echo "Installing web deps (fastapi, uvicorn, python-multipart)..." >&2
  pip install fastapi uvicorn python-multipart
fi

echo "Serving private demo at http://$HOST:$PORT/  (health: /healthz)" >&2
exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
