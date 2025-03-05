import json
from app.extensions import db
from app.models.task_progress import TaskProgress
from datetime import datetime, timedelta

def set_progress(task_id, data):
    """Store progress data in database"""
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

def get_progress(task_id):
    """Get progress data from database"""
    task = TaskProgress.query.get(task_id)
    if task and not task.is_expired:
        return json.loads(task.data)
    return None

def delete_progress(task_id):
    """Delete progress data from database"""
    task = TaskProgress.query.get(task_id)
    if task:
        db.session.delete(task)
        db.session.commit()

def update_progress(task_id, status=None, progress=None, error=None, **kwargs):
    """Update progress data in database"""
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