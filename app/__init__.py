from flask import Flask, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
import shutil
import redis
from flask_migrate import Migrate
from dotenv import load_dotenv
from app.config import Config

# Initialize extensions without the app
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    load_dotenv()  # Ensure environment variables are loaded
    
    # Add this configuration section
    app.config.from_object(Config)
    
    # Configure SendGrid
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')
    app.config['SENDGRID_API_KEY'] = os.getenv('SENDGRID_API_KEY')
    
    # Remove the duplicate secret key config and keep:
    app.config.from_object(Config)
    
    # Get the database URL from environment variable
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        if os.environ.get('RENDER') == "true":
            raise ValueError("DATABASE_URL environment variable is required in production")
        # Local development fallback
        database_url = 'sqlite:///instance/app.db'
        os.makedirs('instance', exist_ok=True)
    
    # Keep the postgres:// to postgresql:// replacement
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
    
    # Set up static folders
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
    
    # Configure Redis connection with Render-specific handling
    if os.environ.get('RENDER') == "true":
        # Render Redis format: redis://red-<instance_id>:<port>
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        if not redis_url.startswith(('redis://', 'rediss://')):
            redis_url = f'redis://{redis_url}'
    else:
        # Local development configuration
        redis_url = 'redis://localhost:6379/0'
    
    app.redis = redis.Redis.from_url(redis_url, socket_connect_timeout=5)
    
    # Test Redis connection
    try:
        app.redis.ping()
    except redis.ConnectionError:
        if os.environ.get('RENDER') == "true":
            raise RuntimeError("Failed to connect to Render Redis. Check your REDIS_URL.")
        else:
            raise RuntimeError("Failed to connect to local Redis. Is it running?")
    
    # Initialize Flask-Migrate
    migrate = Migrate(app, db)
    
    # Initialize extensions with the app
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    # Import models after db initialization
    with app.app_context():
        from app.models.user import User
        
        # Create database tables
        db.create_all()
        
        # Register blueprints
        from app.routes.auth import bp as auth_bp
        from app.routes.main import bp as main_bp
        
        app.register_blueprint(auth_bp, url_prefix='/auth')
        app.register_blueprint(main_bp)
        
        # Handle static files for Render environment
        if os.environ.get('RENDER') == "true":
            # Attempt to create static directory if missing
            try:
                os.makedirs(STATIC_FOLDER, exist_ok=True)
            except Exception as e:
                app.logger.error(f"Static directory creation failed: {str(e)}")
            
            if not os.path.exists(STATIC_FOLDER):
                app.logger.warning(f"Static directory {STATIC_FOLDER} not found - using fallback")
                STATIC_FOLDER = os.path.join(os.path.dirname(__file__), 'static')
    
    # Add this to force HTTPS in production
    @app.before_request
    def enforce_https():
        if os.environ.get('FLASK_ENV') == 'production':
            if not request.is_secure and request.headers.get('X-Forwarded-Proto') != 'https':
                url = request.url.replace('http://', 'https://', 1)
                return redirect(url, code=301)
    
    return app 