#!/usr/bin/env bash
# Build the production image and run it locally on http://localhost:8080
#   GEMINI_API_KEY=... ./deploy/run_local_docker.sh        # real Gemini
#   MOCK_LLM=1 ./deploy/run_local_docker.sh                # canned responses, no key
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8080}"
docker build -f deploy/Dockerfile -t annadrishti:local .
docker rm -f annadrishti-local >/dev/null 2>&1 || true
echo "Serving on http://localhost:$PORT  (Ctrl-C to stop)"
exec docker run --rm --name annadrishti-local -p "$PORT:8080" \
  -e GEMINI_API_KEY="${GEMINI_API_KEY:-}" -e GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.8-flash}" \
  -e MOCK_LLM="${MOCK_LLM:-0}" -e USE_VERTEX="${USE_VERTEX:-0}" \
  -e GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-}" \
  annadrishti:local
