import os
from celery import Celery
from dotenv import load_dotenv
from app import create_app

# Load environment variables
load_dotenv()

# Create Flask app
flask_app = create_app()

# Configure Celery
def make_celery(app):
    # Get Redis URL from environment or use default
    broker_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    result_backend = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    # Initialize Celery
    celery_app = Celery(
        'docecho',
        broker=broker_url,
        backend=result_backend,
        include=['app.utils.pdf_processor']  # Include task modules here
    )
    
    # Optional Celery configuration
    celery_app.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        worker_prefetch_multiplier=1,  # Process tasks one at a time
        task_acks_late=True,  # Only acknowledge tasks after they're processed
        task_reject_on_worker_lost=True,  # Re-queue tasks if worker is lost
        broker_connection_retry_on_startup=True,  # Retry connecting to broker on startup
    )
    
    # Set Flask app context for tasks
    class ContextTask(celery_app.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery_app.Task = ContextTask
    return celery_app

# Create the Celery app
celery = make_celery(flask_app)

# This allows for direct invocation of this script (useful for development)
if __name__ == '__main__':
    celery.start() 