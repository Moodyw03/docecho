from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from app.forms import RegistrationForm, LoginForm, PasswordUpdateForm
from app import db
import jwt
from datetime import datetime, timedelta
from flask import current_app
from werkzeug.security import generate_password_hash
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To
import os
from sqlalchemy import func
import logging
from app.utils.email import send_verification_email, send_password_reset_email

logger = logging.getLogger(__name__)
bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            if not user.email_verified:
                session['unverified_email'] = user.email
                flash('Please verify your email before logging in', 'warning')
                return redirect(url_for('auth.login'))
            if user.check_password(form.password.data):
                login_user(user)
                return redirect(url_for('main.index'))
        flash('Invalid email or password')          
    return render_template('auth/login.html', form=form)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            print("\nForm submitted and validated")
            email = form.email.data.strip().lower()  # Normalize email
            print(f"Normalized email: {email}")
            
            if User.query.filter(func.lower(User.email) == email).first():
                print("Email already exists")
                flash('Email address already exists', 'danger')
                return redirect(url_for('auth.register'))
            
            print("Creating new user...")
            new_user = User(email=email, credits=5)  # Use normalized lowercase email
            new_user.set_password(form.password.data)
            
            db.session.add(new_user)
            db.session.commit()
            print(f"User created with ID: {new_user.id} and {new_user.credits} credits")
            
            # Remove duplicate token generation
            token = new_user.set_verification_token()  # Let the model handle token generation
            
            # Simplify email sending flow
            try:
                send_verification_email(new_user, token)
                session['unverified_email'] = new_user.email
                flash('Registration successful! Please check your email to verify your account.', 'success')
                return redirect(url_for('auth.login'))
                
            except Exception as email_error:
                print(f"\nFailed to send verification email: {str(email_error)}")
                # Clean up unverified user
                db.session.delete(new_user)
                db.session.commit()
                flash('Account creation failed due to email error. Please try again.', 'danger')
            
            print("=== Registration Process Complete ===\n")
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            print(f"\nRegistration error: {str(e)}")
            if hasattr(e, 'body'):
                print(f"Error details: {e.body}")
            current_app.logger.error(f'Registration error: {str(e)}', exc_info=True)
            flash(f'Registration failed: {str(e)}', 'danger')
    else:
        if form.errors:
            print(f"\nForm validation errors: {form.errors}")
    
    print("=== End Registration Process ===\n")
    return render_template('auth/register.html', form=form)

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('main.index'))

@bp.route('/verify/<token>')
def verify_email(token):
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        user_id = payload['user_id']
        user = User.query.get(user_id)
        
        if not user:
            flash('Invalid verification link', 'danger')
            return redirect(url_for('auth.login'))
        
        if user.email_verified:
            flash('Your email has already been verified', 'info')
            return redirect(url_for('auth.login'))
        
        user.email_verified = True
        db.session.commit()
        flash('Your email has been verified! You can now log in.', 'success')
        return redirect(url_for('auth.login'))
    except Exception as e:
        logger.error(f"Email verification error: {str(e)}")
        flash('The verification link is invalid or has expired', 'danger')
        return redirect(url_for('auth.login'))

def generate_verification_token(user):
    """Generate a JWT token for email verification."""
    payload = {
        'user_id': user.id,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    token = jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')
    return token

@bp.route('/resend-verification')
def resend_verification():
    email = session.get('unverified_email')
    if not email:
        flash('No email to verify', 'danger')
        return redirect(url_for('auth.login'))
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('auth.login'))
    
    if user.email_verified:
        flash('Your email is already verified', 'info')
        return redirect(url_for('auth.login'))
    
    token = generate_verification_token(user)
    success = send_verification_email(user, token)
    
    if success:
        flash('Verification email sent. Please check your inbox.', 'success')
    else:
        flash('Failed to send verification email. Please try again later.', 'danger')
    
    return redirect(url_for('auth.login'))

@bp.route('/test-sendgrid')
def test_sendgrid():
    try:
        if not current_app.config.get('MAIL_DEFAULT_SENDER'):
            return "Error: MAIL_DEFAULT_SENDER not configured", 500
            
        message = Mail(
            from_email=current_app.config['MAIL_DEFAULT_SENDER'],
            to_emails=current_app.config['MAIL_DEFAULT_SENDER'],  # Send to the same address
            subject='SendGrid Test',
            html_content='<strong>This is a test from Flask</strong>')
        
        sendgrid_api_key = current_app.config.get('SENDGRID_API_KEY')
        if not sendgrid_api_key:
            return "Error: SENDGRID_API_KEY not configured", 500
            
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        
        if response.status_code not in [200, 201, 202]:
            return f"Error: Failed to send email - Status: {response.status_code}", 500
            
        return f"Email sent successfully! Status: {response.status_code}"
    except Exception as e:
        current_app.logger.error(f"Test email error: {str(e)}")
        if hasattr(e, 'body'):
            current_app.logger.error(f"SendGrid error details: {e.body}")
        return f"Error: {str(e)}", 500

@bp.route('/debug-verify/<email>')
def debug_verify(email):
    user = User.query.filter_by(email=email).first()
    if user:
        send_verification_email(user)
        return f"Verification email re-sent to {email}"
    return "User not found"

