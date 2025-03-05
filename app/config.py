import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-key-please-change')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Upload paths
    if os.environ.get('RENDER') == "true":
        UPLOAD_FOLDER = '/opt/data/uploads'
        OUTPUT_FOLDER = '/opt/data/output'
        TEMP_FOLDER = '/opt/data/temp'
    else:
        UPLOAD_FOLDER = 'uploads'
        OUTPUT_FOLDER = 'output'
        TEMP_FOLDER = 'temp'
    
    # Stripe configuration
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    
    # Email configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.sendgrid.net')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'yes', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'apikey')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
    
    # Application URL for email links
    BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8000')