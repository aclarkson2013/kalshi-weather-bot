# Deploy to Railway

Railway is the easiest cloud deploy option. It supports multi-service apps, has managed PostgreSQL and Redis, and auto-deploys from GitHub.

**Estimated cost:** ~$5-15/month depending on usage.

## Prerequisites

- [Railway account](https://railway.app) (sign up with GitHub)
- [Railway CLI](https://docs.railway.app/develop/cli) installed (`npm install -g @railway/cli`)

## Option A: One-Click Deploy

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/new?repo=https://github.com/aclarkson2013/boz-weather-trader)

This deploys the backend service only. You'll need to add the remaining services manually (see Steps 4-7 below).

## Option B: CLI Deploy (Recommended)

### Step 1: Login and Create Project

```bash
railway login
railway init  # Creates a new project
```

### Step 2: Add PostgreSQL

```bash
railway add --plugin postgresql
```

Railway auto-injects `DATABASE_URL` into your services. However, our app needs the `asyncpg` driver prefix. You'll set a custom `DATABASE_URL` in Step 5.

### Step 3: Add Redis

```bash
railway add --plugin redis
```

Railway auto-injects `REDIS_URL`.

### Step 4: Deploy Backend

```bash
railway up --service backend
```

Set environment variables in the Railway dashboard or CLI:

```bash
# Required — generate a Fernet key
railway variables set ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Required — use asyncpg driver (replace the Railway-provided DATABASE_URL)
# Get the Railway DATABASE_URL, then prefix it with postgresql+asyncpg://
# Example: if Railway gives postgres://user:pass@host:5432/db
#   set: postgresql+asyncpg://user:pass@host:5432/db
railway variables set DATABASE_URL="postgresql+asyncpg://YOUR_USER:YOUR_PASS@YOUR_HOST:5432/YOUR_DB"

# Required — Celery broker and result backend
# Use the Railway REDIS_URL with different DB numbers
railway variables set CELERY_BROKER_URL="redis://YOUR_REDIS_HOST:6379/1"
railway variables set CELERY_RESULT_BACKEND="redis://YOUR_REDIS_HOST:6379/2"

# Required — app settings
railway variables set ENVIRONMENT=production
railway variables set LOG_LEVEL=WARNING
railway variables set NWS_USER_AGENT="BozWeatherTrader/1.0 (your-email@example.com)"
```

### Step 5: Deploy Celery Worker

Create a new service in Railway dashboard, pointing to the same repo. Override the start command:

```
celery -A backend.celery_app worker --loglevel=warning --concurrency=2
```

Copy all environment variables from the backend service.

### Step 6: Deploy Celery Beat

Create another service, same repo. Override the start command:

```
celery -A backend.celery_app beat --loglevel=warning
```

Copy all environment variables from the backend service.

### Step 7: Deploy Frontend

Create a new service pointing to the same repo. Configure:

- **Root directory:** `frontend`
- **Build command:** `npm run build`
- **Start command:** `npm start`

Set environment variable:

```bash
NEXT_PUBLIC_API_URL=https://YOUR-BACKEND-SERVICE.up.railway.app
```

> **Important:** `NEXT_PUBLIC_API_URL` must be set *before* the build. It is baked into the JavaScript bundle at build time.

### Step 8: Verify

1. Visit your backend URL + `/health` — should return `{"status": "ok"}`
2. Visit your frontend URL — should load the dashboard
3. Check Railway logs for any errors

## DATABASE_URL Format

Railway provides PostgreSQL URLs in the format:
```
postgres://user:password@host:port/database
```

Boz Weather Trader requires the `asyncpg` driver:
```
postgresql+asyncpg://user:password@host:port/database
```

Replace `postgres://` with `postgresql+asyncpg://` when setting `DATABASE_URL`.

## Updating

Railway auto-deploys when you push to GitHub. To manually redeploy:

```bash
railway up
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Backend crashes on startup | Check `ENCRYPTION_KEY` is set (no default — app fails fast without it) |
| Database connection refused | Verify `DATABASE_URL` uses `postgresql+asyncpg://` prefix |
| Frontend shows "Cannot connect" | Verify `NEXT_PUBLIC_API_URL` matches your backend's Railway URL |
| Celery tasks not running | Ensure worker and beat services have the same env vars as backend |
| Migrations not running | Backend entrypoint runs `alembic upgrade head` automatically on start |
