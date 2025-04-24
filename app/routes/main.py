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
from datetime import datetime, timezone
from app.utils.redis import get_redis
import shutil
import logging

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

@bp.route('/download/<task_id>/<file_type>', methods=['GET'])
def download_file(task_id, file_type):
    """Download a processed file"""
    logger = logging.getLogger(__name__)
    logger.info(f"Download request received for task {task_id}, file type: {file_type}")
    logger.info(f"Request args: {request.args}")
    logger.info(f"Request headers: {dict(request.headers)}")

    try:
        # Get progress data to check if task is completed
        progress_data = get_progress(task_id)
        if not progress_data:
            logger.error(f"[{task_id}] Progress data not found.")
            abort(404, "Task not found or has expired.")

        logger.info(f"[{task_id}] Download request. Progress data: {progress_data}")
        logger.info(f"[{task_id}] Available keys in progress data: {list(progress_data.keys())}")
        logger.info(f"[{task_id}] Requested file type: {file_type}")

        status = progress_data.get('status', '')
        # Allow download even if PDF failed in 'both' mode
        if status.lower() != 'completed' and not status.startswith('Warning'):
            logger.error(f"[{task_id}] Task status is '{status}', not 'completed'.")
            abort(404, "Task processing not completed or failed.")

        output_folder = current_app.config['OUTPUT_FOLDER']
        file_path = None
        remote_url = None
        original_file_path_from_progress = None

        # --- Determine the expected file path and remote URL from progress data ---
        if file_type == 'audio':
            original_file_path_from_progress = progress_data.get('audio_file')
            remote_url = progress_data.get('remote_audio_url') or progress_data.get('remote_file_url') # Include generic remote_file_url
        elif file_type == 'pdf':
            original_file_path_from_progress = progress_data.get('pdf_file')
            remote_url = progress_data.get('remote_pdf_url') or progress_data.get('remote_file_url')
        else:
             logger.error(f"[{task_id}] Invalid file_type requested: {file_type}")
             abort(400, "Invalid file type requested.")

        logger.info(f"[{task_id}] Original file path from progress: {original_file_path_from_progress}")
        logger.info(f"[{task_id}] Remote URL from progress: {remote_url}")

        # --- Check for the file locally ---
        if original_file_path_from_progress:
            # 1. Check the exact path stored in progress data
            logger.info(f"[{task_id}] Checking original path: {original_file_path_from_progress}")
            if os.path.exists(original_file_path_from_progress) and os.path.isfile(original_file_path_from_progress):
                logger.info(f"[{task_id}] File found at original path: {original_file_path_from_progress}")
                file_path = original_file_path_from_progress
            else:
                logger.warning(f"[{task_id}] File NOT found at original path: {original_file_path_from_progress}")

                # 2. If original path fails, construct path using OUTPUT_FOLDER and filename
                filename = os.path.basename(original_file_path_from_progress)
                alternative_path = os.path.join(output_folder, filename)
                logger.info(f"[{task_id}] Checking alternative path: {alternative_path}")
                if os.path.exists(alternative_path) and os.path.isfile(alternative_path):
                    logger.info(f"[{task_id}] File found at alternative path: {alternative_path}")
                    file_path = alternative_path
                else:
                    logger.warning(f"[{task_id}] File NOT found at alternative path: {alternative_path}")
                    # 3. List directory contents for debugging if file still not found
                    try:
                        files_in_output = os.listdir(output_folder)
                        logger.info(f"[{task_id}] Files currently in output directory ({output_folder}): {files_in_output}")
                    except Exception as e:
                        logger.error(f"[{task_id}] Error listing output directory ({output_folder}): {str(e)}")

        # --- Fallback Mechanisms (if file not found locally) ---
        if not file_path:
            logger.warning(f"[{task_id}] File not found locally. Attempting fallbacks.")

            # 4. Try Redis fallback
            logger.info(f"[{task_id}] Attempting Redis fallback.")
            redis_client = get_redis()
            content_key = f"file_content:{task_id}:{file_type}"
            file_content = None
            try:
                 file_content = redis_client.get(content_key)
            except Exception as e:
                 logger.error(f"[{task_id}] Error accessing Redis key {content_key}: {str(e)}")

            if file_content:
                logger.info(f"[{task_id}] Retrieved file content from Redis (key: {content_key}).")
                # Try to write Redis content back to a consistent path for future requests
                # Use original filename if possible, otherwise generate one
                filename_for_redis_write = os.path.basename(original_file_path_from_progress) if original_file_path_from_progress else f"{task_id}_{file_type}.{'mp3' if file_type == 'audio' else 'pdf'}"
                redis_write_path = os.path.join(output_folder, filename_for_redis_write)
                try:
                    os.makedirs(os.path.dirname(redis_write_path), exist_ok=True)
                    with open(redis_write_path, 'wb') as f:
                        f.write(file_content)
                    logger.info(f"[{task_id}] Wrote Redis content to file: {redis_write_path}")
                    file_path = redis_write_path # Use the newly written file
                except Exception as e:
                    logger.error(f"[{task_id}] Error writing Redis content to file {redis_write_path}: {str(e)}")
                    # If write fails, we can't serve it directly, proceed to remote URL check
            else:
                logger.warning(f"[{task_id}] File content not found in Redis (key: {content_key}).")

            # 5. Try Remote URL fallback (only if Redis didn't yield a file_path)
            if not file_path and remote_url:
                logger.info(f"[{task_id}] No local file or Redis content. Redirecting to remote URL: {remote_url}")
                return redirect(remote_url)

            # 6. If all fallbacks fail, abort
            if not file_path:
                 logger.error(f"[{task_id}] File not found after checking all local paths, Redis, and remote URL.")
                 abort(404, f"File not found for task {task_id}.")

        # --- Send the file ---
        logger.info(f"[{task_id}] Proceeding to send file: {file_path}")
        # Generate a unique download filename to prevent caching issues (optional, but good practice)
        # original_filename = os.path.basename(file_path)
        # download_filename = f"{original_filename.split('.')[0]}_{uuid.uuid4().hex[:8]}.{original_filename.split('.')[-1]}"
        download_filename = os.path.basename(file_path) # Keep original name for simplicity now

        logger.info(f"[{task_id}] Sending file: {file_path} as {download_filename}")

        # Set response headers to prevent caching
        response = send_file(
            file_path,
            as_attachment=True,
            download_name=download_filename,
            mimetype='audio/mpeg' if file_type == 'audio' else 'application/pdf'
        )
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        # After successful download, clean up progress data if it's been more than 1 hour (optional)
        try:
            # Using updated_at field from progress data
            updated_at_str = progress_data.get('updated_at')
            if updated_at_str:
                 # Ensure timestamp is timezone-aware if needed, assuming UTC from isoformat
                updated_at = datetime.fromisoformat(updated_at_str)
                # Make timezone-aware for comparison if needed, assuming UTC
                if updated_at.tzinfo is None:
                     updated_at = updated_at.replace(tzinfo=timezone.utc)
                now_aware = datetime.now(timezone.utc)

                elapsed = (now_aware - updated_at).total_seconds()
                if elapsed > 3600:  # 1 hour
                    delete_progress(task_id)
                    logger.info(f"[{task_id}] Cleaned up expired progress data.")
        except Exception as e:
            logger.error(f"[{task_id}] Error cleaning up progress data: {str(e)}")

        return response

    except Exception as e:
        task_id_str = f"[{task_id}] " if 'task_id' in locals() else ""
        logger.exception(f"{task_id_str}Error processing download request: {str(e)}")
        # Use traceback for more detail in logs
        import traceback
        logger.error(traceback.format_exc())
        abort(500, f"Error processing download request: {str(e)}")

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
            
        # Check both capitalized and lowercased version of 'completed'
        status = data.get('status', '')
        if status.lower() != 'completed' and not status.startswith('Warning'):
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
                               status=status)
                               
    except Exception as e:
        current_app.logger.error(f"Error generating download page for task {task_id}: {str(e)}")
        flash("An error occurred. Please try again.", "error")
        return redirect(url_for('main.index'))

