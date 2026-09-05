# Deploying Extroc

This exists to demo the app off a laptop. The problem statement is explicit
that deployment infrastructure is not expected and is not scored (section 6,
"You are NOT expected to build: ... Production infrastructure, CI/CD or
deployment pipelines"; section 3, "Do not spend hackathon hours on
infrastructure"). Nothing here should take time away from Tier 1/2/3 work.

## Shape

One Cloud Run service, one container, three processes: `uvicorn` (FastAPI),
`node` (the built Next.js app), and `nginx` in front of both on the one port
Cloud Run gives the container. See `../Dockerfile` and `container/start.sh`
for exactly how they're wired.

### Why there is no `ollama serve` in the container

`.env.example` tells you to run a local `ollama` daemon alongside
`OLLAMA_API_KEY`. That is correct on a laptop and wrong in a container, and
the difference cost a deploy cycle to find.

The daemon does not authenticate to Ollama Cloud with the API key. It signs
upstream requests with the machine's own keypair (`~/.ollama/id_ed25519`),
which `ollama signin` registers against your account. A container generates a
fresh, unregistered keypair on every cold start, so every model call came
back `401` while the identical key worked on a developer laptop.

The Python client (`ollama/_client.py`) reads `OLLAMA_API_KEY` into an
`Authorization` header and `OLLAMA_HOST` as the base URL, so setting
`OLLAMA_HOST=https://ollama.com` calls the cloud API directly, with the key,
and needs no daemon at all. `deploy/release.sh` sets that pair. comarketer's
Cloud Run deployment does the same thing and ships no ollama binary either.

Dropping the daemon also removed a 679-second image build step and the
bundled llama.cpp runtime, which was never going to run inference here.

`OLLAMA_API_KEY` still comes first in the provider's `selects_on` order, so
the default model stays `deepseek-v4-flash:cloud` (the measured one) rather
than falling back to the `OLLAMA_HOST` default of `qwen3:8b`.

It deploys into an **existing** GCP project (`generative-ai-solutions`),
labeled `hackathon=bessemer-tech-catalyst`, not a new project. Every resource
this creates carries that label, so it is one filter away from being found
and torn down after the hackathon.

## Cost

- `--min-instances 0`: the service costs nothing while nobody is using it.
  This is the entire cost strategy; everything else is a detail.
- `--max-instances 2`: a ceiling against a runaway bill, not a capacity plan.
- `--cpu 1 --memory 1Gi`, default CPU throttling: cheap, because the actual
  model inference happens on Ollama Cloud, not in this container. Ollama
  Cloud's own usage is billed separately to whoever owns the `OLLAMA_API_KEY`
  and is outside Cloud Run's bill entirely. The same is true of Sarvam for
  voice.
- No VPC connector, no NAT, no load balancer: the outbound call to
  `https://ollama.com` is plain internet egress, which Cloud Run does not
  charge a premium for.
- Artifact Registry has a cleanup policy keeping the 5 newest images; without
  one, image storage is small per push but grows forever.

## One-time setup

Needs `gcloud`, authenticated as someone who can enable APIs and create
service accounts in `generative-ai-solutions`.

```bash
./deploy/bootstrap.sh      # labels the project, enables APIs, creates the
                            # Artifact Registry repo and the runtime service
                            # account, creates the (empty) Ollama secret

./deploy/secrets.sh        # pastes the actual Ollama Cloud and Sarvam keys
                            # into those secrets; never appears in this repo
                            # or in CI. Sarvam is optional (voice); skip it
                            # with Ctrl-D on an empty line.

./deploy/github-oidc.sh    # sets up Workload Identity Federation scoped to
                            # jai-krishna-0921/crew-ops-advisor on
                            # refs/heads/deploy/extroc, prints two values to
                            # add as GitHub repository secrets
```

After `github-oidc.sh` prints its output, add the two secrets it names under
the GitHub repo's Settings > Secrets and variables > Actions. Nothing else in
the repo needs a secret: the app is deployed with `OLLAMA_API_KEY` and
`SARVAM_API_KEY` wired straight from Secret Manager, never as GitHub secrets.

Rotating a key later is `deploy/secrets.sh` (which adds a new secret version)
followed by `SKIP_BUILD=1 ./deploy/release.sh`. The redeploy is required:
`--set-secrets ...:latest` is resolved when the revision is created, and
revisions are immutable, so a new secret version does not reach the running
service on its own.

## Deploying

From here, `git push` to `deploy/extroc` triggers `.github/workflows/deploy.yml`,
which runs `deploy/release.sh` (build, push, `gcloud run deploy`) and then
`deploy/smoke.sh` against the live URL.

To deploy from a laptop instead of CI:

```bash
./deploy/release.sh
```

## What this does not do

- It does not touch `main`. `deploy/extroc` is a separate branch with its own
  workflow; main's existing CI (lint, type-check, tests, the dataset-is-
  unmodified guard) is unchanged.
- It does not add authentication in front of the demo (`--allow-unauthenticated`).
  Fine for a synthetic dataset with no real PII; not a decision to carry into
  anything real without revisiting it.
- It does not run more than one instance at a time in the common case, so
  concurrent demo users share one container. Raise `--max-instances` in
  `deploy/release.sh` if that stops being enough; it is not currently a
  cost-relevant setting because it is a ceiling, not a floor.
