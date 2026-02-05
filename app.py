from flask import Flask, jsonify
from config import config
from extensions import db, login_manager
from models import User
import os

# Import API blueprint (API-only backend for Render)
from api_routes import api_bp


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # CORS for API (frontend on Vercel)
    try:
        from flask_cors import CORS
        frontend_url = os.environ.get('FRONTEND_URL', '')
        origins = [u.strip() for u in frontend_url.split(',') if u.strip()] if frontend_url else []
        # Include Vercel production URL by default so CORS works even if FRONTEND_URL not set
        default_origins = [
            'https://skandaenterpriese.vercel.app',
            'https://skandaenterpriese-pawishrajhenars-projects.vercel.app',
            'https://skandaenterpriese-git-main-pawishrajhenars-projects.vercel.app',
            'http://localhost:3000', 'http://127.0.0.1:3000', 'http://localhost:8080'
        ]
        for o in default_origins:
            if o not in origins:
                origins.append(o)
        CORS(app, origins=origins, supports_credentials=True,
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
    
    # API requests: return 401 JSON instead of redirect
    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import request
        return jsonify({'error': 'Authentication required'}), 401
    
    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Register API blueprint only (API-only backend)
    app.register_blueprint(api_bp)
    
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
    
    # Root: API-only backend - direct users to frontend
    @app.route('/')
    def root():
        return jsonify({
            'message': 'Skanda API. Use the frontend at https://skandaenterpriese.vercel.app',
            'api': '/api/*',
            'health': '/health'
        }), 200
    
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

