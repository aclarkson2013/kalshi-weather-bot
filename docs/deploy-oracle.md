# Deploy to Oracle Cloud Free Tier

Oracle Cloud offers a **free forever** ARM VM with 4 OCPU and 24 GB RAM — more than enough for the entire Boz Weather Trader stack including monitoring. This is the most cost-effective option and runs the same Docker Compose setup as local development.

**Cost:** $0/month (free forever on Always Free tier).

## Prerequisites

- [Oracle Cloud account](https://www.oracle.com/cloud/free/) (requires credit card for verification, but free tier resources are never billed)

## Step 1: Create an ARM VM Instance

1. Log into the Oracle Cloud Console
2. Navigate to **Compute > Instances > Create Instance**
3. Configure:
   - **Name:** `boz-weather-trader`
   - **Image:** Ubuntu 22.04 (or 24.04)
   - **Shape:** VM.Standard.A1.Flex
     - OCPU: 4 (or fewer — 1 is sufficient)
     - Memory: 24 GB (or fewer — 4 GB is sufficient)
   - **Networking:** Create a new VCN or use existing
   - **SSH key:** Add your public SSH key
4. Click **Create**

### Open Firewall Ports

In your VCN's security list, add ingress rules:

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22 | TCP | Your IP | SSH access |
| 3000 | TCP | 0.0.0.0/0 | Frontend (or use a reverse proxy) |
| 8000 | TCP | 0.0.0.0/0 | Backend API (or use a reverse proxy) |

> **Recommended:** Use an Nginx reverse proxy with HTTPS instead of exposing ports directly. See [Optional: HTTPS Setup](#optional-https-with-lets-encrypt) below.

## Step 2: Install Docker

SSH into your VM and install Docker:

```bash
ssh ubuntu@YOUR_VM_IP

# Update packages
sudo apt update && sudo apt upgrade -y

# Install Docker
sudo apt install -y docker.io docker-compose-plugin

# Add your user to the docker group (avoids needing sudo)
sudo usermod -aG docker $USER

# Log out and back in for group change to take effect
exit
ssh ubuntu@YOUR_VM_IP

# Verify
docker --version
docker compose version
```

## Step 3: Clone and Configure

```bash
git clone https://github.com/aclarkson2013/boz-weather-trader.git
cd boz-weather-trader

# Generate .env with a random encryption key
bash scripts/generate-env.sh

# Edit .env — at minimum, set your email for NWS
nano .env
# Change: NWS_USER_AGENT=BozWeatherTrader/1.0 (your-email@example.com)
```

### Required .env Changes for Production

```bash
# In .env, update these values:

# Use a strong PostgreSQL password (not the default "boz")
DATABASE_URL=postgresql+asyncpg://boz:YOUR_STRONG_PASSWORD@postgres:5432/boz_weather_trader

# Set production mode
ENVIRONMENT=production

# Set your email for NWS API (required by NWS terms)
NWS_USER_AGENT=BozWeatherTrader/1.0 (your-real-email@example.com)

# Set the frontend API URL to your VM's public IP or domain
NEXT_PUBLIC_API_URL=http://YOUR_VM_IP:8000
```

Also update `.env.docker` with matching values (this file is used by Docker Compose):

```bash
cp .env.docker .env.docker.bak
nano .env.docker
# Update DATABASE_URL, ENCRYPTION_KEY, NWS_USER_AGENT to match .env
```

## Step 4: Start Services

**Core services only (no monitoring):**

```bash
docker compose -f docker-compose.yml -f docker-compose.cloud.yml up -d
```

**Full stack with monitoring (Prometheus + Grafana):**

```bash
docker compose up -d
```

**Production settings (resource limits, 4 workers) without monitoring:**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml up -d
```

The first build will take 5-10 minutes on ARM (compiling Python packages).

## Step 5: Verify

```bash
# Check all services are running
docker compose ps

# Check backend health
curl http://localhost:8000/health

# View logs
docker compose logs -f backend
```

Visit `http://YOUR_VM_IP:3000` in your browser to access the dashboard.

## Optional: HTTPS with Let's Encrypt

For production use, set up Nginx as a reverse proxy with free SSL certificates:

```bash
# Install Nginx and Certbot
sudo apt install -y nginx certbot python3-certbot-nginx

# Point a domain to your VM's IP (e.g., boz.yourdomain.com)
# Then configure Nginx:

sudo tee /etc/nginx/sites-available/boz <<'EOF'
server {
    listen 80;
    server_name boz.yourdomain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws {
        proxy_pass http://localhost:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/boz /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Get SSL certificate
sudo certbot --nginx -d boz.yourdomain.com
```

After HTTPS is configured, update `NEXT_PUBLIC_API_URL` in `.env.docker` to use `https://boz.yourdomain.com/api` and rebuild the frontend:

```bash
docker compose up -d --build frontend
```

## Updating

```bash
cd ~/boz-weather-trader
git pull
docker compose -f docker-compose.yml -f docker-compose.cloud.yml up -d --build
```

## Monitoring Health

```bash
# Check service status
docker compose ps

# View real-time logs
docker compose logs -f --tail=50

# Check disk usage
df -h

# Check memory usage
free -h
```

## Auto-Restart on Reboot

Docker Compose services are configured with `restart: unless-stopped`, so they'll restart automatically after a VM reboot. To ensure Docker itself starts on boot:

```bash
sudo systemctl enable docker
```

## Security Hardening

- [ ] Change the default PostgreSQL password from `boz` to a strong random password
- [ ] Ensure `ENCRYPTION_KEY` was generated (not the placeholder value)
- [ ] Set up HTTPS with Let's Encrypt (see above)
- [ ] Restrict SSH access to your IP only
- [ ] Close port 8000 externally if using Nginx reverse proxy
- [ ] Set `GF_SECURITY_ADMIN_PASSWORD` if using Grafana (don't leave it as `admin`)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Build fails on ARM | Python/Node ARM images are supported. If a specific package fails, check for ARM wheels or build from source |
| Out of memory during build | Limit concurrent builds: `docker compose up -d --build --parallel 2` |
| Services won't start | Check logs: `docker compose logs backend` — common issue is missing `ENCRYPTION_KEY` |
| Can't reach from browser | Check Oracle security list rules allow ingress on ports 3000/8000 |
| Database connection refused | Ensure postgres service is healthy: `docker compose ps` |
| Slow first build | Normal on ARM — Python packages compile from source. Subsequent builds use cache |
