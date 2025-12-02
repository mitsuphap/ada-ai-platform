# Frontend Deployment Guide - Vercel

## Step 1: Add Credit Card to Fly.io (Keep Backend Running)

1. Visit: https://fly.io/trial
2. Click "Add Payment Method"
3. Add your credit card (no charge for free tier)
4. This prevents your backend from stopping after 5 minutes

**Note:** Your backend will continue to run for free, but adding a card removes the trial timeout.

---

## Step 2: Prepare Frontend for Deployment

The frontend is already configured:
- ✅ `.env.production` file created with backend URL
- ✅ `axios.ts` uses `VITE_API_URL` environment variable
- ✅ Backend CORS updated to allow Vercel domains

---

## Step 3: Deploy to Vercel

### Option A: Deploy via Vercel Dashboard (Easiest)

1. **Push your code to GitHub** (if not already):
   ```bash
   git add .
   git commit -m "Prepare frontend for deployment"
   git push origin main
   ```

2. **Go to Vercel:**
   - Visit: https://vercel.com
   - Sign up/Login with GitHub

3. **Import Project:**
   - Click "Add New..." → "Project"
   - Import your GitHub repository
   - Select the repository

4. **Configure Project:**
   - **Framework Preset:** Vite
   - **Root Directory:** `Implementation/frontend`
   - **Build Command:** `npm install && npm run build`
   - **Output Directory:** `dist`
   - **Install Command:** `npm install`

5. **Environment Variables:**
   - Click "Environment Variables"
   - Add: `VITE_API_URL` = `https://ada-backend.fly.dev`
   - Select: Production, Preview, Development

6. **Deploy:**
   - Click "Deploy"
   - Wait for build to complete (~2-3 minutes)

7. **Get Your Frontend URL:**
   - After deployment, Vercel will provide a URL like: `https://your-app-name.vercel.app`
   - Copy this URL

### Option B: Deploy via Vercel CLI

1. **Install Vercel CLI:**
   ```bash
   npm install -g vercel
   ```

2. **Login:**
   ```bash
   vercel login
   ```

3. **Navigate to frontend directory:**
   ```bash
   cd Implementation/frontend
   ```

4. **Deploy:**
   ```bash
   vercel
   ```
   
   When prompted:
   - Set up and deploy? **Yes**
   - Which scope? **Your account**
   - Link to existing project? **No**
   - Project name? **ada-frontend** (or your choice)
   - Directory? **./** (current directory)
   - Override settings? **No**

5. **Set environment variable:**
   ```bash
   vercel env add VITE_API_URL production
   # Enter: https://ada-backend.fly.dev
   ```

6. **Redeploy with env var:**
   ```bash
   vercel --prod
   ```

---

## Step 4: Update Backend CORS (After Getting Vercel URL)

After deployment, update backend CORS with your actual Vercel URL:

1. **Get your Vercel URL** (e.g., `https://ada-frontend.vercel.app`)

2. **Update backend CORS:**
   - Edit `Implementation/backend/main.py`
   - Replace `"https://*.vercel.app"` with your actual URL
   - Or keep the wildcard if you want preview deployments to work

3. **Redeploy backend:**
   ```bash
   fly deploy
   ```

---

## Step 5: Test Your Deployment

1. **Visit your frontend URL:**
   - Open: `https://your-app-name.vercel.app`

2. **Test API connection:**
   - Check browser console for any errors
   - Try using the scraper features
   - Verify API calls are going to `https://ada-backend.fly.dev`

---

## Troubleshooting

### Frontend can't connect to backend
- Check `VITE_API_URL` is set correctly in Vercel
- Verify backend CORS allows your Vercel domain
- Check browser console for CORS errors

### Build fails
- Make sure `Root Directory` is set to `Implementation/frontend`
- Check build logs in Vercel dashboard
- Verify all dependencies are in `package.json`

### API calls fail
- Verify backend is running: `https://ada-backend.fly.dev/health`
- Check CORS settings in backend
- Verify `VITE_API_URL` environment variable

---

## Cost Summary

- **Backend (Fly.io):** $0/month (free tier)
- **Frontend (Vercel):** $0/month (free tier)
- **Total:** $0/month

---

## URLs After Deployment

- **Backend:** `https://ada-backend.fly.dev`
- **Frontend:** `https://your-app-name.vercel.app`
- **API Docs:** `https://ada-backend.fly.dev/docs`

---

## Next Steps

1. ✅ Add credit card to Fly.io
2. ✅ Deploy frontend to Vercel
3. ✅ Test full-stack application
4. ✅ Share your app URL!

