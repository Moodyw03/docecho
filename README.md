# DocEcho

DocEcho is a web application that converts PDF documents to audio, allowing users to listen to their documents on the go. The application also supports translation features, making it a versatile tool for accessibility and language learning.

## Features

- **PDF to Audio Conversion**: Upload PDF files and convert them to MP3 audio files
- **Translation Support**: Translate documents to different languages before conversion
- **Multiple Output Formats**: Choose between audio-only or both audio and PDF outputs
- **Progress Tracking**: Real-time progress updates during conversion
- **User Management**: User accounts with credit system for document processing
- **Account Recovery**: Password reset functionality via email
- **Responsive Design**: Modern, glass-like UI that works on desktop and mobile devices

## Installation

### Prerequisites

- Python 3.9 or higher
- FFmpeg (for audio processing)
- PostgreSQL (for production) or SQLite (for development)

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

   # Stripe Configuration
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

6. Run the application:

   ```bash
   python app.py
   ```

7. Access the application at http://localhost:8000

### Email Configuration

The application uses SendGrid for sending verification and password reset emails. To configure email functionality:

1. Create a SendGrid account and obtain an API key
2. Add a verified sender email address in your SendGrid account
3. Configure the email settings in your `.env` file as shown above
4. Test the email functionality using the `/auth/test-reset-email` route (in development mode)

> **Note**: Without proper email configuration, user registration and password reset features will not work correctly.

## File Paths Management

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
- Files are cleaned up after successful download or after a configurable time period

## Deployment

### Fly.io Deployment

The application is configured for deployment on [Fly.io](https://fly.io/) with the following architecture:

- **Web Process**: Gunicorn server with 2 workers and 4 threads per worker
- **Worker Process**: Celery worker with 2 concurrent processes for background tasks
- **Persistent Storage**: 1GB volume mounted at `/app/data`
- **Database**: PostgreSQL on Fly.io

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
- `MAIL_SERVER=smtp.sendgrid.net`
- `MAIL_PORT=587`
- `MAIL_USERNAME=apikey`
- `MAIL_PASSWORD=<your-sendgrid-api-key>`
- `MAIL_DEFAULT_SENDER=<your-verified-email>`
- `MAIL_USE_TLS=true`
- `GOOGLE_APPLICATION_CREDENTIALS=credentials.json`
- `FRONTEND_URL=https://<your-app-name>.fly.dev`

These can be set using the `fly secrets set` command as detailed in the deployment guide.

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

- Each user starts with a limited number of credits
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

Or access the admin interface at `/admin/users` (admin access required).

#### Adding Credits

To add credits to a user:

```bash
python add_credits.py <user_id> <credits_to_add>
```

Example:

```bash
python add_credits.py 1 10
```

#### Deleting Users

To delete a specific user:

```bash
python delete_user.py <user_id>
```

To delete all users:

```bash
python delete_users.py
```

Or use the admin interface at `/clear-users` (admin access required).

## Troubleshooting

### Database Issues

If you encounter database-related errors:

1. Check that your database connection is properly configured in the `.env` file
2. Ensure migrations are up to date with `flask db upgrade`
3. The application includes a file-based fallback for progress tracking if database operations fail

### Deployment Issues

If you encounter issues with your Fly.io deployment:

1. Check the logs with `fly logs`
2. Verify that both web and worker processes are running with `fly status`
3. Ensure the storage volume is properly mounted with `fly ssh console` and check the `/app/data` directory
4. For host issues, check `fly incidents hosts list` to see if there are any active incidents

### Processing Errors

If PDF processing fails:

1. Verify that FFmpeg is properly installed and accessible
2. Check that the PDF is not password-protected or corrupted
3. Review the application logs for specific error messages
4. Ensure the worker process is running properly

## License

[MIT License](LICENSE)

## Contact

For support or inquiries, please contact [your-email@example.com](mailto:your-email@example.com).
