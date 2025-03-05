#!/usr/bin/env python
"""
Script to list all registered users in the DocEcho application.
Run this from the project root directory.
"""

import os
import sys
from dotenv import load_dotenv
from app import create_app, db
from app.models.user import User

def list_users():
    """List all users in the database"""
    # Load environment variables
    load_dotenv()
    
    # Create app with context
    app = create_app()
    
    with app.app_context():
        users = User.query.all()
        
        if not users:
            print("No users found in the database.")
            return
        
        # Print header
        print("\n{:<5} {:<30} {:<10} {:<10} {:<20}".format(
            "ID", "Email", "Credits", "Verified", "Created"))
        print("-" * 80)
        
        # Print each user
        for user in users:
            created_at = user.created_at.strftime('%Y-%m-%d %H:%M') if user.created_at else 'N/A'
            verified = "Yes" if user.email_verified else "No"
            
            print("{:<5} {:<30} {:<10} {:<10} {:<20}".format(
                user.id, user.email, user.credits, verified, created_at))
        
        print("\nTotal users: {}".format(len(users)))

if __name__ == "__main__":
    list_users() 