import os
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()

def init_db(app):
    """Initialize database with the Flask app"""
    db.init_app(app)
    
    # Log database connection info
    logger.info(f"Database initialized with URI type: {app.config['SQLALCHEMY_DATABASE_URI'].split(':')[0]}")
    
    # Set up connection pooling options
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql'):
        logger.info("Setting up PostgreSQL connection pooling")
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': 5,
            'max_overflow': 10
        }

def get_db():
    """Helper function to get db instance with proper app context checks"""
    from flask import current_app, has_app_context
    
    if not has_app_context():
        logger.warning("No application context when accessing db. Creating temporary context.")
        from app import create_app
        app = create_app()
        with app.app_context():
            return db
    return db

# Add this to make db explicitly available for import
__all__ = ['db', 'get_db']
