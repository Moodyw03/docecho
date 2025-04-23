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
import copy
import json
from datetime import datetime

bp = Blueprint('main', __name__)

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
            # Get the current app
            app = current_app._get_current_object()
            
            # Save the uploaded file using the configured UPLOAD_FOLDER
            safe_filename = secure_filename(file.filename)
            upload_folder = current_app.config['UPLOAD_FOLDER']
            # Ensure the upload folder exists (especially for local dev)
            os.makedirs(upload_folder, exist_ok=True)
            file_path = os.path.join(upload_folder, safe_filename)
            file.save(file_path)
            current_app.logger.info(f"File saved to: {file_path}")
            
            # Read the file content into memory to pass directly to the task
            # This avoids needing shared volumes between the web and worker processes
            pdf_content = None
            try:
                with open(file_path, 'rb') as f:
                    pdf_content = f.read()
                current_app.logger.info(f"File content read: {len(pdf_content)} bytes")
            except Exception as e:
                current_app.logger.error(f"Error reading file content: {str(e)}")
                return jsonify({"error": f"Error reading file: {str(e)}"}), 500
            
            voice = request.form.get("voice", "en")
            output_format = request.form.get("output_format", "audio")
            speed = float(request.form.get("speed", "1.0"))
            
            required_credits = 1
            if output_format in ["audio", "both"]:
                required_credits += 1  # Add 1 more for audio (2 total for audio, 3 for both)
            
            if current_user.credits < required_credits:
                return jsonify({"error": "Insufficient credits"}), 402
            
            # Deduct credits and commit before starting the task
            user_id = current_user.id
            with app.app_context():
                user = User.query.get(user_id)
                if user:
                    user.credits -= required_credits
                    db.session.commit()
                    current_app.logger.info(f"Deducted {required_credits} credits from user {user_id}")
            
            # Let's define the intended final output directory using config
            final_output_dir = current_app.config['OUTPUT_FOLDER']
            # Define the temporary directory using config
            temp_dir = current_app.config['TEMP_FOLDER'] 
            # Ensure the output and temp folders exist
            os.makedirs(final_output_dir, exist_ok=True)
            os.makedirs(temp_dir, exist_ok=True) 
            # The final filename will be constructed within the task based on this dir.

            # Store parameters needed for processing
            process_params = {
                'filename': safe_filename,
                'file_content': pdf_content,  # Pass file content instead of path
                'voice': voice,
                'speed': speed,
                'output_format': output_format,
                'output_path': final_output_dir, # Pass the configured output directory
                'temp_path': temp_dir # Pass the configured temporary directory
            }

            # Log the parameters for debugging
            log_params = process_params.copy()
            log_params['file_content'] = f"<{len(pdf_content)} bytes>"  # Don't log binary content
            current_app.logger.info(f"Enqueuing PDF processing with parameters: {json.dumps(log_params, default=str)}")

            # Enqueue the task with Celery
            # .delay() is a shortcut for .apply_async()
            task = process_pdf.delay(**process_params)
            task_id = task.id # Get the Celery task ID

            current_app.logger.info(f"Enqueued background processing task {task_id}")
            return jsonify({"task_id": task_id}), 202
            
        return jsonify({"error": "Invalid file type"}), 400
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        current_app.logger.error(f"Error processing file: {str(e)}\n{error_details}")
        return jsonify({"error": str(e)}), 500

