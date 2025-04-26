import redis
import os
import logging
from flask import current_app, has_app_context
import json

# Configure logging
logger = logging.getLogger(__name__)

def get_redis():
    """
    Get a Redis client connection using the configured Redis URL.
    
    Returns:
        A Redis client instance, or a dummy client if Redis is not configured
    """
    try:
        # Try to get the Redis URL from the app config first (in app context)
        if has_app_context():
            redis_url = current_app.config.get('REDIS_URL')
            if not redis_url:
                redis_url = current_app.config.get('CELERY_RESULT_BACKEND')
        else:
            # If not in app context, try environment variables
            redis_url = os.environ.get('REDIS_URL')
            
        # If no Redis URL is found, use a default for local development
        if not redis_url:
            logger.warning("No Redis URL found. Using localhost:6379")
            redis_url = 'redis://localhost:6379/0'
            
        # Create and return the Redis client
        return redis.from_url(redis_url)
    except Exception as e:
        logger.error(f"Error connecting to Redis: {str(e)}")
        # Return a dummy Redis client that won't break the code if Redis is unavailable
        return DummyRedisClient()
        
class DummyRedisClient:
    """
    A fallback class that provides basic Redis-like functionality when Redis is unavailable.
    This prevents the application from crashing when Redis operations are attempted.
    """
    def __init__(self):
        self.storage = {}
        logger.warning("Using DummyRedisClient - Redis operations will not persist!")
        
    def set(self, key, value, ex=None):
        """Store a key-value pair, with optional expiration"""
        self.storage[key] = value
        logger.info(f"DummyRedis: SET {key}")
        return True
        
    def get(self, key):
        """Get a value by key"""
        value = self.storage.get(key)
        logger.info(f"DummyRedis: GET {key} -> {'found' if value else 'not found'}")
        return value
        
    def delete(self, key):
        """Delete a key"""
        if key in self.storage:
            del self.storage[key]
            logger.info(f"DummyRedis: DEL {key}")
            return 1
        return 0
        
    def exists(self, key):
        """Check if a key exists"""
        exists = key in self.storage
        logger.info(f"DummyRedis: EXISTS {key} -> {exists}")
        return exists
        
    def mset(self, mapping):
        """Set multiple keys"""
        for k, v in mapping.items():
            self.storage[k] = v
        logger.info(f"DummyRedis: MSET {list(mapping.keys())}")
        return True
        
    def keys(self, pattern="*"):
        """Get keys matching a pattern (simple implementation)"""
        if pattern == "*":
            return list(self.storage.keys())
        matching_keys = []
        for key in self.storage.keys():
            if pattern in key:
                matching_keys.append(key)
        logger.info(f"DummyRedis: KEYS {pattern} -> found {len(matching_keys)} keys")
        return matching_keys
        
    def expire(self, key, seconds):
        """Set expiration on key (not implemented in dummy)"""
        logger.info(f"DummyRedis: EXPIRE {key} {seconds} (not implemented)")
        return True  # Just pretend it worked 

def update_progress(task_id, status, progress=None, error=False):
    """Update the progress of a task in Redis."""
    redis = get_redis()
    progress_data = {
        'status': status,
        'error': error
    }
    if progress is not None:
        progress_data['progress'] = progress
    redis.setex(
        f'progress:{task_id}',
        current_app.config.get('REDIS_TTL', 3600),
        json.dumps(progress_data)
    ) 