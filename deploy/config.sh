# One place every deploy script reads its target from. Sourced, never
# executed. A variable already set in the environment wins, so a second
# environment is `PROJECT_ID=... ./deploy/xxx.sh`, not an edit to this file.
#
# NOT A NEW PROJECT. This deploys into an existing project the team already
# uses for other things, tagged with a label instead, so a hackathon demo
# does not spawn its own billing account and its own IAM to clean up later.
export PROJECT_ID="${PROJECT_ID:-generative-ai-solutions}"
export REGION="${REGION:-us-central1}"
export REPO="${REPO:-extroc}"
export SERVICE="${SERVICE:-extroc}"
export REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

# The GitHub repository allowed to deploy via Workload Identity Federation.
export REPO_SLUG="${REPO_SLUG:-jai-krishna-0921/crew-ops-advisor}"

# How this project's resources are told apart from everything else already
# living in $PROJECT_ID, in `gcloud ... --filter="labels.hackathon=..."` and in
# the billing console's cost breakdown by label.
export HACKATHON_LABEL="${HACKATHON_LABEL:-bessemer-tech-catalyst}"

# Secret Manager names. Values never appear in this repo, in the Dockerfile,
# or in a `gcloud run deploy` line: Cloud Run reads them at start, and only
# the runtime service account can.
export SECRET_OLLAMA_KEY="${SECRET_OLLAMA_KEY:-ollama-api-key}"
# Voice (speech in/out). Optional: an empty secret is fine, the app reports
# voice as unconfigured rather than failing, but wiring it in release.sh
# needs at least an empty version to exist, which bootstrap.sh creates.
export SECRET_SARVAM_KEY="${SECRET_SARVAM_KEY:-sarvam-api-key}"

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
