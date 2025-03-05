#!/usr/bin/env python
"""
Script to delete all registered users in the DocEcho application.
Run this from the project root directory.

Usage:
    python delete_users.py

This script requires confirmation before deleting users.
"""

import os
import sys
from dotenv import load_dotenv
from app import create_app, db
from app.models.user import User

def delete_all_users():
    """Delete all users from the database with confirmation"""
    # Load environment variables
    load_dotenv()
    
    # Create app with context
    app = create_app()
    
    with app.app_context():
        # Count users
        user_count = User.query.count()
        
        if user_count == 0:
            print("No users found in the database.")
            return
        
        # List users before deletion
        users = User.query.all()
        
        print("\nUsers that will be deleted:")
        print("-" * 50)
        for user in users:
            print(f"ID: {user.id}, Email: {user.email}, Credits: {user.credits}")
        print("-" * 50)
        print(f"Total users to delete: {user_count}")
        
        # Ask for confirmation
        confirmation = input("\nWARNING: This will delete ALL users from the database.\nType 'DELETE ALL USERS' to confirm: ")
        
        if confirmation != "DELETE ALL USERS":
            print("Operation cancelled.")
            return
        
        # Delete all users
        try:
            User.query.delete()
            db.session.commit()
            print(f"\nSuccess! All {user_count} users have been deleted from the database.")
        except Exception as e:
            db.session.rollback()
            print(f"Error deleting users: {str(e)}")

if __name__ == "__main__":
    delete_all_users() 