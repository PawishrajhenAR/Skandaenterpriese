from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = None  # API-only: unauthorized_handler returns 401 JSON
login_manager.login_message = 'Authentication required'
login_manager.login_message_category = 'info'


def is_postgresql(database_uri):
    """Check if database URI is PostgreSQL"""
    return database_uri and ('postgresql' in database_uri.lower() or 'postgres' in database_uri.lower())
