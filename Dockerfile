# Use an official Python image as a base
FROM python:3.9-slim

# Install system dependencies - add curl for health checks and ca-certificates for SSL
RUN apt-get update && apt-get install -y ffmpeg curl ca-certificates && apt-get clean

# Create a non-root user to run the application
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory in the container
WORKDIR /app

# Copy the requirements.txt file
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code to the container
COPY . /app/

# Create necessary directories and set permissions
RUN mkdir -p /app/app/static/uploads /app/app/static/output /app/app/static/progress /app/app/static/temp /app/app/static/fonts /app/data \
    && chown -R appuser:appuser /app

# Copy font files to the container
COPY app/static/fonts/NotoSansCJKjp-Regular.otf /app/app/static/fonts/
COPY app/static/fonts/NotoSansCJKsc-Regular.otf /app/app/static/fonts/
COPY app/static/fonts/NotoSansCJKkr-Regular.otf /app/app/static/fonts/
COPY app/static/fonts/DejaVuSans.ttf /app/app/static/fonts/

# Ensure font files are readable
RUN chmod 644 /app/app/static/fonts/*

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_APP=app.py

# Switch to non-root user
USER appuser

# Start the app using gunicorn with config file
CMD ["gunicorn", "--config", "gunicorn_config.py", "wsgi:app"]
