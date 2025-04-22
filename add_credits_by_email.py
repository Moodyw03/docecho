#!/usr/bin/env python
"""
Script to add credits to a user in the DocEcho application by email.
Run this from the project root directory.

Usage:
    python add_credits_by_email.py <email> <credits_to_add>
    
Example:
    python add_credits_by_email.py user@example.com 30
"""

import os
import sys
from dotenv import load_dotenv
from app import create_app, db
from app.models.user import User

def add_credits_by_email(email, credits_to_add):
    """Add credits to a user by email"""
    # Load environment variables
    load_dotenv()
    
    # Create app with context
    app = create_app()
    
    with app.app_context():
        # Find the user by email
        user = User.query.filter_by(email=email).first()
        
        if not user:
            print(f"Error: User with email {email} not found.")
            return
        
        # Store original credits for reporting
        original_credits = user.credits
        
        # Add credits
        user.credits += credits_to_add
        
        # Commit changes
        db.session.commit()
        
        print(f"\nCredits added successfully!")
        print(f"User: {user.email} (ID: {user.id})")
        print(f"Original credits: {original_credits}")
        print(f"Added credits: {credits_to_add}")
        print(f"New total: {user.credits}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python add_credits_by_email.py <email> <credits_to_add>")
        sys.exit(1)
    
    try:
        email = sys.argv[1]
        credits_to_add = int(sys.argv[2])
    except ValueError:
        print("Error: Credits must be an integer.")
        sys.exit(1)
    
    add_credits_by_email(email, credits_to_add) 