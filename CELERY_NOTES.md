# Celery Working Configuration

This file documents the working Celery setup with Redis for DocEcho.

## Configuration Details

The Celery worker is now working with Redis as the broker and result backend. Key components:

- Using Redis on localhost:6379
- Task handling for PDF processing
- Proper connection management for reliability

## Implementation

### celery_worker.py

```python
import os
from celery import Celery
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# Configure Celery
def make_celery():
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

    return celery_app

# Create the Celery app
celery = make_celery()

# This allows for direct invocation of this script (useful for development)
if __name__ == '__main__':
    celery.start()
```

## Worker Output

Successful worker startup:

```
-------------- celery@gabriels-MacBook-Pro.local v5.5.1 (immunity)
--- ***** -----
-- ******* ---- macOS-15.3.2-arm64-arm-64bit 2025-04-24 20:59:20
- *** --- * ---
- ** ---------- [config]
- ** ---------- .> app:         docecho:0x102dd4fd0
- ** ---------- .> transport:   redis://localhost:6379/0
- ** ---------- .> results:     redis://localhost:6379/0
- *** --- * --- .> concurrency: 10 (prefork)
-- ******* ---- .> task events: OFF (enable -E to monitor tasks in this worker)
--- ***** -----
-------------- [queues]
                .> celery           exchange=celery(direct) key=celery

[tasks]
  . app.utils.pdf_processor.process_pdf
[2025-04-24 20:59:20,938: INFO/MainProcess] Connected to redis://localhost:6379/0
[2025-04-24 20:59:20,940: INFO/MainProcess] mingle: searching for neighbors
[2025-04-24 20:59:21,945: INFO/MainProcess] mingle: all alone
[2025-04-24 20:59:21,955: INFO/MainProcess] celery@gabriels-MacBook-Pro.local ready.
```

## Starting the Worker

To start the Celery worker:

```bash
celery -A celery_worker.celery worker --loglevel=info
```

## Requirements

Make sure these dependencies are in your requirements.txt:

- celery>=5.5.0
- redis>=4.5.0
- python-dotenv

## Environment Setup

Ensure Redis is installed and running locally:

```bash
# Install Redis (macOS)
brew install redis

# Start Redis server
redis-server
```
