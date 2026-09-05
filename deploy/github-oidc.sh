#!/usr/bin/env bash
# Let deploy/extroc on this one GitHub repository deploy, without ever
# holding a key.
#
# Workload Identity Federation: GitHub mints a short-lived OIDC token that
# says which repository and which ref is running, Google trades it for an
# access token, and nothing long-lived exists to leak. The alternative is a
# service account JSON key in a repository secret, a credential that outlives
# whoever added it and that no rotation policy here would ever reach.
#
# THE ATTRIBUTE CONDITION IS THE WHOLE SECURITY BOUNDARY. Without one, any
# repository on GitHub could mint a token for this pool; without the ref half
# of it, any branch of THIS repository could deploy, not just deploy/extroc.
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.sh

POOL="github"
PROVIDER="github-oidc"
DEPLOY_SA="${SERVICE}-deploy@${PROJECT_ID}.iam.gserviceaccount.com"
RUN_SA="${SERVICE}-run@${PROJECT_ID}.iam.gserviceaccount.com"
# The configured value first: the lookup needs cloudresourcemanager enabled
# for whoever is calling, which is not guaranteed on a fresh project.
NUMBER="${PROJECT_NUMBER:-$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')}"

say "deploy service account"
gcloud iam service-accounts describe "$DEPLOY_SA" --project "$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "${SERVICE}-deploy" \
      --display-name="Extroc CI deployer" --project "$PROJECT_ID" --quiet

# What a deployer needs and nothing else. Notably absent: owner, and any role
# that could read the Ollama secret's VALUE. CI wires it into the service by
# name; it never needs to see it. iam.serviceAccountUser is scoped to the
# runtime SA alone, not project-wide, so this account cannot act as anything
# else in the project.
for role in roles/run.admin roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${DEPLOY_SA}" --role="$role" --quiet >/dev/null
done
gcloud iam service-accounts add-iam-policy-binding "$RUN_SA" \
  --member="serviceAccount:${DEPLOY_SA}" --role="roles/iam.serviceAccountUser" \
  --project "$PROJECT_ID" --quiet >/dev/null
say "roles granted"

say "identity pool"
gcloud iam workload-identity-pools describe "$POOL" --location=global --project "$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud iam workload-identity-pools create "$POOL" --location=global \
      --display-name="GitHub Actions" --project "$PROJECT_ID" --quiet

say "provider, pinned to ${REPO_SLUG} on refs/heads/deploy/extroc"
gcloud iam workload-identity-pools providers describe "$PROVIDER" \
  --location=global --workload-identity-pool="$POOL" --project "$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
      --location=global --workload-identity-pool="$POOL" \
      --issuer-uri="https://token.actions.githubusercontent.com" \
      --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
      --attribute-condition="assertion.repository == '${REPO_SLUG}' && assertion.ref == 'refs/heads/deploy/extroc'" \
      --project "$PROJECT_ID" --quiet

say "letting that repository/branch impersonate the deployer"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${REPO_SLUG}" \
  --project "$PROJECT_ID" --quiet >/dev/null

cat <<OUT

Add these to the GitHub repository (Settings > Secrets and variables > Actions,
"Repository secrets"):

  GCP_WORKLOAD_IDENTITY_PROVIDER
      projects/${NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}

  GCP_DEPLOY_SERVICE_ACCOUNT
      ${DEPLOY_SA}

Neither is a credential: the provider name and the account address are public
identifiers, and holding them grants nothing without a token minted by
GitHub for ${REPO_SLUG} on refs/heads/deploy/extroc specifically.
OUT