@bp.route('/debug-email')
def debug_email():
    try:
        # Print configuration
        print(f"MAIL_DEFAULT_SENDER: {current_app.config.get('MAIL_DEFAULT_SENDER')}")
        print(f"SENDGRID_API_KEY present: {bool(current_app.config.get('SENDGRID_API_KEY'))}")
        
        if not current_app.config.get('MAIL_DEFAULT_SENDER'):
            print("Error: MAIL_DEFAULT_SENDER not configured")
            return "Error: MAIL_DEFAULT_SENDER not configured", 500
            
        # Create test message
        message = Mail(
            from_email=Email(current_app.config['MAIL_DEFAULT_SENDER']),
            to_emails=[To(current_app.config['MAIL_DEFAULT_SENDER'])],
            subject='Debug Test Email',
            html_content='<strong>This is a debug test from Flask</strong>'
        )
        
        print("Message created successfully")
        
        # Log SendGrid setup
        sendgrid_api_key = current_app.config.get('SENDGRID_API_KEY')
        if not sendgrid_api_key:
            print("Error: SENDGRID_API_KEY not configured")
            return "Error: SENDGRID_API_KEY not configured", 500
            
        print("Initializing SendGrid client...")
        sg = SendGridAPIClient(sendgrid_api_key)
        
        print("Sending email...")
        response = sg.send(message)
        
        result = {
            'status_code': response.status_code,
            'body': response.body.decode() if response.body else None,
            'headers': dict(response.headers) if response.headers else None
        }
        
        print(f"SendGrid Response: {result}")
        
        if response.status_code not in [200, 201, 202]:
            error_msg = f"Error: Failed to send email - {result}"
            print(error_msg)
            return error_msg, 500
            
        success_msg = f"Email sent successfully! Details: {result}"
        print(success_msg)
        return success_msg
        
    except Exception as e:
        error_msg = f"Debug email error: {str(e)}"
        print(error_msg)
        if hasattr(e, 'body'):
            print(f"SendGrid error details: {e.body}")
        return f"Error: {str(e)}", 500

@bp.route('/dev/clear-users')
def dev_clear_users():
    if current_app.config['ENV'] != 'development':
        return "Not allowed in production", 403
        
    try:
        num_users = User.query.count()
        User.query.delete()
        db.session.commit()
        return f"Cleared {num_users} users from database"
    except Exception as e:
        db.session.rollback()
        return f"Error clearing users: {str(e)}", 500

@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Please enter your email address', 'danger')
            return render_template('auth/forgot_password.html')
        
        user = User.query.filter(func.lower(User.email) == email).first()
        if not user:
            # Don't reveal that the user doesn't exist
            flash('If your email is registered, you will receive a password reset link shortly', 'info')
            return render_template('auth/forgot_password.html')
        
        # Generate a password reset token
        payload = {
            'user_id': user.id,
            'exp': datetime.utcnow() + timedelta(hours=1)
        }
        token = jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')
        
        # Send the password reset email
        success = send_password_reset_email(user, token)
        
        if success:
            flash('A password reset link has been sent to your email address', 'success')
        else:
            logger.error(f"Failed to send password reset email to {email}")
            flash('Failed to send password reset email. Please try again later.', 'danger')
        
        return render_template('auth/forgot_password.html')
    
    return render_template('auth/forgot_password.html')

@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        user_id = payload['user_id']
        user = User.query.get(user_id)
        
        if not user:
            flash('Invalid reset link', 'danger')
            return redirect(url_for('auth.login'))
        
    except jwt.ExpiredSignatureError:
        flash('The reset link has expired', 'danger')
        return redirect(url_for('auth.forgot_password'))
    except jwt.InvalidTokenError:
        flash('Invalid reset link', 'danger')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash('Please enter and confirm your new password', 'danger')
            return render_template('auth/reset_password.html', token=token)
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('auth/reset_password.html', token=token)
        
        if len(password) < 8:
            flash('Password must be at least 8 characters long', 'danger')
            return render_template('auth/reset_password.html', token=token)
        
        # Update the user's password
        user.set_password(password)
        db.session.commit()
        
        flash('Your password has been reset successfully. You can now log in with your new password.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', token=token)

@bp.route('/test-reset-email')
def test_reset_email():
    """Test route to verify password reset email functionality"""
    if not current_app.debug:
        return "This route is only available in debug mode", 403
    
    # Get the first user or create a test user
    user = User.query.first()
    if not user:
        return "No users found in the database", 404
    
    # Generate a test token
    payload = {
        'user_id': user.id,
        'exp': datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')
    
    # Send the test email
    success = send_password_reset_email(user, token)
    
    if success:
        return f"Test password reset email sent to {user.email}. Check your inbox."
    else:
        return "Failed to send test password reset email. Check the logs for details.", 500

@bp.route('/update-password', methods=['GET', 'POST'])
@login_required
def update_password():
    form = PasswordUpdateForm()
    if form.validate_on_submit():
        # Verify current password
        if not current_user.check_password(form.current_password.data):
            flash('Current password is incorrect', 'danger')
            return redirect(url_for('auth.update_password'))
        
        # Update password
        current_user.set_password(form.new_password.data)
        db.session.commit()
        
        flash('Your password has been updated successfully', 'success')
        return redirect(url_for('main.dashboard'))
    
    return render_template('auth/update_password.html', form=form)