@bp.route('/direct-download/<task_id>/<file_type>')
@login_required
def direct_download(task_id, file_type):
    """
    A simplified direct download route without JavaScript redirection
    This is useful for debugging and when regular download mechanisms fail
    """
    try:
        current_app.logger.info(f"Direct download requested for task {task_id}, file type {file_type}")
        
        if file_type not in ['audio', 'pdf']:
            return "Invalid file type. Must be 'audio' or 'pdf'.", 400
            
        data = get_progress(task_id)
        if not data:
            return "Task not found. It may have expired.", 404
            
        # Check both capitalized and lowercased version of 'completed'
        status = data.get('status', '')
        if status.lower() != 'completed' and not status.startswith('Warning'):
            return f"Task not ready. Current status: {status}", 400
            
        file_key = f"{file_type}_file"
        if file_key not in data:
            return f"No {file_type} file available for this task.", 404
            
        original_file_path = data[file_key]
        current_app.logger.info(f"Original file path for {file_type}: {original_file_path}")
        
        # Try the original path first
        file_path = original_file_path
        
        # If the file doesn't exist at the original path, try finding it by filename in the output directory
        if not os.path.exists(file_path):
            current_app.logger.warning(f"File not found at original path: {file_path}")
            
            # Extract just the filename
            filename = os.path.basename(file_path)
            output_dir = current_app.config['OUTPUT_FOLDER']
            
            # Alternative path - look in the output directory
            alternative_path = os.path.join(output_dir, filename)
            current_app.logger.info(f"Trying alternative path: {alternative_path}")
            
            if os.path.exists(alternative_path):
                current_app.logger.info(f"File found at alternative path!")
                file_path = alternative_path
            else:
                # Try one more approach - list all files in the output directory and look for similar names
                try:
                    output_files = os.listdir(output_dir)
                    current_app.logger.info(f"Files in output directory: {output_files}")
                    
                    # Look for files with similar names (e.g., without specific path components)
                    filename_base = os.path.splitext(filename)[0]
                    for output_file in output_files:
                        if filename_base in output_file:
                            matching_path = os.path.join(output_dir, output_file)
                            current_app.logger.info(f"Found matching file: {matching_path}")
                            file_path = matching_path
                            break
                except Exception as e:
                    current_app.logger.error(f"Error listing output directory: {e}")
        
        if not os.path.exists(file_path):
            return f"File does not exist at path: {file_path}", 404
            
        original_filename = os.path.basename(file_path)
        download_name = f"{os.path.splitext(original_filename)[0]}_{task_id[:6]}{os.path.splitext(original_filename)[1]}"
        
        return send_file(
            file_path,
            mimetype='audio/mpeg' if file_type == 'audio' else 'application/pdf',
            as_attachment=True,
            download_name=download_name
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in direct download: {e}")
        return f"Error: {str(e)}", 500