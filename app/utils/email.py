import os
import logging
from datetime import datetime
from flask import render_template, current_app
from flask_mail import Message
from app.extensions import mail

logger = logging.getLogger(__name__)

def send_email(subject, recipients, html_body, text_body=None, sender=None):
    """Send an email using Flask-Mail."""
    try:
        # Use the provided sender or format the default sender with a name
        if sender is None:
            default_email = current_app.config['MAIL_DEFAULT_SENDER']
            sender = ("DocEcho Team", default_email)
        
        msg = Message(subject, recipients=recipients, sender=sender)
        msg.html = html_body
        if text_body:
            msg.body = text_body
        mail.send(msg)
        logger.info(f"Email sent to {recipients} with subject: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return False

def send_verification_email(user, token):
    """Send a verification email to a user."""
    verify_url = f"{current_app.config['BASE_URL']}/auth/verify/{token}"
    
    html = render_template('email/verify_email.html', 
                          verify_url=verify_url,
                          year=datetime.now().year)
    
    text = render_template('email/verify_email.txt',
                          verify_url=verify_url,
                          year=datetime.now().year)
    
    return send_email(
        subject="Verify Your DocEcho Account",
        recipients=[user.email],
        html_body=html,
        text_body=text
    )

def send_password_reset_email(user, token):
    """Send a password reset email to a user."""
    reset_url = f"{current_app.config['BASE_URL']}/auth/reset-password/{token}"
    
    html = render_template('email/reset_password.html', 
                          reset_url=reset_url,
                          year=datetime.now().year)
    
    text = render_template('email/reset_password.txt',
                          reset_url=reset_url,
                          year=datetime.now().year)
    
    return send_email(
        subject="Reset Your DocEcho Password",
        recipients=[user.email],
        html_body=html,
        text_body=text
    ) 