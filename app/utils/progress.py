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
        # Ensure we're in an app context
        if not has_app_context():
            logger.info("No application context found. Creating a new app context.")
            from app import create_app
            app = create_app()
            with app.app_context():
                return _set_progress_internal(task_id, data)
        else:
            # Always save to file first as a reliable backup
            _save_progress_to_file(task_id, data)
            # Then try to save to database
            return _set_progress_internal(task_id, data)
    except Exception as e:
        logger.error(f"Error setting progress: {str(e)}")
        traceback.print_exc()
        # Try file-based fallback
        return _save_progress_to_file(task_id, data)

def _set_progress_internal(task_id, data):
    """Internal function to set progress with proper error handling"""
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
                logger.error(f"Max retries reached for database save. Falling back to file storage.")
                # Always ensure we fall back to file storage
                return _save_progress_to_file(task_id, data)

def get_progress(task_id):
    """Get progress data from database with file fallback"""
    try:
        # Try to load from file first for reliability
        file_data = _load_progress_from_file(task_id)
        
        # Ensure we're in an app context for DB access
        if not has_app_context():
            logger.info("No application context found. Creating a new app context.")
            from app import create_app
            app = create_app()
            with app.app_context():
                db_data = _get_progress_internal(task_id)
        else:
            db_data = _get_progress_internal(task_id)
        
        # Prefer DB data if available, otherwise use file data
        if db_data:
            return db_data
        
        if file_data:
            logger.info(f"Using file-based progress data for task {task_id}")
            return file_data
            
        logger.warning(f"No progress data found for task {task_id} in database or file storage")
        return None
    except Exception as e:
        logger.error(f"Error getting progress: {str(e)}")
        traceback.print_exc()
        # Fall back to file storage as last resort
        return _load_progress_from_file(task_id)

def _get_progress_internal(task_id):
    """Internal function to get progress with proper error handling"""
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
                logger.error(f"Max retries reached for database query. Falling back to file storage.")
                break
                
            time.sleep(0.5)  # Brief pause before retry
    
    # After max retries or on failure, fall back to file
    return None

def delete_progress(task_id):
    """Delete progress data from database with file fallback"""
    try:
        # Always delete file backup to ensure cleanup
        _delete_progress_file(task_id)
        
        # Ensure we're in an app context
        if not has_app_context():
            logger.info("No application context found. Creating a new app context.")
            from app import create_app
            app = create_app()
            with app.app_context():
                return _delete_progress_internal(task_id)
        else:
            return _delete_progress_internal(task_id)
    except Exception as e:
        logger.error(f"Error deleting progress: {str(e)}")
        traceback.print_exc()
        # Try file-based fallback
        return _delete_progress_file(task_id)

def _delete_progress_internal(task_id):
    """Internal function to delete progress with proper error handling"""
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
        # Get existing data
        data = get_progress(task_id) or {}
        
        # For debugging, log what we're updating
        if status is not None or progress is not None or error is not None:
            logger.info(f"Updating task {task_id}: status={status}, progress={progress}, error={error}")
        
        # Update fields
        if status is not None:
            data['status'] = status
        if progress is not None:
            data['progress'] = progress
        if error is not None:
            data['error'] = error
            
        # Update any additional fields
        for key, value in kwargs.items():
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