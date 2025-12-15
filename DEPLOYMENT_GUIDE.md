# Complete Deployment Guide - Backend & Frontend

## Prerequisites

- ✅ GitHub repository with your code
- ✅ Fly.io account (for backend)
- ✅ Vercel account (for frontend)
- ✅ API keys ready (GEMINI_API_KEY, GOOGLE_CSE_API_KEY, GOOGLE_CSE_CX)

---

## Part 1: Deploy Backend to Fly.io

### Step 1: Install Fly CLI

**Windows (PowerShell as Administrator):**
```bash
iwr https://fly.io/install.ps1 -useb | iex
```

**Verify installation:**
```bash
fly version
```

### Step 2: Login to Fly.io

```bash
fly auth login
```

This opens a browser to authenticate.

### Step 3: Create PostgreSQL Database

```bash
fly postgres create --name ada-db-20250115 --region iad --vm-size shared-cpu-1x --volume-size 1
```

**When prompted:**
- Initial cluster size: Enter `1` (for free tier)

**Save your database password** (shown after creation) - you won't see it again!

### Step 4: Create Backend App

```bash
cd C:\Users\Sky\Documents\Project\F2025_4495_050_PKu046
fly launch --no-deploy
```

**When prompted:**
- App name: `ada-backend` (or press Enter)
- Region: `iad` (or press Enter)
- PostgreSQL: Skip (we'll attach manually)
- Redis: No
- Tweaks: No

### Step 5: Attach Database to Backend

```bash
fly postgres attach ada-db-20250115
```

This automatically sets `DATABASE_URL` environment variable.

### Step 6: Set API Keys (Secrets)

```bash
fly secrets set GEMINI_API_KEY=your_actual_gemini_key
fly secrets set GOOGLE_CSE_API_KEY=your_actual_google_cse_key
fly secrets set GOOGLE_CSE_CX=your_actual_cse_cx
fly secrets set AUTO_API_KEY=your_api_key  # Optional
```

**Verify secrets:**
```bash
fly secrets list
```

### Step 7: Deploy Backend

```bash
fly deploy
```

**Wait 2-5 minutes** for deployment to complete.

### Step 8: Get Backend URL

```bash
fly status
```

Or open in browser:
```bash
fly open
```

**Your backend URL:** `https://ada-backend.fly.dev`

### Step 9: Test Backend

Visit:
- `https://ada-backend.fly.dev/health` - Should return `{"status": "ok"}`
- `https://ada-backend.fly.dev/docs` - API documentation

---

## Part 2: Deploy Frontend to Vercel

### Step 1: Push Code to GitHub

```bash
git add .
git commit -m "Prepare for deployment"
git push origin ada  # or your branch name
```

### Step 2: Go to Vercel

1. Visit: https://vercel.com
2. Sign up/Login with GitHub

### Step 3: Import Project

1. Click "Add New..." → "Project"
2. Import your GitHub repository
3. Select: `mitsuphap/F2025_4495_050_PKu046`

### Step 4: Configure Project Settings

**Framework Preset:**
- Select: `Vite`

**Root Directory:**
- Click "Edit"
- Enter: `Implementation/frontend`

**Build Command:**
- Should be: `npm run build`
- If not, click "Override" toggle and enter: `npm run build`

**Output Directory:**
- Should be: `dist`

**Install Command:**
- Should be: `npm install`

### Step 5: Add Environment Variable

1. Expand "Environment Variables" section
2. Click "Add"
3. Add:
   - **Name:** `VITE_API_URL`
   - **Value:** `https://ada-backend.fly.dev`
   - **Select:** Production, Preview, Development (all three)
4. Click "Add"

### Step 6: Deploy

1. Click "Deploy" button
2. Wait 2-3 minutes for build to complete

### Step 7: Get Frontend URL

After deployment:
- Production URL: `https://ada-frontend.vercel.app` (or your project name)
- Preview URL: `https://ada-frontend-xxxxx.vercel.app` (temporary)

### Step 8: Promote to Production (if needed)

If deployment is "Preview":
1. Go to Deployments tab
2. Click on the successful deployment
3. Click "Promote to Production"

---

## Part 3: Update Backend CORS (After Frontend Deployment)

### Step 1: Update CORS in Backend

The backend CORS is already configured to allow all origins (`["*"]`), but if you need to update it:

Edit `Implementation/backend/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Step 2: Redeploy Backend

```bash
git add Implementation/backend/main.py
git commit -m "Update CORS"
git push origin ada
fly deploy
```

---

## Part 4: Verify Everything Works

### Test Backend:
- ✅ `https://ada-backend.fly.dev/health` - Returns `{"status": "ok"}`
- ✅ `https://ada-backend.fly.dev/docs` - Shows API documentation

### Test Frontend:
- ✅ `https://ada-frontend.vercel.app/` - Home page loads
- ✅ `https://ada-frontend.vercel.app/scraper` - Scraper page loads
- ✅ Try searching - Should connect to backend without CORS errors

### Test Integration:
1. Open frontend: `https://ada-frontend.vercel.app/scraper`
2. Enter a search topic
3. Click "Search & Scrape Automatically"
4. Should work without network errors

---

## Troubleshooting

### Backend Issues

**Database connection fails:**
```bash
# Check database status
fly status -a ada-db-20250115

# Restart database if needed
fly apps restart ada-db-20250115
```

**Backend won't start:**
```bash
# Check logs
fly logs

# Check status
fly status
```

**CORS errors:**
- Verify backend CORS allows `["*"]`
- Redeploy backend: `fly deploy`

### Frontend Issues

**404 errors on routes:**
- Verify `vercel.json` exists in `Implementation/frontend/`
- Check Root Directory is set to `Implementation/frontend`

**Build fails:**
- Verify Build Command is `npm run build`
- Check build logs in Vercel dashboard

**Network errors:**
- Verify `VITE_API_URL` is set correctly in Vercel
- Check backend is running: `https://ada-backend.fly.dev/health`
- Verify backend CORS allows all origins

---

## Quick Reference Commands

### Backend (Fly.io)
```bash
# Deploy
fly deploy

# Check status
fly status

# View logs
fly logs

# Restart
fly apps restart ada-backend

# Set secret
fly secrets set KEY=value

# List secrets
fly secrets list
```

### Frontend (Vercel)
- Deployments happen automatically on git push
- Or manually: Vercel Dashboard → Deployments → Redeploy

---

## URLs After Deployment

- **Backend:** `https://ada-backend.fly.dev`
- **Frontend:** `https://ada-frontend.vercel.app`
- **API Docs:** `https://ada-backend.fly.dev/docs`

---

## Cost Summary

- **Backend (Fly.io):** $0/month (free tier)
- **Frontend (Vercel):** $0/month (free tier)
- **Database (Fly.io):** $0/month (free tier)
- **Total:** $0/month

---

## Next Steps

1. ✅ Test all endpoints
2. ✅ Share frontend URL with team
3. ✅ Monitor usage and costs
4. ✅ Set up custom domain (optional)

---

## Need Help?

- **Backend logs:** `fly logs`
- **Frontend logs:** Vercel Dashboard → Deployments → Click deployment → Logs
- **Backend status:** `fly status`
- **Frontend status:** Vercel Dashboard → Deployments



