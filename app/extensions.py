import os
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize extensions - REMOVE global db and mail instances
# db = SQLAlchemy()
login_manager = LoginManager()
# mail = Mail()

def init_extensions(app):
    """Initialize non-DB extensions. DB init assumed handled by Migrate."""
    # Retrieve mail instance stored in create_app
    mail = app.extensions['mail']

    # Initialize login_manager (global) and mail (passed via app.extensions)
    login_manager.init_app(app)
    mail.init_app(app)

    login_manager.login_view = 'auth.login'

    # Log database connection info (DB assumed initialized before this)
    logger.info(f"Database connection check: {app.config['SQLALCHEMY_DATABASE_URI'].split(':')[0]}")
    
    # Set up connection pooling options (DB assumed initialized before this)
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql'):
        logger.info("Setting up PostgreSQL connection pooling")
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': 5,
            'max_overflow': 10
        }

def get_db():
    """Helper function to get the db instance from the current app context."""
    from flask import current_app, has_app_context

    if not has_app_context():
        # This should ideally not happen if called correctly
        logger.error("get_db called without active app context!")
        raise RuntimeError("Application context required to get DB instance.")

    # Retrieve db from app extensions
    try:
        # SQLAlchemy 3.x stores the extension instance directly
        return current_app.extensions['sqlalchemy']
    except KeyError:
        logger.error("SQLAlchemy extension not found in current_app.extensions")
        raise RuntimeError("SQLAlchemy not initialized for this app context.")

# Update exports
__all__ = ['login_manager', 'get_db']
