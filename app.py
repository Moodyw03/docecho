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
    app = Flask(__name__)
    app.secret_key = os.getenv('FLASK_SECRET_KEY')
    
    # Configure app
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
    if not app.config['SECRET_KEY']:
        logger.warning("No SECRET_KEY set! Using a random key for development.")
        app.config['SECRET_KEY'] = os.urandom(32)
    
    # Database configuration
    database_url = os.getenv('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        # Heroku/Render style PostgreSQL URL
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        # Fallback to SQLite
        if os.environ.get('RENDER') == "true":
            db_path = '/data/database.db'
        else:
            db_path = os.path.join(app.instance_path, 'users.db')
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

# Create database tables
with app.app_context():
    try:
        db.create_all()
        print("Database tables created successfully")
    except Exception as e:
        print(f"Error creating database tables: {e}")

def ensure_directories():
    base_dir = '/data' if os.environ.get('RENDER') else os.path.dirname(os.path.abspath(__file__))
    required_dirs = ['uploads', 'output', 'temp']
    
    for dir_name in required_dirs:
        dir_path = os.path.join(base_dir, dir_name)
        os.makedirs(dir_path, exist_ok=True)
        # Ensure directory is writable
        os.chmod(dir_path, 0o755)
    return base_dir

# Call ensure_directories after defining it
ensure_directories()

# Global dictionary to store progress information
progress_dict = {}

# Mapping language codes and TLDs for accents
language_map = {
    "en": {"lang": "en", "tld": "com"},
    "en-uk": {"lang": "en", "tld": "co.uk"},
    "pt": {"lang": "pt", "tld": "com.br"},
    "es": {"lang": "es", "tld": "com"},
    "fr": {"lang": "fr", "tld": "fr"},
    "de": {"lang": "de", "tld": "de"},
    "it": {"lang": "it", "tld": "it"},
    "zh-CN": {"lang": "zh-CN", "tld": "com"},
    "ja": {"lang": "ja", "tld": "co.jp"}
}

def extract_text_chunks_from_pdf(pdf_path, max_chunk_length=500):
    try:
        reader = PdfReader(pdf_path)
        chunks = []
        current_chunk = ''
        
        # Add progress tracking for PDF reading
        total_pages = len(reader.pages)
        for page_num, page in enumerate(reader.pages):
            # Free up memory after every few pages
            if page_num % 10 == 0:
                import gc
                gc.collect()
            
            page_text = page.extract_text()
            if not page_text:
                continue
                
            # Split by sentences instead of words for more natural breaks
            sentences = page_text.replace('\n', ' ').split('. ')
            
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 2 > max_chunk_length:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence + '. '
                else:
                    current_chunk += sentence + '. '
                    
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks
    except Exception as e:
        raise Exception(f"Error extracting text from PDF: {e}")

def convert_text_to_audio(text, output_filename, voice, speed, tld='com'):
    try:
        temp_output = os.path.join('temp', output_filename.replace(".mp3", "_temp.mp3"))
        output_path = os.path.join('temp', output_filename)
        tts = gTTS(text, lang=voice, tld=tld)
        tts.save(temp_output)

        # Adjust the speed if necessary
        if speed != 1.0:
            sound = AudioSegment.from_file(temp_output)
            sound = sound.speedup(playback_speed=speed)
            sound.export(output_path, format="mp3")
            os.remove(temp_output)  # Remove the temporary file
        else:
            os.rename(temp_output, output_path)

        return output_path
    except Exception as e:
        raise Exception(f"Error converting text to audio: {e}")

def concatenate_audio_files(audio_files, output_path):
    try:
        combined = AudioSegment.empty()
        for file in audio_files:
            audio = AudioSegment.from_file(file)
            combined += audio
        combined.export(output_path, format="mp3")
    except Exception as e:
        raise Exception(f"Error concatenating audio files: {e}")

def register_fonts():
    font_dir = os.path.join(os.path.dirname(__file__), 'fonts')
    pdfmetrics.registerFont(TTFont('NotoSans', os.path.join(font_dir, 'NotoSans-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('NotoSansJP', os.path.join(font_dir, 'NotoSansJP-Regular.otf')))
    addMapping('NotoSans', 0, 0, 'NotoSans')
    addMapping('NotoSansJP', 0, 0, 'NotoSansJP')

def create_translated_pdf(text, output_path, language_code='en'):
    try:
        c = canvas.Canvas(output_path, pagesize=letter)
        width, height = letter
        y = height - 50  # Start from top
        
        # Use default Helvetica font
        c.setFont("Helvetica", 11)
        
        # Split text into lines for better handling
        lines = text.split('\n')
        for line in lines:
            # Basic word wrapping
            words = line.split()
            current_line = []
            
            for word in words:
                current_line.append(word)
                line_width = c.stringWidth(' '.join(current_line), "Helvetica", 11)
                
                if line_width > width - 100:
                    # Remove last word and print line
                    current_line.pop()
                    if current_line:
                        c.drawString(50, y, ' '.join(current_line))
                        y -= 20
                    current_line = [word]
                
                # Check if we need a new page
                if y < 50:
                    c.showPage()
                    c.setFont("Helvetica", 11)
                    y = height - 50
            
            # Print remaining words in the line
            if current_line:
                c.drawString(50, y, ' '.join(current_line))
                y -= 20
        
        c.save()
        return output_path
        
    except Exception as e:
        print(f"PDF Creation Error: {str(e)}")  # Add debug logging
        raise Exception(f"Error creating PDF: {str(e)}")

def process_pdf(filename, file_path, language_code, tld, speed, task_id, output_format="audio"):
    try:
        logger.info(f"Starting processing for task {task_id}")
        if not os.path.exists('output'):
            os.makedirs('output')
        if not os.path.exists('temp'):
            os.makedirs('temp')

        # Initialize progress
        progress_dict[task_id] = {'status': 'Processing', 'progress': 0}

        # Extract text chunks
        progress_dict[task_id]['status'] = 'Extracting text from PDF...'
        text_chunks = extract_text_chunks_from_pdf(file_path)
        total_chunks = len(text_chunks)

        if total_chunks == 0:
            raise Exception("No text could be extracted from the PDF")

        # Initialize the translator
        translator = Translator()
        
        # Process chunks in smaller batches
        batch_size = 10
        audio_chunks = []
        translated_text = []  # Store all translated text
        
        for batch_start in range(0, total_chunks, batch_size):
            batch_end = min(batch_start + batch_size, total_chunks)
            batch = text_chunks[batch_start:batch_end]
            
            for i, chunk in enumerate(batch):
                overall_progress = int(((batch_start + i) / total_chunks) * 100)
                progress_dict[task_id]['progress'] = overall_progress
                progress_dict[task_id]['status'] = f'Processing chunk {batch_start + i + 1} of {total_chunks}...'

                try:
                    translated_chunk = translator.translate(chunk, dest=language_code).text
                    translated_text.append(translated_chunk)  # Store translated text
                    
                    if output_format in ["audio", "both"]:
                        # Convert the translated chunk to audio
                        chunk_filename = f"{task_id}_chunk_{batch_start + i}.mp3"
                        audio_chunk_path = convert_text_to_audio(
                            translated_chunk,
                            chunk_filename,
                            language_code,
                            speed,
                            tld,
                        )
                        audio_chunks.append(audio_chunk_path)

                except Exception as e:
                    logger.error(f"Error processing chunk {batch_start + i}: {str(e)}")
                    continue

            # Free up memory after each batch
            import gc
            gc.collect()

        # Handle PDF creation if requested
        if output_format in ["pdf", "both"]:
            pdf_filename = filename.replace(".pdf", f"_translated_{task_id}.pdf")
            pdf_path = os.path.join("output", pdf_filename)
            create_translated_pdf('\n'.join(translated_text), pdf_path, language_code)
            progress_dict[task_id]['pdf_file'] = pdf_path

        # Handle audio if requested
        if output_format in ["audio", "both"]:
            if audio_chunks:
                output_filename = filename.replace(".pdf", f"_{task_id}.mp3")
                final_audio_file = os.path.join("output", output_filename)
                concatenate_audio_files(audio_chunks, final_audio_file)
                progress_dict[task_id]['audio_file'] = final_audio_file

        # Clean up
        for audio_file in audio_chunks:
            try:
                os.remove(audio_file)
            except:
                pass
        try:
            os.remove(file_path)
        except:
            pass

        progress_dict[task_id]['progress'] = 100
        progress_dict[task_id]['status'] = 'Completed'

    except Exception as e:
        logger.error(f"Error in process_pdf: {str(e)}")
        progress_dict[task_id]['status'] = 'Error'
        progress_dict[task_id]['error'] = str(e)

# Credit packages
CREDIT_PACKAGES = {
    'starter': {'price': 10, 'credits': 10},
    'value': {'price': 25, 'credits': 45},
    'pro': {'price': 50, 'credits': 100}
}

# Credit costs
CREDIT_COSTS = {
    'pdf': 1,  # 1 credit per page for PDF
    'audio': 2  # 2 credits per page for audio
}

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY')

# Update Flask secret key
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')

@app.route("/", methods=["POST"])
@login_required
def process_file():
    if not current_user.is_authenticated:
        return jsonify({"error": "Please login to use this service"}), 401
        
    try:
        if "pdf_file" not in request.files:
            return jsonify({"error": "No file part in the request"}), 400
            
        file = request.files["pdf_file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400
            
        if file and file.filename.endswith(".pdf"):
            # Create task and process file
            task_id = str(uuid.uuid4())
            file_path = os.path.join('uploads', f"{task_id}_{file.filename}")
            file.save(file_path)
            
            voice = request.form.get("voice", "en")
            output_format = request.form.get("output_format", "audio")
            speed = float(request.form.get("speed", "1.0"))
            
            # Check if user has enough credits
            required_credits = 2 if output_format == "audio" else 1
            if current_user.credits < required_credits:
                return jsonify({"error": "Insufficient credits"}), 402
            
            # Deduct credits
            current_user.credits -= required_credits
            db.session.commit()
            
            lang_settings = language_map.get(voice, {"lang": "en", "tld": "com"})
            
            thread = threading.Thread(
                target=process_pdf,
                args=(file.filename, file_path, lang_settings["lang"], 
                      lang_settings["tld"], speed, task_id, output_format)
            )
            thread.start()
            
            return jsonify({"task_id": task_id}), 202
            
        return jsonify({"error": "Invalid file type"}), 400
        
    except Exception as e:
        print(f"Error in process_file: {str(e)}")  # Add debug logging
        return jsonify({"error": str(e)}), 500

@app.route('/progress/<task_id>')
def progress(task_id):
    if task_id in progress_dict:
        return jsonify(progress_dict[task_id])
    else:
        return jsonify({'status': 'Unknown Task'}), 404

@app.route('/download/<task_id>')
def download(task_id):
    if task_id in progress_dict:
        if progress_dict[task_id]['status'] == 'Completed':
            output_format = request.args.get('format', 'audio')
            
            if output_format == 'pdf' and 'pdf_file' in progress_dict[task_id]:
                return send_file(progress_dict[task_id]['pdf_file'], as_attachment=True)
            elif output_format == 'audio' and 'audio_file' in progress_dict[task_id]:
                return send_file(progress_dict[task_id]['audio_file'], as_attachment=True)
            else:
                return jsonify({'error': 'Requested format not available'}), 400
                
        elif progress_dict[task_id]['status'] == 'Error':
            return jsonify({'error': progress_dict[task_id]['error']}), 500
        else:
            return jsonify({'status': progress_dict[task_id]['status']}), 202
    else:
        return jsonify({'error': 'Invalid Task ID'}), 404

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

# Initialize database and test user if needed
if os.environ.get('FLASK_ENV') != 'production':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(email='test2@example.com').first():
            test_user = User(email='test2@example.com', credits=5)
            test_user.set_password('testpassword')
            db.session.add(test_user)
            db.session.commit()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

