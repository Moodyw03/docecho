from app import create_app, db
import logging
import os
import gc

# Configure logging for production
logging_level = logging.DEBUG if os.environ.get('FLASK_ENV') == 'development' else logging.INFO
logging.basicConfig(
    level=logging_level,
    format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Set garbage collection thresholds for better memory management
# Lower threshold means more frequent collection
gc.set_threshold(100, 5, 5)  # Default is (700, 10, 10)

# Create the Flask application
app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # Use port 8000 to avoid conflict with AirPlay
    port = int(os.environ.get('PORT', 8000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)

