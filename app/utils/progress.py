import redis
import json
import os

# Initialize Redis client
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client = redis.from_url(redis_url)

def set_progress(task_id, data):
    """Store progress data in Redis"""
    redis_client.setex(f"progress:{task_id}", 3600, json.dumps(data))  # Expires in 1 hour

def get_progress(task_id):
    """Get progress data from Redis"""
    data = redis_client.get(f"progress:{task_id}")
    return json.loads(data) if data else None

def delete_progress(task_id):
    """Delete progress data from Redis"""
    redis_client.delete(f"progress:{task_id}")

def update_progress(task_id, status=None, progress=None, error=None, **kwargs):
    """Update progress data in Redis"""
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