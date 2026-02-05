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
    
    # Determine deployment mode
    # DEPLOY_MODE=api for Render (API only)
    # DEPLOY_MODE=frontend for Vercel (templates/UI)
    # Default: full (both API and frontend)
    deploy_mode = os.environ.get('DEPLOY_MODE', 'full').lower()
    
    # CORS for API
    try:
        from flask_cors import CORS
        if deploy_mode == 'api':
            # API mode: allow frontend origins
            origins = [
                'https://skandaenterpriese.vercel.app',
                'https://skandaenterpriese-pawishrajhenars-projects.vercel.app',
                'https://skandaenterpriese-git-main-pawishrajhenars-projects.vercel.app',
                'http://localhost:5000', 'http://127.0.0.1:5000'
            ]
            CORS(app, origins=origins, supports_credentials=True,
                 allow_headers=['Content-Type', 'Authorization'],
                 expose_headers=['Content-Type'])
        else:
            CORS(app, supports_credentials=True)
    except ImportError:
        pass
    
    # Initialize extensions
    db.init_app(app)
    
    if hasattr(config[config_name], 'SQLALCHEMY_ENGINE_OPTIONS'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = config[config_name].SQLALCHEMY_ENGINE_OPTIONS
    
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
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
    
    # Register blueprints based on deploy mode
    if deploy_mode == 'api':
        # Render: API only
        app.register_blueprint(api_bp)
        
        @app.route('/')
        def root():
            return jsonify({
                'message': 'Skanda API Backend',
                'frontend': 'https://skandaenterpriese.vercel.app',
                'api': '/api/*',
                'health': '/health'
            }), 200
    
    elif deploy_mode == 'frontend':
        # Vercel: Frontend (templates) only
        app.register_blueprint(main_bp)
        app.register_blueprint(auth_bp, url_prefix='/auth')
        app.register_blueprint(bill_bp, url_prefix='/bills')
        app.register_blueprint(vendor_bp, url_prefix='/vendors')
        app.register_blueprint(credit_bp, url_prefix='/credits')
        app.register_blueprint(delivery_bp, url_prefix='/deliveries')
        app.register_blueprint(report_bp, url_prefix='/reports')
        app.register_blueprint(permission_bp, url_prefix='/permissions')
        app.register_blueprint(ocr_bp, url_prefix='/ocr')
        app.register_blueprint(proxy_bp, url_prefix='/proxy')
    
    else:
        # Full mode: both API and frontend (local development)
        app.register_blueprint(api_bp)
        app.register_blueprint(main_bp)
        app.register_blueprint(auth_bp, url_prefix='/auth')
        app.register_blueprint(bill_bp, url_prefix='/bills')
        app.register_blueprint(vendor_bp, url_prefix='/vendors')
        app.register_blueprint(credit_bp, url_prefix='/credits')
        app.register_blueprint(delivery_bp, url_prefix='/deliveries')
        app.register_blueprint(report_bp, url_prefix='/reports')
        app.register_blueprint(permission_bp, url_prefix='/permissions')
        app.register_blueprint(ocr_bp, url_prefix='/ocr')
        app.register_blueprint(proxy_bp, url_prefix='/proxy')
    
    # Create directories (use /tmp on serverless)
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
    
    # Health endpoints
    @app.route('/health')
    def health():
        return jsonify({'status': 'ok', 'mode': deploy_mode}), 200
    
    @app.route('/health/db')
    def db_health():
        try:
            from extensions import db, is_postgresql
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            return jsonify({'status': 'healthy'}), 200
        except Exception as e:
            return jsonify({'status': 'unhealthy', 'error': str(e)}), 500
    
    return app


# Create app instance
app = create_app(os.environ.get('FLASK_ENV', 'production'))

if __name__ == '__main__':
    app = create_app('development')
    app.run(debug=True, host='0.0.0.0', port=5000)
