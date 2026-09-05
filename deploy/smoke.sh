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

say "smoke test passed"
