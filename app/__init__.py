from flask import Flask, request, redirect, current_app, send_from_directory, url_for
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
# Import db globally now
from app.extensions import db, login_manager, init_extensions
from flask_mail import Mail
from celery_worker import celery
from flask_cors import CORS

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
                db.session.remove()
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
    
    # Add supported languages to the app config
    app.config['LANGUAGES_SUPPORTED'] = app.config.get('LANGUAGES_SUPPORTED', 'en').split(',')
    
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
    print(f"Mail Server configured: {'Yes' if app.config.get('MAIL_SERVER') else 'No'}")
    print(f"Mail Default Sender configured: {'Yes' if app.config.get('MAIL_DEFAULT_SENDER') else 'No'}")
    
    # Instantiate Mail locally (needs config)
    mail = Mail()
    app.extensions['mail'] = mail # Store mail instance for init_extensions

    # Configure database (needs to happen before db.init_app)
    configure_database(app)

    # Set up static folders
    configure_static_folders(app)

    # Initialize db with the app *before* Migrate
    db.init_app(app)

    # Initialize Migrate *after* db.init_app
    migrate = Migrate(app, db)

    # Initialize other extensions (Mail, LoginManager)
    init_extensions(app)

    # Initialize CORS
    # Allow requests from the configured BASE_URL (frontend) for all routes
    CORS(app, origins=[app.config.get('BASE_URL', '*')], supports_credentials=True)

    # Create progress directory
    with app.app_context():
        progress_dir = os.path.join(app.root_path, 'static', 'progress')
        os.makedirs(progress_dir, exist_ok=True)
        
        # Ensure email templates directory exists
        email_templates_dir = os.path.join(app.root_path, 'templates', 'email')
        os.makedirs(email_templates_dir, exist_ok=True)
    
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
    def  enforce_https():
        if os.environ.get('FLASK_ENV') == 'production':
            if not request.is_secure and request.headers.get('X-Forwarded-Proto') != 'https':
                url = request.url.replace('http://', 'https://', 1)
                return redirect(url, code=301)
    
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    @app.route('/download/<path:filename>')
    def download_file(filename):
        return send_from_directory(app.config.get('OUTPUT_FOLDER', '.'), filename, as_attachment=True)

    @app.route('/download/<uuid>')
    def download_by_uuid(uuid):
        """Download a file by UUID with type parameter"""
        # Check for query parameter first, then assume audio as default
        file_type = request.args.get('type', 'audio')
        output_dir = app.config.get('OUTPUT_FOLDER', '.')
        
        app.logger.info(f"Download request for {uuid}, type={file_type}")
        
        # List files in the output directory
        try:
            if not os.path.exists(output_dir):
                app.logger.error(f"Output directory does not exist: {output_dir}")
                return redirect(url_for('main.downloads_page', _external=True))
            
            files = os.listdir(output_dir)
            app.logger.info(f"Files in output directory: {files}")
            
            # Look for files matching the UUID or containing it
            matching_files = []
            for file in files:
                if uuid in file:
                    matching_files.append(file)
                    
            app.logger.info(f"Matching files for UUID {uuid}: {matching_files}")
            
            # Find file matching the requested type
            target_file = None
            for file in matching_files:
                if file_type == 'audio' and file.endswith('.mp3'):
                    target_file = file
                    break
                elif file_type == 'pdf' and file.endswith('.pdf'):
                    target_file = file
                    break
            
            if target_file:
                app.logger.info(f"Found matching file: {target_file}")
                return send_from_directory(output_dir, target_file, as_attachment=True)
            else:
                app.logger.warning(f"No matching {file_type} file in filesystem for UUID {uuid}, checking Redis")
                # If no file found on filesystem, try getting from Redis
                from app.utils.redis import get_redis
                from io import BytesIO
                from flask import send_file
                
                # Try to get from Redis
                try:
                    redis_client = get_redis()
                    content_key = f"file_content:{uuid}:{file_type}"
                    app.logger.info(f"Trying Redis key: {content_key}")
                    
                    file_content = redis_client.get(content_key)
                    
                    if file_content:
                        app.logger.info(f"Found file content in Redis for {uuid}, size: {len(file_content)} bytes")
                        
                        # Determine filename and mimetype
                        file_extension = 'mp3' if file_type == 'audio' else ('pdf' if file_type == 'pdf' else 'txt')
                        download_filename = f"docecho_{uuid}.{file_extension}"
                        mimetype = 'audio/mpeg' if file_type == 'audio' else ('application/pdf' if file_type == 'pdf' else 'text/plain')
                        
                        # Send the file content from memory
                        return send_file(
                            BytesIO(file_content), 
                            as_attachment=True,
                            download_name=download_filename,
                            mimetype=mimetype
                        )
                    else:
                        app.logger.error(f"No content found in Redis for key: {content_key}")
                        # Redirect to downloads page instead of showing an error
                        if hasattr(app, 'config') and app.config.get('DEBUG', False):
                            return f"File not found for {uuid}. Redis key: {content_key}", 404
                        return redirect(url_for('main.downloads_page', _external=True))
                except Exception as e:
                    app.logger.error(f"Error retrieving from Redis: {str(e)}")
                    # Redirect to downloads page instead of showing an error
                    if hasattr(app, 'config') and app.config.get('DEBUG', False):
                        return f"Error retrieving file: {str(e)}", 500
                    return redirect(url_for('main.downloads_page', _external=True))
                
        except Exception as e:
            app.logger.error(f"Error in download_by_uuid: {str(e)}")
            # Redirect to downloads page instead of showing an error
            if hasattr(app, 'config') and app.config.get('DEBUG', False):
                return f"Error accessing files: {str(e)}", 500
            return redirect(url_for('main.downloads_page', _external=True))

    return app

