# Use an official Python image as a base
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    ffmpeg \
    libsm6 \
    libxext6 \
    libtesseract-dev \
    python3-dev \
    build-essential \
    libssl-dev \
    libffi-dev \
    # Pillow dependencies
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    tk-dev \
    tcl-dev \
    && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

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

# Copy the font files that exist
COPY app/static/fonts/* /app/app/static/fonts/

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
