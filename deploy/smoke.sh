#!/usr/bin/env bash
# The minimum check that a rollout actually answers, run right after
# deploy/release.sh so a broken revision is caught in the pipeline rather
# than by the next person who opens the demo.
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.sh

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
[ -n "$URL" ] || die "could not resolve the service URL"

say "checking ${URL}/api/health"
BODY="$(curl -fsS "${URL}/api/health")" || die "the API did not answer at all"
echo "$BODY"
echo "$BODY" | grep -q '"dataset_loaded":true' || die "dataset_loaded is not true"

say "checking ${URL}/"
curl -fsS -o /dev/null "${URL}/" || die "the web app did not answer"

# THE ORIGIN HEADER IS THE WHOLE POINT OF THIS CHECK. Voice broke in a
# deployment that passed every other test here, because the WebSocket route
# refuses an Origin it does not know and curl does not send one by default. A
# handshake without Origin proves nothing a browser cares about.
say "checking the voice WebSocket accepts a browser Origin"
# A 101 here means curl then sits on an open socket until --max-time kills it,
# which is the healthy shape and not a failure: the status is already
# recorded by then. A refused origin answers 403 immediately instead.
STATUS="$(curl -sS -o /dev/null -w '%{http_code}' -m 8 --http1.1 \
  "${URL}/api/voice/session?provider=sarvam" \
  -H "Origin: ${URL}" \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" 2>/dev/null || true)"
[ "$STATUS" = "101" ] \
  || die "the voice WebSocket answered ${STATUS} to an Origin of ${URL}, not 101. \
Add that origin to CREWOPS_ALLOWED_ORIGINS."

say "smoke test passed"
