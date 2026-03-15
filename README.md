# FoamPilot

An AI agent that lets engineers set up, run, and analyze OpenFOAM CFD simulations through natural language.

> **Status:** MVP implementation complete — 84/84 unit tests passing. Web UI available alongside the terminal REPL.

---

## What It Does

You describe your simulation in plain English. FoamPilot handles the rest:

```
You:   "Run a turbulent pipe flow at Re=10000 with k-epsilon, show me the wall pressure drop."

Agent: → Searches 236 v11 tutorials for the closest match
       → Copies and modifies the template case
       → Runs blockMesh, checks mesh quality
       → Launches simpleFoam, monitors convergence
       → Extracts pressure data, generates plot
       → Reports: "Pressure drop = 47.3 Pa/m (±2% vs Moody chart)"
```

It never generates OpenFOAM files from scratch. It always finds the closest tutorial, copies it, and surgically edits it — preserving valid syntax for your OpenFOAM version.

---

## Interfaces

FoamPilot ships two UIs — choose whichever fits your workflow:

| Interface | Command | Best for |
|-----------|---------|----------|
| **Web UI** | `foampilot web` | Rich panels, real-time agent visibility, approval dialogs |
| **Terminal REPL** | `foampilot run` | Headless servers, scripting, CI pipelines |

---

## Architecture

FoamPilot uses a multi-agent orchestrator pattern. Each phase runs as an isolated subagent with its own context, tool subset, and typed output contract.

```
User prompt
    │
    ▼
Orchestrator
    ├── ConsultAgent   → SimulationSpec (physics, geometry, objectives)
    ├── SetupAgent     → SetupResult   (case directory, files created/modified)
    ├── MeshAgent      → MeshResult    (quality metrics, pass/fail)
    ├── RunAgent       → RunResult     (convergence data, final residuals)
    └── AnalyzeAgent   → AnalysisResult (quantities, validation, plots)
```

Each agent runs the same core loop: call the LLM → execute tool → feed result back → repeat. The loop compacts its own context automatically when it grows large.

---

## Key Design Decisions

| Principle | How it's enforced |
|-----------|-------------------|
| Template-first, never generative | `copy_tutorial` + `edit_foam_dict` — the agent cannot write arbitrary file content without a template base |
| Version-aware everything | Every prompt includes a `VersionProfile` context block; every tool validates against the active version's capability set |
| Structured tool output | Tools return compact JSON summaries — a 10,000-line solver log becomes a 20-field convergence report |
| Context is precious | Subagents isolate context; compaction triggers at 70% of the context window |
| Human in the loop | Three permission levels: AUTO (silent), NOTIFY (shown, not blocked), APPROVE (explicit confirmation required) |
| Reproducibility | Every session writes `FOAMPILOT.md` — a human-readable log of every decision, file change, and result |

---

## Project Structure

```
foampilot/
├── src/foampilot/
│   ├── core/           # Agent loop, orchestrator, compaction, permissions, state
│   ├── version/        # Version profiles (v11, v13), registry, Docker detector
│   ├── tools/          # 16 tools across foam/, general/, viz/ categories
│   ├── index/          # OpenFOAM dict parser, tutorial index builder & searcher
│   ├── agents/         # 5 subagent classes (consult, setup, mesh, run, analyze)
│   ├── prompts/        # System prompts for each agent + version context injector
│   ├── ui/
│   │   ├── terminal.py        # Event-driven terminal REPL (Rich)
│   │   └── web/
│   │       ├── server.py      # FastAPI + WebSocket server
│   │       ├── runner.py      # Sync→async bridge for the orchestrator
│   │       └── frontend/      # React + TypeScript + Tailwind UI (Vite)
│   └── docker/         # Docker SDK client, container manager, volume/path handling
├── benchmarks/         # Benchmark runner, scorer, report generator, 10 YAML cases
├── tests/
│   ├── unit/           # 84 tests — all passing, no Docker or API key needed
│   ├── integration/    # Docker + API key required — run manually
│   └── fixtures/       # Sample dicts, log files, mini case directories
├── scripts/
│   └── build_index.py  # Builds src/foampilot/index/data/tutorial_index_v11.json
├── OpenFOAM-11/        # OpenFOAM Foundation v11 source (tutorials used for indexing)
├── docker-compose.yml
├── Dockerfile.agent
├── pyproject.toml
└── .env.example
```

