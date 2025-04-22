import multiprocessing
import os

# Gunicorn configuration for production
bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"

# Use environment variables if set, otherwise use defaults
workers = int(os.getenv('GUNICORN_WORKERS', '2'))
threads = int(os.getenv('GUNICORN_THREADS', '4'))
timeout = int(os.getenv('GUNICORN_TIMEOUT', '300'))

# Keep these settings for better stability
keepalive = 5
max_requests = 500
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

# Preload application code - disable for better reliability
preload_app = False

# Worker settings for better memory management
worker_tmp_dir = '/dev/shm'
forwarded_allow_ips = '*'