from PyPDF2 import PdfReader
from gtts import gTTS
from pydub import AudioSegment
from googletrans import Translator
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from app.utils.progress import update_progress
# Import celery instance
from celery_worker import celery
import os
import gc
import time
import threading
import concurrent.futures
import requests
import logging
from flask import current_app # Import current_app to access config (alternative: pass config values)
import re
import tempfile
import shutil
from datetime import datetime
import base64
from io import BytesIO
import json
from app.utils.file_storage import copy_to_remote_storage
from app.utils.redis import get_redis
from celery import shared_task
from app import create_app

# Add logger instance
logger = logging.getLogger(__name__)

# Simple rate limiter for Google Translate API
class TranslateRateLimiter:
    def __init__(self, max_requests_per_second=5):
        self.max_requests_per_second = max_requests_per_second
        self.last_request_time = 0
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        with self.lock:
            current_time = time.time()
            time_since_last_request = current_time - self.last_request_time
            if time_since_last_request < 1.0 / self.max_requests_per_second:
                time.sleep(1.0 / self.max_requests_per_second - time_since_last_request)
            self.last_request_time = time.time()

# Create a global rate limiter
translate_rate_limiter = TranslateRateLimiter()

# Mapping language codes and TLDs for accents
language_map = {
    "en": {"lang": "en", "tld": "com"},
    "en-uk": {"lang": "en", "tld": "co.uk"},
    "pt": {"lang": "pt", "tld": "com.br"},
    "es": {"lang": "es", "tld": "com"},
    "fr": {"lang": "fr", "tld": "fr"},
    "de": {"lang": "de", "tld": "de"},
    "it": {"lang": "it", "tld": "it"},
    "ru": {"lang": "ru", "tld": "ru"},
    "tr": {"lang": "tr", "tld": "com.tr"},    # Turkish
    "nl": {"lang": "nl", "tld": "nl"},        # Dutch
    "pl": {"lang": "pl", "tld": "pl"},         # Polish
    "ja": {"lang": "ja", "tld": "co.jp", "audio_only": True},  # Japanese
    "zh-CN": {"lang": "zh-CN", "tld": "com", "audio_only": True},  # Chinese (Simplified)
    "ar": {"lang": "ar", "tld": "com", "audio_only": True},    # Arabic 
    "ko": {"lang": "ko", "tld": "co.kr", "audio_only": True}   # Korean
}

# Smaller chunk size for better processing
def extract_text_chunks_from_pdf(pdf_path, max_chunk_length=200):
    try:
        reader = PdfReader(pdf_path)
        chunks = []
        current_chunk = ''
        
        total_pages = len(reader.pages)
        for page_num, page in enumerate(reader.pages):
            # Garbage collection on every page
            gc.collect()
            
            page_text = page.extract_text()
            if not page_text:
                continue
                
            sentences = page_text.replace('\n', ' ').split('. ')
            
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 2 > max_chunk_length:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence + '. '
                else:
                    current_chunk += sentence + '. '
            
            # Free up memory from page immediately
            page = None
            gc.collect()
                    
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # Help garbage collector
        reader = None
        gc.collect()
            
        return chunks
    except Exception as e:
        raise Exception(f"Error extracting text from PDF: {e}")