@bp.route('/progress/<task_id>')
def progress(task_id):
    try:
        current_app.logger.info(f"Checking progress for task {task_id}")
        
        # Always look in both the database and files for progress data
        try:
            # First try to get progress from the shared database
            from app.utils.progress import get_progress
            data = get_progress(task_id)
            
            if data:
                # Cache response information for better performance
                response = jsonify(data)
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
                current_app.logger.debug(f"Progress data for task {task_id}: {data}")
                return response
            
            # If no data in database, check if the task is still initializing
            # This can happen if the task was just created but not yet written to the database
            current_app.logger.warning(f"No progress data found for task {task_id}")
            
            # Return a "processing" status to avoid error messages to the client
            # The client will retry automatically
            return jsonify({
                'status': 'initializing', 
                'progress': 0,
                'message': 'Task is still initializing...',
                'task_id': task_id
            }), 202  # 202 Accepted indicates the request is being processed
            
        except Exception as inner_e:
            current_app.logger.error(f"Error retrieving progress data: {str(inner_e)}")
            # Return a default response to avoid breaking the client
            return jsonify({
                'status': 'processing',
                'progress': 0,
                'message': 'Retrieving progress information...',
                'task_id': task_id
            }), 202
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        current_app.logger.error(f"Error checking progress for task {task_id}: {str(e)}\n{error_details}")
        
        # Even on error, return a graceful response to the client
        return jsonify({
            'status': 'processing',
            'progress': 0, 
            'message': 'System is processing your request...',
            'task_id': task_id
        }), 202

@bp.route('/download/<task_id>')
@login_required
def download(task_id):
    try:
        # Log basic request information for debugging
        current_app.logger.info(f"Download request received for task {task_id}")
        current_app.logger.info(f"Request headers: {dict(request.headers)}")
        current_app.logger.info(f"Request args: {dict(request.args)}")
        
        data = get_progress(task_id)
        current_app.logger.info(f"Download request for task {task_id}. Progress data: {data}")
        
        if not data:
            current_app.logger.error(f"Task {task_id} not found in progress data")
            return jsonify({"error": "Task not found"}), 404
            
        if data.get('status') != 'completed' and not data.get('status', '').startswith('Warning'):
            current_app.logger.error(f"Task {task_id} not completed. Status: {data.get('status')}")
            return jsonify({"error": "Files not ready"}), 400
            
        file_type = request.args.get('type', 'audio')  # Default to audio if not specified
        current_app.logger.info(f"Requested file type: {file_type}")
        
        # Log all the keys in the data for better debugging
        current_app.logger.info(f"Available keys in progress data: {list(data.keys())}")
        
        if file_type == 'audio' and 'audio_file' not in data:
            current_app.logger.error(f"Audio file not found in data for task {task_id}")
            return jsonify({"error": "Audio file not found"}), 404
        elif file_type == 'pdf' and 'pdf_file' not in data:
            current_app.logger.error(f"PDF file not found in data for task {task_id}")
            # If we're in 'Warning' state and PDF failed but audio succeeded, return helpful message
            if data.get('status', '').startswith('Warning') and file_type == 'pdf':
                return jsonify({"error": "PDF generation failed, but audio is available"}), 400
            return jsonify({"error": "PDF file not found"}), 404
            
        file_path = data['audio_file'] if file_type == 'audio' else data['pdf_file']
        current_app.logger.info(f"File path for {file_type}: {file_path}")
        
        # Verify file exists before sending
        if not os.path.exists(file_path):
            current_app.logger.error(f"File not found at path: {file_path}")
            # Log the output directory for debugging
            output_dir = current_app.config['OUTPUT_FOLDER']
            contents = os.listdir(output_dir) if os.path.exists(output_dir) else []
            current_app.logger.error(f"Contents of output directory: {contents}")
            return jsonify({"error": f"{file_type.upper()} file not found"}), 404

        # Get fresh file handle
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"{file_type.upper()} file not found")

        # Log file details
        file_size = os.path.getsize(file_path)
        current_app.logger.info(f"Sending file: {file_path}, size: {file_size} bytes")
        
        # Create a unique filename for the download to prevent caching issues
        original_filename = os.path.basename(file_path)
        download_filename = f"{os.path.splitext(original_filename)[0]}_{task_id[:6]}{os.path.splitext(original_filename)[1]}"
        current_app.logger.info(f"Using download filename: {download_filename}")

        response = send_file(
            file_path,
            mimetype='audio/mpeg' if file_type == 'audio' else 'application/pdf',
            as_attachment=True,
            download_name=download_filename,
            conditional=True  # Add conditional sending
        )
        
        # Add some cache control headers to prevent caching issues
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        # Log all response headers for debugging
        current_app.logger.info(f"Response headers: {dict(response.headers)}")
        
        # Only delete progress if both files have been downloaded
        if request.args.get('final') == 'true':
            delete_progress(task_id)
            current_app.logger.info(f"Cleaned up progress data for task {task_id}")
        
        current_app.logger.info(f"Successfully sent {file_type} file for task {task_id}")
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error downloading file for task {task_id}: {str(e)}")
        # Add traceback for better debugging
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@bp.route('/pricing')
def pricing():
    try:
        # Get the public key from app config
        stripe_public_key = current_app.config.get('STRIPE_PUBLIC_KEY')
        
        if not stripe_public_key:
            current_app.logger.error("Stripe public key not configured")
            
        return render_template('pricing.html',
            title='Pricing',
            stripe_public_key=stripe_public_key,
            credit_packages=CREDIT_PACKAGES)
    except Exception as e:
        current_app.logger.error(f"Stripe configuration error: {str(e)}")
        abort(500, "Payment system configuration error")

