from flask import Blueprint, render_template, request, jsonify, send_file, url_for, redirect, flash, current_app, abort
from flask_login import login_required, current_user
from app.models.user import User
from app import db
from app.utils.progress import get_progress, update_progress, delete_progress
import os
import uuid
import threading
from app.utils.pdf_processor import process_pdf
import stripe
from werkzeug.utils import secure_filename

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
            update_progress(task_id, status='uploading', progress=0)
            
            # Create upload directory if it doesn't exist
            upload_dir = os.path.join(app.root_path, 'static', 'uploads')
            output_dir = os.path.join(app.root_path, 'static', 'output')
            os.makedirs(upload_dir, exist_ok=True)
            os.makedirs(output_dir, exist_ok=True)
            
            # Save the uploaded file with safe filename
            safe_filename = secure_filename(file.filename)
            file_path = os.path.join(upload_dir, f"{task_id}_{safe_filename}")
            file.save(file_path)
            
            voice = request.form.get("voice", "en")
            output_format = request.form.get("output_format", "audio")
            speed = float(request.form.get("speed", "1.0"))
            
            required_credits = 1  # Base for PDF
            if output_format in ["audio", "both"]:
                required_credits += 1  # Add 1 more for audio (2 total for audio, 3 for both)
            
            if current_user.credits < required_credits:
                return jsonify({"error": "Insufficient credits"}), 402
            
            current_user.credits -= required_credits
            db.session.commit()
            
            def process_with_app_context(app, *args):
                with app.app_context():
                    process_pdf(*args)
            
            # Generate output filename
            output_filename = f"{os.path.splitext(safe_filename)[0]}_{task_id}.mp3"
            output_path = os.path.join(output_dir, output_filename)
            
            # Start processing in a background thread with app context
            thread = threading.Thread(
                target=process_with_app_context,
                args=(app, safe_filename, file_path, voice, speed, task_id, output_format, output_path)
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
    data = get_progress(task_id)
    if data:
        return jsonify(data)
    return jsonify({'status': 'Unknown Task'}), 404

@bp.route('/download/<task_id>')
@login_required
def download(task_id):
    try:
        data = get_progress(task_id)
        current_app.logger.info(f"Download request for task {task_id}. Progress data: {data}")
        
        if not data:
            current_app.logger.error(f"Task {task_id} not found in progress data")
            return jsonify({"error": "Task not found"}), 404
            
        if data.get('status') != 'completed':
            current_app.logger.error(f"Task {task_id} not completed. Status: {data.get('status')}")
            return jsonify({"error": "Files not ready"}), 400
            
        file_type = request.args.get('type', 'audio')  # Default to audio if not specified
        current_app.logger.info(f"Requested file type: {file_type}")
        
        if file_type == 'audio' and 'audio_file' not in data:
            current_app.logger.error(f"Audio file not found in data for task {task_id}")
            return jsonify({"error": "Audio file not found"}), 404
        elif file_type == 'pdf' and 'pdf_file' not in data:
            current_app.logger.error(f"PDF file not found in data for task {task_id}")
            return jsonify({"error": "PDF file not found"}), 404
            
        file_path = data['audio_file'] if file_type == 'audio' else data['pdf_file']
        current_app.logger.info(f"File path for {file_type}: {file_path}")
        
        # Verify file exists before sending
        if not os.path.exists(file_path):
            current_app.logger.error(f"File not found at path: {file_path}")
            return jsonify({"error": f"{file_type.upper()} file not found"}), 404

        # Get fresh file handle
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"{file_type.upper()} file not found")

        response = send_file(
            file_path,
            mimetype='audio/mpeg' if file_type == 'audio' else 'application/pdf',
            as_attachment=True,
            download_name=os.path.basename(file_path),
            conditional=True  # Add conditional sending
        )
        
        # Only delete progress if both files have been downloaded
        if request.args.get('final') == 'true':
            delete_progress(task_id)
            current_app.logger.info(f"Cleaned up progress data for task {task_id}")
        
        current_app.logger.info(f"Successfully sent {file_type} file for task {task_id}")
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error downloading file for task {task_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route('/pricing')
def pricing():
    return render_template('pricing.html', 
                          stripe_public_key=current_app.config['STRIPE_PUBLIC_KEY'],
                          credit_packages=CREDIT_PACKAGES)

@bp.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    package_id = request.form.get('package_id')
    package = CREDIT_PACKAGES.get(package_id)
    
    if not package:
        abort(400, "Invalid package selected")
    
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f'{package["credits"]} Credits Package',
                    },
                    'unit_amount': package['price'] * 100,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('main.payment_success', _external=True),
            cancel_url=url_for('main.pricing', _external=True),
            metadata={
                'user_id': current_user.id,
                'credits': package['credits']
            }
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        current_app.logger.error(f"Stripe error: {str(e)}")
        return str(e), 400

@bp.route('/payment-success')
@login_required
def payment_success():
    # Update user credits (you'll need to implement webhook verification for production)
    return redirect(url_for('main.index'))

@bp.route('/terms')
def terms():
    return render_template('terms.html')

@bp.route('/clear-users')
def clear_users():
    if os.environ.get('FLASK_ENV') == 'development':
        from app.models.user import User
        User.query.delete()
        db.session.commit()
        return 'Users cleared'
    return 'Not allowed in production'

def process_pdf(filename, file_path, voice, speed, task_id, output_format, output_path):
    try:
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
            output_path=output_path
        )
        
    except Exception as e:
        # Log the error
        current_app.logger.error(f"Error processing PDF: {str(e)}")
        raise e