import os
import logging
import boto3
from flask import current_app, has_app_context
from botocore.exceptions import ClientError
from urllib.parse import urljoin

# Configure logging
logger = logging.getLogger(__name__)

def copy_to_remote_storage(local_file_path, remote_path):
    """
    Copy a file to remote storage (S3 or similar) and return a URL to access it.
    
    Args:
        local_file_path: Path to the local file to upload
        remote_path: Path/key to use in remote storage (e.g. "task_id/filename.mp3")
        
    Returns:
        URL to the file in remote storage, or None if remote storage is not configured/upload fails
    """
    # Check if remote storage is configured via environment variables
    aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    s3_bucket = os.environ.get('S3_BUCKET_NAME')
    s3_region = os.environ.get('AWS_REGION', 'us-east-1')
    cdn_base_url = os.environ.get('CDN_BASE_URL')
    
    # If any required config is missing, skip remote storage
    if not all([aws_access_key, aws_secret_key, s3_bucket]):
        logger.info(f"Remote storage not configured. Skipping upload of {local_file_path}")
        return None
    
    try:
        # Check if the local file exists
        if not os.path.exists(local_file_path):
            logger.error(f"Local file {local_file_path} does not exist")
            return None
            
        # Initialize S3 client
        s3_client = boto3.client(
            's3',
            region_name=s3_region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        
        # Determine content type based on file extension
        content_type = 'application/octet-stream'  # Default
        if local_file_path.endswith('.mp3'):
            content_type = 'audio/mpeg'
        elif local_file_path.endswith('.pdf'):
            content_type = 'application/pdf'
        elif local_file_path.endswith('.txt'):
            content_type = 'text/plain'
        
        # Upload file to S3
        s3_client.upload_file(
            local_file_path, 
            s3_bucket, 
            remote_path,
            ExtraArgs={
                'ContentType': content_type,
                'ACL': 'public-read'  # Make the file publicly accessible
            }
        )
        
        # Construct the URL to the uploaded file
        if cdn_base_url:
            # If a CDN is configured, use that base URL
            remote_url = urljoin(cdn_base_url, remote_path)
        else:
            # Otherwise, construct a direct S3 URL
            remote_url = f"https://{s3_bucket}.s3.{s3_region}.amazonaws.com/{remote_path}"
        
        logger.info(f"Successfully uploaded {local_file_path} to {remote_url}")
        return remote_url
        
    except Exception as e:
        logger.error(f"Error uploading {local_file_path} to remote storage: {str(e)}")
        return None 