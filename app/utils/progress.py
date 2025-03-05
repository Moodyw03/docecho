import json
from app.extensions import db
from app.models.task_progress import TaskProgress
from datetime import datetime, timedelta
from flask import current_app
import traceback

def set_progress(task_id, data):
    """Store progress data in database"""
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
        # Don't re-raise to avoid breaking background tasks

def _set_progress_internal(task_id, data):
    """Internal function to set progress with proper error handling"""
    try:
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
        if 'db' in locals() and hasattr(db, 'session'):
            db.session.rollback()
        print(f"Error in _set_progress_internal: {str(e)}")
        traceback.print_exc()
        return False

def get_progress(task_id):
    """Get progress data from database"""
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
        return None

def _get_progress_internal(task_id):
    """Internal function to get progress with proper error handling"""
    try:
        # Use filter_by instead of get for more explicit querying
        task = TaskProgress.query.filter_by(task_id=task_id).first()
        
        if task and not task.is_expired:
            return json.loads(task.data)
        
        print(f"No valid progress data found for task {task_id}")
        return None
    except Exception as e:
        print(f"Error in _get_progress_internal: {str(e)}")
        traceback.print_exc()
        return None

def delete_progress(task_id):
    """Delete progress data from database"""
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
        # Don't re-raise to avoid breaking background tasks

def _delete_progress_internal(task_id):
    """Internal function to delete progress with proper error handling"""
    try:
        task = TaskProgress.query.filter_by(task_id=task_id).first()
        
        if task:
            db.session.delete(task)
            db.session.commit()
            print(f"Progress data deleted for task {task_id}")
            return True
        
        print(f"No progress data found to delete for task {task_id}")
        return False
    except Exception as e:
        if 'db' in locals() and hasattr(db, 'session'):
            db.session.rollback()
        print(f"Error in _delete_progress_internal: {str(e)}")
        traceback.print_exc()
        return False

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