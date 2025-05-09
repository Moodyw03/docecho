# DocEcho

DocEcho is a web application that converts PDF documents to audio, allowing users to listen to their documents on the go. The application also supports translation features, making it a versatile tool for accessibility and language learning.

## Features

- **PDF to Audio Conversion**: Upload PDF files and convert them to MP3 audio files
- **Translation Support**: Translate documents to different languages before conversion
- **Multiple Output Formats**: Choose between audio-only or both audio and PDF outputs
- **Customizable Speech Speed**: Adjust the speed of the generated audio
- **Progress Tracking**: Real-time progress updates during conversion
- **User Management**: User accounts with credit system for document processing
- **Account Recovery**: Password reset functionality via email
- **Responsive Design**: Modern, glass-like UI that works on desktop and mobile devices
- **Async Processing**: Background task processing with Celery and Redis
- **Scalable Architecture**: Separated web and worker processes for better performance
- **Memory Optimization**: Advanced garbage collection and memory management

## Technical Stack

- **Backend**: Flask (Python 3.9+)
- **Database**: PostgreSQL (production), SQLite (development)
- **Task Queue**: Celery with Redis as broker and backend
- **PDF Processing**: PyPDF2, ReportLab
- **Text-to-Speech**: gTTS (Google Text-to-Speech)
- **Translation**: Google Translate API
- **Payment Processing**: Stripe
- **Email Service**: SendGrid
- **Deployment**: Fly.io with Docker containerization
- **Storage**: Persistent volume storage for uploads and outputs

## Unicode and CJK Support

DocEcho supports multiple languages including CJK (Chinese, Japanese, Korean) for both audio and PDF output. This is achieved through:

- **Unicode-Compatible Fonts**: Noto Sans CJK for CJK languages and DejaVu Sans for other Unicode characters
- **Font Registration**: Custom font handling with ReportLab's TTFont system
- **Automatic Language Detection**: PDF generation automatically selects the appropriate font based on the target language
- **Multilingual Text Processing**: Proper text extraction and handling across languages

For proper deployment, ensure the following fonts are included in your `app/static/fonts` directory:

- `NotoSansCJK-Regular.ttc` for CJK languages
- `DejaVuSans.ttf` for extended Unicode support

These fonts are pre-installed in the Docker container for Fly.io deployment.

## Installation

### Prerequisites

- Python 3.9 or higher
- FFmpeg (for audio processing)
- PostgreSQL (for production) or SQLite (for development)
- Redis (for task queue)

### Local Development Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/docecho.git
   cd docecho
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables by creating a `.env` file:

   ```
   FLASK_ENV=development
   FLASK_SECRET_KEY=your_secret_key
   JWT_SECRET_KEY=your_jwt_secret
   DATABASE_URL=sqlite:///instance/app.db  # For local development
   REDIS_URL=redis://localhost:6379/0  # For Celery task queue
   LANGUAGES_SUPPORTED=en,en-uk,pt,es,fr,de,it,zh-CN,ja,ru,ar,hi,ko,tr,nl,pl

   # Stripe Configuration (for payment processing)
   STRIPE_PUBLIC_KEY=your_stripe_public_key
   STRIPE_SECRET_KEY=your_stripe_secret_key
   STRIPE_WEBHOOK_SECRET=your_stripe_webhook_secret

   # Email Configuration (Required for user registration)
   MAIL_SERVER=smtp.sendgrid.net
   MAIL_PORT=587
   MAIL_USERNAME=apikey
   MAIL_PASSWORD=your_sendgrid_api_key
   MAIL_USE_TLS=true
   MAIL_DEFAULT_SENDER=your_verified_email@example.com
   SENDGRID_API_KEY=your_sendgrid_api_key
   BASE_URL=http://localhost:8000  # Change this to your production URL in production
   ```

   > **Important**: For user registration and password reset to work, you must configure the email settings correctly.

5. Initialize the database:

   ```bash
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

6. Start Redis server (required for Celery):

   ```bash
   # Install Redis if not already installed
   # On macOS: brew install redis
   # On Ubuntu: sudo apt install redis-server

   # Start Redis server
   redis-server
   ```

7. Start the Celery worker in a separate terminal window:

   ```bash
   celery -A celery_worker.celery worker --loglevel=info
   ```

8. Run the Flask application in another terminal window:

   ```bash
   python app.py
   ```

9. Access the application at http://localhost:8000

### Email Configuration

The application uses SendGrid for sending verification and password reset emails. To configure email functionality:

1. Create a SendGrid account and obtain an API key
2. Add a verified sender email address in your SendGrid account
3. Configure the email settings in your `.env` file as shown above
4. Test the email functionality using the `/auth/test-reset-email` route (in development mode)

> **Note**: Without proper email configuration, user registration and password reset features will not work correctly.

## File Structure Management

The application manages file paths in the following way:

### In Local Development

- Uploaded PDFs: `app/static/uploads/{user_id}/{unique_id}/input.pdf`
- Generated audio: `app/static/output/{user_id}/{unique_id}/output.mp3`
- Translated PDFs: `app/static/output/{user_id}/{unique_id}/translated.pdf`
- Temporary files: `app/static/temp/{user_id}/{unique_id}/`
- Progress tracking: `app/static/progress/{task_id}.json`

### In Production (Fly.io)

The production environment uses a mounted volume at `/app/data` to ensure file persistence:

- All uploaded and generated files are stored in subdirectories under `/app/data`
- The data volume is mounted to both web and worker processes
- Redis is used for sharing progress data between processes
- Files are cleaned up after successful download or after a configurable time period

## Deployment

### Fly.io Deployment

The application is configured for deployment on [Fly.io](https://fly.io/) with the following architecture:

- **Web Process**: Gunicorn server with 2 workers and 4 threads per worker
- **Worker Process**: Celery worker with 2 concurrent processes for background tasks
- **Persistent Storage**: 1GB volume mounted at `/app/data`
- **Database**: PostgreSQL on Fly.io
- **Redis**: Redis instance on Fly.io for task queue and result storage
- **VM Size**: shared-cpu-1x with 1GB memory

The deployment configuration in `fly.toml` includes:

```toml
[processes]
  web = "gunicorn --bind :8080 --workers 2 --threads 4 --timeout 120 --worker-class gthread wsgi:app"
  worker = "celery -A celery_worker.celery worker --loglevel=INFO -c 2 --pool=solo"
