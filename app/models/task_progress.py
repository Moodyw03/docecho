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
        cls.query.filter(cls.expires_at < datetime.utcnow()).delete()
        db.session.commit() 