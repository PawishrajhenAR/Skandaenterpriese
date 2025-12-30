from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import sqlite3
import os

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


def init_sqlite_wal_mode(database_uri):
    """
    Initialize SQLite database with WAL mode for better concurrency.
    Only runs for SQLite databases (not PostgreSQL/Supabase).
    """
    if database_uri and database_uri.startswith('sqlite:///'):
        db_path = database_uri.replace('sqlite:///', '')
        try:
            # Connect to database and enable WAL mode
            conn = sqlite3.connect(db_path, timeout=20.0)
            conn.execute('PRAGMA journal_mode=WAL;')
            conn.execute('PRAGMA synchronous=NORMAL;')  # Better performance with WAL
            conn.execute('PRAGMA foreign_keys=ON;')  # Enable foreign key constraints
            conn.execute('PRAGMA busy_timeout=20000;')  # 20 second timeout
            conn.close()
        except Exception as e:
            print(f"Warning: Could not enable WAL mode: {e}")


def is_postgresql(database_uri):
    """Check if database URI is PostgreSQL"""
    return database_uri and ('postgresql' in database_uri.lower() or 'postgres' in database_uri.lower())


def is_sqlite(database_uri):
    """Check if database URI is SQLite"""
    return database_uri and database_uri.startswith('sqlite:///')
