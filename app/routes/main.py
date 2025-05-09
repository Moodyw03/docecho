from flask import Blueprint, render_template, request, jsonify, send_file, url_for, redirect, flash, current_app, abort
from flask_login import login_required, current_user
from app.models.user import User
from app import db
from app.utils.progress import get_progress, update_progress, delete_progress
import os
import uuid
import threading
from app.utils.pdf_processor import process_pdf, language_map
import stripe
from werkzeug.utils import secure_filename
import copy
import json
from datetime import datetime, timezone
from app.utils.redis import get_redis
import shutil
import logging
from io import BytesIO # Import BytesIO

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
            audio_speed = float(request.form.get("audio_speed", "1.0"))
            
            # Check if this language only supports audio
            lang_details = language_map.get(voice, {})
            if lang_details.get("audio_only", False) and output_format in ["pdf", "both"]:
                current_app.logger.info(f"Language {voice} only supports audio output. Overriding format {output_format} to 'audio'")
                output_format = "audio"
            
            # Calculate required credits
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
            task = process_pdf.delay(
                file_content=pdf_content,
                filename=safe_filename,
                voice={'language': voice},
                output_format=output_format,
                user_id=user_id,
                audio_speed=audio_speed
            )
            return jsonify({'task_id': task.id, 'status': 'processing'}), 202
            
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
            current_app.logger.info(f"[{task_id}] Data returned by get_progress: {data}")  # Log the data here
            
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
    """Download a processed file via Redis or S3 redirect with improved robustness"""
    logger = logging.getLogger(__name__)
    logger.info(f"Download request received for task {task_id}, file type: {file_type}")
    
    try:
        # 1. First try to get progress data 
        progress_data = get_progress(task_id)
        
        # If progress data exists and task is not completed, let's wait a bit
        if progress_data and progress_data.get('status') not in ['completed', 'Warning']:
            # Check how far along the task is
            progress = progress_data.get('progress', 0)
            status = progress_data.get('status', 'processing')
            
            # If it's in the final stages, give it a bit more time
            if status in ['combining_audio', 'generating_audio'] or progress >= 80:
                logger.info(f"[{task_id}] Task is in final stages ({status}, {progress}%), waiting briefly")
                # Wait up to 3 seconds for possible completion
                import time
                max_wait_time = 3.0  # seconds
                wait_increment = 0.5  # check every 0.5 seconds
                wait_time = 0
                
                while wait_time < max_wait_time:
                    time.sleep(wait_increment)
                    wait_time += wait_increment
                    # Check progress again
                    updated_progress = get_progress(task_id)
                    if updated_progress and updated_progress.get('status') == 'completed':
                        logger.info(f"[{task_id}] Task completed during wait period!")
                        progress_data = updated_progress
                        break
        
        # Even if the task is not completed according to progress data, we'll try to get the file anyway
        # The file might already be in Redis or Storage but the progress update is delayed
        
        # 2. Check for Remote S3 URL first
        if progress_data:
            remote_urls = progress_data.get('remote_urls', {})
            remote_url = remote_urls.get(file_type)
            # Fallback check for older keys if needed
            if not remote_url:
                remote_url = progress_data.get(f'remote_{file_type}_url') or progress_data.get('remote_file_url')
                
            if remote_url:
                logger.info(f"[{task_id}] Found remote URL for {file_type}: {remote_url}. Redirecting.")
                return redirect(remote_url)
            else:
                logger.info(f"[{task_id}] No remote URL found for {file_type} in progress data.")
        else:
            logger.warning(f"[{task_id}] No progress data found, will try direct Redis access")
        
        # 3. If no S3 URL, try getting content from Redis
        logger.info(f"[{task_id}] Attempting Redis fetch for type: {file_type}")
        redis_client = get_redis()
        content_key = f"file_content:{task_id}:{file_type}"
        logger.info(f"[{task_id}] Constructed Redis key: {content_key}")
        file_content = None
        try:
            file_content = redis_client.get(content_key)
            if file_content:
                logger.info(f"[{task_id}] Successfully retrieved {len(file_content)} bytes from Redis key {content_key}")
            else:
                logger.warning(f"[{task_id}] Redis key {content_key} returned None.")
        except Exception as e:
            logger.error(f"[{task_id}] Error accessing Redis key {content_key}: {str(e)}")
            file_content = None

        if file_content:
            # Determine filename and mimetype
            file_extension = 'mp3' if file_type == 'audio' else ('pdf' if file_type == 'pdf' else 'txt')
            download_filename = f"docecho_{task_id}.{file_extension}"
            mimetype = 'audio/mpeg' if file_type == 'audio' else ('application/pdf' if file_type == 'pdf' else 'text/plain')
            
            logger.info(f"[{task_id}] Sending file from Redis content as {download_filename} with mimetype {mimetype}")

            # Send the file content from memory
            response = send_file(
                BytesIO(file_content), 
                as_attachment=True,
                download_name=download_filename,
                mimetype=mimetype
            )
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            
            return response
        
        # 4. If no direct file content found, let's check if we should do a waiting page or error
        if progress_data:
            status = progress_data.get('status', '')
            progress = progress_data.get('progress', 0)
            
            if status == 'completed':
                # This shouldn't happen - no file found but status is completed
                logger.error(f"[{task_id}] Task status is 'completed' but file not found!")
                flash("File processing completed but file not found. Please try again.", "error")
            elif progress >= 50:
                # File is being processed, show waiting page
                logger.info(f"[{task_id}] File is still processing (progress: {progress}%), showing wait page")
                # Send a special page that auto-refreshes
                return render_template('waiting.html', 
                                      task_id=task_id, 
                                      file_type=file_type, 
                                      progress=progress,
                                      status=status)
            else:
                logger.error(f"[{task_id}] File processing not far enough along (progress: {progress}%)")
                flash("File is still being processed. Please wait and try again in a few moments.", "warning")
        else:
            logger.error(f"[{task_id}] File content not found and no progress data available.")
            flash("File processing information not found. Please try generating the file again.", "error")
        
        return redirect(url_for('main.index'))

    except Exception as e:
        task_id_str = f"[{task_id}] " if 'task_id' in locals() else ""
        logger.exception(f"{task_id_str}Error processing download request: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        flash("An error occurred processing your download request. Please try again.", "error")
        return redirect(url_for('main.index'))

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

@bp.route('/test-pdf/<language_code>', methods=['GET'])
@login_required
def test_pdf_rendering(language_code):
    """
    Test route for PDF rendering in different languages
    This is only for admin/testing purposes
    """
    # Only allow admins or in development mode
    if not (current_user.is_admin or current_app.config.get('FLASK_ENV') == 'development'):
        abort(403)
    
    try:
        from app.utils.pdf_processor import create_translated_pdf
        import tempfile
        import os
        from flask import send_file
        
        # Sample text for testing
        sample_texts = {
            # Only including supported languages
            'en': """Welcome to the DocEcho app.
This text is an example of how English is displayed.
We hope the text is displayed correctly.""",
            'fr': """Bienvenue dans l'application DocEcho.
Ce texte est un exemple de la façon dont le français est affiché.
Nous espérons que le texte s'affiche correctement.""",
            'es': """Bienvenido a la aplicación DocEcho.
Este texto es un ejemplo de cómo se muestra el español.
Esperamos que el texto se muestre correctamente.""",
            'de': """Willkommen bei der DocEcho-App.
Dieser Text ist ein Beispiel dafür, wie Deutsch angezeigt wird.
Wir hoffen, dass der Text korrekt angezeigt wird.""",
            'it': """Benvenuti nell'app DocEcho.
Questo testo è un esempio di come viene visualizzato l'italiano.
Speriamo che il testo venga visualizzato correttamente.""",
            'pt': """Bem-vindo ao aplicativo DocEcho.
Este texto é um exemplo de como o português é exibido.
Esperamos que o texto seja exibido corretamente.""",
            'ru': """Добро пожаловать в приложение DocEcho.
Этот текст является примером того, как отображается русский язык.
Мы надеемся, что текст отображается правильно.""",
            'nl': """Welkom bij de DocEcho-app.
Deze tekst is een voorbeeld van hoe Nederlands wordt weergegeven.
We hopen dat de tekst correct wordt weergegeven.""",
            'pl': """Witamy w aplikacji DocEcho.
Ten tekst jest przykładem wyświetlania języka polskiego.
Mamy nadzieję, że tekst jest wyświetlany poprawnie.""",
            'tr': """DocEcho uygulamasına hoş geldiniz.
Bu metin, Türkçe'nin nasıl görüntülendiğine dair bir örnektir.
Metnin doğru şekilde görüntülenmesini umuyoruz."""
        }
        
        # Default text if language not in sample list
        default_text = f"This is a test text for {language_code} language.\nWe are testing PDF rendering capabilities.\nThis should display correctly in most Latin-based scripts."
        
        # Get the appropriate text
        text = sample_texts.get(language_code, default_text)
        
        # Create a temporary file for the PDF
        fd, temp_path = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)
        
        # Generate PDF with the test text
        create_translated_pdf(text, temp_path, language_code=language_code)
        
        # Send the file to user
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=f"test_{language_code}.pdf",
            mimetype='application/pdf'
        )
    except Exception as e:
        current_app.logger.error(f"Error in test-pdf route: {str(e)}")
        return f"Error generating test PDF: {str(e)}", 500

