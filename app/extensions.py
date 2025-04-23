import os
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize extensions globally
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail() # Add global mail instance back

def init_extensions(app):
    """Initialize non-DB extensions using instances stored on app."""
    # Retrieve mail instance stored in create_app
    # This ensures mail is initialized with the correct app config
    mail_instance_from_app = app.extensions['mail']

    # Initialize login_manager (global) and mail (using instance from app)
    login_manager.init_app(app)
    mail_instance_from_app.init_app(app)

    login_manager.login_view = 'auth.login'

    # Logging/pooling config can happen here or after db.init_app in create_app
    # Let's keep it simple here for now.

def get_db():
    """Helper function to get the globally defined db instance."""
    # Assumes db has been initialized via init_app by the app factory
    return db

# Update exports
__all__ = ['db', 'login_manager', 'mail', 'get_db'] # Add mail back
