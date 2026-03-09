"""
Database initialization for Supabase PostgreSQL.
Creates all tables. Run migrations/001_initial_schema.sql in Supabase SQL Editor first,
or use this script to create tables via SQLAlchemy.
"""

from app import create_app
from extensions import db
from models import *  # Import all models to ensure they're registered

app = create_app('development')

with app.app_context():
    print("Creating database tables in Supabase...")
    db.create_all()
    print("All tables created successfully!")
    print("\nNext step: Run 'python seed.py' to populate initial data (users, permissions, etc.)")