def convert_text_to_audio(text, output_filename, voice, speed, temp_directory, tld='com'):
    try:
        # Use the provided temp_directory instead of os.getcwd()
        # temp_dir = os.path.join(os.getcwd(), 'temp') # Remove this line
        os.makedirs(temp_directory, exist_ok=True) # Ensure the passed temp_directory exists

        temp_output = os.path.join(temp_directory, output_filename.replace(".mp3", "_temp.mp3"))
        # Rename confusing variable name
        temp_audio_chunk_path = os.path.join(temp_directory, output_filename) 

        # Translate the text to the target language first
        translator = Translator()
        try:
            # Apply rate limiting before translation
            translate_rate_limiter.wait_if_needed()
            
            translated_text, error = translate_with_timeout(translator, text, dest=voice, timeout=30)
            if error:
                logger.warning(f"Translation failed, using original text: {error}")
                translated_text = text
            elif not translated_text:
                logger.warning("Translation returned empty result, using original text")
                translated_text = text
        except Exception as e:
            logger.warning(f"Translation error: {e}, using original text")
            translated_text = text

        # Add timeout/retry logic for gTTS
        max_retries = 3
        for attempt in range(max_retries):
            try:
                tts = gTTS(translated_text, lang=voice, tld=tld)
                tts.save(temp_output)
                break
            except (requests.exceptions.RequestException, Exception) as e:
                if attempt < max_retries - 1:
                    time.sleep(2)  # Wait before retry
                    continue
                raise Exception(f"Failed to generate audio after {max_retries} attempts: {e}")

        if speed != 1.0:
            sound = AudioSegment.from_file(temp_output)
            sound = sound.speedup(playback_speed=speed)
            # Export to the correctly named variable
            sound.export(temp_audio_chunk_path, format="mp3") 
            if os.path.exists(temp_output):
                os.remove(temp_output)
        else:
            # Rename to the correctly named variable
            os.rename(temp_output, temp_audio_chunk_path)

        # Return the path to the created chunk
        return temp_audio_chunk_path 
    except Exception as e:
        # Consider logging the specific error and filename
        logger.error(f"Error converting text to audio for chunk {output_filename}: {e}")
        raise Exception(f"Error converting text to audio: {e}")

def concatenate_audio_files(audio_files, output_path):
    logger.info(f"Starting concatenation. Input files: {audio_files}, Output path: {output_path}")
    if not audio_files:
        logger.warning("Concatenation called with no audio files.")
        # Decide how to handle this: raise error or create empty file?
        # For now, let's raise an error to make it clear.
        raise ValueError("Cannot concatenate an empty list of audio files.")
        
    try:
        combined = AudioSegment.empty()
        for i, file in enumerate(audio_files):
            try:
                logger.debug(f"Concatenating chunk {i}: {file}")
                # Check if file exists just before loading
                if not os.path.exists(file):
                    logger.error(f"Audio chunk file not found during concatenation: {file}")
                    # Optionally, skip this chunk or raise an error
                    # Raising error for now to highlight the issue
                    raise FileNotFoundError(f"Audio chunk file not found: {file}")
                    
                audio = AudioSegment.from_file(file)
                combined += audio
                logger.debug(f"Successfully added chunk {i}: {file}. Current combined duration: {len(combined)}ms")
            except Exception as chunk_e:
                logger.error(f"Error processing audio chunk {file}: {str(chunk_e)}", exc_info=True)
                # Decide whether to continue or fail the whole process
                raise Exception(f"Failed to process chunk {file}: {str(chunk_e)}")
                
        # Ensure output directory exists before exporting
        output_dir = os.path.dirname(output_path)
        logger.debug(f"Ensuring output directory exists: {output_dir}")
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"Exporting combined audio ({len(combined)}ms) to: {output_path}")
        combined.export(output_path, format="mp3")
        
        # Verify export by checking file existence and size
        if os.path.exists(output_path):
             logger.info(f"Successfully exported combined audio. File size: {os.path.getsize(output_path)} bytes.")
        else:
             logger.error(f"Export failed! Combined audio file not found at: {output_path}")
             raise IOError(f"Failed to export combined audio file to {output_path}")
             
    except Exception as e:
        # Log which specific file caused the error if possible
        failed_file = file if 'file' in locals() else 'N/A' 
        logger.error(f"Concatenation failed. Last attempted chunk file: {failed_file}. Output path: {output_path}. Error: {e}", exc_info=True)
        # Re-raise the specific error or a generic one
        raise Exception(f"Error concatenating audio files: {e}")

