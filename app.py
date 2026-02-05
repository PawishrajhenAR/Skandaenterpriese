from flask import Flask, jsonify, redirect, url_for
from config import config
from extensions import db, login_manager
from models import User, Permission
import os

# Import blueprints
from api_routes import api_bp
from main_routes import main_bp
from auth_routes import auth_bp
from bill_routes import bill_bp
from vendor_routes import vendor_bp
from credit_routes import credit_bp
from delivery_routes import delivery_bp
from report_routes import report_bp
from permission_routes import permission_bp
from ocr_routes import ocr_bp
from proxy_routes import proxy_bp


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # CORS for API
    try:
        from flask_cors import CORS
        CORS(app, supports_credentials=True,
             allow_headers=['Content-Type', 'Authorization'],
             expose_headers=['Content-Type'])
    except ImportError:
        pass  # flask-cors not installed
    
    # Initialize extensions
    db.init_app(app)
    
    # Configure SQLAlchemy engine options if specified
    if hasattr(config[config_name], 'SQLALCHEMY_ENGINE_OPTIONS'):
        engine_options = config[config_name].SQLALCHEMY_ENGINE_OPTIONS
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_options
    
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Template context processor for permissions
    @app.context_processor
    def utility_processor():
        def has_permission(permission_code):
            from flask_login import current_user
            if not current_user.is_authenticated:
                return False
            return current_user.has_permission(permission_code)
        return dict(has_permission=has_permission)
    
    # Register all blueprints
    app.register_blueprint(api_bp)  # API routes under /api
    app.register_blueprint(main_bp)  # Dashboard at / and /dashboard
    app.register_blueprint(auth_bp, url_prefix='/auth')  # Login/logout
    app.register_blueprint(bill_bp, url_prefix='/bills')
    app.register_blueprint(vendor_bp, url_prefix='/vendors')
    app.register_blueprint(credit_bp, url_prefix='/credits')
    app.register_blueprint(delivery_bp, url_prefix='/deliveries')
    app.register_blueprint(report_bp, url_prefix='/reports')
    app.register_blueprint(permission_bp, url_prefix='/permissions')
    app.register_blueprint(ocr_bp, url_prefix='/ocr')
    app.register_blueprint(proxy_bp, url_prefix='/proxy')
    
    # Create upload/backup directories (use /tmp on Vercel - read-only filesystem)
    try:
        upload_folder = app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
    except (OSError, PermissionError):
        app.config['UPLOAD_FOLDER'] = '/tmp/uploads/bills'
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    try:
        backup_folder = app.config.get('BACKUP_FOLDER')
        if backup_folder:
            os.makedirs(backup_folder, exist_ok=True)
    except (OSError, PermissionError):
        pass
    
    # Health endpoints for deployment verification
    @app.route('/health')
    def health():
        """Simple health check for Render/Vercel"""
        return jsonify({'status': 'ok', 'service': 'skanda-api'}), 200
    
    @app.route('/health/db')
    def db_health():
        """Check database connection health"""
        try:
            from extensions import db, is_postgresql
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            
            database_uri = app.config['SQLALCHEMY_DATABASE_URI']
            response = {
                'status': 'healthy',
                'database_type': 'postgresql' if is_postgresql(database_uri) else 'unknown'
            }
            
            if is_postgresql(database_uri):
                # Get database name from connection string
                try:
                    # Extract database name from URI
                    if '@' in database_uri:
                        db_name = database_uri.split('/')[-1].split('?')[0]
                        response['database_name'] = db_name
                    # Get connection info
                    result = db.session.execute(text("SELECT version()"))
                    version = result.scalar()
                    response['postgresql_version'] = version.split(',')[0] if version else 'unknown'
                except:
                    pass
            
            return response, 200
        except Exception as e:
            return jsonify({'status': 'unhealthy', 'error': str(e)}), 500
    
    return app


# Create app instance for Gunicorn (production)
# Gunicorn will use: gunicorn app:app
app = create_app(os.environ.get('FLASK_ENV', 'production'))

if __name__ == '__main__':
    # Development server
    app = create_app('development')
    # NOTE: db.create_all() should only be run via init_db.py
    # Removing it from here prevents accidental database resets
    # Run 'python init_db.py' manually to initialize database schema
    app.run(debug=True, host='0.0.0.0', port=5000)