@bp.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    try:
        # Get Stripe API key directly from environment
        stripe_secret_key = os.environ.get('STRIPE_SECRET_KEY')
        
        if not stripe_secret_key:
            current_app.logger.error("Stripe secret key not found in environment")
            return "Stripe API key not configured", 500
            
        # Set the API key directly
        stripe.api_key = stripe_secret_key
        
        # Log for debugging
        current_app.logger.info(f"Using Stripe API key: {stripe_secret_key[:4]}...{stripe_secret_key[-4:]}")
        
        package_id = request.form.get('package_id')
        package = CREDIT_PACKAGES.get(package_id)
        
        if not package:
            abort(400, "Invalid package selected")
        
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
    # This is just a redirect page after successful payment
    # The actual credit update happens in the webhook
    flash('Payment successful! Your credits will be added shortly.', 'success')
    return render_template('payment_success.html')

@bp.route('/webhook', methods=['POST'])
def webhook():
    """Handle Stripe webhook events, particularly for successful payments"""
    try:
        # Get the webhook secret from environment
        webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
        
        # Get the event data
        payload = request.get_data(as_text=True)
        sig_header = request.headers.get('Stripe-Signature')
        
        # No verification if webhook secret is not set (not recommended for production)
        if webhook_secret:
            try:
                event = stripe.Webhook.construct_event(
                    payload, sig_header, webhook_secret
                )
            except ValueError as e:
                # Invalid payload
                current_app.logger.error(f"Webhook error: {str(e)}")
                return jsonify(error=str(e)), 400
            except stripe.error.SignatureVerificationError as e:
                # Invalid signature
                current_app.logger.error(f"Webhook signature verification failed: {str(e)}")
                return jsonify(error=str(e)), 400
        else:
            # If no webhook secret is set, parse the event data directly (not secure)
            # This should only be used for development/testing
            current_app.logger.warning("No webhook secret set - using insecure event parsing")
            data = json.loads(payload)
            event = stripe.Event.construct_from(data, stripe.api_key)
        
        # Set the Stripe API key
        stripe_secret_key = os.environ.get('STRIPE_SECRET_KEY')
        if not stripe_secret_key:
            current_app.logger.error("Stripe secret key not found in environment")
            return jsonify(error="Stripe API key not configured"), 500
        stripe.api_key = stripe_secret_key
        
        # Handle the event
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            
            # Log the session for debugging
            current_app.logger.info(f"Processing completed checkout session: {session.id}")
            
            # Get the user ID and credits from metadata
            user_id = session.get('metadata', {}).get('user_id')
            credits_to_add = session.get('metadata', {}).get('credits')
            
            if not user_id or not credits_to_add:
                current_app.logger.error("Missing user_id or credits in session metadata")
                return jsonify(error="Missing metadata"), 400
            
            try:
                # Convert to proper types
                user_id = int(user_id)
                credits_to_add = int(credits_to_add)
                
                # Update the user's credits
                with current_app.app_context():
                    user = User.query.get(user_id)
                    if user:
                        user.credits += credits_to_add
                        db.session.commit()
                        current_app.logger.info(f"Added {credits_to_add} credits to user {user_id}")
                    else:
                        current_app.logger.error(f"User {user_id} not found")
                        return jsonify(error=f"User {user_id} not found"), 404
            except Exception as e:
                current_app.logger.error(f"Error updating user credits: {str(e)}")
                return jsonify(error=str(e)), 500
        
        return jsonify(success=True)
    except Exception as e:
        current_app.logger.error(f"Webhook error: {str(e)}")
        return jsonify(error=str(e)), 500

