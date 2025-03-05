# DocEcho Deployment Checklist

This document outlines the steps to deploy DocEcho to Render.com.

## Pre-Deployment Checklist

- [x] Update `render.yaml` with correct environment variables
- [x] Ensure all required dependencies are in `requirements.txt`
- [x] Verify `wsgi.py` is properly configured
- [x] Ensure email templates are in the correct directory
- [x] Set secure values for `JWT_SECRET_KEY` and `FLASK_SECRET_KEY`
- [x] Configure `BASE_URL` to point to the production URL
- [x] Ensure database connection string is correct
- [x] Verify SendGrid API key and email settings

## Deployment Steps

1. **Push changes to GitHub**

   ```bash
   git add .
   git commit -m "Prepare for deployment"
   git push origin main
   ```

2. **Deploy to Render**

   - Log in to your Render.com dashboard
   - Navigate to your DocEcho service
   - Click "Deploy" to deploy the latest changes
   - Monitor the deployment logs for any errors

3. **Verify Deployment**
   - Check that the application is running at https://docecho.onrender.com
   - Test user registration and password reset functionality
   - Verify that emails are being sent correctly
   - Test PDF to audio conversion

## Post-Deployment Tasks

- [ ] Monitor application logs for any errors
- [ ] Verify database migrations have been applied
- [ ] Test all critical functionality
- [ ] Check that static files are being served correctly
- [ ] Verify that file uploads and processing work correctly

## Troubleshooting

If you encounter issues during deployment:

1. **Check Render Logs**

   - Navigate to your service in the Render dashboard
   - Click on "Logs" to view deployment and application logs

2. **Database Issues**

   - Verify that the database connection string is correct
   - Check that migrations have been applied
   - Ensure the database user has the necessary permissions

3. **Email Issues**

   - Verify SendGrid API key is valid
   - Check that the sender email is verified in SendGrid
   - Test email functionality using the `/auth/test-reset-email` route

4. **File Storage Issues**
   - Check that the disk is mounted correctly
   - Verify that the application has permission to write to the disk
   - Ensure the necessary directories exist and are writable
