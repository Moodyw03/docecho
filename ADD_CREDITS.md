# Adding Credits to DocEcho User Accounts

This document provides instructions for adding credits to user accounts in the DocEcho application, both in local development and in production on Fly.io.

## Method 1: Using the manage_credits.py Script (Recommended)

The recommended way to manage user credits is using the comprehensive `manage_credits.py` script:

```bash
# Add credits by user ID
python manage_credits.py --id <user_id> --add <credits>

# Add credits by email
python manage_credits.py --email <email> --add <credits>

# Set credits to specific value
python manage_credits.py --email <email> --set <credits>

# List all users and their credits
python manage_credits.py --list

# List limited number of users
python manage_credits.py --list --limit 20

# Search for users by email
python manage_credits.py --search example.com
```

This script provides all credit management functionality in one tool.

## Method 2: Using the add_credits.py Script (Legacy)

The DocEcho application includes a script for adding credits to users by their ID:

```bash
python add_credits.py <user_id> <credits_to_add>
```

Example:

```bash
python add_credits.py 1 30
```

This adds 30 credits to the user with ID 1.

## Method 3: Using the add_credits_by_email.py Script (Legacy)

For convenience, you can use the `add_credits_by_email.py` script to add credits using email addresses:

```bash
python add_credits_by_email.py <email> <credits_to_add>
```

Example:

```bash
python add_credits_by_email.py user@example.com 30
```

This adds 30 credits to the user with email user@example.com.

## Method 4: Using Fly.io SSH and Direct SQL (Production)

For production environments on Fly.io, you can use direct SQL commands:

1. Connect to your Fly.io app via SSH:

   ```bash
   fly ssh console -a docecho
   ```

2. Once connected, access the PostgreSQL database:

   ```bash
   psql $DATABASE_URL
   ```

3. Check if the user exists:

   ```sql
   SELECT id, email, credits FROM users WHERE email = 'user@example.com';
   ```

4. Add credits to an existing user:

   ```sql
   UPDATE users
   SET credits = credits + 30
   WHERE email = 'user@example.com'
   RETURNING id, email, credits - 30 as old_credits, credits as new_credits;
   ```

5. If the user doesn't exist, create one with initial credits:
   ```sql
   INSERT INTO users (
     email,
     password_hash,
     subscription_tier,
     credits,
     email_verified,
     created_at
   )
   VALUES (
     'user@example.com',
     'placeholder_hash_to_reset_later',
     'free',
     30,
     true,
     NOW()
   )
   RETURNING id, email, credits;
   ```

## Method 5: Using Fly Postgres Directly (Production)

You can also connect directly to the PostgreSQL database:

1. Connect to your Fly.io PostgreSQL instance:

   ```bash
   fly postgres connect -a docecho-db
   ```

2. Switch to the "docecho" database:

   ```sql
   \c docecho
   ```

3. Verify the users table exists:

   ```sql
   \dt
   ```

   This should show the users table in the public schema.

4. Check if the user exists and view current credits:

   ```sql
   SELECT id, email, credits FROM public.users WHERE email = 'user@example.com';
   ```

   Note: Using the full schema name `public.users` is recommended to avoid ambiguity.

5. Add credits to an existing user:

   ```sql
   UPDATE public.users
   SET credits = credits + 30
   WHERE email = 'user@example.com'
   RETURNING id, email, credits - 30 as old_credits, credits as new_credits;
   ```

6. After updating credits, restart the application to ensure changes are reflected:

   ```bash
   fly apps restart docecho
   ```

## Troubleshooting

If credits are added successfully but don't appear in the application:

1. Verify the database update was successful:

   ```sql
   SELECT id, email, credits FROM public.users WHERE email = 'user@example.com';
   ```

2. Try these troubleshooting steps:

   - Log out and log back into the account
   - Clear browser cache and cookies
   - Restart the application server:
     ```bash
     fly apps restart docecho
     ```

3. If you encounter "relation does not exist" errors:

   - Check that you're connected to the correct database (`\c docecho`)
   - Verify table existence with `\dt`
   - Use the full schema reference (`public.users`) in your queries

4. If credits still don't appear, check for caching mechanisms in the application:

   ```bash
   fly ssh console -a docecho
   cd /app
   grep -r "cache" .
   ```

5. Ensure the dashboard route is fetching fresh user data each time:
   ```bash
   grep -r "dashboard" app/routes/
   ```

## Adding Credits to Multiple Users

For bulk operations, you can create a CSV file with email addresses and credit amounts, then process it with a script:

```python
import csv
from app import create_app, db
from app.models.user import User

app = create_app()

with app.app_context():
    with open('credits.csv', 'r') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header row
        for row in reader:
            email, credits = row[0], int(row[1])
            user = User.query.filter_by(email=email).first()
            if user:
                user.credits += credits
                print(f"Added {credits} credits to {email}")
            else:
                print(f"User {email} not found")
    db.session.commit()
```

Save this as `bulk_add_credits.py` and use with a CSV file in the format:

```
email,credits
user1@example.com,10
user2@example.com,20
```
