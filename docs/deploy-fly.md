# Deploy to Fly.io

Fly.io runs Docker containers on lightweight VMs worldwide. It offers a free tier with up to 3 shared VMs and has built-in Postgres and Redis support.

**Estimated cost:** Free tier covers 3 VMs. Full deploy (4 services) ~$5-10/month.

## Prerequisites

- [Fly.io account](https://fly.io) (sign up at fly.io)
- [flyctl CLI](https://fly.io/docs/flyctl/install/) installed

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
fly auth login
```

## Architecture on Fly

You'll create 4 Fly apps from the same repo:

| App | Config | Purpose |
|-----|--------|---------|
| `boz-weather-trader` | `fly.toml` | FastAPI backend + Alembic migrations |
| `boz-weather-trader-web` | `fly.frontend.toml` | Next.js PWA frontend |
| `boz-celery-worker` | CLI flags | Celery task worker |
| `boz-celery-beat` | CLI flags | Celery beat scheduler |

Plus managed Postgres and Redis.

> **Free tier note:** The free tier allows 3 shared VMs. To stay free, combine celery-worker and celery-beat into a single process (see [Free Tier Tips](#free-tier-tips) below).

## Step 1: Create Postgres

```bash
fly postgres create --name boz-db --region iad --vm-size shared-cpu-1x --volume-size 1
```

Note the connection string. You'll need it in the format:
```
postgresql+asyncpg://user:password@boz-db.flycast:5432/boz_weather_trader
```

## Step 2: Create Redis

```bash
fly redis create --name boz-redis --region iad --plan free
```

Note the Redis URL provided by Fly (Upstash Redis).

## Step 3: Deploy Backend

The repo includes `fly.toml` pre-configured for the backend.

```bash
# Launch the app (first time only)
fly launch --copy-config --name boz-weather-trader --region iad --no-deploy

# Attach Postgres
fly postgres attach boz-db --app boz-weather-trader

# Set secrets
fly secrets set \
  ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  DATABASE_URL="postgresql+asyncpg://USER:PASS@boz-db.flycast:5432/boz_weather_trader" \
  REDIS_URL="redis://YOUR_REDIS_URL" \
  CELERY_BROKER_URL="redis://YOUR_REDIS_URL/1" \
  CELERY_RESULT_BACKEND="redis://YOUR_REDIS_URL/2" \
  NWS_USER_AGENT="BozWeatherTrader/1.0 (your-email@example.com)" \
  --app boz-weather-trader

# Deploy
fly deploy
```

Verify: `fly status` and visit `https://boz-weather-trader.fly.dev/health`

## Step 4: Deploy Celery Worker

```bash
# Create a new app for the worker (no public-facing ports)
fly launch --name boz-celery-worker --region iad --no-deploy --no-public-ips \
  --dockerfile Dockerfile.backend

# Set the same secrets as backend
fly secrets set \
  ENCRYPTION_KEY="SAME_AS_BACKEND" \
  DATABASE_URL="postgresql+asyncpg://USER:PASS@boz-db.flycast:5432/boz_weather_trader" \
  REDIS_URL="redis://YOUR_REDIS_URL" \
  CELERY_BROKER_URL="redis://YOUR_REDIS_URL/1" \
  CELERY_RESULT_BACKEND="redis://YOUR_REDIS_URL/2" \
  NWS_USER_AGENT="BozWeatherTrader/1.0 (your-email@example.com)" \
  --app boz-celery-worker

# Deploy with custom command
fly deploy --app boz-celery-worker \
  --dockerfile Dockerfile.backend \
  --entrypoint "" \
  --command "celery -A backend.celery_app worker --loglevel=warning --concurrency=2"
```

## Step 5: Deploy Celery Beat

```bash
fly launch --name boz-celery-beat --region iad --no-deploy --no-public-ips \
  --dockerfile Dockerfile.backend

# Set same secrets as backend
fly secrets set \
  ENCRYPTION_KEY="SAME_AS_BACKEND" \
  DATABASE_URL="postgresql+asyncpg://USER:PASS@boz-db.flycast:5432/boz_weather_trader" \
  REDIS_URL="redis://YOUR_REDIS_URL" \
  CELERY_BROKER_URL="redis://YOUR_REDIS_URL/1" \
  CELERY_RESULT_BACKEND="redis://YOUR_REDIS_URL/2" \
  --app boz-celery-beat

fly deploy --app boz-celery-beat \
  --dockerfile Dockerfile.backend \
  --entrypoint "" \
  --command "celery -A backend.celery_app beat --loglevel=warning"
```

## Step 6: Deploy Frontend

```bash
# Edit fly.frontend.toml — update NEXT_PUBLIC_API_URL to your backend URL
# Then deploy:
fly launch --config fly.frontend.toml --name boz-weather-trader-web --region iad --no-deploy
fly deploy --config fly.frontend.toml
```

> **Important:** Edit `fly.frontend.toml` and set `NEXT_PUBLIC_API_URL` to your actual backend URL (e.g., `https://boz-weather-trader.fly.dev`) *before* deploying. This value is baked into the JavaScript bundle at build time.

## Step 7: Verify

```bash
# Check all apps
fly status --app boz-weather-trader
fly status --app boz-weather-trader-web
fly status --app boz-celery-worker
fly status --app boz-celery-beat

# Check backend health
curl https://boz-weather-trader.fly.dev/health

# View logs
fly logs --app boz-weather-trader
```

## DATABASE_URL Format

Fly Postgres provides URLs in the format:
```
postgres://user:password@host:5432/database
```

Boz Weather Trader requires the `asyncpg` driver:
```
postgresql+asyncpg://user:password@host:5432/database
```

Replace `postgres://` with `postgresql+asyncpg://` when setting `DATABASE_URL`.

## Free Tier Tips

To stay within the 3-VM free tier, combine Celery worker and beat into a single process:

```bash
# Skip Steps 4 and 5. Instead, deploy a single combined Celery app:
fly launch --name boz-celery --region iad --no-deploy --no-public-ips \
  --dockerfile Dockerfile.backend

# Deploy with combined worker+beat command
fly deploy --app boz-celery \
  --dockerfile Dockerfile.backend \
  --entrypoint "" \
  --command "celery -A backend.celery_app worker --beat --loglevel=warning --concurrency=2"
```

This uses 3 VMs total: backend + frontend + celery (combined).

## Updating

```bash
fly deploy                                    # Backend
fly deploy --config fly.frontend.toml         # Frontend
fly deploy --app boz-celery-worker            # Worker
fly deploy --app boz-celery-beat              # Beat
```

## Scaling

```bash
# Scale backend to 2 machines
fly scale count 2 --app boz-weather-trader
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Backend won't start | Check `fly logs` — likely missing secrets (`ENCRYPTION_KEY` has no default) |
| Database connection refused | Ensure you used `fly postgres attach` and the `postgresql+asyncpg://` prefix |
| Frontend shows blank page | Verify `NEXT_PUBLIC_API_URL` was set correctly *before* build |
| Celery tasks not running | Check worker logs: `fly logs --app boz-celery-worker` |
| ARM build errors | Fly builds on x86 by default. Add `--remote-only` to force remote builds |
