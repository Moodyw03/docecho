from flask_login import UserMixin
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean
from sqlalchemy.orm import declarative_base
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from app import db, login_manager

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

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def set_verification_token(self, token=None):
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