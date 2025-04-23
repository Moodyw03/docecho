import os
from app import create_app
from celery import Celery

# Create Flask app instance to access config
flask_app = create_app()

# Configure Celery
celery = Celery(
    flask_app.import_name,
    broker=flask_app.config['CELERY_BROKER_URL'],
    backend=flask_app.config.get('CELERY_RESULT_BACKEND'), # Use .get() for optional backend
    include=['app.utils.pdf_processor'] # Add other task modules if needed
)
celery.conf.update(flask_app.config)

# Define a base task that sets up Flask app context
class ContextTask(celery.Task):
    abstract = True # Ensure this isn't registered as a task itself
    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return self.run(*args, **kwargs)

# Set the base task for all tasks
celery.Task = ContextTask 