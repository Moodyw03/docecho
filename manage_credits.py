#!/usr/bin/env python
"""
Script to manage user credits in the DocEcho application.
Run this from the project root directory.

Usage:
    python manage_credits.py --id <user_id> --add <credits>
    python manage_credits.py --email <email> --add <credits>
    python manage_credits.py --email <email> --set <credits>
    python manage_credits.py --list [--limit <num>]
    python manage_credits.py --search <query>
    
Examples:
    python manage_credits.py --id 1 --add 10
    python manage_credits.py --email user@example.com --add 30
    python manage_credits.py --email user@example.com --set 100
    python manage_credits.py --list --limit 20
    python manage_credits.py --search example.com
"""

import os
import sys
import argparse
from dotenv import load_dotenv
from app import create_app, db
from app.models.user import User
from sqlalchemy import or_

def find_user_by_id(session, user_id):
    """Find a user by ID"""
    return session.query(User).get(user_id)

def find_user_by_email(session, email):
    """Find a user by email"""
    return session.query(User).filter_by(email=email).first()

def add_credits(user, credits_to_add):
    """Add credits to a user"""
    original_credits = user.credits
    user.credits += credits_to_add
    return original_credits

def set_credits(user, new_credits):
    """Set a user's credits to a specific value"""
    original_credits = user.credits
    user.credits = new_credits
    return original_credits

def list_users(session, limit=None):
    """List all users with their credits"""
    query = session.query(User).order_by(User.id)
    if limit:
        query = query.limit(limit)
    return query.all()

def search_users(session, query_string):
    """Search for users by email"""
    search_pattern = f"%{query_string}%"
    return session.query(User).filter(
        User.email.like(search_pattern)
    ).order_by(User.id).all()

def main():
    """Main function to handle command line arguments"""
    parser = argparse.ArgumentParser(description='Manage user credits in DocEcho')
    
    # Create mutually exclusive group for operations
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--id', type=int, help='User ID')
    group.add_argument('--email', type=str, help='User email')
    group.add_argument('--list', action='store_true', help='List all users')
    group.add_argument('--search', type=str, help='Search users by email')
    
    # Credit operations
    parser.add_argument('--add', type=int, help='Credits to add')
    parser.add_argument('--set', type=int, help='Set credits to this value')
    parser.add_argument('--limit', type=int, help='Limit number of results when listing users')
    
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Create app with context
    app = create_app()
    
    with app.app_context():
        user = None
        
        # Handle user lookup
        if args.id:
            user = find_user_by_id(db.session, args.id)
            if not user:
                print(f"Error: User with ID {args.id} not found.")
                return
                
        elif args.email:
            user = find_user_by_email(db.session, args.email)
            if not user:
                print(f"Error: User with email {args.email} not found.")
                return
        
        # Handle credit operations
        if user and args.add:
            original_credits = add_credits(user, args.add)
            db.session.commit()
            print(f"\nCredits added successfully!")
            print(f"User: {user.email} (ID: {user.id})")
            print(f"Original credits: {original_credits}")
            print(f"Added credits: {args.add}")
            print(f"New total: {user.credits}")
            
        elif user and args.set is not None:
            original_credits = set_credits(user, args.set)
            db.session.commit()
            print(f"\nCredits updated successfully!")
            print(f"User: {user.email} (ID: {user.id})")
            print(f"Original credits: {original_credits}")
            print(f"New credit value: {user.credits}")
            
        elif args.list:
            users = list_users(db.session, args.limit)
            
            if not users:
                print("No users found in the database.")
                return
                
            print("\n{:<5} {:<30} {:<10} {:<10} {:<20}".format(
                "ID", "Email", "Credits", "Verified", "Created"))
            print("-" * 80)
            
            for user in users:
                created_at = user.created_at.strftime('%Y-%m-%d %H:%M') if user.created_at else 'N/A'
                verified = "Yes" if user.email_verified else "No"
                
                print("{:<5} {:<30} {:<10} {:<10} {:<20}".format(
                    user.id, user.email, user.credits, verified, created_at))
            
            print(f"\nTotal users: {len(users)}")
            
        elif args.search:
            users = search_users(db.session, args.search)
            
            if not users:
                print(f"No users found matching '{args.search}'.")
                return
                
            print("\n{:<5} {:<30} {:<10} {:<10} {:<20}".format(
                "ID", "Email", "Credits", "Verified", "Created"))
            print("-" * 80)
            
            for user in users:
                created_at = user.created_at.strftime('%Y-%m-%d %H:%M') if user.created_at else 'N/A'
                verified = "Yes" if user.email_verified else "No"
                
                print("{:<5} {:<30} {:<10} {:<10} {:<20}".format(
                    user.id, user.email, user.credits, verified, created_at))
            
            print(f"\nTotal matching users: {len(users)}")
        
        elif user and not (args.add or args.set is not None):
            # Just display user info if no operation specified
            print("\nUser Information:")
            print(f"ID: {user.id}")
            print(f"Email: {user.email}")
            print(f"Credits: {user.credits}")
            print(f"Verified: {'Yes' if user.email_verified else 'No'}")
            print(f"Created: {user.created_at.strftime('%Y-%m-%d %H:%M') if user.created_at else 'N/A'}")
            print(f"Subscription: {user.subscription_tier}")

if __name__ == "__main__":
    main() 