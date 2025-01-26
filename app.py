from flask import Flask, render_template, request, jsonify, send_file, url_for, redirect, flash
from PyPDF2 import PdfReader
from gtts import gTTS
from pydub import AudioSegment
import os
from googletrans import Translator
import threading
import uuid
import time
from pathlib import Path
import logging
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from textwrap import wrap
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import stripe
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

STATIC_FOLDER = '/data' if os.environ.get('RENDER') else 'static'
UPLOAD_FOLDER = os.path.join(STATIC_FOLDER, 'uploads')
OUTPUT_FOLDER = os.path.join(STATIC_FOLDER, 'output')
TEMP_FOLDER = os.path.join(STATIC_FOLDER, 'temp')

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()

# User Model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    credits = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

def create_app():
    app = Flask(__name__, 
                template_folder='app/templates',
                static_folder='static')
    app.secret_key = os.getenv('FLASK_SECRET_KEY')
    
    # Create instance directory if it doesn't exist
    os.makedirs('instance', exist_ok=True)
    
    # Configure app
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
    if not app.config['SECRET_KEY']:
        logger.warning("No SECRET_KEY set! Using a random key for development.")
        app.config['SECRET_KEY'] = os.urandom(32)
    
    # Database configuration
    database_url = os.getenv('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        # Fallback to SQLite
        if os.environ.get('RENDER') == "true":
            db_path = '/data/database.db'
        else:
            # Use absolute path for SQLite database
            db_path = os.path.abspath(os.path.join('instance', 'docecho.db'))
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    
    # Configure upload paths
    if os.environ.get('RENDER') == "true":
        app.config['UPLOAD_FOLDER'] = '/data/uploads'
        app.config['OUTPUT_FOLDER'] = '/data/output'
        app.config['TEMP_FOLDER'] = '/data/temp'
    else:
        app.config['UPLOAD_FOLDER'] = 'uploads'
        app.config['OUTPUT_FOLDER'] = 'output'
        app.config['TEMP_FOLDER'] = 'temp'
    
    # Ensure required directories exist
    for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER'], app.config['TEMP_FOLDER']]:
        os.makedirs(folder, exist_ok=True)
        if os.environ.get('RENDER') == "true":
            os.chmod(folder, 0o755)
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    
    # Ensure directories exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # User loader callback
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Routes
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/pricing')
    def pricing():
        return render_template('pricing.html', stripe_public_key=STRIPE_PUBLIC_KEY)

    @app.route('/create-checkout-session', methods=['POST'])
    def create_checkout_session():
        package = request.form.get('package')
        if package not in CREDIT_PACKAGES:
            return jsonify({'error': 'Invalid package'}), 400

        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'unit_amount': CREDIT_PACKAGES[package]['price'] * 100,
                        'product_data': {
                            'name': f'{package.title()} Package',
                            'description': f'{CREDIT_PACKAGES[package]["credits"]} credits',
                        },
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=url_for('success', package=package, _external=True),
                cancel_url=url_for('pricing', _external=True),
                client_reference_id=str(current_user.id),
            )
            return jsonify({'id': checkout_session.id})
        except Exception as e:
            return jsonify({'error': str(e)}), 403

    @app.route('/success')
    @login_required
    def success():
        package = request.args.get('package')
        if package in CREDIT_PACKAGES:
            user = User.query.get(current_user.id)
            user.credits += CREDIT_PACKAGES[package]['credits']
            db.session.commit()
            flash('Payment successful! Credits have been added to your account.', 'success')
        return redirect(url_for('index'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            try:
                email = request.form.get('email')
                password = request.form.get('password')
                
                app.logger.info(f"Login attempt for email: {email}")
                
                user = User.query.filter_by(email=email).first()
                if user and user.check_password(password):
                    login_user(user)
                    app.logger.info(f"Login successful for user: {email}")
                    return redirect(url_for('index'))
                
                app.logger.warning(f"Failed login attempt for email: {email}")
                flash('Invalid email or password')
            except Exception as e:
                app.logger.error(f"Login error: {str(e)}")
                flash('An error occurred during login')
        
        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            try:
                email = request.form.get('email')
                password = request.form.get('password')
                
                app.logger.info(f"Registration attempt for email: {email}")
                
                if User.query.filter_by(email=email).first():
                    flash('Email already registered')
                    return redirect(url_for('register'))
                
                user = User(email=email)
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                
                app.logger.info(f"Registration successful for email: {email}")
                flash('Registration successful')
                return redirect(url_for('login'))
            except Exception as e:
                app.logger.error(f"Registration error: {str(e)}")
                flash('An error occurred during registration')
                db.session.rollback()
        
        return render_template('register.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('index'))

    @app.route('/terms')
    def terms():
        return render_template('terms.html')

    @app.route('/health')
    def health_check():
        return {'status': 'healthy'}, 200

    return app

# Create the app instance
app = create_app()

if __name__ == "__main__":
    # Create database tables within application context
    with app.app_context():
        try:
            # Ensure instance directory exists
            os.makedirs('instance', exist_ok=True)
            
            # Create all database tables
            db.create_all()
            print("Database tables created successfully")
            
            # Initialize test user if in development
            if os.environ.get('FLASK_ENV') != 'production':
                if not User.query.filter_by(email='test2@example.com').first():
                    test_user = User(email='test2@example.com', credits=5)
                    test_user.set_password('testpassword')
                    db.session.add(test_user)
                    db.session.commit()
                    
        except Exception as e:
            print(f"Error creating database tables: {e}")
            raise e

    # Run the application
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

