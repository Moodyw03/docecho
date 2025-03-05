from app.extensions import db
from datetime import datetime, timedelta
import json

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
            # Get current time once to ensure consistency
            now = datetime.utcnow()
            
            # Find expired records
            expired_records = cls.query.filter(cls.expires_at < now).all()
            
            # Log how many records will be deleted
            if expired_records:
                print(f"Deleting {len(expired_records)} expired progress records")
                
                # Delete records one by one to avoid potential issues
                for record in expired_records:
                    db.session.delete(record)
                
                # Commit the changes
                db.session.commit()
            else:
                print("No expired progress records found")
                
        except Exception as e:
            # Rollback in case of error
            db.session.rollback()
            raise e 