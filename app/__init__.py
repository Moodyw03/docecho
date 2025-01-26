from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
from app.config import Config
import shutil

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    from app.routes.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    from app.routes.main import bp as main_bp
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
    
    return app 