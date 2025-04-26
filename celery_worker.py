import os
from celery import Celery
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Celery
def make_celery():
    # Get Redis URL from environment or use default
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Create Celery instance
    celery = Celery(
        'app',
        broker=redis_url,
        backend=redis_url,
        include=['app.utils.pdf_processor']
    )
    
    # Optional Celery configuration
    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        worker_max_tasks_per_child=1,  # Restart worker after each task
        worker_prefetch_multiplier=1,  # Only prefetch one task at a time
        task_acks_late=True,  # Only acknowledge task after it's completed
        task_reject_on_worker_lost=True,  # Reject task if worker dies
        task_track_started=True,  # Track when task starts
        task_time_limit=3600,  # 1 hour time limit
        task_soft_time_limit=3300,  # 55 minutes soft time limit
    )
    
    return celery

# Create Celery app
celery = make_celery()

# This allows for direct invocation of this script (useful for development)
if __name__ == '__main__':
    celery.start() 