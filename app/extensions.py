import os
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()

def init_db(app):
    db.init_app(app)

# Add this to make db explicitly available for import
__all__ = ['db']
