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
    STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY')
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')