```

For a complete step-by-step guide, please refer to the [DEPLOYMENT_FLY.md](DEPLOYMENT_FLY.md) file, which includes:

- Installing the Fly.io CLI
- Authenticating with Fly.io
- Setting up a PostgreSQL database
- Initializing and deploying your application
- Creating persistent storage volumes
- Setting required environment variables
- Managing and scaling your deployment
- Troubleshooting common issues

### Environment Variables for Production

For production deployment on Fly.io, you'll need to set the following environment variables:

- `FLASK_ENV=production`
- `FLASK_SECRET_KEY=<your-secure-random-key>`
- `DATABASE_URL=<your-database-url>` (Set automatically when using Fly Postgres)
- `REDIS_URL=<your-redis-url>` (Set automatically when using Fly Redis)
- `MAIL_SERVER=smtp.sendgrid.net`
- `MAIL_PORT=587`
- `MAIL_USERNAME=apikey`
- `MAIL_PASSWORD=<your-sendgrid-api-key>`
- `MAIL_DEFAULT_SENDER=<your-verified-email>`
- `MAIL_USE_TLS=true`
- `SENDGRID_API_KEY=<your-sendgrid-api-key>`
- `STRIPE_PUBLIC_KEY=<your-stripe-public-key>`
- `STRIPE_SECRET_KEY=<your-stripe-secret-key>`
- `STRIPE_WEBHOOK_SECRET=<your-stripe-webhook-secret>`
- `FRONTEND_URL=https://<your-app-name>.fly.dev`
- `LANGUAGES_SUPPORTED=en,en-uk,pt,es,fr,de,it,zh-CN,ja,ru,ar,hi,ko,tr,nl,pl`
- `OUTPUT_FOLDER=/app/data/output`
- `UPLOAD_FOLDER=/app/data/uploads`
- `TEMP_FOLDER=/app/data/temp`

These can be set using the `fly secrets set` command as detailed in the deployment guide.

## Advanced Configuration

### Celery Worker Configuration

The Celery worker is configured in `celery_worker.py` with optimized settings:

```python
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
```

### Gunicorn Configuration

The Gunicorn server is configured in `gunicorn_config.py` with production-ready settings:

```python
workers = int(os.getenv('GUNICORN_WORKERS', '2'))
threads = int(os.getenv('GUNICORN_THREADS', '4'))
timeout = int(os.getenv('GUNICORN_TIMEOUT', '300'))
keepalive = 5
max_requests = 500
max_requests_jitter = 50
worker_class = 'sync'
```

### Memory Management

The application uses optimized garbage collection settings to improve memory management:

```python
gc.set_threshold(100, 5, 5)  # Default is (700, 10, 10)
```

## Usage

### Account Management

#### Registration and Login

1. Create an account by clicking "Register" on the login page
2. Verify your email address by clicking the link sent to your email
3. Log in with your email and password

#### Password Recovery

If you forget your password:

1. Click "Forgot password?" on the login page
2. Enter your email address
3. Check your email for a password reset link
4. Click the link and set a new password
5. Log in with your new password

### Converting a PDF to Audio

1. Log in to your account (or create one if you don't have it)
2. On the home page, upload a PDF file
3. Select the desired voice/language
4. Choose the output format (audio or both audio and PDF)
5. Adjust the speech speed if needed
6. Click "Convert" to start the process
7. Monitor the progress bar for conversion status
8. Download the resulting audio and/or PDF files when processing is complete

### Credit System

- Each user starts with 5 free credits
- Converting a PDF to audio costs 1 credit
- Adding audio output costs an additional 1 credit
- Users can purchase more credits through the pricing page

## Administration

### User Management

#### Viewing Users

To view all registered users:

```bash
python list_users.py
```

#### Adding Credits

To add credits to a user:

```bash
python add_credits.py <user_id> <credits_to_add>
```

Example:

```bash
python add_credits.py 1 10
```

For adding credits to users by email:

```bash
python add_credits_by_email.py <email> <credits_to_add>
```

#### Deleting Users

To delete a specific user:

```bash
python delete_user.py <user_id>
```

To delete all users (use with caution):

```bash
python delete_users.py
```

## Troubleshooting

### Database Issues

If you encounter database-related errors:

1. Check that your database connection is properly configured in the `.env` file
2. Ensure migrations are up to date with `flask db upgrade`
3. For SQLite issues, try resetting the database with `./reset_db.sh`
4. The application includes a file-based fallback for progress tracking if database operations fail

### Task Processing Issues

If document processing is not working:

1. Verify that Redis is running and accessible
2. Check that the Celery worker is running (`celery -A celery_worker.celery worker --loglevel=info`)
3. Look for errors in the Celery worker logs
4. Ensure the required directories exist and have proper permissions

### Email Issues

If email functionality is not working:

1. Verify your SendGrid API key is valid and properly set
2. Check that your sender email is verified in SendGrid
3. Test the email configuration with `/auth/test-sendgrid`
4. Check application logs for specific error messages

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT License](LICENSE)

## Contact

For support or inquiries, please contact [your-email@example.com](mailto:your-email@example.com).
