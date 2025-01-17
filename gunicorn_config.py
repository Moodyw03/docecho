import multiprocessing
import os

# Gunicorn configuration for production
bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"
workers = multiprocessing.cpu_count() * 2 + 1
threads = 2
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
worker_class = 'sync'

# Access logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# SSL configuration (if needed)
# keyfile = 'path/to/keyfile'
# certfile = 'path/to/certfile'

# Worker process name
proc_name = 'docecho'

# Preload application code
preload_app = True