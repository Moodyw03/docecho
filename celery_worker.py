import os
from celery import Celery

# Read broker URL from environment variable, fallback for local dev
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Define Celery instance directly
celery = Celery(
    'docecho', # Use a consistent name, e.g., your app name
    broker=redis_url,
    backend=redis_url, # Using Redis as result backend is common
    include=['app.utils.pdf_processor'] # Tell Celery where to find tasks
)

# Optional: Set some default configurations if needed
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# Define a base task that sets up Flask app context *when the task runs*
class ContextTask(celery.Task):
    abstract = True
    _flask_app = None # Cache app instance

    @property
    def flask_app(self):
        # Lazily create app instance only when needed by a task
        if self._flask_app is None:
            from app import create_app # Import here to avoid top-level circular import
            self._flask_app = create_app()
        return self._flask_app

    def __call__(self, *args, **kwargs):
        with self.flask_app.app_context():
            return self.run(*args, **kwargs)

# Set the base class for tasks
celery.Task = ContextTask 