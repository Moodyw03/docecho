import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///instance/users.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
    OUTPUT_FOLDER = os.getenv('OUTPUT_FOLDER', 'output')
    TEMP_FOLDER = os.getenv('TEMP_FOLDER', 'temp')

def get_upload_path():
    if os.environ.get('RENDER') == "true":
        base_path = '/data'
    else:
        base_path = 'instance'
    return os.path.join(base_path, 'uploads')