from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
import shutil

# Initialize extensions without the app
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    
    # Configure the app
    app.config['SECRET_KEY'] = 'your-secret-key'  # Change this to a secure key
    
    # Configure database path
    if os.environ.get('RENDER') == "true":
        # Use persistent storage on Render
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////opt/data/docecho.db'
    else:
        # Use local path for development
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///docecho.db'
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Set up static folders
    if os.environ.get('RENDER') == "true":
        STATIC_FOLDER = '/opt/data/static'
    else:
        STATIC_FOLDER = os.path.join(os.path.dirname(__file__), 'static')
    
    app.static_folder = STATIC_FOLDER
    app.config['UPLOAD_FOLDER'] = os.path.join(STATIC_FOLDER, 'uploads')
    app.config['OUTPUT_FOLDER'] = os.path.join(STATIC_FOLDER, 'output')
    app.config['TEMP_FOLDER'] = os.path.join(STATIC_FOLDER, 'temp')
    
    # Initialize extensions with the app
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    with app.app_context():
        # Import models
        from app.models.user import User
        
        # Create database tables
        db.create_all()
        
        # Register blueprints
        from app.routes.auth import bp as auth_bp
        from app.routes.main import bp as main_bp
        
        app.register_blueprint(auth_bp, url_prefix='/auth')
        app.register_blueprint(main_bp)
        
        # Create necessary directories
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
        os.makedirs(app.config['TEMP_FOLDER'], exist_ok=True)
        
        # Handle static files for Render environment
        if os.environ.get('RENDER') == "true":
            # Create the base static directory
            os.makedirs(STATIC_FOLDER, exist_ok=True)
            
            # Copy static files to mounted disk while preserving directory structure
            local_static = os.path.join(os.path.dirname(__file__), 'static')
            if os.path.exists(local_static):
                for root, dirs, files in os.walk(local_static):
                    for file in files:
                        # Get the relative path from local_static
                        rel_path = os.path.relpath(root, local_static)
                        # Create source and destination paths
                        src_file = os.path.join(root, file)
                        dst_dir = os.path.join(STATIC_FOLDER, rel_path)
                        dst_file = os.path.join(dst_dir, file)
                        
                        # Create destination directory if it doesn't exist
                        os.makedirs(dst_dir, exist_ok=True)
                        # Copy the file
                        shutil.copy2(src_file, dst_file)
    
    return app 