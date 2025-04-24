import json
from app.extensions import db, get_db
from app.models.task_progress import TaskProgress
from datetime import datetime, timedelta
from flask import current_app, has_app_context
import traceback
import os
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('progress_tracker')

# File-based fallback for when database operations fail
def _get_progress_file_path(task_id):
    """Get the file path for storing progress data"""
    try:
        if has_app_context():
            app_root = current_app.root_path
        else:
            # Fallback if no app context
            from app import create_app
            app = create_app()
            with app.app_context():
                app_root = app.root_path
                
        progress_dir = os.path.join(app_root, 'static', 'progress')
        os.makedirs(progress_dir, exist_ok=True)
        return os.path.join(progress_dir, f"{task_id}.json")
    except Exception as e:
        logger.error(f"Error getting progress file path: {str(e)}")
        # Ultimate fallback
        fallback_dir = "/tmp/docecho_progress"
        os.makedirs(fallback_dir, exist_ok=True)
        return os.path.join(fallback_dir, f"{task_id}.json")

def _save_progress_to_file(task_id, data):
    """Save progress data to a file"""
    try:
        file_path = _get_progress_file_path(task_id)
        
        # Add expiration time (1 hour from now)
        file_data = {
            'data': data,
            'expires_at': (datetime.utcnow() + timedelta(hours=1)).timestamp()
        }
        
        # Create a temporary file first, then rename to avoid corruption
        temp_file_path = file_path + ".tmp"
        with open(temp_file_path, 'w') as f:
            json.dump(file_data, f)
            f.flush()
            os.fsync(f.fileno())
        
        # Atomic rename
        os.replace(temp_file_path, file_path)
            
        logger.info(f"Progress data saved to file for task {task_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving progress to file: {str(e)}")
        traceback.print_exc()
        return False

def _load_progress_from_file(task_id):
    """Load progress data from a file"""
    try:
        file_path = _get_progress_file_path(task_id)
        
        if not os.path.exists(file_path):
            logger.debug(f"No progress file found for task {task_id}")
            return None
            
        try:
            with open(file_path, 'r') as f:
                file_data = json.load(f)
        except json.JSONDecodeError:
            logger.error(f"Corrupted progress file for task {task_id}, removing")
            os.remove(file_path)
            return None
            
        # Check if expired
        expires_at = datetime.fromtimestamp(file_data['expires_at'])
        if datetime.utcnow() > expires_at:
            logger.info(f"Progress data for task {task_id} has expired")
            os.remove(file_path)  # Clean up expired file
            return None
            
        return file_data['data']
    except Exception as e:
        logger.error(f"Error loading progress from file: {str(e)}")
        traceback.print_exc()
        return None

def _delete_progress_file(task_id):
    """Delete progress file"""
    try:
        file_path = _get_progress_file_path(task_id)
        
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Progress file deleted for task {task_id}")
            return True
            
        return False
    except Exception as e:
        logger.error(f"Error deleting progress file: {str(e)}")
        traceback.print_exc()
        return False

def set_progress(task_id, data):
    """Store progress data in database with file fallback"""
    try:
        # Ensure we're in an app context (caller's responsibility)
        if not has_app_context():
            logger.error(f"[{task_id}] set_progress called without active app context!")
            # Attempt file save as absolute fallback if no context
            return _save_progress_to_file(task_id, data)

        # Always save to file first as a reliable backup? Or save to DB first?
        # Let's try DB first, then file on DB error.
        db_success = _set_progress_internal(task_id, data)
        if not db_success:
            # If DB failed, ensure file save happens
             logger.warning(f"[{task_id}] DB save failed, ensuring file save.")
             return _save_progress_to_file(task_id, data)
        return True # DB save was successful

    except Exception as e:
        logger.error(f"[{task_id}] Error setting progress: {str(e)}", exc_info=True)
        # Try file-based fallback on any unexpected error
        return _save_progress_to_file(task_id, data)

