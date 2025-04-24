import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

class Config:
    # Secret key for session
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    
    # Flask-SQLAlchemy settings
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///instance/app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File paths
    STATIC_FOLDER = os.environ.get('STATIC_FOLDER') or os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'static')
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    OUTPUT_FOLDER = os.environ.get('OUTPUT_FOLDER') or os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
    TEMP_FOLDER = os.environ.get('TEMP_FOLDER') or os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp')
    
    # Mail settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.sendgrid.net')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 't', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'apikey')
    MAIL_PASSWORD = os.environ.get('SENDGRID_API_KEY')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    
    # Redis/Celery settings
    CELERY_BROKER_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    
    # JWT Settings
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=1)
    
    # Stripe API configuration
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    # Supported languages configuration
    # Comma-separated string of language codes (e.g., "en,fr,es,de,it")
    # If not set, defaults to English
    LANGUAGES_SUPPORTED = os.environ.get('LANGUAGES_SUPPORTED', 'en')
    
    # Get list of languages that have PDF rendering issues 
    # These languages will only be offered with audio output
    PROBLEMATIC_LANGUAGES = os.environ.get('PROBLEMATIC_LANGUAGES', 'zh-CN,ja,ar,hi,ko').split(',')
    
    # Application environment
    APP_ENV = os.environ.get('APP_ENV', 'development')

    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
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

    # Celery configuration
    # Use REDIS_URL from environment (provided by Fly Redis) or fallback
    CELERY_BROKER_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    # Optional: configure other Celery settings if needed
    # CELERY_TASK_SERIALIZER = 'json'
    # CELERY_RESULT_SERIALIZER = 'json'
    # CELERY_ACCEPT_CONTENT = ['json']
    # CELERY_TIMEZONE = 'UTC'
    # CELERY_ENABLE_UTC = True