def create_translated_pdf(text, output_path, language_code='en'):
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import os
        from flask import current_app
        
        # Create Canvas with letter size
        c = canvas.Canvas(output_path, pagesize=letter)
        width, height = letter
        y = height - 50
        
        # Determine appropriate font based on language
        font_name = "Helvetica"
        font_size = 11
        
        # Languages that need special font handling
        complex_script_languages = {
            # Empty dictionary since we've removed all complex script languages
        }
        
        # Check if language needs special handling
        if language_code in complex_script_languages:
            logger.info(f"Using special font handling for language: {language_code}")
            font_config = complex_script_languages[language_code]
            
            # For languages with complex scripts, we'll add a specific warning note
            warning_message = font_config.get("message", "Some characters may not render correctly due to font limitations.")
            c.setFont("Helvetica", 9)
            c.drawString(50, height - 30, f"Warning: {warning_message}")
            
            # Use fallback font since we can't guarantee the availability of specialized fonts
            font_name = font_config["fallback"]
            
            # Special handling for RTL languages (like Arabic)
            is_rtl = font_config.get("rtl", False)
            if is_rtl:
                # Add note about RTL limitations                
                c.setFont("Helvetica", 9)
                c.drawString(50, height - 45, "Note: PDF generated with left-to-right layout for Arabic text.")
                c.drawString(50, height - 60, "For best results, consider using audio output.")
                y = height - 80  # Start content lower due to multiple notes
                
                # Simple RTL simulation - reversing each line
                # This is not perfect but helps visualize the text better than nothing
                # Note: Proper RTL would require specialized RTL-aware libraries
                text_lines = text.split('\n')
                reversed_lines = []
                for line in text_lines:
                    # Reverse the line for RTL display
                    # This is a simple approach and won't handle complex bidirectional text properly
                    reversed_lines.append(' '.join(reversed(line.split())))
                text = '\n'.join(reversed_lines)
            else:
                y = height - 50  # Reset to default starting position
        
        # Set the font
        c.setFont(font_name, font_size)
        
        lines = text.split('\n')
        for line in lines:
            # Skip empty lines
            if not line or line.isspace():
                y -= 10  # Less space for empty line
                continue
                
            words = line.split()
            current_line = []
            
            for word in words:
                current_line.append(word)
                try:
                    line_width = c.stringWidth(' '.join(current_line), font_name, font_size)
                except:
                    # If we can't determine width, make a conservative estimate
                    line_width = len(' '.join(current_line)) * (font_size * 0.6)
                
                if line_width > width - 100:
                    current_line.pop()
                    if current_line:
                        try:
                            c.drawString(50, y, ' '.join(current_line))
                        except Exception as e:
                            # If drawing fails, try to represent characters as best as possible
                            logger.warning(f"Error drawing text: {e}, attempting fallback")
                            # Replace non-Latin characters with a question mark
                            safe_text = ''.join([c if ord(c) < 128 else '?' for c in ' '.join(current_line)])
                            c.drawString(50, y, safe_text)
                        y -= 20
                    current_line = [word]
                
                if y < 50:
                    c.showPage()
                    c.setFont(font_name, font_size)
                    y = height - 50
            
            if current_line:
                try:
                    c.drawString(50, y, ' '.join(current_line))
                except Exception as e:
                    # Fallback for problematic characters
                    logger.warning(f"Error drawing text: {e}, attempting fallback")
                    safe_text = ''.join([c if ord(c) < 128 else '?' for c in ' '.join(current_line)])
                    c.drawString(50, y, safe_text)
                y -= 20
        
        # Add a footer explaining PDF limitations
        y = 30
        c.setFont("Helvetica", 8)
        c.drawString(50, y, "Note: This PDF is machine-translated and may contain errors.")
        y -= 12
        c.drawString(50, y, "For the best experience with non-Latin languages, please use the audio output.")
        
        c.save()
        return output_path
    except Exception as e:
        logger.error(f"Error creating PDF: {str(e)}")
        raise Exception(f"Error creating PDF: {str(e)}")

# Helper function for translation with timeout
def translate_with_timeout(translator, text, dest, timeout=10):
    result = None
    error = None
    
    def translate_task():
        nonlocal result, error
        try:
            # Wait if we're about to hit rate limits
            translate_rate_limiter.wait_if_needed()
            
            # Now make the translation request
            result = translator.translate(text, dest=dest).text
        except AttributeError as e:
            if "'NoneType' object has no attribute 'group'" in str(e):
                error = Exception("Translation API error: token retrieval failed. This may be due to an API rate limit or a change in the translation service. Please try again later or contact support if the issue persists.")
            else:
                error = e
        except Exception as e:
            error = e
    
    thread = threading.Thread(target=translate_task)
    thread.daemon = True
    thread.start()
    thread.join(timeout)
    
    if thread.is_alive():
        return None, TimeoutError("Translation timed out")
    
    if error:
        return None, error
        
    return result, None

