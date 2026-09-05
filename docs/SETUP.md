# Setup

Everything needed to get the API and the web console running, in order. The
README carries a five line quick start; this is the version that answers "it
did not work".

If you only want to see it run: `make install && make dev`, then open
[http://localhost:3000](http://localhost:3000).

---

## Prerequisites

| Tool                            | Version      | Why                                          |
| ------------------------------- | ------------ | -------------------------------------------- |
| Python                          | 3.12 or 3.13 | `api/pyproject.toml` pins `>=3.12,<3.14` |
| [uv](https://docs.astral.sh/uv/) | any recent   | Installs and runs the Python side            |
| Node                            | 20 or newer  | Next.js 16                                   |
| [pnpm](https://pnpm.io/)         | 9 or newer   | The lockfile is pnpm's                       |
| make                            | any          | A thin wrapper over the two commands above   |

No API key, no database server, no Docker. The dataset is a directory of JSON
files that ships in the repository, and the only persistence is a SQLite file
the API creates for itself.

Install uv and pnpm if you do not have them:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
npm install -g pnpm
```

---

## Install

```bash
make install
```

That is two commands, and running them by hand is fine if you would rather see
what is happening:

```bash
cd api && uv sync --extra dev     # creates api/.venv and installs everything
cd web && pnpm install
```

`uv sync` reads `api/uv.lock`, so the versions are the ones this was built and
tested against. Nothing is installed globally.

---

## Run

### Both together

```bash
make dev
```

- API on [http://localhost:8000](http://localhost:8000), with reload
- Web on [http://localhost:3000](http://localhost:3000), with Turbopack

The target traps signals and kills both children on exit, so one Ctrl-C stops
the pair. Open [http://localhost:3000](http://localhost:3000) and you are looking at the landing page;
the console is at `/ask`.

### Separately

Two terminals, which is what you want when you are working on one side:

```bash
make serve   # API only, :8000
make web     # Web only, :3000
```

Or without make:

```bash
cd api && uv run uvicorn --factory crewops.server.app:create_app --reload --port 8000
cd web && pnpm dev
```

`--factory` is not optional. `create_app` is a function that builds the app,
not a module level instance, because the world state is loaded once at startup
and a test needs to be able to build a second app against a different snapshot.

### Without a browser

The whole product is reachable from a terminal:

```bash
cd api
uv run crewops ask "Who is on reserve at BLR on 2026-09-15?"
uv run crewops brief 2026-09-15
```

---

## What is where

| URL               | What it is                                                         |
| ----------------- | ------------------------------------------------------------------ |
| `/`             | Landing page. Explains the boundary. Talks to no API.              |
| `/ask`          | The console. This is the product.                                  |
| `/brief`        | The proactive morning watchlist for a date                         |
| `/ops`          | The rules engine, exposed directly, with no model anywhere near it |
| `/architecture` | Where the model stops and deterministic code starts                |
| `:8000/docs`    | FastAPI's own OpenAPI browser                                      |

`/?q=...` and `/?thread=...` forward to `/ask`, so older links still work.

---

## Configuration

### The API

Read from `.env.local` first, then `.env`, both at the repository root, then
the real environment. `.env.local` never overrides a variable that is already
set, so an export in your shell always wins. Both files are gitignored.

Every one of these is optional.

| Variable                              | Default                    | What it does                                      |
| ------------------------------------- | -------------------------- | ------------------------------------------------- |
| `ANTHROPIC_API_KEY`                 | unset                      | Turns on agent mode, Anthropic                    |
| `OPENAI_API_KEY`                    | unset                      | Turns on agent mode, OpenAI                       |
| `OLLAMA_API_KEY` or `OLLAMA_HOST` | unset                      | Turns on agent mode, Ollama                       |
| `CREWOPS_LLM_PROVIDER`              | auto                       | Force one of`anthropic`, `openai`, `ollama` |
| `CREWOPS_MODEL`                     | per provider               | Override the model id                             |
| `CREWOPS_PLAN_MODEL`                | same as`CREWOPS_MODEL`   | A different model for planning only               |
| `CREWOPS_MEMORY_DB`                 | `api/.crewops/memory.db` | Where conversations are logged                    |

**Where to put the file.** Any of these, and the first value found wins:

```
.env.local        .env          (repository root)
api/.env.local    api/.env
web/.env.local    web/.env
```

plus the directory you ran the command from. A variable already exported in
your shell always beats every file, so a real deployment is never overwritten
by a checkout.

**Provider selection is by presence, in order: Anthropic, then OpenAI, then
Ollama.** The first one whose variable carries a usable value wins.

**A placeholder is not a usable value.** `ANTHROPIC_API_KEY=your-key-here`,
`changeme`, `<your key>` and the like are recognised as templates, skipped, and
reported. Without that, a copied `.env.example` selected Anthropic, failed to
authenticate on every turn, and left a perfectly good Ollama key behind it
doing nothing. `CREWOPS_LLM_PROVIDER` still exists to settle it explicitly.

### If it says deterministic and you have a key

**Run `uv run crewops health` from `api/`.** It now prints a `Why` row that
names the provider it chose and the reason, lists every env file it read, and
names any value it ignored as a placeholder. `GET /api/health` returns the same
thing as `llm_detail`, `env_files_searched` and `ignored_placeholders`.

That one command answers the three things that actually go wrong: the file is
somewhere it was not read, the key is a template, or the variable is spelled
differently from the three above.

### The web console

`web/.env.example` documents three variables and every value in it is already
the default, so **an absent `web/.env.local` is the correct state for a demo**.

| Variable                   | Default                   | What it does                              |
| -------------------------- | ------------------------- | ----------------------------------------- |
| `NEXT_PUBLIC_API_BASE`   | `http://localhost:8000` | Where the API is                          |
| `NEXT_PUBLIC_USE_MOCKS`  | `0`                     | Serve fixtures instead of calling the API |
| `NEXT_PUBLIC_MOCK_SPEED` | `1`                     | Playback speed for the mock stream        |

Do not set `NEXT_PUBLIC_USE_MOCKS=1` for a demo. The figures on screen would be
invented rather than computed, which is the one thing this system exists not to
do. It is there so the frontend can be worked on with no Python running.

---

## Running with no API key

This is the default and it is a supported configuration rather than a degraded
one. With no key the deterministic resolver answers: same tools, same rules
engine, same simulations, same ranked options, same grounding check, same
`Reply` type. What a key adds is a language model choosing the tool plan and
writing the prose, which is language, not truth.

The section rail's dot at the bottom right says which engine is live, and the
answer itself carries its mode.

---

## Check the install

```bash
make check           # ruff, mypy, the boundary test, and the full suite
make test            # the Python suite on its own
make golden          # parity against the shipped answer keys
make eval            # scorecard across all 38 questions, every tier
make validate-data   # the dataset's own validator, read only
make boundary        # assert no model client reaches the deterministic core
```

`make boundary` is the one worth running first if you are evaluating this. It
fails the build if any module under `domain/`, `rules/`, `ops/` or `store/`
imports a model client, which is the claim the whole submission rests on.

A quick end to end check that does not need a browser:

```bash
curl -s localhost:8000/api/health
cd api && uv run crewops ask "How many duty hours has C-1042 accrued?"
```

---

## When it does not work

**`make dev` exits immediately.** Something is already on 8000 or 3000. Find it
with `lsof -i :8000` and stop it, or run the two halves separately on other
ports.

**Connection refused, or every panel is empty.** The web console talks to the
API over HTTP, so `pnpm dev` on its own is not enough: something has to be
serving :8000. `make dev` runs both. If you are running them separately, start
the API first and check it:

```bash
curl -s localhost:8000/api/health
```

If that fails, the API is not up. If it succeeds and the console still cannot
reach it, check `NEXT_PUBLIC_API_BASE` in any `web/.env.local` you have: it
defaults to `http://localhost:8000`, and an absent file is the correct state.

**A change to the Python is not taking effect.** `uvicorn --reload` does not
always pick up every edit. Stop `make dev` and start it again. This is the
usual reason a fix appears not to work.

**Agent mode will not turn on.** `cd api && uv run crewops health` and read the
`Why` row. It tells you which files were read, which provider was selected and
why, and which values were ignored as placeholders. The three usual causes are
a file in a directory that was not searched, a template value, and a typo in
the variable name.

**Answers arrive but say the mode is deterministic.** That is agent mode being
off, not a failure. See above.

**`uv sync` cannot find a Python.** `uv python install 3.13` and try again.

**Ports are fine but the web build complains about the fonts.** The two
variable fonts are committed under `web/src/app/fonts/`. If they are missing,
the archives in `fonts/` at the repository root extract to the same names.

---

## Related

- [`COMMANDS.md`](../COMMANDS.md) is the demo script: every command in the
  order to run it, with what each one proves.
- [`docs/CONTRACTS.md`](CONTRACTS.md) is the tool surface and the HTTP and SSE
  contracts.
- [`docs/AGENT-DESIGN.md`](AGENT-DESIGN.md) is the graph, the guards and the
  verifier.
