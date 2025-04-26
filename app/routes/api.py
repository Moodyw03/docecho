from flask import Blueprint, request, jsonify, current_app
from app.utils.pdf_processor import process_pdf
from app.utils.redis import get_redis
import os
import time

bp = Blueprint('api', __name__)

@bp.route('/process', methods=['POST'])
def process_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if not file.filename:
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are supported'}), 400
        
        # Get request parameters
        voice = request.form.get('voice', 'en')
        output_format = request.form.get('output_format', 'audio')
        user_id = request.form.get('user_id')
        audio_speed = float(request.form.get('audio_speed', 1.0))
        
        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400
        
        # Read file content
        file_content = file.read()
        
        # Start Celery task
        task = process_pdf.delay(
            file_content=file_content,
            filename=file.filename,
            voice={'language': voice},
            output_format=output_format,
            user_id=user_id,
            audio_speed=audio_speed
        )
        
        return jsonify({
            'task_id': task.id,
            'status': 'processing'
        }), 202
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/progress/<task_id>', methods=['GET'])
def get_progress(task_id):
    try:
        redis = get_redis()
        progress = redis.get(f'progress:{task_id}')
        
        if progress is None:
            return jsonify({'error': 'Task not found'}), 404
        
        return jsonify(progress.decode('utf-8')), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500 