# repMind

A personal Hevy AI training assistant. Connects to your Hevy account, caches your
full workout history locally, and gives you:

1. **Dashboard** — per-lift trend charts (estimated 1RM over time), weekly volume per
   muscle group, stalled-lift detection, and a coach-voiced "what to improve this week"
   card.
2. **Chat** — Claude-powered, reads your real training history and can *propose* Hevy
   routines. Nothing is ever pushed to Hevy without an explicit **Approve & Push** click.

Single-user, self-hosted. Optimized for one person's real data, not multi-tenant scale.

## Stack

- **Backend:** Python / FastAPI + SQLite (SQLModel). Anthropic Python SDK (`claude-opus-4-8`).
- **Frontend:** React + Vite + Recharts.
- **Hevy:** isolated client module (`backend/app/hevy/client.py`) — all Hevy API quirks
  live in one file so it's easy to patch as the (early-stage) API changes.

## Requirements

- **Hevy Pro** + a Hevy API key: https://hevy.com/settings?developer
- An **Anthropic API key**.
- Python 3.11+, Node 18+.

## Setup

```bash
cp .env.example .env          # fill in HEVY_API_KEY and ANTHROPIC_API_KEY
                              # leave DRY_RUN=true until you've verified the pipeline

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxies /api to :8000)
```

First run performs a full workout sync on startup. Use the **Sync now** button (or
`POST /api/sync`) afterward for delta syncs.

## Safety model

- `HEVY_API_KEY` and `ANTHROPIC_API_KEY` are read server-side only. The frontend never
  sees them — it talks only to the backend.
- **`DRY_RUN=true`** makes every Hevy *write* log its resolved payload and return a fake
  id instead of pushing live. Verify the whole flow this way before flipping to `false`.
- Claude can *read* your history freely but can only *propose* routines. A routine is
  pushed to Hevy only after you click **Approve & Push**.
- The Hevy API has no DELETE endpoints; repMind builds no delete features.

## Coaching context

`coach-context.md` holds your training philosophy and goals. It's read fresh at the start
of each chat session — edit it as your numbers and priorities change; no code edits needed.

## Deployment (self-hosted on a tailnet host)

Deployed to `pi4host` and served at **http://pi4host:8000** (tailnet-only — bound to the
tailscale IP, not the LAN). Runs as the `repmind` systemd service (auto-restart, starts on
boot); FastAPI serves the built frontend as static files, so the host needs no Node runtime.

Ship updates with one command from this Mac (Tailscale must be up):

```bash
./deploy.sh
```

It builds the frontend locally, pushes `main`, pulls the backend on the Pi, rsyncs the built
UI, reinstalls any new deps, restarts the service, and health-checks. Commit backend changes
before running (the Pi deploys backend from pushed `main`; the frontend ships from the local
build). Logs on the host: `journalctl -u repmind -f`.
