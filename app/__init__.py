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
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///docecho.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Set up static folders
    STATIC_FOLDER = '/data' if os.environ.get('RENDER') else 'static'
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
            render_static = '/opt/data/static'
            os.makedirs(render_static, exist_ok=True)
            
            # Copy static files to mounted disk
            local_static = os.path.join(os.path.dirname(__file__), 'static')
            if os.path.exists(local_static):
                for item in os.listdir(local_static):
                    s = os.path.join(local_static, item)
                    d = os.path.join(render_static, item)
                    if os.path.isdir(s):
                        shutil.copytree(s, d, dirs_exist_ok=True)
                    else:
                        shutil.copy2(s, d)
                
                app.static_folder = render_static
        
        # Ensure required directories exist
        static_path = os.path.join(app.root_path, 'static')
        upload_path = os.path.join(static_path, 'uploads')
        output_path = os.path.join(static_path, 'output')
        temp_path = os.path.join(static_path, 'temp')
        
        for path in [static_path, upload_path, output_path, temp_path]:
            os.makedirs(path, exist_ok=True)
    
    return app 