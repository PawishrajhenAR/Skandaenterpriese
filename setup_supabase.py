"""
Automated Supabase setup script
Creates schema and migrates data from SQLite if exists
"""

import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
import urllib.parse

# Supabase connection string (password URL-encoded)
DATABASE_URL = "postgresql://postgres:skandadb%40007@db.yqhwlczamvzmbziabwyv.supabase.co:5432/postgres"

def print_header(text):
    print(f"\n{'='*60}")
    print(f"{text}")
    print(f"{'='*60}\n")

def print_success(text):
    print(f"✓ {text}")

def print_error(text):
    print(f"✗ {text}")

def print_info(text):
    print(f"ℹ {text}")

def test_connection():
    """Test connection to Supabase"""
    print_header("Testing Supabase Connection")
    try:
        engine = create_engine(DATABASE_URL, connect_args={'sslmode': 'require'})
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            print_success(f"Connected to PostgreSQL: {version.split(',')[0]}")
            return True
    except Exception as e:
        print_error(f"Connection failed: {e}")
        return False

def create_schema():
    """Create database schema from SQL file"""
    print_header("Creating Database Schema")
    try:
        schema_file = Path("migrations/001_initial_schema.sql")
        if not schema_file.exists():
            print_error(f"Schema file not found: {schema_file}")
            return False
        
        with open(schema_file, 'r') as f:
            sql_content = f.read()
        
        engine = create_engine(DATABASE_URL, connect_args={'sslmode': 'require'})
        
        # Execute entire SQL file as one transaction
        with engine.begin() as conn:  # begin() auto-commits on success, rolls back on error
            # Execute the entire SQL file
            conn.execute(text(sql_content))
        
        print_success("Schema created successfully!")
        return True
    except Exception as e:
        print_error(f"Schema creation failed: {e}")
        return False

def check_tables():
    """Check if tables exist"""
    print_header("Verifying Tables")
    try:
        engine = create_engine(DATABASE_URL, connect_args={'sslmode': 'require'})
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]
            
            expected_tables = [
                'tenants', 'users', 'vendors', 'bills', 'bill_items',
                'proxy_bills', 'proxy_bill_items', 'credit_entries',
                'delivery_orders', 'ocr_jobs', 'audit_logs',
                'permissions', 'role_permissions'
            ]
            
            print_info(f"Found {len(tables)} tables")
            for table in expected_tables:
                if table in tables:
                    print_success(f"  {table}")
                else:
                    print_error(f"  {table} - MISSING")
            
            return len([t for t in expected_tables if t in tables]) == len(expected_tables)
    except Exception as e:
        print_error(f"Table check failed: {e}")
        return False

def migrate_data():
    """Migrate data from SQLite if database exists"""
    print_header("Checking for SQLite Data")
    sqlite_db = Path("skanda.db")
    
    if not sqlite_db.exists():
        print_info("No SQLite database found. Skipping data migration.")
        print_info("You can run seed.py to create initial data.")
        return True
    
    print_info(f"Found SQLite database: {sqlite_db}")
    print_warning("SQLite database found but migration script has been removed.")
    print_info("If you need to migrate data, use the Supabase dashboard or SQL tools.")
    print_info("For new setups, use seed.py to create initial data.")
    return True

def fix_sequences():
    """Fix PostgreSQL sequences after data migration"""
    print_header("Fixing PostgreSQL Sequences")
    try:
        engine = create_engine(DATABASE_URL, connect_args={'sslmode': 'require'})
        tables = [
            'tenants', 'users', 'vendors', 'bills', 'bill_items',
            'proxy_bills', 'proxy_bill_items', 'credit_entries',
            'delivery_orders', 'ocr_jobs', 'audit_logs', 'permissions', 'role_permissions'
        ]
        
        with engine.connect() as conn:
            for table in tables:
                try:
                    result = conn.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {table}"))
                    max_id = result.scalar()
                    sequence_name = f"{table}_id_seq"
                    next_val = max(max_id + 1, 1)
                    conn.execute(text(f"SELECT setval('{sequence_name}', {next_val}, false)"))
                    conn.commit()
                    print_success(f"{table}: sequence set to {next_val}")
                except Exception as e:
                    print_warning(f"{table}: {e}")
        
        print_success("Sequences fixed!")
        return True
    except Exception as e:
        print_error(f"Sequence fix failed: {e}")
        return False

