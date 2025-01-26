import os
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def init_db(app):
    db.init_app(app)

# Add this to make db explicitly available for import
__all__ = ['db']
