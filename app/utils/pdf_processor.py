from PyPDF2 import PdfReader
from gtts import gTTS
from pydub import AudioSegment
from googletrans import Translator
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
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
import textwrap
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import cidfonts
from reportlab.lib.fonts import addMapping
from PIL import Image, ImageDraw, ImageFont

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
    "ja": {"lang": "ja", "tld": "co.jp"},     # Japanese - now supports PDF
    "zh-CN": {"lang": "zh-CN", "tld": "com"}, # Chinese (Simplified) - now supports PDF
    "ar": {"lang": "ar", "tld": "com", "audio_only": True},    # Arabic 
    "ko": {"lang": "ko", "tld": "co.kr"}      # Korean - now supports PDF
}

# Smaller chunk size for better processing
def extract_text_chunks_from_pdf(pdf_path, max_chunk_length=500):
    try:
        reader = PdfReader(pdf_path)
        chunks = []
        current_chunk = ''
        
        total_pages = len(reader.pages)
        for page_num, page in enumerate(reader.pages):
            # Garbage collection on every page
            gc.collect()
            
            # Extract text with more careful layout handling
            page_text = page.extract_text()
            if not page_text:
                continue
            
            # Preserve paragraph breaks for better layout and comprehension
            paragraphs = re.split(r'\n\s*\n', page_text)
            
            for paragraph in paragraphs:
                # Remove excessive whitespace but preserve line breaks for layout
                paragraph = re.sub(r'\s+', ' ', paragraph).strip()
                paragraph = paragraph.replace('\n', ' ').strip()
                
                # Split into sentences more intelligently
                sentences = re.split(r'(?<=[.!?])\s+', paragraph)
                
                for sentence in sentences:
                    if not sentence.strip():
                        continue
                        
                    # If adding this sentence would exceed max_chunk_length
                    if len(current_chunk) + len(sentence) + 2 > max_chunk_length:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence.strip() + ' '
                    else:
                        current_chunk += sentence.strip() + ' '
            
            # Add a paragraph break at the end of each page
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ''
            
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
        logger.error(f"Error extracting text from PDF: {str(e)}")
        raise Exception(f"Error extracting text from PDF: {e}")

