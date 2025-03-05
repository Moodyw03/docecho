# DocEcho

DocEcho is a web application that converts PDF documents to audio, allowing users to listen to their documents on the go. The application also supports translation features, making it a versatile tool for accessibility and language learning.

## Features

- **PDF to Audio Conversion**: Upload PDF files and convert them to MP3 audio files
- **Translation Support**: Translate documents to different languages before conversion
- **Multiple Output Formats**: Choose between audio-only or both audio and PDF outputs
- **Progress Tracking**: Real-time progress updates during conversion
- **User Management**: User accounts with credit system for document processing
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
   ```

   > **Important**: For user registration to work, you must configure the email settings. The application uses SendGrid for sending verification emails.

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

### Production Deployment

The application is configured for deployment on Render.com with the included `render.yaml` file. It uses PostgreSQL for the database and sets up the necessary environment variables.

## Usage

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

### File Management

The application organizes files in the following directories:

- `app/static/uploads`: Temporary storage for uploaded PDF files
- `app/static/output`: Generated audio and PDF files
- `app/static/progress`: Progress tracking data (file-based fallback)
- `app/static/temp`: Temporary files used during processing

## Troubleshooting

### Database Issues

If you encounter database-related errors:

1. Check that your database connection is properly configured in the `.env` file
2. Ensure migrations are up to date with `flask db upgrade`
3. The application includes a file-based fallback for progress tracking if database operations fail

### Processing Errors

If PDF processing fails:

1. Verify that FFmpeg is properly installed and accessible
2. Check that the PDF is not password-protected or corrupted
3. Review the application logs for specific error messages

## License

[MIT License](LICENSE)

## Contact

For support or inquiries, please contact [your-email@example.com](mailto:your-email@example.com).
