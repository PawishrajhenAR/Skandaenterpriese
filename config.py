import os
from pathlib import Path

# Load .env file for DATABASE_URL, SECRET_KEY, FLASK_ENV (Supabase)
from dotenv import load_dotenv
load_dotenv()

basedir = Path(__file__).parent.absolute()

# Ensure upload/backup directories exist (skip on Vercel - read-only filesystem)
try:
    basedir.mkdir(parents=True, exist_ok=True)
except (OSError, PermissionError):
    pass

# Vercel serverless has read-only filesystem; use /tmp for writable paths
_vercel = os.environ.get('VERCEL') == '1'


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database: Supabase PostgreSQL only (DATABASE_URL required)
    database_url = os.environ.get('DATABASE_URL', '')
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    # Tests use in-memory SQLite (conftest overrides); production requires Supabase
    if not database_url or 'postgresql' not in database_url.lower():
        if 'pytest' in __import__('sys').modules:
            database_url = 'sqlite:///:memory:'  # Tests only
        elif os.environ.get('FLASK_ENV') == 'development' or os.environ.get('USE_SQLITE') == '1':
            _db_path = (basedir / "local.db").resolve().as_posix()
            database_url = f'sqlite:///{_db_path}'
        else:
            raise ValueError(
                "DATABASE_URL must be set to a Supabase PostgreSQL connection string. "
                "Add it to .env: DATABASE_URL=postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres"
            )
    
    SQLALCHEMY_DATABASE_URI = database_url
    if 'postgresql' in database_url.lower():
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'pool_recycle': 3600,
            'pool_size': 5,
            'max_overflow': 10,
            'connect_args': {
                'connect_timeout': 10,
                'sslmode': 'require' if 'supabase' in database_url.lower() else 'prefer'
            }
        }
    else:
        # Tests only (sqlite:///:memory:)
        SQLALCHEMY_ENGINE_OPTIONS = {'connect_args': {'check_same_thread': False}}
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = Path('/tmp/uploads/bills') if _vercel else (basedir / 'static' / 'uploads' / 'bills')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    BACKUP_FOLDER = Path('/tmp/backups') if _vercel else (basedir / 'backups')
    BACKUP_RETENTION_DAYS = 30


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
