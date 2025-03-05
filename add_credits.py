#!/usr/bin/env python
"""
Script to add credits to a user in the DocEcho application.
Run this from the project root directory.

Usage:
    python add_credits.py <user_id> <credits_to_add>
    
Example:
    python add_credits.py 1 10
"""

import os
import sys
from dotenv import load_dotenv
from app import create_app, db
from app.models.user import User

def add_credits(user_id, credits_to_add):
    """Add credits to a user"""
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
        
        # Store original credits for reporting
        original_credits = user.credits
        
        # Add credits
        user.credits += credits_to_add
        
        # Commit changes
        db.session.commit()
        
        print(f"\nCredits added successfully!")
        print(f"User: {user.email}")
        print(f"Original credits: {original_credits}")
        print(f"Added credits: {credits_to_add}")
        print(f"New total: {user.credits}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python add_credits.py <user_id> <credits_to_add>")
        sys.exit(1)
    
    try:
        user_id = int(sys.argv[1])
        credits_to_add = int(sys.argv[2])
    except ValueError:
        print("Error: User ID and credits must be integers.")
        sys.exit(1)
    
    add_credits(user_id, credits_to_add) 