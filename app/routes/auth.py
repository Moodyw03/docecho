from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from app.forms import RegistrationForm, LoginForm
from app import db
import jwt
from datetime import datetime, timedelta
from flask import current_app
from flask_mail import Message
from werkzeug.security import generate_password_hash
from app import mail

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
            if User.query.filter_by(email=form.email.data).first():
                flash('Email address already exists', 'danger')
                return redirect(url_for('auth.register'))
            
            new_user = User(email=form.email.data)
            new_user.set_password(form.password.data)
            
            db.session.add(new_user)
            db.session.commit()
            
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
    # Change this to False to test email sending
    if False:
        user.email_verified = True
        db.session.commit()
        current_app.logger.info("Bypassed email verification for development")
        return
    try:
        # Generate verification token
        token = jwt.encode(
            {
                'user_id': user.id,
                'exp': datetime.utcnow() + timedelta(hours=24)
            },
            current_app.config['JWT_SECRET_KEY'],
            algorithm='HS256'
        )
        
        # Create verification URL
        verification_url = url_for('auth.verify_email', token=token, _external=True)
        
        # Build email message
        msg = Message('Verify Your Email Address', recipients=[user.email])
        msg.html = render_template(
            'emails/verify_email.html',
            verification_url=verification_url
        )
        
        # Attempt to send email
        mail.send(msg)
        current_app.logger.info(f"Verification email sent to {user.email}")
        
    except Exception as e:
        current_app.logger.error(f"Email error: {str(e)}")
        # Temporary debug output
        print(f"Verification URL: {verification_url}")

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