def save_file_to_redis(file_path, task_id, file_type):
    """Save file content to Redis with proper error handling"""
    try:
        from app.utils.redis import get_redis
        import os
        
        if not os.path.exists(file_path):
            logger.error(f"[{task_id}] File not found at path {file_path}")
            return False
            
        # Read file content
        with open(file_path, 'rb') as f:
            file_content = f.read()
            
        # Get Redis connection
        redis_client = get_redis()
        if not redis_client:
            logger.error(f"[{task_id}] Could not get Redis connection")
            return False
            
        # Set the content in Redis with a key that includes task_id and file_type
        content_key = f"file_content:{task_id}:{file_type}"
        
        # Store file content with 7-day expiration (604800 seconds)
        try:
            redis_client.set(content_key, file_content, ex=604800)
            logger.info(f"[{task_id}] Saved {len(file_content)} bytes to Redis key {content_key}")
            return True
        except Exception as redis_err:
            logger.error(f"[{task_id}] Error storing content in Redis: {str(redis_err)}")
            return False
            
    except Exception as e:
        logger.error(f"[{task_id}] Error in save_file_to_redis: {str(e)}")
        return False

@shared_task
def process_pdf(file_content, filename, voice, output_format, user_id, audio_speed=1.0):
    app = create_app()
    with app.app_context():
        try:
            update_progress(
                task_id=process_pdf.request.id,
                status='initializing',
                progress=0
            )
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
            try:
                update_progress(
                    task_id=process_pdf.request.id,
                    status='extracting_text',
                    progress=20
                )
                text = ''
                with open(temp_file_path, 'rb') as file:
                    pdf_reader = PdfReader(file)
                    for page in pdf_reader.pages:
                        text += page.extract_text()
                update_progress(
                    task_id=process_pdf.request.id,
                    status='generating_audio',
                    progress=40
                )
                chunks = [text[i:i+5000] for i in range(0, len(text), 5000)]
                audio_files = []
                for i, chunk in enumerate(chunks):
                    tts = gTTS(text=chunk, lang=voice['language'])
                    audio_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
                    tts.save(audio_file.name)
                    if float(audio_speed) != 1.0:
                        sound = AudioSegment.from_file(audio_file.name)
                        sound = sound.speedup(playback_speed=float(audio_speed))
                        sound.export(audio_file.name, format="mp3")
                    audio_files.append(audio_file.name)
                    progress = 40 + (i / len(chunks)) * 40
                    update_progress(
                        task_id=process_pdf.request.id,
                        status='generating_audio',
                        progress=progress
                    )
                update_progress(
                    task_id=process_pdf.request.id,
                    status='combining_audio',
                    progress=80
                )
                combined = AudioSegment.empty()
                for audio_file in audio_files:
                    combined += AudioSegment.from_mp3(audio_file)
                output_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(user_id))
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, f'{os.path.splitext(filename)[0]}.mp3')
                combined.export(output_path, format='mp3')
                for audio_file in audio_files:
                    os.unlink(audio_file)
                os.unlink(temp_file_path)
                update_progress(
                    task_id=process_pdf.request.id,
                    status='completed',
                    progress=100,
                    audio_file=output_path
                )
                return {
                    'status': 'completed',
                    'output_path': output_path,
                    'audio_file': output_path
                }
            except Exception as e:
                logger.error(f'Error processing PDF: {str(e)}')
                update_progress(
                    task_id=process_pdf.request.id,
                    status='error',
                    error=str(e)
                )
                raise
        except Exception as e:
            logger.error(f'Error in process_pdf task: {str(e)}')
            update_progress(
                task_id=process_pdf.request.id,
                status='error',
                error=str(e)
            )
            raise             raise
