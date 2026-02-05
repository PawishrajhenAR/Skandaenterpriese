# Skanda Deployment Guide

## Architecture

- **Backend (Render)**: Flask API-only at `https://skandaenterpriese-1.onrender.com`
- **Frontend (Vercel)**: Static HTML/CSS/JS at `https://skandaenterpriese.vercel.app`
- **Database**: Supabase PostgreSQL

## Backend (Render)

### Environment Variables

Set in Render Dashboard → Service → Environment:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Supabase PostgreSQL connection string |
| `SECRET_KEY` | Yes | Random string for session encryption |
| `FRONTEND_URL` | Yes | Vercel frontend URL, e.g. `https://skandaenterpriese.vercel.app` |
| `FLASK_ENV` | No | Set to `production` |

### Health Endpoints

- `GET /health` - Simple health check
- `GET /health/db` - Database connectivity check

### API Base

All API routes are under `/api/`:

- `POST /api/auth/login` - Login (JSON body: `{username, password}`)
- `POST /api/auth/logout` - Logout
- `GET /api/auth/me` - Current user + permissions
- `GET /api/dashboard` - Dashboard stats
- `GET /api/bills` - Bills list
- `GET /api/vendors` - Vendors list
- ... (see `api_routes.py` for full list)

## Frontend (Vercel)

### Configuration (required to fix 404s)

1. In Vercel Dashboard → Project **skandaenterpriese** → **Settings** → **General**
2. **Root Directory**: Enable "Override" → set to `frontend`
3. **Framework Preset**: Other (static)
4. **Build Command**: (leave empty)
5. Click **Save**, then go to **Deployments** → **Redeploy** (or push to GitHub)

Without Root Directory = `frontend`, Vercel deploys Flask (which has no `/` route) and returns 404.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `API_URL` | No | Backend API URL. Default: `https://skandaenterpriese-1.onrender.com` |

To override the API URL, set `API_URL` and add a build command that injects it into `js/config.js`.

### Static Structure

```
frontend/
├── index.html      # Login
├── dashboard.html  # Dashboard
├── bills.html      # Bills list
├── vendors.html    # Vendors list
├── css/
├── js/
│   ├── config.js   # API_BASE URL (edit or inject at build)
│   ├── api.js      # Fetch wrapper
│   └── main.js
└── icons/
```

## CORS

The backend allows requests from `FRONTEND_URL`. Ensure:

1. Render: `FRONTEND_URL` matches your Vercel deployment URL exactly (including `https://`)
2. Session cookies use `SameSite=None; Secure` in production

## Render Service (Suspended)

If the Render service is suspended, unsuspend it from the Render Dashboard to enable the backend.

## Troubleshooting

### CORS: "No 'Access-Control-Allow-Origin' header"

1. **Set `FRONTEND_URL` in Render**  
   Render Dashboard → Service → Environment → Add `FRONTEND_URL` = `https://skandaenterpriese.vercel.app` (or your actual Vercel URL).

2. **Redeploy Render**  
   After changing env vars, trigger a manual deploy so the backend picks up the new CORS origin.

3. **Check URL match**  
   The origin must match exactly (including `https://` and no trailing slash).

### 404 on root URL (Render)

If `GET /` returns 404, the backend may be running an old build. Redeploy the Render service.

### Frontend calling wrong backend URL

If the frontend still calls `skandaenterpriese.onrender.com` instead of `skandaenterpriese-1.onrender.com`:

1. Ensure `frontend/js/config.js` has the correct `API_BASE` for your Render service.
2. Redeploy Vercel so the updated config is served.
3. Hard refresh (Ctrl+Shift+R) or clear cache to avoid cached JS.
