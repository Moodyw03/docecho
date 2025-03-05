from app.extensions import db
from datetime import datetime, timedelta
import json
from flask import current_app

class TaskProgress(db.Model):
    __tablename__ = 'task_progress'
    
    task_id = db.Column(db.String(64), primary_key=True)
    data = db.Column(db.Text, nullable=False)  # JSON data
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(hours=1))
    
    @property
    def is_expired(self):
        return datetime.utcnow() > self.expires_at
    
    @classmethod
    def cleanup_expired(cls):
        """Delete expired progress records"""
        try:
            # Ensure we're in an app context
            if not current_app:
                raise RuntimeError("No application context found. Make sure this function is called within an app context.")
                
            # Get current time once to ensure consistency
            now = datetime.utcnow()
            
            # Find expired records
            expired_records = cls.query.filter(cls.expires_at < now).all()
            
            # Log how many records will be deleted
            if expired_records:
                current_app.logger.info(f"Deleting {len(expired_records)} expired progress records")
                
                # Delete records one by one to avoid potential issues
                for record in expired_records:
                    db.session.delete(record)
                
                # Commit the changes
                db.session.commit()
                return len(expired_records)
            else:
                current_app.logger.info("No expired progress records found")
                return 0
                
        except Exception as e:
            # Rollback in case of error
            if 'db' in locals() and hasattr(db, 'session'):
                db.session.rollback()
            current_app.logger.error(f"Error cleaning up expired records: {str(e)}")
            return 0 