import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from extensions import db
from models import User, Tenant, Vendor, Bill, Permission, RolePermission
from werkzeug.security import generate_password_hash


class TestConfig:
    """Test configuration"""
    SECRET_KEY = 'test-secret-key'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TESTING = True
    WTF_CSRF_ENABLED = False
    UPLOAD_FOLDER = Path(tempfile.mkdtemp()) / 'uploads' / 'bills'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024


@pytest.fixture
def app():
    """Create application for testing"""
    app = create_app('development')
    # Override with test config
    for key in dir(TestConfig):
        if not key.startswith('_'):
            app.config[key] = getattr(TestConfig, key)
    
    # Create upload directory
    app.config['UPLOAD_FOLDER'].mkdir(parents=True, exist_ok=True)
    
    with app.app_context():
        db.create_all()
        # Create test data
        setup_test_data()
        yield app
        db.session.remove()
        db.drop_all()
        # Cleanup upload directory
        if app.config['UPLOAD_FOLDER'].exists():
            shutil.rmtree(app.config['UPLOAD_FOLDER'].parent)
    
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create test CLI runner"""
    return app.test_cli_runner()


@pytest.fixture
def admin_user(app):
    """Create and return admin user"""
    with app.app_context():
        tenant = Tenant.query.filter_by(code='skanda').first()
        user = User.query.filter_by(username='admin').first()
        return user


@pytest.fixture
def salesman_user(app):
    """Create and return salesman user"""
    with app.app_context():
        user = User.query.filter_by(username='salesman').first()
        return user


@pytest.fixture
def organiser_user(app):
    """Create and return organiser user"""
    with app.app_context():
        user = User.query.filter_by(username='organiser').first()
        return user


def setup_test_data():
    """Setup test data in database"""
    # Create tenant
    tenant = Tenant.query.filter_by(code='skanda').first()
    if not tenant:
        tenant = Tenant(name='Skanda Enterprises', code='skanda', is_active=True)
        db.session.add(tenant)
        db.session.flush()
    
    # Create test users if they don't exist
    if not User.query.filter_by(username='admin').first():
        admin = User(
            tenant_id=tenant.id,
            username='admin',
            password_hash=generate_password_hash('admin123'),
            role='ADMIN',
            is_active=True
        )
        db.session.add(admin)
    
    if not User.query.filter_by(username='salesman').first():
        salesman = User(
            tenant_id=tenant.id,
            username='salesman',
            password_hash=generate_password_hash('salesman123'),
            role='SALESMAN',
            is_active=True
        )
        db.session.add(salesman)
    
    if not User.query.filter_by(username='delivery').first():
        delivery = User(
            tenant_id=tenant.id,
            username='delivery',
            password_hash=generate_password_hash('delivery123'),
            role='DELIVERY',
            is_active=True
        )
        db.session.add(delivery)
    
    if not User.query.filter_by(username='organiser').first():
        organiser = User(
            tenant_id=tenant.id,
            username='organiser',
            password_hash=generate_password_hash('organiser123'),
            role='ORGANISER',
            is_active=True
        )
        db.session.add(organiser)
    
    db.session.commit()


def login_user(client, username, password):
    """Helper function to login a user"""
    return client.post('/login', data={
        'username': username,
        'password': password
    }, follow_redirects=True)


def logout_user(client):
    """Helper function to logout"""
    return client.get('/logout', follow_redirects=True)