def configure_database(app):
    """Configure database connection"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        if os.environ.get('FLY_APP_NAME'):
            raise ValueError("DATABASE_URL environment variable is required in production")
        # Local development fallback
        # database_url = 'sqlite:///instance/app.db'
        # os.makedirs('instance', exist_ok=True)
        # Use /tmp for potentially fewer permission issues
        db_path = '/tmp/docecho_app.db'
        database_url = f'sqlite:///{db_path}'
        print(f"Using temporary local database: {db_path}")
    
    # Convert postgres:// to postgresql:// for SQLAlchemy 1.4+
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    # Log database connection info (without credentials)
    masked_url = database_url
    if '@' in database_url:
        parts = database_url.split('@')
        auth_parts = parts[0].split(':')
        if len(auth_parts) > 2:
            # Hide password
            masked_url = f"{auth_parts[0]}:****@{parts[1]}"
    print(f"Connecting to database: {masked_url}")
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Only set these for PostgreSQL connections
    if database_url.startswith('postgresql'):
        print("Configuring PostgreSQL connection pool")
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': 5,
            'max_overflow': 10
        }

def configure_static_folders(app):
    """Configure upload, output, and temp folders based on environment or defaults."""
    # Static folder is handled by Flask default or fly.toml [[statics]]
    # Just ensure Upload/Output/Temp folders are configured
    app.config.update(
        UPLOAD_FOLDER=os.environ.get('UPLOAD_FOLDER', app.config.get('UPLOAD_FOLDER')),
        OUTPUT_FOLDER=os.environ.get('OUTPUT_FOLDER', app.config.get('OUTPUT_FOLDER')),
        TEMP_FOLDER=os.environ.get('TEMP_FOLDER', app.config.get('TEMP_FOLDER'))
    )

    # Ensure directories exist if running locally or if needed
    # In Fly.io, these should point to the mounted volume /app/data/*
    # The volume mount should handle creation, but making sure doesn't hurt.
    try:
        # Use os.makedirs for safety, even though Fly mount should exist
        if app.config.get('UPLOAD_FOLDER'):
             os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        if app.config.get('OUTPUT_FOLDER'):
             os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
        if app.config.get('TEMP_FOLDER'):
             os.makedirs(app.config['TEMP_FOLDER'], exist_ok=True)
    except Exception as e:
        app.logger.error(f"Error ensuring data directories exist: {str(e)}")

def register_blueprints_and_models(app):
    """Register blueprints and initialize models"""
    from app.models.user import User
    from app.models.task_progress import TaskProgress
    
    # Register blueprints
    from app.routes.auth import bp as auth_bp
    from app.routes.main import bp as main_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp) 

# Create Flask app
app = create_app()

# Initialize Celery with Flask app context
celery.conf.update(app.config) 