def _set_progress_internal(task_id, data):
    """Internal function to set progress with proper error handling. Assumes app context."""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Get the proper database instance
            database = get_db()
            
            # Check if task exists
            task = TaskProgress.query.filter_by(task_id=task_id).first()
            
            if task:
                task.data = json.dumps(data)
                task.expires_at = datetime.utcnow() + timedelta(hours=1)
            else:
                # Create new task
                task = TaskProgress(
                    task_id=task_id,
                    data=json.dumps(data),
                    expires_at=datetime.utcnow() + timedelta(hours=1)
                )
                database.session.add(task)
            
            # Commit changes
            database.session.commit()
            logger.info(f"Progress data saved to database for task {task_id}")
            # Attempt to clean up the fallback file if DB save succeeds
            _delete_progress_file(task_id)
            return True
        except Exception as e:
            retry_count += 1
            logger.warning(f"Database error on attempt {retry_count}/{max_retries}: {str(e)}")
            try:
                database.session.rollback()
                time.sleep(0.5)  # Brief pause before retry
            except:
                pass
            
            if retry_count >= max_retries:
                logger.error(f"[{task_id}] Max retries reached for database save. DB save failed.")
                # Return False to indicate DB failure, set_progress will handle file fallback
                return False
    return False # Should not be reached ideally, but indicates failure

def get_progress(task_id):
    """Get progress data from database with file fallback"""
    db_data = None
    try:
        # Try removing session *before* attempting read
        if has_app_context():
            try:
                db.session.remove() 
                logger.debug(f"[{task_id}] Explicitly removed session before get_progress DB read.")
            except Exception as remove_err:
                 logger.warning(f"[{task_id}] Error removing session in get_progress: {remove_err}")
        
        # Ensure we're in an app context (caller's responsibility)
        if not has_app_context():
             logger.error(f"[{task_id}] get_progress called without active app context!")
             # Try loading from file if no context
             return _load_progress_from_file(task_id)

        # Try database first
        db_data = _get_progress_internal(task_id)

        if db_data:
            # Successfully retrieved from DB
            return db_data

        # If DB failed or returned None, try loading from file
        logger.warning(f"[{task_id}] No data from DB, trying file fallback.")
        file_data = _load_progress_from_file(task_id)

        if file_data:
            logger.info(f"[{task_id}] Using file-based progress data for task {task_id}")
            return file_data

        # No data found in database or file storage, return a default initializing state
        # This is better than returning None and will prevent errors downstream
        logger.warning(f"[{task_id}] No progress data found for task {task_id} in database or file storage")
        return {
            'status': 'initializing',
            'progress': 0,
            'message': 'Task is still initializing...',
            'task_id': task_id
        }

    except Exception as e:
        logger.error(f"[{task_id}] Error getting progress: {str(e)}", exc_info=True)
        # Fall back to file storage as last resort on unexpected error
        file_data = _load_progress_from_file(task_id)
        if file_data:
            return file_data
        
        # If all else fails, return a default response
        return {
            'status': 'initializing',
            'progress': 0,
            'message': 'Error retrieving progress. Task may be restarting...',
            'task_id': task_id
        }

def _get_progress_internal(task_id):
    """Internal function to get progress with proper error handling. Assumes app context."""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Get the proper database instance
            database = get_db()
            
            # Use filter_by instead of get for more explicit querying
            task = TaskProgress.query.filter_by(task_id=task_id).first()
            
            if task and not task.is_expired:
                result = json.loads(task.data)
                return result
            
            logger.debug(f"No valid progress data found for task {task_id} in database")
            return None
        except Exception as e:
            retry_count += 1
            logger.warning(f"Database error on attempt {retry_count}/{max_retries}: {str(e)}")
            
            if retry_count >= max_retries:
                logger.error(f"[{task_id}] Max retries reached for database query. DB read failed.")
                # Return None, get_progress will handle file fallback
                return None

            time.sleep(0.5)  # Brief pause before retry
    
    # If loop finishes without returning (e.g., max retries hit), return None
    return None

