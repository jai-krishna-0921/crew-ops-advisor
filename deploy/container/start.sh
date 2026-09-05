#!/usr/bin/env bash
# One container, three processes: uvicorn (FastAPI, the deterministic core and
# the agent), node (the built Next.js server), and nginx (the one thing Cloud
# Run's single port actually talks to). Neither backing process is reachable
# from outside the container; nginx is the whole attack surface.
#
# There is deliberately no `ollama serve` here. The model is called over
# https://ollama.com with OLLAMA_API_KEY (see the Dockerfile header and
# deploy/release.sh), which is what comarketer's Cloud Run deployment does
# too. A local daemon authenticates upstream with a registered keypair, not
# with the key, so in a container it is 401s and dead weight.
set -euo pipefail

LISTEN_PORT="${PORT:-8080}"
mkdir -p /tmp/nginx
LISTEN_PORT="${LISTEN_PORT}" envsubst '${LISTEN_PORT}' \
  < /etc/nginx/nginx.conf.template > /tmp/nginx.conf

CREWOPS_DATA_DIR=/app/data/crew-ops-advisor-dataset/data \
  uvicorn --factory crewops.server.app:create_app --host 127.0.0.1 --port 8000 &
API_PID=$!

(cd /app/web && PORT=3000 HOSTNAME=127.0.0.1 node server.js) &
WEB_PID=$!

# nginx must not take traffic before the two things it proxies to can answer:
# Cloud Run's own health check would otherwise pass against an nginx that is
# up while a request coming through it 502s.
ready() {
  for _ in $(seq 1 60); do
    curl -fsS "http://127.0.0.1:$1$2" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}
ready 8000 /api/health || echo "warning: FastAPI did not answer /api/health in time, starting nginx anyway"
ready 3000 / || echo "warning: Next.js did not answer / in time, starting nginx anyway"

nginx -c /tmp/nginx.conf -g "daemon off;" &
NGINX_PID=$!

# Cloud Run sends SIGTERM on scale-down or a new revision; propagate it to all
# three processes instead of leaving two orphaned when the shell exits.
terminate() {
  kill -TERM "$API_PID" "$WEB_PID" "$NGINX_PID" 2>/dev/null || true
}
trap terminate TERM INT

wait -n "$API_PID" "$WEB_PID" "$NGINX_PID"
terminate
wait