def convert_text_to_audio(text, output_filename, voice, speed, temp_directory, tld='com', src='auto'):
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
            
            translated_text, error = translate_with_timeout(translator, text, dest=voice, src=src, timeout=30)
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
            try:
                sound = AudioSegment.from_file(temp_output)
                # Use PyDub's speedup method which doesn't require audioop
                sound = sound.speedup(playback_speed=float(speed))
                # Export to the correctly named variable
                sound.export(temp_audio_chunk_path, format="mp3") 
                if os.path.exists(temp_output):
                    os.remove(temp_output)
            except Exception as speed_err:
                logger.error(f"Error adjusting audio speed: {speed_err}. Using original audio.")
                # If speed adjustment fails, use the original audio
                os.rename(temp_output, temp_audio_chunk_path)
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
    """
    Concatenate multiple audio files into a single file with memory-efficient approach.
    For large files, uses a stream-based approach to avoid loading all audio into memory.
    """
    logger.info(f"Starting concatenation. Input files: {len(audio_files)} files, Output path: {output_path}")
    if not audio_files:
        logger.warning("Concatenation called with no audio files.")
        raise ValueError("Cannot concatenate an empty list of audio files.")
        
    try:
        # Check if the total size of audio files is large (>100MB)
        total_size = sum(os.path.getsize(f) for f in audio_files if os.path.exists(f))
        logger.info(f"Total audio size to concatenate: {total_size/1024/1024:.2f} MB")
        
        # For large files, use a more memory-efficient approach
        if total_size > 100 * 1024 * 1024:  # >100MB
            logger.info("Using memory-efficient concatenation for large files")
            
            # Get format and rate info from first file
            first_file = audio_files[0]
            info = AudioSegment.from_file(first_file)
            
            # Create a temporary directory for intermediate files
            temp_dir = tempfile.mkdtemp(prefix="audio_concat_")
            try:
                # Process files in batches of 10 to avoid memory issues
                batch_size = 10
                batch_files = []
                
                for i in range(0, len(audio_files), batch_size):
                    batch = audio_files[i:i+batch_size]
                    
                    # Create a batch output file
                    batch_output = os.path.join(temp_dir, f"batch_{i//batch_size}.mp3")
                    
                    # Combine this small batch
                    mini_combined = AudioSegment.empty()
                    for file in batch:
                        if os.path.exists(file):
                            segment = AudioSegment.from_file(file)
                            mini_combined += segment
                            # Clear segment to free memory
                            segment = None
                            gc.collect()
                    
                    # Export batch
                    mini_combined.export(batch_output, format="mp3")
                    batch_files.append(batch_output)
                    
                    # Clear mini_combined to free memory
                    mini_combined = None
                    gc.collect()
                
                # Now combine all batch files using ffmpeg directly (most efficient)
                # Create a file list for ffmpeg
                list_file = os.path.join(temp_dir, "files.txt")
                with open(list_file, 'w') as f:
                    for batch_file in batch_files:
                        f.write(f"file '{batch_file}'\n")
                
                # Use ffmpeg to concatenate without reencoding
                import subprocess
                cmd = [
                    'ffmpeg', '-y', '-f', 'concat', '-safe', '0', 
                    '-i', list_file, '-c', 'copy', output_path
                ]
                
                logger.info(f"Running ffmpeg command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    logger.error(f"FFmpeg error: {result.stderr}")
                    raise Exception(f"FFmpeg concatenation failed: {result.stderr}")
                
                logger.info(f"Successfully concatenated {len(audio_files)} files to {output_path}")
                
            finally:
                # Clean up temporary files
                try:
                    shutil.rmtree(temp_dir)
                except Exception as cleanup_err:
                    logger.warning(f"Error cleaning up temp files: {cleanup_err}")
        
        else:
            # For smaller files, use the simpler approach
            logger.info("Using standard concatenation for smaller files")
            combined = AudioSegment.empty()
            
            for i, file in enumerate(audio_files):
                try:
                    logger.debug(f"Concatenating chunk {i}: {file}")
                    
                    # Check if file exists just before loading
                    if not os.path.exists(file):
                        logger.error(f"Audio chunk file not found during concatenation: {file}")
                        continue  # Skip missing files rather than failing
                        
                    audio = AudioSegment.from_file(file)
                    combined += audio
                    
                    # Help garbage collector after each file
                    audio = None
                    if i % 10 == 0:  # Every 10 files, force garbage collection
                        gc.collect()
                        
                    logger.debug(f"Successfully added chunk {i}. Current combined duration: {len(combined)}ms")
                    
                except Exception as chunk_e:
                    logger.error(f"Error processing audio chunk {file}: {str(chunk_e)}", exc_info=True)
                    # Continue with next file instead of failing the whole process
            
            # Export the combined audio
            combined.export(output_path, format="mp3")
            logger.info(f"Successfully concatenated {len(audio_files)} files to {output_path}")
            
            # Clear memory
            combined = None
            gc.collect()
            
        return output_path
            
    except Exception as e:
        logger.error(f"Error concatenating audio files: {str(e)}", exc_info=True)
        raise Exception(f"Failed to concatenate audio files: {str(e)}")

def create_translated_pdf(text, output_path, language_code='en'):
    """
    Create a PDF with the translated text that properly preserves layout and handles non-Latin scripts.
    Uses Pillow for text rendering to ensure proper font support.
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.units import inch
    from PIL import Image, ImageDraw, ImageFont
    from io import BytesIO
    import textwrap
    import os
    
    try:
        # Define page dimensions (in pixels for PIL, 72 dpi)
        page_width, page_height = int(A4[0]), int(A4[1])
        
        # Path to fonts directory
        font_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts')
        
        # Default to Noto Sans for most languages
        font_file = os.path.join(font_path, 'NotoSans-Regular.ttf')
        font_size = 16  # Larger for PIL
        
        # Use Noto CJK for Asian languages
        if language_code in ['ja', 'zh-CN', 'ko']:
            # Use TTC font which has better CJK support
            font_file = os.path.join(font_path, 'NotoSansCJK-Regular.ttc')
        
        # Check if font file exists
        if not os.path.exists(font_file):
            logger.warning(f"Font file not found: {font_file}, using system default")
            # Use system default
            font = ImageFont.load_default()
        else:
            try:
                # Try to load the font
                # For TTC files, we need to specify the index
                font_index = 0
                if language_code == 'ja':
                    font_index = 0  # Japanese
                elif language_code == 'zh-CN':
                    font_index = 1  # Simplified Chinese
                elif language_code == 'ko':
                    font_index = 2  # Korean
                
                if font_file.endswith('.ttc'):
                    font = ImageFont.truetype(font_file, size=font_size, index=font_index)
                else:
                    font = ImageFont.truetype(font_file, size=font_size)
                
                logger.info(f"Using font {font_file} for {language_code}")
            except Exception as e:
                logger.warning(f"Error loading font: {e}, using system default")
                font = ImageFont.load_default()
        
        # Set margins
        left_margin = 72  # 1 inch in pixels
        right_margin = page_width - 72
        top_margin = 72
        bottom_margin = page_height - 72
        text_width = right_margin - left_margin
        
        # Split text into paragraphs
        paragraphs = text.split('\n\n')
        
        # Create list to store page images
        pages = []
        
        # Current position on page
        y_position = top_margin
        
        # Create a new page image
        current_page = Image.new('RGB', (page_width, page_height), color='white')
        draw = ImageDraw.Draw(current_page)
        
        for paragraph in paragraphs:
            # Skip empty paragraphs
            if not paragraph.strip():
                continue
                
            # Wrap text to fit within margins
            paragraph = paragraph.replace('\n', ' ').strip()
            wrapped_lines = textwrap.wrap(paragraph, width=int(text_width/10))  # Approximate character count
            
            # Check if we need a new page
            if y_position + (len(wrapped_lines) * (font_size + 4)) > bottom_margin:
                # Save current page
                pages.append(current_page)
                # Create new page
                current_page = Image.new('RGB', (page_width, page_height), color='white')
                draw = ImageDraw.Draw(current_page)
                y_position = top_margin
            
            # Add each line of the wrapped paragraph
            for line in wrapped_lines:
                if y_position + font_size > bottom_margin:
                    # Save current page
                    pages.append(current_page)
                    # Create new page
                    current_page = Image.new('RGB', (page_width, page_height), color='white')
                    draw = ImageDraw.Draw(current_page)
                    y_position = top_margin
                
                # Draw text
                draw.text((left_margin, y_position), line, font=font, fill='black')
                y_position += font_size + 4  # Add line spacing
            
            # Add some space between paragraphs
            y_position += (font_size + 4) // 2
        
        # Add the last page
        if current_page:
            pages.append(current_page)
        
        # Create PDF from images
        if pages:
            # Save the first page as PDF
            pages[0].save(
                output_path, 
                save_all=True, 
                append_images=pages[1:] if len(pages) > 1 else [],
                resolution=72.0,
                quality=95,
                format='PDF'
            )
            logger.info(f"Created translated PDF at {output_path}")
            return output_path
        else:
            raise Exception("No pages were created")
        
    except Exception as e:
        logger.error(f"Error creating PDF: {str(e)}")
        # Create a simple fallback PDF with just the text
        try:
            with open(output_path, 'wb') as f:
                c = canvas.Canvas(f, pagesize=letter)
                c.setFont('Helvetica', 10)
                c.drawString(72, 800, "Error creating formatted PDF. Here is the plain text:")
                
                # Split text into smaller chunks
                chunks = [text[i:i+100] for i in range(0, len(text), 100)]
                y = 780
                for chunk in chunks[:200]:  # Limit to first 200 chunks to avoid massive PDFs
                    if y < 50:
                        c.showPage()
                        y = 800
                    c.drawString(72, y, chunk)
                    y -= 12
                
                c.save()
                logger.info(f"Created fallback PDF at {output_path}")
                return output_path
        except Exception as fallback_error:
            logger.error(f"Failed to create fallback PDF: {str(fallback_error)}")
            raise

# Helper function for translation with timeout
def translate_with_timeout(translator, text, dest, timeout=10, src='auto'):
    result = None
    error = None
    
    def translate_task():
        nonlocal result, error
        try:
            # Wait if we're about to hit rate limits
            translate_rate_limiter.wait_if_needed()
            
            # Now make the translation request with source language
            result = translator.translate(text, src=src, dest=dest).text
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
        temp_file_path = None
        audio_files = []
        output_path = None
        pdf_output_path = None
        
        try:
            # Initialize progress
            update_progress(
                task_id=process_pdf.request.id,
                status='initializing',
                progress=0
            )
            
            # Save incoming PDF to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name
                
            # Create temporary directory for processing chunks
            temp_dir = tempfile.mkdtemp(prefix="docecho_")
            
            try:
                # Extract text in chunks to preserve memory
                update_progress(
                    task_id=process_pdf.request.id,
                    status='extracting_text',
                    progress=10
                )
                
                # Use improved chunking function that preserves layout and handles larger files
                text_chunks = extract_text_chunks_from_pdf(temp_file_path, max_chunk_length=1000)
                
                # Combine chunks for translation but maintain structure
                full_text = '\n\n'.join(text_chunks)
                
                # Add translation step here
                update_progress(
                    task_id=process_pdf.request.id,
                    status='translating_text',
                    progress=30
                )
                
                # Only translate if the language is not English
                language_code = voice['language']
                translated_chunks = []
                
                # Get TLD for gTTS
                tld = language_map.get(language_code, {}).get('tld', 'com')
                
                # Detect source language for better translation
                source_language = 'auto'
                detected = False
                
                # Get the first substantial chunk to try to detect language
                detection_text = ""
                for chunk in text_chunks:
                    if len(chunk.strip()) > 50:
                        detection_text = chunk
                        break
                
                # Try to detect the source language
                if detection_text:
                    try:
                        detector = Translator()
                        detection = detector.detect(detection_text)
                        if detection and hasattr(detection, 'lang'):
                            source_language = detection.lang
                            detected = True
                            logger.info(f"Detected source language: {source_language}")
                    except Exception as detect_err:
                        logger.warning(f"Language detection failed: {detect_err}")
                
                # Determine if translation is needed
                needs_translation = True
                
                # If target is English and source is also English, no translation needed
                if language_code == 'en' and (source_language == 'en' or not detected):
                    needs_translation = False
                    logger.info("Source text appears to be in English, skipping translation to English")
                
                # Only perform translation if needed
                if needs_translation:
                    # For larger texts, break into smaller parts for translation
                    # This helps with API limits and improves reliability
                    max_translate_length = 10000  # Characters per translation request
                    full_translated_text = ""
                    
                    for i, chunk in enumerate(text_chunks):
                        try:
                            translator = Translator()
                            chunk_translated, error = translate_with_timeout(
                                translator, 
                                chunk, 
                                dest=language_code, 
                                src=source_language,
                                timeout=60
                            )
                            
                            if error:
                                logger.warning(f"Translation error for chunk {i}: {error}. Using original text.")
                                translated_chunks.append(chunk)
                            else:
                                translated_chunks.append(chunk_translated)
                                
                            # Update progress based on translation progress
                            progress = 30 + (i / len(text_chunks)) * 20
                            update_progress(
                                task_id=process_pdf.request.id,
                                status='translating_text',
                                progress=progress
                            )
                            
                            # Help with garbage collection
                            gc.collect()
                            
                        except Exception as e:
                            logger.error(f"Error during translation of chunk {i}: {str(e)}")
                            translated_chunks.append(chunk)  # Fallback to original text for this chunk
                    
                    # Join translated chunks for full text
                    full_translated_text = '\n\n'.join(translated_chunks)
                else:
                    # If no translation needed, use original chunks
                    logger.info("Skipping translation, using original text")
                    translated_chunks = text_chunks
                    full_translated_text = full_text
                
                update_progress(
                    task_id=process_pdf.request.id,
                    status='generating_audio',
                    progress=50
                )
                
                # Process audio in smaller chunks to prevent memory issues
                audio_files = []
                audio_chunk_size = 3000  # Characters per audio chunk
                
                # Split translated text into audio-sized chunks
                audio_text_chunks = []
                for chunk in translated_chunks:
                    # Further split large chunks for audio processing
                    if len(chunk) > audio_chunk_size:
                        # Split at sentence boundaries where possible
                        sentences = re.split(r'(?<=[.!?])\s+', chunk)
                        current_audio_chunk = ""
                        
                        for sentence in sentences:
                            if len(current_audio_chunk) + len(sentence) > audio_chunk_size:
                                if current_audio_chunk:
                                    audio_text_chunks.append(current_audio_chunk)
                                current_audio_chunk = sentence
                            else:
                                if current_audio_chunk:
                                    current_audio_chunk += " " + sentence
                                else:
                                    current_audio_chunk = sentence
                                    
                        if current_audio_chunk:
                            audio_text_chunks.append(current_audio_chunk)
                    else:
                        audio_text_chunks.append(chunk)
                
                # Generate audio for each chunk with retry mechanism
                for i, chunk in enumerate(audio_text_chunks):
                    # Skip empty chunks
                    if not chunk.strip():
                        continue
                        
                    # Try up to 3 times to generate audio
                    max_retries = 3
                    retry_count = 0
                    chunk_file_path = None
                    
                    while retry_count < max_retries:
                        try:
                            # Generate temporary filename
                            temp_audio_file = f"chunk_{i}.mp3"
                            
                            # Convert text to audio with improved memory handling
                            chunk_file_path = convert_text_to_audio(
                                chunk, 
                                temp_audio_file,
                                language_code, 
                                float(audio_speed),
                                temp_dir,
                                tld,
                                src=source_language
                            )
                            
                            if os.path.exists(chunk_file_path):
                                audio_files.append(chunk_file_path)
                                break  # Success, exit retry loop
                            else:
                                raise Exception(f"Audio file was not created")
                                
                        except Exception as e:
                            retry_count += 1
                            logger.error(f"Error generating audio for chunk {i} (attempt {retry_count}): {str(e)}")
                            time.sleep(1)  # Brief pause before retry
                            
                            if retry_count >= max_retries:
                                logger.warning(f"Failed to generate audio for chunk {i} after {max_retries} attempts")
                                # Continue with next chunk instead of failing entire job
                    
                    # Update progress
                    progress = 50 + (i / len(audio_text_chunks)) * 30
                    update_progress(
                        task_id=process_pdf.request.id,
                        status='generating_audio',
                        progress=progress
                    )
                    
                    # Help garbage collection
                    gc.collect()
                
                # Check if we have any audio files to combine
                if not audio_files:
                    raise Exception("No audio chunks were successfully created")
                
                update_progress(
                    task_id=process_pdf.request.id,
                    status='combining_audio',
                    progress=80
                )
                
                # Setup output directory
                output_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(user_id))
                os.makedirs(output_dir, exist_ok=True)
                
                # Combine audio files
                output_path = os.path.join(output_dir, f'{os.path.splitext(filename)[0]}.mp3')
                
                try:
                    # Use improved memory-efficient audio combining
                    concatenate_audio_files(audio_files, output_path)
                except Exception as e:
                    logger.error(f"Error combining audio files: {str(e)}")
                    
                    # Fallback method if concatenation fails
                    try:
                        combined = AudioSegment.empty()
                        for audio_file in audio_files:
                            if os.path.exists(audio_file):
                                segment = AudioSegment.from_mp3(audio_file)
                                combined += segment
                                # Clear memory after each file is processed
                                segment = None
                                gc.collect()
                        
                        combined.export(output_path, format='mp3')
                        combined = None  # Clear memory
                        gc.collect()
                    except Exception as fallback_error:
                        logger.error(f"Fallback audio combining also failed: {str(fallback_error)}")
                        raise
                
                # Clean up temporary audio files
                for audio_file in audio_files:
                    try:
                        if os.path.exists(audio_file):
                            os.unlink(audio_file)
                    except Exception as e:
                        logger.warning(f"Failed to delete temporary audio file {audio_file}: {str(e)}")
                
                # Save the output files to Redis for download
                if output_format == 'audio' or output_format == 'both':
                    save_file_to_redis(output_path, process_pdf.request.id, 'audio')
                
                # Handle PDF output if requested
                if output_format == 'pdf' or output_format == 'both':
                    pdf_output_path = os.path.join(output_dir, f'{os.path.splitext(filename)[0]}.pdf')
                    try:
                        # Use translated text for PDF creation with improved layout
                        create_translated_pdf(full_translated_text, pdf_output_path, language_code)
                        save_file_to_redis(pdf_output_path, process_pdf.request.id, 'pdf')
                    except Exception as e:
                        logger.error(f"Error creating PDF: {str(e)}")
                        # Continue execution even if PDF fails
                
                update_progress(
                    task_id=process_pdf.request.id,
                    status='completed',
                    progress=100,
                    audio_file=output_path
                )
                
                # Clean up temporary files
                if temp_file_path and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                
                # Clean up temp directory
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp directory {temp_dir}: {str(e)}")
                
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
            
            # Clean up any temporary files
            try:
                if temp_file_path and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                
                # Clean up any orphaned audio chunks
                for audio_file in audio_files:
                    if os.path.exists(audio_file):
                        os.unlink(audio_file)
                        
                # Clean up temp directory if it exists
                if 'temp_dir' in locals() and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except Exception as cleanup_err:
                logger.error(f"Error during cleanup: {str(cleanup_err)}")
                
            raise
