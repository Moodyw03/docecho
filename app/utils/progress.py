import json
from app.extensions import db
from app.models.task_progress import TaskProgress
from datetime import datetime, timedelta
from flask import current_app
import traceback
import os
import time

# File-based fallback for when database operations fail
def _get_progress_file_path(task_id):
    """Get the file path for storing progress data"""
    try:
        if current_app:
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
        print(f"Error getting progress file path: {str(e)}")
        # Ultimate fallback
        return f"/tmp/docecho_progress_{task_id}.json"

def _save_progress_to_file(task_id, data):
    """Save progress data to a file"""
    try:
        file_path = _get_progress_file_path(task_id)
        
        # Add expiration time (1 hour from now)
        file_data = {
            'data': data,
            'expires_at': (datetime.utcnow() + timedelta(hours=1)).timestamp()
        }
        
        with open(file_path, 'w') as f:
            json.dump(file_data, f)
            
        print(f"Progress data saved to file for task {task_id}")
        return True
    except Exception as e:
        print(f"Error saving progress to file: {str(e)}")
        traceback.print_exc()
        return False

def _load_progress_from_file(task_id):
    """Load progress data from a file"""
    try:
        file_path = _get_progress_file_path(task_id)
        
        if not os.path.exists(file_path):
            print(f"No progress file found for task {task_id}")
            return None
            
        with open(file_path, 'r') as f:
            file_data = json.load(f)
            
        # Check if expired
        expires_at = datetime.fromtimestamp(file_data['expires_at'])
        if datetime.utcnow() > expires_at:
            print(f"Progress data for task {task_id} has expired")
            os.remove(file_path)  # Clean up expired file
            return None
            
        return file_data['data']
    except Exception as e:
        print(f"Error loading progress from file: {str(e)}")
        traceback.print_exc()
        return None

def _delete_progress_file(task_id):
    """Delete progress file"""
    try:
        file_path = _get_progress_file_path(task_id)
        
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Progress file deleted for task {task_id}")
            return True
            
        return False
    except Exception as e:
        print(f"Error deleting progress file: {str(e)}")
        traceback.print_exc()
        return False

def set_progress(task_id, data):
    """Store progress data in database with file fallback"""
    try:
        # Ensure we're in an app context
        if not current_app:
            print("No application context found. Creating a new app context.")
            from app import create_app
            app = create_app()
            with app.app_context():
                return _set_progress_internal(task_id, data)
        else:
            return _set_progress_internal(task_id, data)
    except Exception as e:
        print(f"Error setting progress: {str(e)}")
        traceback.print_exc()
        # Try file-based fallback
        return _save_progress_to_file(task_id, data)

def _set_progress_internal(task_id, data):
    """Internal function to set progress with proper error handling"""
    try:
        # Use the existing session with proper context management
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
            db.session.add(task)
        
        # Commit changes
        db.session.commit()
        print(f"Progress data saved for task {task_id}")
        return True
    except Exception as e:
        try:
            db.session.rollback()
        except:
            pass
        print(f"Error in _set_progress_internal: {str(e)}")
        traceback.print_exc()
        # Try file-based fallback
        return _save_progress_to_file(task_id, data)

def get_progress(task_id):
    """Get progress data from database with file fallback"""
    try:
        # Ensure we're in an app context
        if not current_app:
            print("No application context found. Creating a new app context.")
            from app import create_app
            app = create_app()
            with app.app_context():
                return _get_progress_internal(task_id)
        else:
            return _get_progress_internal(task_id)
    except Exception as e:
        print(f"Error getting progress: {str(e)}")
        traceback.print_exc()
        # Try file-based fallback
        return _load_progress_from_file(task_id)

def _get_progress_internal(task_id):
    """Internal function to get progress with proper error handling"""
    try:
        # Use filter_by instead of get for more explicit querying
        task = TaskProgress.query.filter_by(task_id=task_id).first()
        
        if task and not task.is_expired:
            result = json.loads(task.data)
            return result
        
        print(f"No valid progress data found for task {task_id}")
        # Try file-based fallback
        return _load_progress_from_file(task_id)
    except Exception as e:
        print(f"Error in _get_progress_internal: {str(e)}")
        traceback.print_exc()
        # Try file-based fallback
        return _load_progress_from_file(task_id)

def delete_progress(task_id):
    """Delete progress data from database with file fallback"""
    try:
        # Ensure we're in an app context
        if not current_app:
            print("No application context found. Creating a new app context.")
            from app import create_app
            app = create_app()
            with app.app_context():
                return _delete_progress_internal(task_id)
        else:
            return _delete_progress_internal(task_id)
    except Exception as e:
        print(f"Error deleting progress: {str(e)}")
        traceback.print_exc()
        # Try file-based fallback
        return _delete_progress_file(task_id)

def _delete_progress_internal(task_id):
    """Internal function to delete progress with proper error handling"""
    try:
        # Use the existing session with proper context management
        task = TaskProgress.query.filter_by(task_id=task_id).first()
        
        if task:
            db.session.delete(task)
            db.session.commit()
            print(f"Progress data deleted for task {task_id}")
            # Also delete any file-based backup
            _delete_progress_file(task_id)
            return True
        
        print(f"No progress data found to delete for task {task_id}")
        # Try file-based fallback
        return _delete_progress_file(task_id)
    except Exception as e:
        print(f"Error in _delete_progress_internal: {str(e)}")
        traceback.print_exc()
        # Try file-based fallback
        return _delete_progress_file(task_id)

def update_progress(task_id, status=None, progress=None, error=None, **kwargs):
    """Update progress data in database"""
    try:
        # Get existing data
        data = get_progress(task_id) or {}
        
        # Update fields
        if status is not None:
            data['status'] = status
        if progress is not None:
            data['progress'] = progress
        if error is not None:
            data['error'] = error
            
        # Update any additional fields
        data.update(kwargs)
        
        # Save updated data
        return set_progress(task_id, data)
    except Exception as e:
        print(f"Error updating progress: {str(e)}")
        traceback.print_exc()
        # Don't re-raise to avoid breaking background tasks 