def seed_initial_data():
    """Seed initial data if tables are empty"""
    print_header("Checking Initial Data")
    try:
        engine = create_engine(DATABASE_URL, connect_args={'sslmode': 'require'})
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM tenants"))
            tenant_count = result.scalar()
            
            if tenant_count == 0:
                print_info("No data found. Running seed script...")
                os.environ['DATABASE_URL'] = DATABASE_URL
                os.environ['FLASK_ENV'] = 'production'
                
                # Import and run seed directly instead of subprocess
                try:
                    from app import create_app
                    from extensions import db
                    from models import Tenant, User, Permission, RolePermission
                    
                    app = create_app('production')
                    with app.app_context():
                        # Import seed logic
                        from seed import PERMISSIONS, DEFAULT_ROLE_PERMISSIONS
                        
                        # Create tenant
                        tenant = Tenant.query.filter_by(code='skanda').first()
                        if not tenant:
                            tenant = Tenant(
                                name='Skanda Enterprises',
                                code='skanda',
                                is_active=True
                            )
                            db.session.add(tenant)
                            db.session.flush()
                            print_success("Created tenant: Skanda Enterprises")
                        
                        # Create permissions
                        for perm_data in PERMISSIONS:
                            perm = Permission.query.filter_by(code=perm_data['code']).first()
                            if not perm:
                                perm = Permission(
                                    name=perm_data['name'],
                                    code=perm_data['code'],
                                    description=perm_data['description'],
                                    category=perm_data['category']
                                )
                                db.session.add(perm)
                        db.session.flush()
                        
                        # Create role permissions
                        roles = ['ADMIN', 'SALESMAN', 'DELIVERY', 'ORGANISER']
                        for role in roles:
                            if role == 'ADMIN':
                                for perm_data in PERMISSIONS:
                                    perm = Permission.query.filter_by(code=perm_data['code']).first()
                                    role_perm = RolePermission.query.filter_by(
                                        role=role,
                                        permission_id=perm.id
                                    ).first()
                                    if not role_perm:
                                        role_perm = RolePermission(
                                            role=role,
                                            permission_id=perm.id,
                                            granted=True
                                        )
                                        db.session.add(role_perm)
                            else:
                                default_perms = DEFAULT_ROLE_PERMISSIONS.get(role, [])
                                for perm_code in default_perms:
                                    perm = Permission.query.filter_by(code=perm_code).first()
                                    if perm:
                                        role_perm = RolePermission.query.filter_by(
                                            role=role,
                                            permission_id=perm.id
                                        ).first()
                                        if not role_perm:
                                            role_perm = RolePermission(
                                                role=role,
                                                permission_id=perm.id,
                                                granted=True
                                            )
                                            db.session.add(role_perm)
                        
                        # Create users
                        users_to_create = [
                            {'username': 'admin', 'role': 'ADMIN', 'password': 'admin12233'},
                            {'username': 'salesman', 'role': 'SALESMAN', 'password': 'salesman123'},
                            {'username': 'delivery', 'role': 'DELIVERY', 'password': 'delivery123'},
                            {'username': 'organiser', 'role': 'ORGANISER', 'password': 'organiser123'}
                        ]
                        
                        for user_data in users_to_create:
                            user = User.query.filter_by(username=user_data['username']).first()
                            if not user:
                                user = User(
                                    tenant_id=tenant.id,
                                    username=user_data['username'],
                                    role=user_data['role'],
                                    is_active=True
                                )
                                user.set_password(user_data['password'])
                                db.session.add(user)
                                print_success(f"Created {user_data['role']} user: {user_data['username']}")
                        
                        db.session.commit()
                        print_success("Initial data seeded successfully!")
                        return True
                except Exception as e:
                    print_error(f"Seed failed: {e}")
                    import traceback
                    traceback.print_exc()
                    return False
            else:
                print_success(f"Found {tenant_count} tenant(s). Data already exists.")
                return True
    except Exception as e:
        print_error(f"Seed check failed: {e}")
        return False

def create_env_file():
    """Create .env file with DATABASE_URL"""
    print_header("Creating .env File")
    env_file = Path(".env")
    
    if env_file.exists():
        print_info(".env file already exists. Updating DATABASE_URL...")
        # Read existing .env
        lines = []
        if env_file.exists():
            with open(env_file, 'r') as f:
                lines = f.readlines()
        
        # Remove old DATABASE_URL if exists
        lines = [l for l in lines if not l.startswith('DATABASE_URL=')]
        
        # Add new DATABASE_URL
        lines.append(f'DATABASE_URL={DATABASE_URL}\n')
        
        with open(env_file, 'w') as f:
            f.writelines(lines)
    else:
        with open(env_file, 'w') as f:
            f.write(f'DATABASE_URL={DATABASE_URL}\n')
    
    print_success(".env file created/updated")
    return True

def main():
    print_header("Supabase Automated Setup")
    print_info("This script will:")
    print_info("1. Test connection to Supabase")
    print_info("2. Create database schema")
    print_info("3. Fix PostgreSQL sequences (if needed)")
    print_info("4. Seed initial data (if needed)")
    print_info("5. Create .env file")
    
    # Auto-proceed (non-interactive mode)
    print_info("Starting automated setup...\n")
    
    # Step 1: Test connection
    if not test_connection():
        print_error("Cannot proceed without database connection.")
        sys.exit(1)
    
    # Step 2: Create schema
    if not create_schema():
        print_error("Schema creation failed.")
        sys.exit(1)
    
    # Step 3: Verify tables
    if not check_tables():
        print_error("Not all tables were created.")
        sys.exit(1)
    
    # Step 4: Fix PostgreSQL sequences (important after data migration)
    fix_sequences()
    
    # Step 5: Seed initial data
    seed_initial_data()
    
    # Step 6: Create .env file
    create_env_file()
    
    print_header("Setup Complete!")
    print_success("Supabase is configured and ready to use.")
    print_info("Next steps:")
    print_info("1. Run: python app.py")
    print_info("2. Visit: http://localhost:5000/health/db")
    print_info("3. Login with default credentials from seed.py")

if __name__ == '__main__':
    main()

