#!/usr/bin/env python
"""
Script to delete a user by email from the DocEcho application.
"""

import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import sqlalchemy as sa
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create a simple Flask app
app = Flask(__name__)

# Configure database
database_url = os.getenv('DATABASE_URL')
if not database_url:
    database_url = 'sqlite:///instance/app.db'
    
# Convert postgres:// to postgresql:// for SQLAlchemy 1.4+
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize db
db = SQLAlchemy(app)

# Define a minimal User model for querying
class User(db.Model):
    __tablename__ = 'users'
    
    id = sa.Column(sa.Integer, primary_key=True)
    email = sa.Column(sa.String, unique=True)
    email_verified = sa.Column(sa.Boolean, default=False)

def delete_user_by_email(email):
    """Delete a user by email address"""
    with app.app_context():
        # Find the user
        user = User.query.filter_by(email=email).first()
        
        if not user:
            print(f"Error: User with email {email} not found.")
            return
        
        # Show user details
        print("\nUser to delete:")
        print(f"ID: {user.id}")
        print(f"Email: {user.email}")
        print(f"Verified: {user.email_verified}")
        
        # Ask for confirmation
        confirmation = input(f"\nWARNING: This will delete user {user.email} (ID: {user.id}).\nType 'DELETE' to confirm: ")
        
        if confirmation != "DELETE":
            print("Operation cancelled.")
            return
        
        # Delete the user
        try:
            db.session.delete(user)
            db.session.commit()
            print(f"\nSuccess! User {user.email} (ID: {user.id}) has been deleted.")
        except Exception as e:
            db.session.rollback()
            print(f"Error deleting user: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # No email provided, use default
        email = "gabbipereira03@gmail.com"
    else:
        email = sys.argv[1]
    
    print(f"Attempting to delete user with email: {email}")
    delete_user_by_email(email) 