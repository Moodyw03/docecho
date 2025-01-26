from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from app.forms import RegistrationForm, LoginForm
from app import db
import jwt
from datetime import datetime, timedelta
from flask import current_app
from werkzeug.security import generate_password_hash
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
from sqlalchemy import func

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
                flash('Please verify your email before logging in', 'warning')
                return redirect(url_for('auth.login'))
            if user.check_password(form.password.data):
                login_user(user)
                flash('Logged in successfully.')
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
            email = form.email.data.strip().lower()  # Normalize email
            if User.query.filter(func.lower(User.email) == email).first():
                flash('Email address already exists', 'danger')
                return redirect(url_for('auth.register'))
            
            new_user = User(email=form.email.data)
            new_user.set_password(form.password.data)
            
            db.session.add(new_user)
            db.session.commit()  # First commit to get user ID
            
            token = jwt.encode(
                {
                    'user_id': new_user.id,
                    'exp': datetime.utcnow() + timedelta(hours=24)
                },
                current_app.config['JWT_SECRET_KEY'],
                algorithm='HS256'
            ).decode('utf-8')  # Generate token after commit
            new_user.set_verification_token(token)
            
            send_verification_email(new_user)
            flash('Registration successful! Check your email to verify.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Registration error: {str(e)}', exc_info=True)
            flash(f'Registration failed: {str(e)}', 'danger')
    
    # Show form with errors
    return render_template('auth/register.html', form=form)

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('main.index'))

@bp.route('/verify-email/<token>')
def verify_email(token):
    try:
        decoded = jwt.decode(
            token,
            current_app.config['JWT_SECRET_KEY'],
            algorithms=['HS256']
        )
        user = User.query.get(decoded['user_id'])
        
        if user and not user.email_verified:
            user.email_verified = True
            user.verification_token = None
            db.session.commit()
            flash('Email verified successfully! You can now login.', 'success')
        else:
            flash('Invalid or expired verification link.', 'danger')
            
    except jwt.ExpiredSignatureError:
        flash('Verification link has expired.', 'danger')
    except jwt.InvalidTokenError:
        flash('Invalid verification link.', 'danger')
        
    return redirect(url_for('auth.login'))

def send_verification_email(user):
    try:
        # Ensure proper token encoding
        token = jwt.encode(
            {
                'user_id': user.id,
                'exp': datetime.utcnow() + timedelta(hours=24)
            },
            current_app.config['JWT_SECRET_KEY'],
            algorithm='HS256'
        ).decode('utf-8')  # Add decode for Flask-JWT compatibility
        
        verification_url = url_for('auth.verify_email', token=token, _external=True)
        
        # Add debug logging
        current_app.logger.debug(f"Verification URL: {verification_url}")
        current_app.logger.debug(f"Sending to: {user.email}")
        
        # Create SendGrid mail object
        message = Mail(
            from_email=current_app.config['MAIL_DEFAULT_SENDER'],
            to_emails=user.email,
            subject='Verify Your Email Address',
            html_content=render_template(
                'emails/verify_email.html',
                verification_url=verification_url
            ))
        
        # Send using SendGrid API
        sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        
        # Add verification
        if not sg.client.api_key:
            current_app.logger.error("NO SENDGRID API KEY FOUND!")
            raise ValueError("Missing SendGrid API key")
        
        response = sg.send(message)
        
        current_app.logger.info(f"Email sent to {user.email} - Status: {response.status_code}")
        
    except Exception as e:
        current_app.logger.error(f"Email error: {str(e)}")
        if hasattr(e, 'body'):
            current_app.logger.error(f"SendGrid error details: {e.body}")

@bp.route('/resend-verification')
@login_required
def resend_verification():
    if current_user.email_verified:
        return redirect(url_for('main.index'))
    
    try:
        send_verification_email(current_user)
        flash('New verification email sent', 'success')
    except Exception as e:
        flash('Failed to resend verification email', 'danger')
    
    return redirect(url_for('auth.login'))

@bp.route('/test-sendgrid')
def test_sendgrid():
    try:
        message = Mail(
            from_email=current_app.config['MAIL_DEFAULT_SENDER'],
            to_emails='gabbipereira03@gmail.com',
            subject='SendGrid Test',
            html_content='<strong>This is a test from Flask</strong>')
        
        sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        response = sg.send(message)
        return f"Email sent! Status: {response.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"

@bp.route('/debug-verify/<email>')
def debug_verify(email):
    user = User.query.filter_by(email=email).first()
    if user:
        send_verification_email(user)
        return f"Verification email re-sent to {email}"
    return "User not found"