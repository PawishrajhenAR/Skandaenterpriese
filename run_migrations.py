"""
Run database migrations on Render/Supabase.
Executes migrations/001_initial_schema.sql against DATABASE_URL.
Idempotent: uses CREATE TABLE IF NOT EXISTS.
"""
import os
import sys
from pathlib import Path

# Load .env if present (local dev)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if not DATABASE_URL:
    print("Error: DATABASE_URL not set")
    sys.exit(1)
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

try:
    import psycopg2
except ImportError:
    print("Error: psycopg2 required. pip install psycopg2-binary")
    sys.exit(1)

def main():
    migration_dir = Path(__file__).parent / 'migrations'
    sql_file = migration_dir / '001_initial_schema.sql'
    if not sql_file.exists():
        print(f"Error: Migration file not found: {sql_file}")
        sys.exit(1)

    sql = sql_file.read_text(encoding='utf-8')
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
        print("✓ Migration 001_initial_schema.sql applied successfully")
    except Exception as e:
        print(f"Migration error: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    main()
