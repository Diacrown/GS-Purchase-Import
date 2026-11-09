# Deploying gemstone-intake to Fly.io

Mirrors how the AGL Report Fetcher is deployed (same provider, same region).
End state: `https://<your-app>.fly.dev` with a single-page UI, drag-and-drop
uploads, and a download button for the EZ JEMS import file.

---

## Prerequisites

- `flyctl` installed and logged in: <https://fly.io/docs/flyctl/install/>
- You are at the project root (this directory, containing `Dockerfile`, `fly.toml`, `gemstone_intake/`, `app/`).

## First-time deploy (new app)

```bash
# 1. Launch — Fly reads fly.toml. When prompted:
#    - "Create .dockerignore?" → No, we ship one
#    - "Deploy now?" → No (set the secret first)
#    - "App name" → change from "gemstone-intake" if taken
fly launch --no-deploy

# 2. Set the API key so /run requires auth (STRONGLY recommended)
fly secrets set INTAKE_API_KEY="$(openssl rand -hex 24)"

# 3. Deploy
fly deploy

# 4. Open
fly open
```

The deploy builds the Docker image, pushes it to Fly's registry, and starts
one machine in the `bom` (Mumbai) region. The health check at `/health`
pings every 30 s; traffic routes once it's green.

## Subsequent deploys

```bash
# Edit code → deploy
fly deploy
```

## Routine ops

```bash
fly logs                  # tail the running container
fly status                # machines + health
fly scale count 2         # add a second machine (for redundancy)
fly secrets set INTAKE_API_KEY="<new-value>"   # rotate the key
fly ssh console           # shell inside the container
```

## Running locally first (recommended before any Fly push)

```bash
pip install -r requirements.txt
INTAKE_API_KEY=dev python -m app.app
# UI at http://localhost:8080
# API key field in the UI accepts "dev"
```

Or via Docker exactly as Fly will run it:

```bash
docker build -t gemstone-intake .
docker run --rm -p 8080:8080 -e INTAKE_API_KEY=dev gemstone-intake
```

## Operating the UI

The manager's workflow once hosted:

1. Open `https://<your-app>.fly.dev` in a browser.
2. Paste the API key (stored in the browser so they don't retype it).
3. Upload the intake Excel (schema: `Report No | Password | Unit Price | FWD LOC | FWD SSP | Lot No?`).
4. Upload the AGL responses ZIP produced by `certificate-scrapper.fly.dev` (one `.html` or `.json` per Report No).
5. Click **Generate import file**.
6. Review the row-status table — amber rows show the warnings.
7. Click **Download EZ JEMS import** and import that file into EZ JEMS.

## Integration with the AGL Report Fetcher

Two deployment styles:

**Side-by-side** (current, simplest):
- `certificate-scrapper.fly.dev` — fetches AGL certs, returns ZIP of responses.
- `<this app>.fly.dev` — takes intake Excel + the ZIP, returns import file.
- Manager uses both tabs.

**Merged** (future, one-click):
- Add this app's `gemstone_intake` package into the AGL fetcher repo.
- Register `app.flask_blueprint.bp` into the fetcher's Flask app.
- A single endpoint accepts intake, runs AGL fetches internally, emits the import file. Trade-off: one deploy is coupled to both workloads.

The web UI on this app is designed to keep working either way — the merged mode just adds a route on the AGL fetcher that the UI can POST to instead of this service's `/run`.

## Scaling notes

- Current defaults: 2 gunicorn workers, 512 MB RAM, shared CPU.
- A batch of ~15 stones processes in ~1 s on `shared-cpu-1x`.
- 32 MB upload cap set in `app/app.py` — bump via `app.config["MAX_CONTENT_LENGTH"]` if you expect huge batches.
- Fly's `auto_stop_machines = "stop"` is on: idle machines suspend; first request after idle has a ~2 s cold start.

## Security checklist

- [x] Non-root user in the container (uid 10001).
- [x] `/health` is public; `/run` requires API key when `INTAKE_API_KEY` is set.
- [x] `force_https = true` in fly.toml.
- [x] Upload size capped at 32 MB.
- [x] `-I`-compatible: the pipeline never imports anything from the uploaded files.
- [ ] Rotate `INTAKE_API_KEY` quarterly; store it in your password manager.
- [ ] If exposing to anyone outside the office, put it behind Fly's private networking or your VPN rather than relying on the key alone.