@bp.route('/terms')
def terms():
    return render_template('terms.html')

@bp.route('/clear-users', methods=['GET', 'POST'])
@login_required
def clear_users():
    """Admin route to clear all users (development only)"""
    # Only allow in development mode and for admin users
    if not (os.environ.get('FLASK_ENV') == 'development' or current_user.email == 'admin@example.com'):
        abort(403, "Unauthorized access")
    
    if request.method == 'POST':
        confirmation = request.form.get('confirmation')
        if confirmation == 'DELETE_ALL_USERS':
            try:
                # Delete all users except the current one
                User.query.filter(User.id != current_user.id).delete()
                db.session.commit()
                flash('All users except your account have been deleted.', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error deleting users: {str(e)}")
                flash(f'Error deleting users: {str(e)}', 'error')
        else:
            flash('Incorrect confirmation text. Users were not deleted.', 'error')
    
    # Count users
    user_count = User.query.count()
    return render_template('admin/clear_users.html', user_count=user_count)

@bp.route('/dashboard')
@login_required
def dashboard():
    """User dashboard showing credits and transaction history"""
    return render_template('dashboard.html', 
                          user=current_user,
                          credit_packages=CREDIT_PACKAGES)

@bp.route('/admin/users')
@login_required
def admin_users():
    """Admin route to view all registered users"""
    # Simple security check - only allow admin or in development mode
    if not (os.environ.get('FLASK_ENV') == 'development' or current_user.email == 'admin@example.com'):
        abort(403, "Unauthorized access")
        
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@bp.route('/downloads/<task_id>')
@login_required
def download_page(task_id):
    """
    Display a page with direct download links when automatic download doesn't work
    """
    try:
        data = get_progress(task_id)
        current_app.logger.info(f"Download page request for task {task_id}. Progress data: {data}")
        
        if not data:
            flash("Task not found or has expired", "error")
            return redirect(url_for('main.index'))
            
        if data.get('status') != 'completed' and not data.get('status', '').startswith('Warning'):
            flash("Files are still being processed. Please wait until they're ready.", "warning")
            return redirect(url_for('main.index'))
        
        # Prepare download links
        download_links = {}
        
        if 'audio_file' in data:
            audio_path = data['audio_file']
            if os.path.exists(audio_path):
                download_links['audio'] = {
                    'url': url_for('main.download', task_id=task_id, type='audio', final='false', t=int(datetime.now().timestamp())),
                    'filename': os.path.basename(audio_path)
                }
        
        if 'pdf_file' in data:
            pdf_path = data['pdf_file']
            if os.path.exists(pdf_path):
                download_links['pdf'] = {
                    'url': url_for('main.download', task_id=task_id, type='pdf', final='true', t=int(datetime.now().timestamp())),
                    'filename': os.path.basename(pdf_path)
                }
                
        if not download_links:
            flash("No files are available for download", "error")
            return redirect(url_for('main.index'))
            
        return render_template('downloads.html', 
                               task_id=task_id, 
                               download_links=download_links,
                               status=data.get('status'))
                               
    except Exception as e:
        current_app.logger.error(f"Error generating download page for task {task_id}: {str(e)}")
        flash("An error occurred. Please try again.", "error")
        return redirect(url_for('main.index'))