#!/usr/bin/env python
"""
Script to delete a specific user from the DocEcho application.
Run this from the project root directory.

Usage:
    python delete_user.py <user_id>
    
Example:
    python delete_user.py 1
"""

import os
import sys
from dotenv import load_dotenv
from app import create_app, db
from app.models.user import User

def delete_user(user_id):
    """Delete a specific user by ID"""
    # Load environment variables
    load_dotenv()
    
    # Create app with context
    app = create_app()
    
    with app.app_context():
        # Find the user
        user = User.query.get(user_id)
        
        if not user:
            print(f"Error: User with ID {user_id} not found.")
            return
        
        # Show user details
        print("\nUser to delete:")
        print(f"ID: {user.id}")
        print(f"Email: {user.email}")
        print(f"Credits: {user.credits}")
        
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
    if len(sys.argv) != 2:
        print("Usage: python delete_user.py <user_id>")
        sys.exit(1)
    
    try:
        user_id = int(sys.argv[1])
    except ValueError:
        print("Error: User ID must be an integer.")
        sys.exit(1)
    
    delete_user(user_id) 