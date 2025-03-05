import json
from app.extensions import db
from app.models.task_progress import TaskProgress
from datetime import datetime, timedelta

def set_progress(task_id, data):
    """Store progress data in database"""
    try:
        task = TaskProgress.query.get(task_id)
        if task:
            task.data = json.dumps(data)
            task.expires_at = datetime.utcnow() + timedelta(hours=1)
        else:
            task = TaskProgress(
                task_id=task_id,
                data=json.dumps(data),
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
        db.session.add(task)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error setting progress: {str(e)}")
        raise e

def get_progress(task_id):
    """Get progress data from database"""
    try:
        task = TaskProgress.query.get(task_id)
        if task and not task.is_expired:
            return json.loads(task.data)
        return None
    except Exception as e:
        print(f"Error getting progress: {str(e)}")
        return None

def delete_progress(task_id):
    """Delete progress data from database"""
    try:
        task = TaskProgress.query.get(task_id)
        if task:
            db.session.delete(task)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting progress: {str(e)}")
        raise e

def update_progress(task_id, status=None, progress=None, error=None, **kwargs):
    """Update progress data in database"""
    try:
        data = get_progress(task_id) or {}
        
        if status is not None:
            data['status'] = status
        if progress is not None:
            data['progress'] = progress
        if error is not None:
            data['error'] = error
            
        # Update any additional fields
        data.update(kwargs)
        
        set_progress(task_id, data)
    except Exception as e:
        print(f"Error updating progress: {str(e)}")
        # Don't re-raise to avoid breaking background tasks 