---

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) for package management
- Docker (for running actual simulations)
- An [Anthropic API key](https://console.anthropic.com)

### Install

```bash
# Clone / navigate to the project
cd foamPilot

# Option A — virtualenvwrapper (recommended)
mkvirtualenv foampilot -p python3.11   # or python3.13
pip install -e ".[dev,web]"

# Option B — standard venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,web]"

# Configure environment
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY at minimum
```

> **Note for uv users on macOS:** uv marks its `.venv` directory with the macOS hidden flag, which Python 3.13 propagates to `.pth` files, causing `ModuleNotFoundError` at import time. Use a regular venv (as above) to avoid this.

### Build the Tutorial Index

This is required before running any simulation. It scans the 236 OpenFOAM v11 tutorial cases and writes a searchable JSON index.

```bash
uv run python scripts/build_index.py \
    --version 11 \
    --tutorials-path OpenFOAM-11/tutorials
```

Output: `src/foampilot/index/data/tutorial_index_v11.json`

To also generate semantic embeddings (adds ~90 MB model download, enables semantic search):

```bash
uv run python scripts/build_index.py \
    --version 11 \
    --tutorials-path OpenFOAM-11/tutorials \
    --embeddings
```

### Run Unit Tests

```bash
uv run pytest tests/unit/ -v
# Expected: 76/76 PASSED
```

### Start Docker Infrastructure

```bash
docker-compose up -d
```

This starts two containers:
- `foampilot-openfoam` — OpenFOAM Foundation v11 with ParaView 5.10
- `foampilot-agent` — Python agent with access to Docker socket

### Launch FoamPilot

Activate your environment first:

```bash
workon foampilot          # virtualenvwrapper
# or
source .venv/bin/activate # standard venv
```

**Web UI** (recommended):

```bash
# First time only — build the React frontend
cd src/foampilot/ui/web/frontend && npm install && npm run build && cd -

# Start the server (opens browser automatically)
foampilot web
```

The web UI runs at `http://127.0.0.1:8080` and provides three panels: a live file explorer, an agent process stream with expandable tool cards, and a chat panel with inline approval prompts.

**Terminal REPL**:

```bash
foampilot run
# or with an immediate prompt:
foampilot run "Simulate lid-driven cavity flow at Re=100"
```

---

## Usage Examples

```bash
# Activate your environment first
workon foampilot   # or: source .venv/bin/activate

# Web UI (opens browser at http://127.0.0.1:8080)
foampilot web

# Web UI on a custom port, no browser
foampilot web --port 9000 --no-browser

# Terminal REPL
foampilot run

# Terminal — direct prompt
foampilot run "Set up a lid-driven cavity at Re=100"

# Run a benchmark evaluation
foampilot eval --case lid_driven_cavity

# Build / rebuild the tutorial index
foampilot index --version 11
```

Destructive actions (file overwrites, solver runs) always pause for approval unless Auto-approve is enabled. In the web UI this appears as an inline approval card; in the terminal it is a prompt in the REPL.

---

## Supported OpenFOAM Versions

| Version | Distribution | Status |
|---------|-------------|--------|
| v11 | Foundation | Full profile — solvers, BCs, schemes, quirks |
| v13 | Foundation | Stub — expand `foundation_v13.py` as needed |

Adding a new version: subclass `VersionProfile` in `src/foampilot/version/profiles/`, register it in `registry.py`.

---

## Tool Reference

| Tool | Permission | Description |
|------|-----------|-------------|
| `search_tutorials` | AUTO | Search the index for matching tutorial cases |
| `copy_tutorial` | APPROVE | Clone a tutorial case to the working directory |
| `read_foam_file` | AUTO | Parse and return an OpenFOAM dictionary as JSON |
| `edit_foam_dict` | APPROVE | Surgical regex edit of a single key-value pair |
| `write_foam_file` | APPROVE | Write or overwrite a file |
| `str_replace` | APPROVE | Uniqueness-enforced string replacement |
| `run_foam_cmd` | APPROVE | Run an OpenFOAM command inside the Docker container |
| `check_mesh` | AUTO | Run checkMesh and return structured quality metrics |
| `parse_log` | AUTO | Parse a solver log for convergence/divergence |
| `extract_data` | AUTO | Extract time steps, forces, or residual series |
| `plot_residuals` | AUTO | Plot convergence history (matplotlib PNG) |
| `plot_field` | AUTO | Plot a field line profile from postProcessing data |
| `bash` | APPROVE | Run a shell command (blocked patterns: `rm -rf`, etc.) |
| `read_file` | AUTO | Read a file with optional line range |
| `write_file` | APPROVE | Write a generic file |
| `web_search` | AUTO | Search the web (stub — configure `WEB_SEARCH_API_KEY`) |

---

## Benchmark Framework

Ten benchmark cases across three tiers test the agent end-to-end:

| Tier | Cases | Focus |
|------|-------|-------|
| 1 | lid-driven cavity, backward-facing step, pipe heat transfer, dam break | Basic setup + convergence |
| 2 | diverging relaxation, bad mesh, BC mismatch | Failure detection + recovery |
| 3 | flat plate turbulent, natural convection, pipe bend | Advanced physics + accuracy |

Run all Tier 1 benchmarks:

```bash
foampilot eval --suite tier1
```

Scores are written to `benchmarks/results/` and summarised in a Markdown table by `report.py`.

---

## Configuration

All settings live in `.env` (copied from `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | **Required.** Anthropic API key |
| `OPENFOAM_VERSION` | `11` | OpenFOAM version to target |
| `OPENFOAM_CONTAINER` | `foampilot-openfoam` | Docker container name |
| `MODEL_FAST` | `claude-haiku-4-5-20251001` | Model for tool-heavy subtasks |
| `MODEL_COMPLEX` | `claude-sonnet-4-6` | Model for reasoning + compaction |
| `PERMISSION_MODE` | `approve` | `auto` / `notify` / `approve` |
| `MAX_TURNS` | `50` | Max agent loop iterations per phase |
| `CONTEXT_COMPACTION_THRESHOLD` | `0.7` | Compact at 70% context usage |
| `CASES_DIR` | `./cases` | Where simulation cases are stored |
| `INDEX_DIR` | `src/foampilot/index/data` | Tutorial index location |

---

## Development

See [development.md](tutorials/development.md) for the full architecture guide, coding conventions, and implementation notes.

```bash
# Activate environment
workon foampilot   # or: source .venv/bin/activate

# Linting
ruff check src/ tests/

# Run all unit tests with coverage
pytest tests/unit/ --cov=src/foampilot --cov-report=html

# Integration tests (requires Docker)
pytest tests/integration/ -v

# Rebuild tutorial index
python scripts/build_index.py --version 11 --tutorials-path OpenFOAM-11/tutorials
```

### Web UI development

```bash
# Run backend + Vite dev server simultaneously (hot reload)
workon foampilot
foampilot web --no-browser &          # API + WS on :8080
cd src/foampilot/ui/web/frontend
npm run dev                           # UI on :5173 (proxies /api and /ws to :8080)

# Rebuild production bundle
npm run build
```

### Adding a New Tool

1. Create `src/foampilot/tools/<category>/<name>.py` subclassing `Tool`.
2. Implement `name`, `description`, `input_schema`, `_run(inputs)` returning `ToolResult`.
3. Register it in `tools/registry.py` inside `build_default_registry()`.
4. Add unit tests in `tests/unit/test_<name>.py`.

### Adding a New OpenFOAM Version

1. Create `src/foampilot/version/profiles/<distro>_v<version>.py`.
2. Subclass `VersionProfile` with class-level attribute overrides (no `__init__`).
3. Register in `src/foampilot/version/registry.py`.
4. Build the index: `scripts/build_index.py --version <version> --tutorials-path <path>`.

---

## License

MIT
