"""
Fix PostgreSQL sequences after data migration
When data is migrated with explicit IDs, PostgreSQL sequences don't advance.
This script resets all sequences to the correct values.
"""

import os
from sqlalchemy import create_engine, text

# Supabase connection string
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:skandadb%40007@db.yqhwlczamvzmbziabwyv.supabase.co:5432/postgres')

def fix_sequences():
    """Fix all PostgreSQL sequences to match current max IDs"""
    print("Fixing PostgreSQL sequences...")
    
    engine = create_engine(DATABASE_URL, connect_args={'sslmode': 'require'})
    
    # Tables with SERIAL/auto-increment IDs
    tables = [
        'tenants',
        'users',
        'vendors',
        'bills',
        'bill_items',
        'proxy_bills',
        'proxy_bill_items',
        'credit_entries',
        'delivery_orders',
        'ocr_jobs',
        'audit_logs',
        'permissions',
        'role_permissions'
    ]
    
    with engine.connect() as conn:
        for table in tables:
            try:
                # Get current max ID
                result = conn.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {table}"))
                max_id = result.scalar()
                
                # Get sequence name (PostgreSQL convention: tablename_id_seq)
                sequence_name = f"{table}_id_seq"
                
                # Reset sequence to max_id + 1 (but at least 1, since sequences start at 1)
                next_val = max(max_id + 1, 1)
                conn.execute(text(f"SELECT setval('{sequence_name}', {next_val}, false)"))
                conn.commit()
                
                print(f"✓ Fixed {table}: sequence set to {next_val} (max_id was {max_id})")
            except Exception as e:
                print(f"✗ Error fixing {table}: {e}")
                conn.rollback()
    
    print("\n✅ All sequences fixed!")

if __name__ == '__main__':
    fix_sequences()

