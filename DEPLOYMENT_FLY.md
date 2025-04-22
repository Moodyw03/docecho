# Deploying DocEcho to Fly.io

This guide provides detailed instructions for deploying DocEcho to [Fly.io](https://fly.io/), a platform for running applications worldwide.

## Prerequisites

- A Fly.io account
- Fly CLI installed on your local machine
- DocEcho codebase cloned to your local machine

## Step 1: Install Fly CLI

```bash
# macOS
brew install flyctl

# Linux
curl -L https://fly.io/install.sh | sh

# Windows (using PowerShell)
pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

## Step 2: Authenticate with Fly.io

```bash
fly auth login
```

## Step 3: Configure PostgreSQL Database

DocEcho requires a PostgreSQL database. You can use Fly Postgres:

```bash
# Create a PostgreSQL app
fly pg create --name docecho-db

# Connect it to your app (after creating the app)
fly pg attach --app docecho --postgres-app docecho-db
```

## Step 4: Initialize the Fly.io App

From the root directory of your project:

```bash
fly launch
```

During the launch process:

- Name your app (e.g., "docecho")
- Select the primary region (London "lhr" is the current default)
- Choose to set up a PostgreSQL database
- Set up an IPv4 address
- Deploy the application

This will create a `fly.toml` file in your project.

## Step 5: Configure Storage Volumes

Create a persistent volume to store uploaded files:

```bash
fly volumes create docecho_data --size 1
```

## Step 6: Set Environment Variables

Set the necessary environment variables using the Fly CLI:

```bash
fly secrets set FLASK_ENV=production
fly secrets set FLASK_SECRET_KEY=your_secure_random_key
fly secrets set MAIL_SERVER=smtp.sendgrid.net
fly secrets set MAIL_PORT=587
fly secrets set MAIL_USERNAME=apikey
fly secrets set MAIL_PASSWORD=your_sendgrid_api_key
fly secrets set MAIL_DEFAULT_SENDER=your_verified_email
fly secrets set MAIL_USE_TLS=true
fly secrets set GOOGLE_APPLICATION_CREDENTIALS=credentials.json
fly secrets set FRONTEND_URL=https://your-app-name.fly.dev
```

## Step 7: Deploy Your Application

Deploy your application with:

```bash
fly deploy
```

## Step 8: Access Your Application

Once deployment is complete, you can access your application:

```bash
fly open
```

## Managing Your Deployment

### Viewing Logs

```bash
fly logs
```

### SSH into Your App

```bash
fly ssh console
```

### Scaling Your App

```bash
# Scale to multiple regions
fly scale count 2 --region syd,lhr

# Scale machine size
fly scale vm shared-cpu-1x --memory 512
```

### Database Migrations

For database migrations, DocEcho is configured to run migrations automatically during deployment with a release command in `fly.toml`.

If you need to run migrations manually:

```bash
fly ssh console
cd /app
python -m flask db upgrade
```

## Troubleshooting

### Deployment Issues

If deployment fails, check the logs:

```bash
fly logs
```

### Database Connection Issues

Verify your PostgreSQL connection string:

```bash
fly ssh console
echo $DATABASE_URL
```

### Resource Limitations

If your app crashes due to resource limitations, consider scaling up:

```bash
fly scale vm shared-cpu-1x --memory 1024
```

## Additional Resources

- [Fly.io Documentation](https://fly.io/docs/)
- [Fly.io PostgreSQL Documentation](https://fly.io/docs/postgres/)
- [Fly.io Scaling Documentation](https://fly.io/docs/apps/scale-count/)
