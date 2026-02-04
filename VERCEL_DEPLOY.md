# Vercel Deployment Guide

## Prerequisites

- Supabase project with Session mode pooler connection string
- GitHub repo connected to Vercel

## Environment Variables

Set in Vercel Project Settings → Environment Variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Supabase pooler URI: `postgresql://postgres.PROJECT_REF:PASSWORD@aws-1-REGION.pooler.supabase.com:5432/postgres` |
| `SECRET_KEY` | Yes | Random string for Flask session encryption |
| `FLASK_ENV` | No | Set to `production` (default) |

## Deploy

1. Push to GitHub
2. Connect repo at [vercel.com/new](https://vercel.com/new)
3. Framework preset: **Flask** (auto-detected)
4. Add environment variables
5. Deploy

Or via CLI:

```bash
vercel
# Add DATABASE_URL and SECRET_KEY when prompted
```

## Limitations

- **File uploads**: Vercel serverless has ephemeral filesystem. Bill image uploads may need Supabase Storage for production.
- **Bundle size**: Python functions have a 250MB limit. `easyocr` adds weight; consider lazy-loading or alternative OCR for production.
