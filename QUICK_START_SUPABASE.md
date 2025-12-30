# Quick Start: Supabase Migration

## 🚀 Quick Setup (5 minutes)

### 1. Create Supabase Project
1. Go to https://supabase.com → Sign up/Login
2. Click "New Project"
3. Fill details → Create project
4. Wait 2-3 minutes

### 2. Get Connection String
1. Settings → Database
2. Copy **Connection string** (URI format)
3. Replace `[YOUR-PASSWORD]` with your database password

### 3. Create Schema
1. Go to **SQL Editor** in Supabase
2. Click **New Query**
3. Copy contents of `migrations/001_initial_schema.sql`
4. Paste and click **Run**

### 4. Seed Initial Data
```bash
# If you need to seed initial data (users, permissions, etc.)
python seed_supabase.py
# Or use the Flask seed script:
python seed.py
```

### 5. Configure Application
```bash
# Set environment variable
export DATABASE_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres"

# Or create .env file:
echo 'DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres' > .env
```

### 6. Run Application
```bash
python app.py
```

### 7. Verify
- Visit http://localhost:5000/health/db
- Should show: `{"status": "healthy", "database_type": "postgresql"}`

## ✅ Done!

Your application is now using Supabase PostgreSQL.

## 📚 More Details

- Full setup guide: `SUPABASE_SETUP.md`
- Migration summary: `MIGRATION_SUMMARY.md`

## 🔧 Troubleshooting

**Connection fails?**
- Check password is correct
- Verify connection string format
- Ensure project is active (not paused)

**Schema errors?**
- Check all tables were created in Supabase dashboard
- Verify migration script ran successfully

**Data missing?**
- Run seed script: `python seed_supabase.py` or `python seed.py`
- Check row counts in Supabase Table Editor

