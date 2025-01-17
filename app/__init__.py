from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
from app.config import Config

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    # Determine the static folder path based on environment
    if os.environ.get('RENDER') == "true":
        static_folder = '/opt/data/static'
    else:
        static_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
    
    app = Flask(__name__,
                template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates')),
                static_folder=static_folder)
    
    app.config.from_object(Config)
    
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    from app.routes.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    from app.routes.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    # Create necessary directories
    os.makedirs(os.path.join(os.path.dirname(__file__), 'templates'), exist_ok=True)
    
    # Create and setup static directory based on environment
    if os.environ.get('RENDER') == "true":
        os.makedirs('/opt/data/static', exist_ok=True)
        os.makedirs('/opt/data/static/css', exist_ok=True)
        os.makedirs('/opt/data/static/js', exist_ok=True)
        
        # Copy static files to mounted disk on first run
        local_static = os.path.join(os.path.dirname(__file__), 'static')
        if os.path.exists(local_static):
            import shutil
            for item in os.listdir(local_static):
                s = os.path.join(local_static, item)
                d = os.path.join('/opt/data/static', item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
    else:
        os.makedirs(os.path.join(os.path.dirname(__file__), 'static'), exist_ok=True)
        os.makedirs(os.path.join(os.path.dirname(__file__), 'static/css'), exist_ok=True)
        os.makedirs(os.path.join(os.path.dirname(__file__), 'static/js'), exist_ok=True)
    
    return app 