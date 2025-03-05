from flask import Flask, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
import shutil
from flask_migrate import Migrate
from dotenv import load_dotenv
from app.config import Config
import threading
import time
import copy

# Initialize extensions without the app
db = SQLAlchemy()
login_manager = LoginManager()

# Background task for cleaning up expired progress records
def cleanup_expired_progress(app):
    """Background task to clean up expired progress records"""
    while True:
        try:
            # Create a fresh app context for each cleanup cycle
            with app.app_context():
                # Import here to avoid circular imports
                from app.models.task_progress import TaskProgress
                
                # Use the app's db instance
                TaskProgress.cleanup_expired()
                print("Cleaned up expired progress records")
        except Exception as e:
            # Log the error outside the app context
            print(f"Error cleaning up expired progress records: {str(e)}")
        
        # Sleep for 1 hour between cleanup cycles
        time.sleep(3600)

def create_app():
    app = Flask(__name__)
    load_dotenv()  # Ensure environment variables are loaded
    
    # Load configuration from Config class
    app.config.from_object(Config)
    
    # Override with environment-specific settings
    app.config.update(
        JWT_SECRET_KEY=os.getenv('JWT_SECRET_KEY', 'fallback_secret_for_dev'),
        MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER'),
        SENDGRID_API_KEY=os.getenv('SENDGRID_API_KEY'),
        STRIPE_PUBLIC_KEY=os.getenv('STRIPE_PUBLIC_KEY'),
        STRIPE_SECRET_KEY=os.getenv('STRIPE_SECRET_KEY'),
        STRIPE_WEBHOOK_SECRET=os.getenv('STRIPE_WEBHOOK_SECRET')
    )
    
    # Log configuration for debugging
    print(f"Stripe Public Key configured: {'Yes' if app.config.get('STRIPE_PUBLIC_KEY') else 'No'}")
    print(f"Stripe Secret Key configured: {'Yes' if app.config.get('STRIPE_SECRET_KEY') else 'No'}")
    print(f"Stripe Webhook Secret configured: {'Yes' if app.config.get('STRIPE_WEBHOOK_SECRET') else 'No'}")
    
    # Configure database
    configure_database(app)
    
    # Set up static folders
    configure_static_folders(app)
    
    # Initialize extensions - IMPORTANT: Initialize db before other extensions
    db.init_app(app)
    
    # Create progress directory
    with app.app_context():
        progress_dir = os.path.join(app.root_path, 'static', 'progress')
        os.makedirs(progress_dir, exist_ok=True)
    
    # Initialize other extensions after db
    migrate = Migrate(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    # Register blueprints and initialize models
    with app.app_context():
        register_blueprints_and_models(app)
    
    # Start background task for cleaning up expired progress records
    # Only start in non-debug mode or when running the main thread in debug mode
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        # Create a separate thread for cleanup
        cleanup_thread = threading.Thread(target=cleanup_expired_progress, args=(app,))
        cleanup_thread.daemon = True
        cleanup_thread.start()
        print("Started background task for cleaning up expired progress records")
    
    # Add HTTPS enforcement in production
    @app.before_request
    def enforce_https():
        if os.environ.get('FLASK_ENV') == 'production':
            if not request.is_secure and request.headers.get('X-Forwarded-Proto') != 'https':
                url = request.url.replace('http://', 'https://', 1)
                return redirect(url, code=301)
    
    return app

def configure_database(app):
    """Configure database connection"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        if os.environ.get('RENDER') == "true":
            raise ValueError("DATABASE_URL environment variable is required in production")
        # Local development fallback
        database_url = 'sqlite:///instance/app.db'
        os.makedirs('instance', exist_ok=True)
    
    # Convert postgres:// to postgresql:// for SQLAlchemy 1.4+
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 20,
        'max_overflow': 0
    }

def configure_static_folders(app):
    """Configure static, upload, output, and temp folders"""
    if os.environ.get('RENDER') == "true":
        STATIC_FOLDER = '/opt/data/static'
    else:
        STATIC_FOLDER = os.path.join(os.path.dirname(__file__), 'static')
    
    app.static_folder = STATIC_FOLDER
    app.config.update(
        UPLOAD_FOLDER='/opt/data/uploads',
        OUTPUT_FOLDER='/opt/data/output',
        TEMP_FOLDER='/opt/data/temp'
    )
    
    # Handle static files for Render environment
    if os.environ.get('RENDER') == "true":
        try:
            os.makedirs(STATIC_FOLDER, exist_ok=True)
        except Exception as e:
            app.logger.error(f"Static directory creation failed: {str(e)}")
        
        if not os.path.exists(STATIC_FOLDER):
            app.logger.warning(f"Static directory {STATIC_FOLDER} not found - using fallback")
            app.static_folder = os.path.join(os.path.dirname(__file__), 'static')

def register_blueprints_and_models(app):
    """Register blueprints and initialize models"""
    from app.models.user import User
    from app.models.task_progress import TaskProgress
    
    # Create database tables
    db.create_all()
    
    # Register blueprints
    from app.routes.auth import bp as auth_bp
    from app.routes.main import bp as main_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp) 