def delete_progress(task_id):
    """Delete progress data from database and file"""
    db_deleted = False
    try:
        # Ensure we're in an app context (caller's responsibility)
        if not has_app_context():
            logger.error(f"[{task_id}] delete_progress called without active app context!")
            # Still attempt file deletion even if context is missing
        else:
             db_deleted = _delete_progress_internal(task_id)

        # Always attempt to delete file backup regardless of DB result or context
        file_deleted = _delete_progress_file(task_id)

        return db_deleted or file_deleted # Return true if either deletion succeeded

    except Exception as e:
        logger.error(f"[{task_id}] Error deleting progress: {str(e)}", exc_info=True)
        # Attempt file deletion on error
        return _delete_progress_file(task_id)

def _delete_progress_internal(task_id):
    """Internal function to delete progress from DB. Assumes app context."""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Get the proper database instance
            database = get_db()
            
            # Use the existing session with proper context management
            task = TaskProgress.query.filter_by(task_id=task_id).first()
            
            if task:
                database.session.delete(task)
                database.session.commit()
                logger.info(f"Progress data deleted from database for task {task_id}")
                # Also delete any file-based backup
                _delete_progress_file(task_id)
                return True
            
            logger.debug(f"No progress data found in database to delete for task {task_id}")
            return True
        except Exception as e:
            retry_count += 1
            logger.warning(f"Database error on attempt {retry_count}/{max_retries}: {str(e)}")
            
            try:
                database.session.rollback()
                time.sleep(0.5)  # Brief pause before retry
            except:
                pass
                
            if retry_count >= max_retries:
                logger.error(f"Max retries reached for database delete. Falling back to file deletion.")
                break
    
    # After max retries or on failure, fall back to file deletion
    return _delete_progress_file(task_id)

def update_progress(task_id, status=None, progress=None, error=None, **kwargs):
    """Update progress data in database"""
    try:
        # REMOVED: get_progress call here. We will construct the full data dict directly.
        # data = get_progress(task_id) or {}
        data = {}

        # For debugging, log what we're updating
        # (Ensure this call itself is within context if get_progress needs it)
        if status is not None or progress is not None or error is not None:
            logger.info(f"Updating task {task_id}: status={status}, progress={progress}, error={error}")
        
        # Update fields
        if status is not None:
            data['status'] = status
        if progress is not None:
            data['progress'] = progress
        if error is not None:
            data['error'] = error
            
        # Normalize file paths in kwargs to ensure consistent paths across environments
        for key, value in kwargs.items():
            # Handle audio_file and pdf_file paths specifically
            if key in ['audio_file', 'pdf_file'] and value:
                try:
                    if has_app_context():
                        # Check if we have an absolute path and convert to a consistent format
                        if os.path.isabs(value):
                            # Get the output folder from config
                            output_folder = current_app.config.get('OUTPUT_FOLDER')
                            
                            # Extract just the filename
                            filename = os.path.basename(value)
                            
                            # Store the output folder path + filename
                            normalized_path = os.path.join(output_folder, filename)
                            logger.info(f"Normalized path for {key}: {value} -> {normalized_path}")
                            data[key] = normalized_path
                        else:
                            # Already a relative path, store as is
                            data[key] = value
                    else:
                        # No app context, store path as is
                        data[key] = value
                except Exception as e:
                    logger.error(f"Error normalizing path for {key}: {str(e)}")
                    # Just store the original value if there's an error
                    data[key] = value
            else:
                # For other values, just store them as is
                data[key] = value
            
        # Add a timestamp for easier debugging
        data['updated_at'] = datetime.utcnow().isoformat()
        
        # Save updated data
        return set_progress(task_id, data)
    except Exception as e:
        logger.error(f"Error updating progress: {str(e)}")
        traceback.print_exc()
        # Don't re-raise to avoid breaking background tasks 
        return False 