from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean
from sqlalchemy.orm import declarative_base
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from app.extensions import db, login_manager
import jwt
from flask import current_app

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    password_hash = Column(String(255))
    subscription_tier = Column(String, default='free')
    pages_used_this_month = Column(Integer, default=0)
    subscription_start = Column(DateTime)
    subscription_end = Column(DateTime)
    stripe_customer_id = Column(String)
    email_verified = Column(Boolean, default=False)
    uq_verification_token = Column(String(255), unique=True)
    credits = Column(Integer, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def is_admin(self):
        """Check if the user is an admin based on email"""
        # List of admin emails - you can update this list as needed
        admin_emails = ['admin@example.com']
        # Get admin emails from environment if available
        if current_app and current_app.config.get('ADMIN_EMAILS'):
            admin_emails = current_app.config.get('ADMIN_EMAILS', '').split(',')
        
        return self.email in admin_emails

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def set_verification_token(self, token=None):
        if token is None:
            # Generate a token if none is provided
            payload = {
                'user_id': self.id,
                'exp': datetime.utcnow() + timedelta(hours=24)
            }
            token = jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')
            
        self.uq_verification_token = token
        db.session.commit()
        return token

    def verify(self):
        self.email_verified = True
        self.uq_verification_token = None
        db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))