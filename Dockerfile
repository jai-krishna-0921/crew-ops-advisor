# One image for the whole demo: Next.js and FastAPI, fronted by nginx on the
# single port Cloud Run gives a container. Three separate Cloud Run services
# would each need their own min/max-instances and their own cold start; for a
# hackathon demo with no real traffic, one scale-to-zero service is the
# cheaper and simpler shape.
#
# NO OLLAMA DAEMON IN HERE, DELIBERATELY. `ollama serve` does not authenticate
# to Ollama Cloud with OLLAMA_API_KEY: it signs upstream requests with the
# machine's own keypair (~/.ollama/id_ed25519), which `ollama signin`
# registers against an account. A container generates a fresh, unregistered
# keypair on every cold start, so every cloud call came back 401 while the
# same key worked on a developer laptop whose keypair was registered.
#
# The Python client (ollama/_client.py) reads OLLAMA_API_KEY into an
# Authorization header and OLLAMA_HOST as the base URL, so pointing
# OLLAMA_HOST at https://ollama.com talks to the cloud API directly with the
# key. That removes a daemon, a 679-second build step and a few hundred MB of
# llama.cpp runtime that was never going to run inference here anyway.
#
# uv rather than pip, because api/ is already locked with it and `uv sync
# --frozen` is the only install that guarantees the container runs what CI ran.
#
# Node is fetched as a first-party tarball (nodejs.org) rather than through a
# third-party apt repository or a curl-pipe-to-bash install script, for the
# same reason api/'s own Dockerfile precedent avoids GHCR for the uv binary:
# fewer parties in the build with the power to break or swap it.

# ---------------------------------------------------------------------------
# The web app, built standalone.
# ---------------------------------------------------------------------------
FROM node:22-slim AS web-builder
WORKDIR /app/web

RUN corepack enable && corepack prepare pnpm@9 --activate

COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY web/ ./
# Baked in at build time: Next.js inlines NEXT_PUBLIC_* into the client
# bundle. Empty means same-origin, relative fetches, which is what nginx's
# single listen port in front of both processes expects.
ENV NEXT_PUBLIC_API_BASE=""
RUN pnpm build

# ---------------------------------------------------------------------------
# The API, as a uv-managed venv.
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS api-builder
WORKDIR /app/api

RUN pip install --no-cache-dir uv==0.5.11

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1

# Manifests first, so a source-only edit does not invalidate the dependency
# layer.
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY api/src/ ./src/
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Runtime. Python base because the API's compiled venv is pinned to this
# interpreter's ABI; Node and Ollama are added to it, not the other way round.
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS final

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates nginx gettext-base xz-utils \
    && rm -rf /var/lib/apt/lists/*

ARG NODE_VERSION=22.11.0
RUN curl -fsSL -o /tmp/node.tar.xz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.xz

WORKDIR /app

# The dataset. Read only at runtime, same as every other entry point in this
# project; see the loader's own DATA_DIR resolution for why the path below
# has to end in crew-ops-advisor-dataset/data.
COPY data/ /app/data/

COPY --from=api-builder /app/api/.venv /app/api/.venv
COPY --from=api-builder /app/api/src /app/api/src
ENV PATH="/app/api/.venv/bin:${PATH}"

COPY --from=web-builder /app/web/.next/standalone /app/web
COPY --from=web-builder /app/web/.next/static /app/web/.next/static
COPY --from=web-builder /app/web/public /app/web/public

COPY deploy/container/nginx.conf.template /etc/nginx/nginx.conf.template
COPY deploy/container/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Not root, for the same reason every long-lived service in this stack runs
# as its own uid: a container escape from a process that already has root is
# a different, worse incident than one that does not.
RUN useradd --create-home --uid 10001 extroc \
    && chown -R extroc:extroc /app /home/extroc
USER extroc
ENV HOME=/home/extroc

EXPOSE 8080
ENV PORT=8080
CMD ["/app/start.sh"]
