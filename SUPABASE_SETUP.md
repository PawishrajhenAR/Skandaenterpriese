# Supabase Setup and Migration Guide

This guide walks you through setting up Supabase PostgreSQL database and migrating from SQLite.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Setting Up Supabase](#setting-up-supabase)
3. [Running Database Migrations](#running-database-migrations)
4. [Migrating Data from SQLite](#migrating-data-from-sqlite)
5. [Configuring the Application](#configuring-the-application)
6. [Verification](#verification)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Supabase account (free tier available at https://supabase.com)
- Python 3.11+
- `psycopg2-binary` package (already in requirements.txt)
- Existing SQLite database (if migrating data)

---

## Setting Up Supabase

### Step 1: Create a Supabase Project

1. Go to https://supabase.com and sign up/login
2. Click "New Project"
3. Fill in project details:
   - **Name**: `skanda-billing` (or your preferred name)
   - **Database Password**: Choose a strong password (save it!)
   - **Region**: Choose closest to your users
   - **Pricing Plan**: Free tier is sufficient for development
4. Click "Create new project"
5. Wait 2-3 minutes for project setup

### Step 2: Get Database Connection String

1. Go to your project dashboard
2. Navigate to **Settings** → **Database**
3. Scroll to **Connection string** section
4. Select **URI** tab
5. Copy the connection string (format: `postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres`)

**Important**: Replace `[YOUR-PASSWORD]` with the password you set during project creation.

### Step 3: Set Up Database Schema

You have two options:

#### Option A: Using Supabase SQL Editor (Recommended)

1. Go to **SQL Editor** in Supabase dashboard
2. Click **New Query**
3. Copy and paste the contents of `migrations/001_initial_schema.sql`
4. Click **Run** (or press Ctrl+Enter)
5. Verify all tables were created successfully

#### Option B: Using Python Script

```bash
# Set your Supabase connection string
export DATABASE_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres"

# Run the migration script
python -c "
from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app('production')
with app.app_context():
    with open('migrations/001_initial_schema.sql', 'r') as f:
        sql = f.read()
        # Execute each statement
        for statement in sql.split(';'):
            statement = statement.strip()
            if statement and not statement.startswith('--'):
                try:
                    db.session.execute(text(statement))
                except Exception as e:
                    print(f'Warning: {e}')
        db.session.commit()
    print('Schema created successfully!')
"
```

---

## Running Database Migrations

After creating the initial schema, run any additional migrations:

```bash
# Set DATABASE_URL environment variable
export DATABASE_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres"

# Run migrations (if needed)
python migrate_db_postgresql.py
python migrate_db_vendor_fields_postgresql.py
python migrate_db_ocr_fields_postgresql.py
```

**Note**: These migrations are idempotent - safe to run multiple times.

---

## Seeding Initial Data

If you need to create initial data (users, permissions, etc.):

### Option 1: Direct Seeding (Recommended)

```bash
# Set environment variable
export DATABASE_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres"

# Run direct seed script (no Flask required)
python seed_supabase.py
```

### Option 2: Flask Seed Script

```bash
# Set environment variable
export DATABASE_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres"

# Run Flask seed script
python seed.py
```

Both scripts will:
- Create default tenant (Skanda Enterprises)
- Create all permissions
- Set up role permissions
- Create default users (admin, salesman, delivery, organiser)

### Verify Data

After seeding, verify data:

```bash
# Check row counts match
python -c "
from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app('production')
with app.app_context():
    tables = ['tenants', 'users', 'vendors', 'bills', 'bill_items', 
              'proxy_bills', 'credit_entries', 'delivery_orders']
    for table in tables:
        result = db.session.execute(text(f'SELECT COUNT(*) FROM {table}'))
        count = result.scalar()
        print(f'{table}: {count} rows')
"
```

---

## Configuring the Application

### For Local Development

Create a `.env` file in the project root:

```env
# Supabase PostgreSQL (recommended for production-like testing)
DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres

# Or use SQLite for local development (no DATABASE_URL)
# Application will automatically use SQLite if DATABASE_URL is not set
```

### For Production (Render/Heroku/etc.)

Set the `DATABASE_URL` environment variable in your hosting platform:

```bash
# In Render dashboard: Environment → Add Environment Variable
DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres
```

### Application Behavior

- **If `DATABASE_URL` is set**: Uses PostgreSQL (Supabase)
- **If `DATABASE_URL` is not set**: Falls back to SQLite for local development
- **In Production mode**: Requires `DATABASE_URL` (will raise error if not set)

---

## Verification

### 1. Test Database Connection

```bash
# Start the application
python app.py

# In another terminal, test health endpoint
curl http://localhost:5000/health/db
```

Expected response:
```json
{
  "status": "healthy",
  "database_type": "postgresql",
  "database_name": "postgres",
  "postgresql_version": "PostgreSQL 15.x"
}
```

### 2. Test Application Features

1. **Login**: Use default credentials from `seed.py`
2. **Create a Vendor**: Verify data persists
3. **Create a Bill**: Test CRUD operations
4. **View Reports**: Ensure queries work correctly
5. **Check Logs**: Verify no database errors

### 3. Verify in Supabase Dashboard

1. Go to **Table Editor** in Supabase
2. Check that all tables exist
3. Verify data was migrated correctly
4. Test a query in **SQL Editor**

---

## Troubleshooting

### Connection Issues

**Error**: `connection refused` or `timeout`

**Solutions**:
- Verify `DATABASE_URL` is correct
- Check Supabase project is active (not paused)
- Verify password is correct (no special characters need URL encoding)
- Check firewall/network restrictions

**Error**: `SSL connection required`

**Solution**: Ensure connection string includes SSL mode:
```python
# In config.py, SSL mode is automatically set for Supabase
# If issues persist, manually add: ?sslmode=require
```

### Migration Issues

**Error**: `relation already exists`

**Solution**: Tables already exist. This is normal if you've run migrations before. The migration scripts are idempotent.

**Error**: `foreign key constraint violation`

**Solution**: Ensure you're migrating tables in the correct order. The migration script handles this automatically.

### Data Type Issues

**Error**: `invalid input syntax for type boolean`

**Solution**: SQLite uses 0/1 for booleans, PostgreSQL uses true/false. The migration script handles this conversion automatically.

### Performance Issues

**Slow queries**:
- Check indexes were created (see `migrations/001_initial_schema.sql`)
- Use Supabase dashboard to analyze query performance
- Consider adding additional indexes for frequently queried columns

---

## Supabase Features You Can Use

### 1. Real-time Subscriptions

Supabase supports real-time updates. You can enable this for live data updates:

```python
# Example: Listen to bill changes
from supabase import create_client

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
supabase.table('bills').on('INSERT', handle_new_bill).subscribe()
```

### 2. Row Level Security (RLS)

Enable RLS in Supabase for additional security:

```sql
-- Example: Users can only see their tenant's data
ALTER TABLE bills ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see only their tenant's bills"
ON bills FOR SELECT
USING (tenant_id = current_setting('app.tenant_id')::int);
```

### 3. Database Backups

Supabase automatically backs up your database:
- **Free tier**: Daily backups (7-day retention)
- **Pro tier**: Point-in-time recovery

### 4. Database Extensions

Enable PostgreSQL extensions in Supabase:

```sql
-- Example: Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

---

## Security Best Practices

1. **Never commit `DATABASE_URL` to version control**
   - Use `.env` file (add to `.gitignore`)
   - Use environment variables in production

2. **Use Connection Pooling**
   - Supabase provides connection pooling
   - Use the connection pooler URL for better performance

3. **Enable SSL**
   - SSL is required for Supabase
   - Automatically configured in `config.py`

4. **Rotate Passwords Regularly**
   - Change database password periodically
   - Update `DATABASE_URL` when changed

5. **Use Supabase API Keys Securely**
   - Store in environment variables
   - Never expose in client-side code

---

## Next Steps

1. ✅ Set up Supabase project
2. ✅ Run initial schema migration
3. ✅ Migrate data from SQLite (if applicable)
4. ✅ Configure application with `DATABASE_URL`
5. ✅ Test all features
6. ✅ Set up automated backups (Supabase handles this)
7. ✅ Monitor database usage in Supabase dashboard

---

## Support

- **Supabase Documentation**: https://supabase.com/docs
- **PostgreSQL Documentation**: https://www.postgresql.org/docs/
- **SQLAlchemy Documentation**: https://docs.sqlalchemy.org/

---

## Migration Checklist

- [ ] Supabase project created
- [ ] Database connection string obtained
- [ ] Initial schema created (`migrations/001_initial_schema.sql`)
- [ ] Data migrated from SQLite (if applicable)
- [ ] `DATABASE_URL` environment variable set
- [ ] Application tested with PostgreSQL
- [ ] All CRUD operations verified
- [ ] Reports and queries working
- [ ] Health check endpoint responding
- [ ] Backup strategy confirmed

---

**Congratulations!** Your application is now running on Supabase PostgreSQL! 🎉