@bp.route('/downloads')
@login_required
def downloads_page():
    """Show user's available downloads"""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
        
    # Get info about files available for this user
    user_id = current_user.id
    
    # Get the output directory from config
    output_dir = current_app.config.get('OUTPUT_FOLDER', '.')
    
    # This will store file information to display
    available_files = []
    
    try:
        # Check for files in the output directory
        if os.path.exists(output_dir):
            files = os.listdir(output_dir)
            
            # Filter files for this user (using a naming convention or metadata)
            for filename in files:
                # Your logic to determine if file belongs to user
                # For example, check for user_id in filename or metadata
                # This is a placeholder logic - adapt to your actual file naming convention
                if f"user_{user_id}_" in filename or f"_{user_id}_" in filename:
                    file_path = os.path.join(output_dir, filename)
                    file_info = {
                        'name': filename,
                        'size': os.path.getsize(file_path),
                        'created': datetime.fromtimestamp(os.path.getctime(file_path)).strftime('%Y-%m-%d %H:%M'),
                        'url': url_for('main.download_file', task_id=filename.split('.')[0])
                    }
                    available_files.append(file_info)
    except Exception as e:
        current_app.logger.error(f"Error listing files: {str(e)}")
    
    return render_template('downloads.html', 
                          files=available_files, 
                          page_title='Your Downloads',
                          user=current_user)