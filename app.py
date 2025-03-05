from app import create_app, db
import logging
import os

# Configure logging for development
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Create the Flask application
app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # Use port 8000 to avoid conflict with AirPlay
    app.run(host='0.0.0.0', port=8000, debug=True)

