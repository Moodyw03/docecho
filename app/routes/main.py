from flask import Blueprint, render_template, request, jsonify, send_file, url_for, redirect, flash
from flask_login import login_required, current_user
import os
import uuid
import threading
from app.utils.pdf_processor import process_pdf
from app.models.user import User
from app import db
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
            file_path = os.path.join('uploads', f"{task_id}_{file.filename}")
            file.save(file_path)
            
            voice = request.form.get("voice", "en")
            output_format = request.form.get("output_format", "audio")
            speed = float(request.form.get("speed", "1.0"))
            
            required_credits = 2 if output_format == "audio" else 1
            if current_user.credits < required_credits:
                return jsonify({"error": "Insufficient credits"}), 402
            
            current_user.credits -= required_credits
            db.session.commit()
            
            thread = threading.Thread(
                target=process_pdf,
                args=(file.filename, file_path, voice, speed, task_id, output_format, progress_dict)
            )
            thread.start()
            
            return jsonify({"task_id": task_id}), 202
            
        return jsonify({"error": "Invalid file type"}), 400
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/progress/<task_id>')
def progress(task_id):
    if task_id in progress_dict:
        return jsonify(progress_dict[task_id])
    return jsonify({'status': 'Unknown Task'}), 404

@bp.route('/download/<task_id>')
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