#!/usr/bin/env bash
# Put values in the secrets. Separate from bootstrap.sh so that script can
# live in a repo and be read in a PR, and this one runs from a terminal with
# keys pasted into it, never committed, never in an argument list where `ps`
# or shell history would keep a copy.
#
# SARVAM IS OPTIONAL. Skip it (press Ctrl-D on an empty line) if the deployed
# demo does not need voice; the app reports voice as unconfigured rather than
# failing on an empty key.
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.sh

put() {
  local name="$1" label="$2"
  gcloud secrets describe "$name" --project "$PROJECT_ID" >/dev/null 2>&1 \
    || die "secret ${name} does not exist yet; run deploy/bootstrap.sh first"
  say "paste the ${label}, then Ctrl-D (or just Ctrl-D to skip):"
  local value
  value="$(cat)"
  [ -n "$value" ] || { say "skipped ${name}"; return 0; }
  printf '%s' "$value" | gcloud secrets versions add "$name" --project "$PROJECT_ID" --data-file=-
}

put "$SECRET_OLLAMA_KEY" "Ollama Cloud key (from ollama.com/settings > API keys)"
put "$SECRET_SARVAM_KEY" "Sarvam API key (from dashboard.sarvam.ai), or skip for text-only"

say "stored. deploy/release.sh will pick up new secret versions automatically."
