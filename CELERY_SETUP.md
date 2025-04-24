# Celery Configuration Setup

This document outlines the working Celery configuration with Redis for the DocEcho application.

## Overview

The application uses Celery with Redis for background task processing. This setup allows PDF processing tasks to be handled asynchronously.

## Configuration Details

The working configuration uses:

- Redis as both the broker and result backend
- Local Redis instance running on default port 6379
- Task serialization using JSON
- PDF processing tasks included from app.utils.pdf_processor

## Key Files

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

## Running the Celery Worker

To start the Celery worker, use:

```bash
celery -A celery_worker.celery worker --loglevel=info
```

## Successful Worker Output

When properly configured, the worker should display output similar to:

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

You can also set the REDIS_URL environment variable to point to your Redis server if not using the default localhost:6379.
