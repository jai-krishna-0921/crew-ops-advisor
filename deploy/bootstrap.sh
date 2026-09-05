#!/usr/bin/env bash
# Project label, APIs, registry, and the runtime service account. Run once,
# by hand, by whoever has the rights to enable APIs and create service
# accounts in $PROJECT_ID.
#
# Idempotent throughout: every step either creates a thing or reports it is
# already there. A bootstrap script somebody is afraid to re-run is one that
# gets run by hand instead.
#
# It does NOT put a value in the Ollama secret. deploy/secrets.sh does that,
# separately, so this file can be safe to read in a PR and that one can be run
# from a terminal with a key pasted into it and never committed.
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.sh

say "project ${PROJECT_ID}"
gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1 \
  || die "project ${PROJECT_ID} does not exist or you cannot see it"

say "labeling the project (not creating a new one)"
# Project-level label updates are alpha-only in gcloud; every other command in
# this file is stable.
gcloud alpha projects update "$PROJECT_ID" \
  --update-labels="hackathon=${HACKATHON_LABEL}" --quiet

say "enabling APIs"
gcloud services enable \
  run.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com iam.googleapis.com iamcredentials.googleapis.com \
  --project "$PROJECT_ID" --quiet

say "artifact registry ${REPO} in ${REGION}"
gcloud artifacts repositories describe "$REPO" \
  --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "$REPO" \
      --repository-format=docker --location "$REGION" \
      --labels="hackathon=${HACKATHON_LABEL}" \
      --description="Extroc demo images (Bessemer Tech Catalyst hackathon)" \
      --project "$PROJECT_ID" --quiet

# Untagged image storage is the one part of this that keeps costing money
# quietly after the hackathon is over. Every push here is tagged with a
# commit SHA and never overwritten, so without this the registry only grows.
say "keep only the 5 newest images"
cat > /tmp/extroc-cleanup-policy.json <<'EOF'
[
  {
    "name": "keep-recent",
    "action": { "type": "Keep" },
    "mostRecentVersions": { "keepCount": 5 }
  },
  {
    "name": "delete-the-rest",
    "action": { "type": "Delete" },
    "condition": { "tagState": "ANY" }
  }
]
EOF
gcloud artifacts repositories set-cleanup-policies "$REPO" \
  --location "$REGION" --project "$PROJECT_ID" \
  --policy=/tmp/extroc-cleanup-policy.json --quiet
rm -f /tmp/extroc-cleanup-policy.json

say "runtime service account"
RUN_SA="${SERVICE}-run@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts describe "$RUN_SA" --project "$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "${SERVICE}-run" \
      --display-name="Extroc Cloud Run runtime" --project "$PROJECT_ID" --quiet

# Least privilege on purpose: the running container reads one secret's value
# and does nothing else. It has no storage, no logging admin, and no ability
# to deploy or modify itself.
say "granting secret access to the runtime account"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUN_SA}" \
  --role="roles/secretmanager.secretAccessor" --quiet >/dev/null

say "creating secret names (values come later, from deploy/secrets.sh)"
for name in "$SECRET_OLLAMA_KEY" "$SECRET_SARVAM_KEY"; do
  gcloud secrets describe "$name" --project "$PROJECT_ID" >/dev/null 2>&1 \
    || gcloud secrets create "$name" --replication-policy=automatic \
        --labels="hackathon=${HACKATHON_LABEL}" --project "$PROJECT_ID" --quiet
done

say "done. next: deploy/secrets.sh, then deploy/github-oidc.sh, then deploy/release.sh"
