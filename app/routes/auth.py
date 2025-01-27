from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from app.forms import RegistrationForm, LoginForm
from app import db
import jwt
from datetime import datetime, timedelta
from flask import current_app
from werkzeug.security import generate_password_hash
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To
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
                session['unverified_email'] = user.email
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
    print("\n=== Starting Registration Process ===")
    if current_user.is_authenticated:
        print("User already authenticated, redirecting to index")
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
                send_verification_email(new_user)
                session['unverified_email'] = new_user.email
                flash('Please check your email to verify your account.', 'info')
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
        print("\n=== Starting verification email process ===")
        print(f"Sending to user: {user.email}")
        
        # Ensure proper token encoding
        token = jwt.encode(
            {
                'user_id': user.id,
                'exp': datetime.utcnow() + timedelta(hours=24)
            },
            current_app.config['JWT_SECRET_KEY'],
            algorithm='HS256'
        )
        print("Token generated successfully")
        
        # Generate verification URL using request.host_url
        verification_url = url_for(
            'auth.verify_email', 
            token=token, 
            _external=True, 
            _scheme='https'  # Force HTTPS links
        )
        print(f"Generated verification URL: {verification_url}")
        
        # Try rendering the template first to catch any template errors
        try:
            html_content = render_template(
                'emails/verify_email.html',
                verification_url=verification_url
            )
            print("Email template rendered successfully")
            print(f"Template content preview: {html_content[:200]}...")
        except Exception as template_error:
            print(f"Template rendering error: {str(template_error)}")
            raise ValueError(f"Failed to render email template: {str(template_error)}")
        
        if not current_app.config.get('MAIL_DEFAULT_SENDER'):
            print("Error: MAIL_DEFAULT_SENDER not configured!")
            raise ValueError("Missing sender email configuration")
            
        # Create SendGrid mail object
        message = Mail(
            from_email=Email(
                email="gabbipereira03@gmail.com",  # Verified email
                name="DocEcho Team"  # Optional display name
            ),
            to_emails=[To(user.email)],
            subject='Verify Your Email Address',
            html_content=html_content
        )
        print("SendGrid message object created")
        
        # Send using SendGrid API
        sendgrid_api_key = current_app.config.get('SENDGRID_API_KEY')
        if not sendgrid_api_key:
            print("Error: SENDGRID_API_KEY not configured!")
            raise ValueError("Missing SendGrid API key configuration")
            
        print("Initializing SendGrid client...")
        sg = SendGridAPIClient(sendgrid_api_key)
        
        print("Attempting to send email...")
        response = sg.send(message)
        
        if response.status_code not in [200, 202]:  # 202 is standard for async acceptance
            error_msg = f"SendGrid API error - Status: {response.status_code}"
            print(error_msg)
            if response.body:
                print(f"Response body: {response.body.decode()}")
            raise ValueError(f"Failed to send email - Status: {response.status_code}")
            
        print(f"Email sent successfully! Status: {response.status_code}")
        print(f"Message ID: {response.headers.get('X-Message-Id', 'Not available')}")
        print("=== End of verification email process ===\n")
        
        # Commit before sending email
        db.session.commit()
        print("Token committed to database")
        
    except jwt.PyJWTError as e:
        print(f"JWT error: {str(e)}")
        raise ValueError("Failed to generate verification token")
    except Exception as e:
        print(f"Email error: {str(e)}")
        if hasattr(e, 'body'):
            print(f"SendGrid error details: {e.body}")
        raise

@bp.route('/resend-verification')
def resend_verification():
    email = session.get('unverified_email')
    if not email:
        flash('No email to verify', 'error')
        return redirect(url_for('auth.login'))
    
    user = User.query.filter_by(email=email).first()
    
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('auth.login'))
    
    # Generate new verification token
    token = user.set_verification_token()
    
    # Create verification URL
    verification_url = url_for('auth.verify_email', 
                             token=token, 
                             _external=True)
    
    # Prepare email
    message = Mail(
        from_email=Email(current_app.config['MAIL_DEFAULT_SENDER']),
        to_emails=[To(user.email)],
        subject='Verify your DocEcho account',
        html_content=f'''
            <h1>Welcome to DocEcho!</h1>
            <p>Please click the link below to verify your email address:</p>
            <p><a href="{verification_url}">Verify Email</a></p>
            <p>If you did not create this account, please ignore this email.</p>
        '''
    )

    try:
        sg = SendGridAPIClient(current_app.config['SENDGRID_API_KEY'])
        response = sg.send(message)
        if response.status_code in [200, 202]:
            session.pop('unverified_email', None)
            flash('Verification email sent! Please check your inbox.', 'success')
    except Exception as e:
        current_app.logger.error(f'Error sending verification email: {str(e)}')
        flash('Error sending verification email. Please try again.', 'error')
    
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