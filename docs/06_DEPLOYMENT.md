# Deployment Guide

Practical notes for deploying the GridWise service in any environment.

## 1. Local Docker

```bash
# Build
docker compose build

# Start
docker compose up -d

# Verify
docker compose ps                  # status = healthy
curl -sf http://127.0.0.1:8000/health

# Logs
docker compose logs -f gridwise-api

# Stop
docker compose down
```

## 2. Generic VPS (Ubuntu / Debian)

```bash
# Install Docker
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
# log out and back in

# Clone repository
git clone <repo-url> gridwise
cd gridwise

# Configure secrets
cp .env.example .env
nano .env   # set OPENROUTER_API_KEY

# Build and run
docker compose up -d --build

# Expose port (optional firewall rule)
sudo ufw allow 8000/tcp

# Verify
curl -sf http://<your-vps-ip>:8000/health
```

## 3. Railway / Render / Fly.io

Each platform has its own conventions. The general pattern:

1. Connect the repository (keep private during event).
2. Set environment variables in the platform's secret store:
   - `GROQ_API_KEY` (required)
   - Other variables optional; defaults are sensible.
3. Build command: `docker build -t gridwise-api .` (or auto-detected).
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
5. Expose port `8000` (or the platform's `$PORT`).
6. Health check path: `/health`.

### Railway example (`railway.toml` or dashboard)

```toml
[build]
builder = "DOCKERFILE"

[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
healthcheckTimeout = 30
```

### Render example (`render.yaml`)

```yaml
services:
  - type: web
    name: gridwise-api
    env: docker
    healthCheckPath: /health
    envVars:
      - key: OPENROUTER_API_KEY
        sync: false   # set in dashboard
      - key: LLM_MODEL
        value: openai/gpt-4o-mini
```

### Fly.io example

```toml
app = "gridwise-api"
primary_region = "sin"

[build]
  dockerfile = "Dockerfile"

[[services]]
  internal_port = 8000
  protocol = "tcp"
  [[services.ports]]
    handlers = ["http"]
    port = 80
    force_https = true

  [[services.http_checks]]
    path = "/health"
    interval = "30s"
    timeout = "5s"
```

## 4. Environment variables in production

Never commit `.env`. Always inject via the platform's secret store:

| Variable | Required | Default | Notes |
|---|---|---|---|
| `GROQ_API_KEY` | Yes | _empty_ | Bearer token for Groq |
| `GROQ_BASE_URL` | No | `https://api.groq.com/openai/v1` | Override for self-hosted / other OpenAI-compatible endpoints |
| `LLM_MODEL` | No | `openai/gpt-oss-120b` | Any Groq-supported model |
| `LLM_TEMPERATURE` | No | `0` | Deterministic interpretation |
| `LLM_REASONING_EFFORT` | No | `low` | `""` to disable reasoning; `low`/`medium`/`high` to enable |
| `LLM_TIMEOUT_SECONDS` | No | `10` | Per-call timeout |
| `LLM_MAX_RETRIES` | No | `2` | Repair-attempt budget |
| `LLM_MOCK` | No | `false` | **Never enable on production** |
| `APP_HOST` | No | `0.0.0.0` | Bind address |
| `APP_PORT` | No | `8000` | Bind port |
| `LOG_LEVEL` | No | `INFO` | `DEBUG` for verbose |

## 5. Pushing the Docker image

```bash
# Build with a registry-friendly tag
docker build -t YOUR_REGISTRY/gridwise-api:1.0.0 .

# Login and push
docker login YOUR_REGISTRY
docker push YOUR_REGISTRY/gridwise-api:1.0.0
```

For Docker Hub: `docker push yourusername/gridwise-api:1.0.0`.
For GHCR: tag as `ghcr.io/yourname/gridwise-api:1.0.0`.

Record the exact reference (e.g. `docker.io/yourusername/gridwise-api:1.0.0`)
in the submission.

## 6. Public reachability checklist

Before declaring the service "live":

- [ ] Public URL is reachable from the open internet.
- [ ] `GET /health` returns 200 with `{"status":"ok"}` from outside the
      development environment.
- [ ] `POST /optimize-energy` accepts a valid sample and returns 200.
- [ ] Endpoint remains reachable during the judging window
      (4-hour online round + post-window access).
- [ ] Repeated requests are stable.
- [ ] `OPENROUTER_API_KEY` is valid and has sufficient quota.
- [ ] No secrets are visible in HTTP responses or logs.

## 7. Local reproduction

Anyone with the repository and Docker should be able to run the service
locally without help. Verify by following the README quickstart on a
fresh machine.