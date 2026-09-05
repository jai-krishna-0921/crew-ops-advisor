#!/usr/bin/env bash
# Build the image and roll it out. The whole pipeline, in one command, run
# the same way by a laptop and by CI, so a deploy from GitHub Actions cannot
# drift from a deploy by hand.
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.sh

TAG="${TAG:-$(git rev-parse --short HEAD)}"
RUN_SA="${SERVICE}-run@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

if [ "${SKIP_BUILD:-0}" != "1" ]; then
  say "building ${TAG}"
  docker build -t "${REGISTRY}/${SERVICE}:${TAG}" -t "${REGISTRY}/${SERVICE}:latest" .
  docker push "${REGISTRY}/${SERVICE}:${TAG}"
  docker push "${REGISTRY}/${SERVICE}:latest"
else
  gcloud artifacts docker images describe "${REGISTRY}/${SERVICE}:${TAG}" \
    --project "$PROJECT_ID" >/dev/null 2>&1 \
    || die "SKIP_BUILD is set but ${REGISTRY}/${SERVICE}:${TAG} does not exist. \
Build it, or pass TAG=<a tag that was built>."
fi

# COST CONTROLS, READ BEFORE RAISING ANY OF THESE:
#   --min-instances 0   the whole saving. Nobody using the demo, nothing billed.
#   --max-instances 2   a hard ceiling on the worst case, not a capacity plan.
#   --cpu 1 --memory 1Gi  three lightweight processes (Ollama Cloud does the
#                         model inference, not this container) plus nginx.
#                         Raise memory first if a cold start OOMs.
#   default CPU throttling (no --no-cpu-throttling): CPU is only allocated
#                         while a request is in flight, which is correct here
#                         because nothing runs on a background thread outside
#                         a request.
#   --execution-environment gen2: needed for the voice WebSocket and for
#                         running three processes in one container; gen1's
#                         sandbox is more restrictive about both.
#
# OLLAMA_HOST IS THE CLOUD API, NOT A LOCAL DAEMON, and that is why the
# container ships without one. ollama/_client.py reads OLLAMA_API_KEY into an
# Authorization header and OLLAMA_HOST as the base URL, so this talks to
# Ollama Cloud directly. A local daemon instead signs upstream calls with a
# machine keypair that "ollama signin" registers to an account, which a fresh
# container never has: the key is correct, every cloud call comes back 401,
# and the same key works on a laptop. comarketer's Cloud Run deployment sets
# exactly this pair, and ships no ollama binary either.
#
# OLLAMA_API_KEY still comes first in the provider's selects_on order, so the
# default model stays deepseek-v4-flash:cloud (the measured one) rather than
# falling back to the OLLAMA_HOST default of qwen3:8b.
say "deploying ${SERVICE}"
gcloud run deploy "$SERVICE" \
  --image "${REGISTRY}/${SERVICE}:${TAG}" \
  --project "$PROJECT_ID" --region "$REGION" \
  --service-account "$RUN_SA" \
  --labels="hackathon=${HACKATHON_LABEL}" \
  --execution-environment=gen2 \
  --allow-unauthenticated \
  --port 8080 \
  --cpu 1 --memory 1Gi \
  --min-instances 0 --max-instances 2 --concurrency 20 --timeout 3600 \
  --set-env-vars "OLLAMA_HOST=https://ollama.com,CREWOPS_VOICE_PROVIDER=sarvam,CREWOPS_SARVAM_STT_MODEL=saaras:v3-realtime,CREWOPS_SARVAM_TTS_MODEL=bulbul:v3,CREWOPS_SARVAM_VOICE=shubh" \
  --set-secrets "OLLAMA_API_KEY=${SECRET_OLLAMA_KEY}:latest,SARVAM_API_KEY=${SECRET_SARVAM_KEY}:latest" \
  --quiet

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
say "live at ${URL}"
