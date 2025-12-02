# Fly.io Deployment Guide

## Quick Start

### 1. Login to Fly.io
```bash
fly auth login
```

### 2. Create PostgreSQL Database

**⚠️ Important:** Managed Postgres (`fly mpg`) costs $38+/month. For FREE tier, use **Unmanaged Postgres** (`fly postgres`).

**Use Unmanaged Postgres (FREE tier):**
```bash
# Create unmanaged Postgres database (FREE with shared-cpu-1x)
# Use a UNIQUE name - add your username, date, or random suffix
fly postgres create --name ada-db-sky-2025 --region iad --vm-size shared-cpu-1x --volume-size 1

# When prompted for "Initial cluster size", enter: 1 (not 3)
# Cluster size 3 is for HA and costs more. Size 1 is free.

# Attach to your app (use the same name you chose above)
fly postgres attach ada-db-sky-2025
```

**Note:** If you get "Name has already been taken", try a more unique name:
- `ada-db-sky-2025` (current suggestion)
- `ada-db-yourname-2025`
- `ada-backend-db-20250115` (with today's date)
- `ada-db-<random-number>` (e.g., `ada-db-12345`)
- Or any unique name you prefer

### 4. Set Environment Variables (Secrets)
```bash
# Get database connection details first
fly postgres connect -a ada-backend-db

# Set secrets (replace with your actual values)
fly secrets set GEMINI_API_KEY=your_gemini_key_here
fly secrets set GOOGLE_CSE_API_KEY=your_google_cse_key_here
fly secrets set GOOGLE_CSE_CX=your_cse_cx_here
fly secrets set AUTO_API_KEY=your_api_key_here  # Optional

# Database connection is auto-set by postgres attach, but you can verify:
fly secrets list
```

### 5. Deploy Backend
```bash
fly deploy
```

### 6. Get Your Backend URL
```bash
fly status
# Or open in browser
fly open
```

Your backend will be available at: `https://ada-backend.fly.dev`

## Useful Commands

```bash
# View logs
fly logs

# Check app status
fly status

# SSH into app (for debugging)
fly ssh console

# Restart app
fly apps restart ada-backend

# View secrets
fly secrets list

# Set a secret
fly secrets set KEY=value

# Remove a secret
fly secrets unset KEY
```

## Frontend Deployment

### Option 1: Deploy to Vercel (Recommended - Free)
1. Go to [vercel.com](https://vercel.com)
2. Import your GitHub repository
3. Set root directory: `Implementation/frontend`
4. Build command: `npm install && npm run build`
5. Add environment variable: `VITE_API_URL=https://ada-backend.fly.dev`
6. Deploy

### Option 2: Deploy to Fly.io
Create a separate Fly.io app for frontend (see fly.toml.frontend.example)

## Database Management

```bash
# Connect to database
fly postgres connect -a ada-backend-db

# View database info
fly postgres status -a ada-backend-db

# Create database backup
fly postgres backup create -a ada-backend-db

# List backups
fly postgres backup list -a ada-backend-db
```

## Troubleshooting

### App won't start
```bash
# Check logs
fly logs

# Check status
fly status

# Verify secrets are set
fly secrets list
```

### Database connection issues
```bash
# Verify database is running
fly postgres status -a ada-backend-db

# Check connection string
fly postgres connect -a ada-backend-db
```

### Build fails
```bash
# Check build logs
fly logs --build

# Try rebuilding
fly deploy --build-only
```

## Cost Estimate

- Backend VM: **Free** (shared-cpu-1x)
- PostgreSQL: **Free** (unmanaged Postgres with shared-cpu-1x, 3GB storage)
  - ⚠️ Managed Postgres (`fly mpg`) costs $38+/month - don't use for free tier
  - ✅ Unmanaged Postgres (`fly postgres`) is FREE
- Frontend: **Free** (Vercel or Fly.io shared-cpu-1x)
- **Total: $0/month** (within free tier limits)

## Notes

- The app name in `fly.toml` is `ada-backend` - change if needed
- Region is set to `iad` (Washington DC) - change to your preferred region
- Database uses free tier (`shared-cpu-1x`) - upgrade if needed
- Frontend CORS is configured for `ada-frontend.fly.dev` - update if using different domain

