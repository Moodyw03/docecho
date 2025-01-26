from flask import Flask
import os
import logging
from dotenv import load_dotenv
from app import create_app, db

# Load environment variables
load_dotenv()

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Define static folders
STATIC_FOLDER = '/data' if os.environ.get('RENDER') else 'static'
UPLOAD_FOLDER = os.path.join(STATIC_FOLDER, 'uploads')
OUTPUT_FOLDER = os.path.join(STATIC_FOLDER, 'output')
TEMP_FOLDER = os.path.join(STATIC_FOLDER, 'temp')

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

