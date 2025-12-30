import os
from pathlib import Path

basedir = Path(__file__).parent.absolute()

# Ensure database directory exists (for SQLite fallback only)
db_dir = basedir
db_dir.mkdir(parents=True, exist_ok=True)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database configuration - prioritize PostgreSQL (Supabase) over SQLite
    database_url = os.environ.get('DATABASE_URL', '')
    
    # Fix postgres:// to postgresql:// for SQLAlchemy 2.0+
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    # Use PostgreSQL if DATABASE_URL is provided, otherwise fall back to SQLite for local dev
    if database_url and 'postgresql' in database_url.lower():
        SQLALCHEMY_DATABASE_URI = database_url
        # PostgreSQL/Supabase engine options
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,  # Verify connections before using
            'pool_recycle': 3600,  # Recycle connections after 1 hour
            'pool_size': 5,  # Connection pool size
            'max_overflow': 10,  # Max overflow connections
            'connect_args': {
                'connect_timeout': 10,  # Connection timeout in seconds
                'sslmode': 'require' if 'supabase' in database_url.lower() else 'prefer'
            }
        }
    else:
        # SQLite fallback for local development
        db_path = db_dir / "skanda.db"
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path.absolute()}'
        # SQLite engine options for better concurrency and reliability
        SQLALCHEMY_ENGINE_OPTIONS = {
            'connect_args': {
                'check_same_thread': False,  # Allow multi-threaded access
                'timeout': 20  # 20 second timeout for database operations
            },
            'pool_pre_ping': True,  # Verify connections before using
            'pool_recycle': 3600,  # Recycle connections after 1 hour
        }
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = basedir / 'static' / 'uploads' / 'bills'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    # Backup configuration
    BACKUP_FOLDER = basedir / 'backups'
    BACKUP_RETENTION_DAYS = 30  # Keep backups for 30 days


class DevelopmentConfig(Config):
    DEBUG = True
    # In development, prefer SQLite unless DATABASE_URL is explicitly set
    if not os.environ.get('DATABASE_URL'):
        db_path = db_dir / "skanda.db"
        Config.SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path.absolute()}'


class ProductionConfig(Config):
    DEBUG = False
    # Production always uses PostgreSQL (Supabase)
    # DATABASE_URL must be set in production environment
    # Validation happens at runtime when config is loaded
    pass


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
