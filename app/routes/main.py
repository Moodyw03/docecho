from flask import Blueprint, render_template, request, jsonify, send_file, url_for, redirect, flash, current_app
from flask_login import login_required, current_user
from app.models.user import User
from app import db
import os
import uuid
import threading
from app.utils.pdf_processor import process_pdf
import stripe

bp = Blueprint('main', __name__)

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY')

# Credit packages
CREDIT_PACKAGES = {
    'starter': {'price': 10, 'credits': 10},
    'value': {'price': 25, 'credits': 45},
    'pro': {'price': 50, 'credits': 100}
}

# Progress tracking
progress_dict = {}

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/', methods=['POST'])
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
            task_id = str(uuid.uuid4())
            
            # Get the current app
            app = current_app._get_current_object()
            
            # Initialize progress tracking for this task
            progress_dict[task_id] = {
                'status': 'uploading',
                'progress': 0,
                'error': None
            }
            
            # Create upload directory if it doesn't exist
            upload_dir = os.path.join(app.root_path, 'static', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Save the uploaded file
            file_path = os.path.join(upload_dir, f"{task_id}_{file.filename}")
            file.save(file_path)
            
            voice = request.form.get("voice", "en")
            output_format = request.form.get("output_format", "audio")
            speed = float(request.form.get("speed", "1.0"))
            
            required_credits = 2 if output_format == "audio" else 1
            if current_user.credits < required_credits:
                return jsonify({"error": "Insufficient credits"}), 402
            
            current_user.credits -= required_credits
            db.session.commit()
            
            def process_with_app_context(app, *args):
                with app.app_context():
                    process_pdf(*args)
            
            # Start processing in a background thread with app context
            thread = threading.Thread(
                target=process_with_app_context,
                args=(app, file.filename, file_path, voice, speed, task_id, output_format, progress_dict)
            )
            thread.daemon = True
            thread.start()
            
            return jsonify({"task_id": task_id}), 202
            
        return jsonify({"error": "Invalid file type"}), 400
        
    except Exception as e:
        current_app.logger.error(f"Error processing file: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/progress/<task_id>')
def progress(task_id):
    if task_id in progress_dict:
        return jsonify(progress_dict[task_id])
    return jsonify({'status': 'Unknown Task'}), 404

@bp.route('/download/<task_id>')
@login_required
def download(task_id):
    try:
        if task_id not in progress_dict:
            return jsonify({"error": "Task not found"}), 404
            
        task_info = progress_dict[task_id]
        
        if task_info.get('status') != 'completed':
            return jsonify({"error": "Audio file not ready"}), 400
            
        if 'audio_file' not in task_info:
            return jsonify({"error": "Audio file not found"}), 404
            
        audio_file = task_info['audio_file']
        
        if not os.path.exists(audio_file):
            return jsonify({"error": "Audio file not found"}), 404
            
        # Get just the filename from the full path
        filename = os.path.basename(audio_file)
        
        return send_file(
            audio_file,
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f"Error downloading file: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/pricing')
def pricing():
    return render_template('pricing.html', stripe_public_key=STRIPE_PUBLIC_KEY)

@bp.route('/create-checkout-session', methods=['POST'])
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
            success_url=url_for('main.success', package=package, _external=True),
            cancel_url=url_for('main.pricing', _external=True),
            client_reference_id=str(current_user.id),
        )
        return jsonify({'id': checkout_session.id})
    except Exception as e:
        return jsonify({'error': str(e)}), 403

@bp.route('/success')
@login_required
def success():
    package = request.args.get('package')
    if package in CREDIT_PACKAGES:
        user = User.query.get(current_user.id)
        user.credits += CREDIT_PACKAGES[package]['credits']
        db.session.commit()
        flash('Payment successful! Credits have been added to your account.', 'success')
    return redirect(url_for('main.index'))

@bp.route('/terms')
def terms():
    return render_template('terms.html')

def process_pdf(filename, file_path, voice, speed, task_id, output_format, progress_dict):
    try:
        # Initialize progress tracking
        progress_dict[task_id] = {
            'status': 'processing',
            'progress': 0,
            'error': None
        }
        
        # Create output directory if it doesn't exist
        output_dir = os.path.join(current_app.root_path, 'static', 'output')
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate output filename
        output_filename = f"{os.path.splitext(filename)[0]}_{task_id}.mp3"
        output_path = os.path.join(output_dir, output_filename)
        
        # Call the actual PDF processing function from utils
        from app.utils.pdf_processor import process_pdf as process_pdf_util
        
        # Pass the output path to the processing function
        process_pdf_util(
            filename=filename,
            file_path=file_path,
            voice=voice,
            speed=speed,
            task_id=task_id,
            output_format=output_format,
            progress_dict=progress_dict,
            output_path=output_path  # Add this parameter
        )
        
        # Verify the file exists before marking as completed
        if os.path.exists(output_path):
            progress_dict[task_id].update({
                'audio_file': output_path,
                'status': 'completed',
                'progress': 100
            })
        else:
            raise FileNotFoundError(f"Generated audio file not found at {output_path}")
        
    except Exception as e:
        # Log the error
        current_app.logger.error(f"Error processing PDF: {str(e)}")
        
        # Update progress dict with error
        progress_dict[task_id].update({
            'status': 'error',
            'error': str(e),
            'progress': 0
        })