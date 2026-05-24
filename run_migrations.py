"""
Run database migrations on Render/Supabase.
Executes every migrations/*.sql file in filename order against DATABASE_URL.
Migrations should be idempotent where possible.
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
    sql_files = sorted(migration_dir.glob('*.sql'))
    if not sql_files:
        print(f"Error: No migration files found in: {migration_dir}")
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    conn.autocommit = True
    cur = conn.cursor()
    try:
        for sql_file in sql_files:
            sql = sql_file.read_text(encoding='utf-8')
            cur.execute(sql)
            print(f"Applied {sql_file.name}")
        print(f"Applied {len(sql_files)} migration(s) successfully")
    except Exception as e:
        print(f"Migration error: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
