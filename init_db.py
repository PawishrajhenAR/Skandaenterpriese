"""
Quick database initialization script.
Run this to create all tables and initialize the database.
"""

from app import create_app
from extensions import db
from models import *  # Import all models to ensure they're registered

app = create_app('development')

with app.app_context():
    print("Creating database tables...")
    db.create_all()
    print("✓ All tables created successfully!")
    print("\nNext step: Run 'python seed.py' to populate initial data (users, permissions, etc.)")





