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

# Add logger instance
logger = logging.getLogger(__name__)

# Mapping language codes and TLDs for accents
language_map = {
    "en": {"lang": "en", "tld": "com"},
    "en-uk": {"lang": "en", "tld": "co.uk"},
    "pt": {"lang": "pt", "tld": "com.br"},
    "es": {"lang": "es", "tld": "com"},
    "fr": {"lang": "fr", "tld": "fr"},
    "de": {"lang": "de", "tld": "de"},
    "it": {"lang": "it", "tld": "it"},
    "zh-CN": {"lang": "zh-CN", "tld": "com", "problematic": True},
    "ja": {"lang": "ja", "tld": "co.jp", "problematic": True},
    "ru": {"lang": "ru", "tld": "ru"},
    "ar": {"lang": "ar", "tld": "com.sa", "problematic": True},    # Arabic
    "hi": {"lang": "hi", "tld": "co.in", "problematic": True},     # Hindi
    "ko": {"lang": "ko", "tld": "co.kr", "problematic": True},     # Korean
    "tr": {"lang": "tr", "tld": "com.tr"},    # Turkish
    "nl": {"lang": "nl", "tld": "nl"},        # Dutch
    "pl": {"lang": "pl", "tld": "pl"}         # Polish
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
            "zh-CN": {
                "needs_special_font": True, 
                "font_family": "SimSun", 
                "fallback": "Helvetica",
                "message": "Chinese characters may not render correctly due to font limitations."
            },
            "ja": {
                "needs_special_font": True, 
                "font_family": "HeiseiMin-W3", 
                "fallback": "Helvetica",
                "message": "Japanese characters may not render correctly due to font limitations."
            },
            "ko": {
                "needs_special_font": True, 
                "font_family": "Malgun Gothic", 
                "fallback": "Helvetica",
                "message": "Korean characters may not render correctly due to font limitations."
            },
            "ar": {
                "needs_special_font": True, 
                "font_family": "Arial Unicode MS", 
                "fallback": "Helvetica", 
                "rtl": True,
                "message": "Arabic text requires right-to-left rendering which is not fully supported. Characters may appear in reverse order."
            },
            "hi": {
                "needs_special_font": True, 
                "font_family": "Arial Unicode MS", 
                "fallback": "Helvetica",
                "message": "Hindi/Devanagari script may not render correctly due to font limitations."
            }
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
            result = translator.translate(text, dest=dest).text
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

@celery.task(bind=True)
def process_pdf(self, filename, file_content, voice, speed, output_format, output_path, temp_path):
    # Use self.request.id as the task_id
    task_id = self.request.id
    try:
        # ADD DELAY: Introduce a small delay to allow filesystem sync
        time.sleep(2) 
        logger.info(f"[{task_id}] Woke up after delay.")
        
        # Force garbage collection at start
        gc.collect()
        logger.info(f"[{task_id}] Starting PDF processing for: {filename}")
        logger.info(f"[{task_id}] Output base path: {output_path}")
        
        # Create a unique temp directory for this task using the task_id
        task_temp_path = os.path.join(temp_path, task_id)
        logger.info(f"[{task_id}] Task-specific temp path: {task_temp_path}")
        
        # Create temp and output directories if they don't exist (using configured paths)
        os.makedirs(task_temp_path, exist_ok=True)
        os.makedirs(output_path, exist_ok=True)
        
        # Save the received file_content to a temporary file
        file_path = os.path.join(task_temp_path, filename)
        logger.info(f"[{task_id}] Saving received file content ({len(file_content)} bytes) to: {file_path}")
        
        with open(file_path, 'wb') as f:
            f.write(file_content)
            # Ensure file is written to disk
            f.flush()
            os.fsync(f.fileno())
        
        # Check if file was successfully saved
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            logger.info(f"[{task_id}] File successfully saved, size: {file_size} bytes")
        else:
            raise Exception(f"Failed to save file content to {file_path}")

        update_progress(task_id, status='Extracting text from PDF...', progress=0)
        text_chunks = extract_text_chunks_from_pdf(file_path)
        total_chunks = len(text_chunks)

        if total_chunks == 0:
            raise Exception("No text could be extracted from the PDF")

        logger.info(f"[{task_id}] Extracted {total_chunks} text chunks.")
        # Use the original translator
        translator = Translator()
        audio_files = []

        # Use ThreadPoolExecutor for parallel audio conversion
        # Define max workers based on CPU or a fixed number
        max_workers = min(8, os.cpu_count() or 1) 
        logger.info(f"[{task_id}] Using {max_workers} workers for audio conversion.")

        # Pass the correct tld based on the voice
        lang_details = language_map.get(voice, {"lang": voice, "tld": "com"})
        tld = lang_details['tld']
        lang_code = lang_details['lang'] # Use this for gTTS lang parameter

        # Process chunks in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for i, chunk in enumerate(text_chunks):
                 # Check if chunk is empty or whitespace
                if not chunk or chunk.isspace():
                    logger.warning(f"[{task_id}] Skipping empty chunk {i}.")
                    continue
                
                # Submit task to convert text to audio
                output_filename=f"chunk_{i}.mp3"
                # Pass task_temp_path instead of temp_path to convert_text_to_audio
                futures.append(executor.submit(convert_text_to_audio, chunk, output_filename, lang_code, speed, task_temp_path, tld))
                time.sleep(0.1) # Small delay to avoid overwhelming API/System

            # Collect results as they complete
            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                try:
                    audio_chunk_path = future.result()
                    if audio_chunk_path:
                        audio_files.append(audio_chunk_path)
                        progress = int(((i + 1) / total_chunks) * 90) # Progress up to 90%
                        update_progress(task_id, status=f"Processing chunk {i+1}/{total_chunks}...", progress=progress)
                    else:
                         logger.warning(f"[{task_id}] Chunk {i} conversion resulted in None path.")
                except Exception as e:
                    logger.error(f"[{task_id}] Error processing chunk {i}: {e}")
                    # Decide if you want to stop the whole task or just skip this chunk
                    # For now, log error and continue
                    update_progress(task_id, status=f"Error processing chunk {i+1}, skipping...", progress=progress)


        # Sort audio files based on chunk index to ensure correct order
        audio_files.sort(key=lambda f: int(os.path.basename(f).split('_')[1].split('.')[0]))
        logger.info(f"[{task_id}] Number of successfully converted audio chunks: {len(audio_files)}")

        if not audio_files and output_format == 'audio':
             raise Exception("No audio chunks were successfully converted.")

        # Initialize final_output_path to avoid "referenced before assignment" error
        final_output_path = None

        if output_format == 'audio':
            update_progress(task_id, status='Concatenating audio files...', progress=90)
            # Construct final path using output_path directly
            final_output_path = os.path.join(output_path, f"{os.path.splitext(filename)[0]}.mp3")
            logger.info(f"[{task_id}] Concatenating audio to: {final_output_path}")
            concatenate_audio_files(audio_files, final_output_path)
        elif output_format == 'text':
            update_progress(task_id, status='Generating text file...', progress=90)
            # Construct final path using output_path directly
            final_output_path = os.path.join(output_path, f"{os.path.splitext(filename)[0]}.txt")
            logger.info(f"[{task_id}] Writing text file to: {final_output_path}")
            full_text = '\n'.join(text_chunks)
            with open(final_output_path, 'w', encoding='utf-8') as f:
                f.write(full_text)
        elif output_format == 'pdf':
            update_progress(task_id, status='Translating text and creating PDF...', progress=90)
            # Construct final path using output_path directly
            final_output_path = os.path.join(output_path, f"{os.path.splitext(filename)[0]}_translated.pdf")
            logger.info(f"[{task_id}] Writing translated PDF to: {final_output_path}")

            full_text = '\n'.join(text_chunks)
            
            # Translate the entire text at once - consider chunking if too large
            try:
                update_progress(task_id, status='Translating text...', progress=92)
                # Use the language code extracted from the map
                translated_text, error = translate_with_timeout(translator, full_text, dest=lang_code, timeout=180) # Increased timeout
                if error:
                    raise Exception(f"Translation failed: {error}")
                if not translated_text:
                    raise Exception("Translation returned empty result.")

                update_progress(task_id, status='Creating translated PDF...', progress=95)
                create_translated_pdf(translated_text, final_output_path, language_code=lang_code)

            except Exception as e:
                logger.error(f"[{task_id}] Error during PDF translation/creation: {e}")
                raise Exception(f"Failed to create translated PDF: {e}")
        elif output_format == 'both':
            # First create audio file
            update_progress(task_id, status='Concatenating audio files...', progress=70)
            audio_path = os.path.join(output_path, f"{os.path.splitext(filename)[0]}.mp3")
            logger.info(f"[{task_id}] Concatenating audio to: {audio_path}")
            concatenate_audio_files(audio_files, audio_path)
            
            # Always set at least one final output path after audio is created
            final_output_path = audio_path
            
            # Then create PDF
            update_progress(task_id, status='Translating text and creating PDF...', progress=80)
            pdf_path = os.path.join(output_path, f"{os.path.splitext(filename)[0]}_translated.pdf")
            logger.info(f"[{task_id}] Writing translated PDF to: {pdf_path}")
            
            full_text = '\n'.join(text_chunks)
            
            try:
                update_progress(task_id, status='Translating text...', progress=85)
                translated_text, error = translate_with_timeout(translator, full_text, dest=lang_code, timeout=180)
                if error:
                    raise Exception(f"Translation failed: {error}")
                if not translated_text:
                    raise Exception("Translation returned empty result.")
                
                update_progress(task_id, status='Creating translated PDF...', progress=95)
                create_translated_pdf(translated_text, pdf_path, language_code=lang_code)
                final_output_path = pdf_path  # Update the final path to the PDF once created
            except Exception as e:
                # Even if PDF creation fails, we have already set final_output_path to audio_path
                logger.error(f"[{task_id}] Error during PDF translation/creation: {e}")
                update_progress(task_id, status=f"Warning: Audio created but PDF failed: {e}", progress=95, has_error=True)
                # Don't raise the exception as we still have an audio file to return
                
        # Cleanup temporary audio files
        logger.info(f"[{task_id}] Cleaning up temporary files from: {task_temp_path}")
        for temp_file in audio_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    # logger.debug(f"[{task_id}] Removed temp file: {temp_file}") # Optional debug logging
            except Exception as e:
                logger.warning(f"[{task_id}] Could not remove temporary file {temp_file}: {e}")

        # Clean up the task-specific temp directory
        try:
            import shutil
            if os.path.exists(task_temp_path):
                shutil.rmtree(task_temp_path)
                logger.info(f"[{task_id}] Removed task-specific temp directory: {task_temp_path}")
        except Exception as e:
            logger.warning(f"[{task_id}] Could not remove task-specific temp directory {task_temp_path}: {e}")

        # Force garbage collection again
        gc.collect()
        
        # Check if final_output_path was assigned properly
        if final_output_path is None:
            error_msg = f"No output file was created. Format: {output_format}"
            logger.error(f"[{task_id}] {error_msg}")
            update_progress(task_id, status=f'Error: {error_msg}', progress=100, error=True)
            raise Exception(error_msg)
        
        logger.info(f"[{task_id}] PDF processing finished successfully. Output: {final_output_path}")
        
        # --- Post-processing: Save to Redis/S3 & Update Progress --- 
        logger.info(f"[{task_id}] Task completed locally. Preparing for Redis/S3 storage and final progress update.")

        final_file_paths = {}
        # Default final status
        final_task_status = 'Completed' 

        if output_format == 'audio' and final_output_path and os.path.exists(final_output_path):
            final_file_paths['audio'] = final_output_path
        elif output_format == 'pdf' and final_output_path and os.path.exists(final_output_path):
            final_file_paths['pdf'] = final_output_path
        elif output_format == 'text' and final_output_path and os.path.exists(final_output_path):
            final_file_paths['text'] = final_output_path
        elif output_format == 'both':
            audio_path = os.path.join(output_path, f"{os.path.splitext(filename)[0]}.mp3")
            pdf_path = os.path.join(output_path, f"{os.path.splitext(filename)[0]}_translated.pdf")
            # Check if audio exists (it should if we got here)
            if os.path.exists(audio_path):
                final_file_paths['audio'] = audio_path
            else: # Should not happen if logic before is correct, but handle defensively
                 logger.error(f"[{task_id}] 'both' format: Audio path {audio_path} not found unexpectedly.")
                 # If audio failed, the whole task should probably error out
                 raise FileNotFoundError(f"Audio file missing in 'both' format: {audio_path}")
                 
            # Check if PDF exists
            if os.path.exists(pdf_path):
                 final_file_paths['pdf'] = pdf_path
                 # Status remains 'Completed' if both exist
            else:
                 # If PDF doesn't exist, set warning status
                 logger.warning(f"[{task_id}] 'both' format: PDF path {pdf_path} not found. Setting status to Warning.")
                 final_task_status = 'Warning: Audio created, PDF failed'
                 # We still proceed to save the audio file

        # Ensure we have at least one file path if status is not Warning
        if not final_file_paths and not final_task_status.startswith('Warning'):
             error_msg = f"No output file paths found for format '{output_format}' despite successful processing steps and no warning status."
             logger.error(f"[{task_id}] {error_msg}")
             update_progress(task_id, status=f'Error: {error_msg}', progress=100, error=True)
             raise Exception(error_msg)

        # --- Save to Redis and/or S3 --- 
        redis_saved_types = []
        s3_remote_urls = {}

        for file_type, local_path in final_file_paths.items():
            logger.info(f"[{task_id}] Processing storage for {file_type} file: {local_path}")
            # 1. Attempt S3 Upload (if configured)
            remote_url = None
            try:
                logger.info(f"[{task_id}] Attempting S3 upload for {local_path}")
                remote_url = copy_to_remote_storage(local_path, f"{task_id}/{os.path.basename(local_path)}")
                if remote_url:
                    s3_remote_urls[file_type] = remote_url
                    logger.info(f"[{task_id}] S3 Upload successful for {file_type}: {remote_url}")
                else:
                    logger.info(f"[{task_id}] S3 upload skipped or failed for {file_type} (not configured or error).")
            except Exception as e:
                logger.error(f"[{task_id}] Error uploading {file_type} to S3: {str(e)}", exc_info=True)

            # 2. Save to Redis (always attempt as fallback or primary if no S3)
            try:
                logger.info(f"[{task_id}] Saving {file_type} content to Redis: {local_path}")
                redis_saved = save_file_to_redis(local_path, task_id, file_type)
                if redis_saved:
                    redis_saved_types.append(file_type)
                    logger.info(f"[{task_id}] Successfully saved {file_type} content to Redis.")
                else:
                    logger.warning(f"[{task_id}] Failed to save {file_type} content to Redis.")
            except Exception as e:
                 logger.error(f"[{task_id}] Error saving {file_type} to Redis: {str(e)}", exc_info=True)

        # --- Final Progress Update --- 
        # Use the determined final_task_status
        final_progress_data = {
            'status': final_task_status, # Use the determined status
            'progress': 100,
            'redis_saved': redis_saved_types, # Indicate which types are in Redis
        }
        if s3_remote_urls:
             final_progress_data['remote_urls'] = s3_remote_urls
             if 'audio' in s3_remote_urls:
                 final_progress_data['remote_audio_url'] = s3_remote_urls['audio']
             if 'pdf' in s3_remote_urls:
                  final_progress_data['remote_pdf_url'] = s3_remote_urls['pdf']
             final_progress_data['remote_file_url'] = next(iter(s3_remote_urls.values()), None)
        
        # Check if *anything* was successfully stored, but only error out if status wasn't already Warning
        if not redis_saved_types and not s3_remote_urls and not final_task_status.startswith('Warning'):
            error_msg = f"Failed to save output to Redis or S3 for task {task_id}."
            logger.error(f"[{task_id}] {error_msg}")
            # Overwrite status to Error
            final_progress_data['status'] = 'Error: Storage Failed' 
            final_progress_data['error'] = error_msg
            update_progress(task_id, **final_progress_data)
            raise Exception(error_msg)
            
        update_progress(task_id, **final_progress_data)
        logger.info(f"[{task_id}] Final progress update (no local paths): {final_progress_data}")

        # --- Cleanup Local Files --- 
        logger.info(f"[{task_id}] Cleaning up local output files.")
        for file_type, local_path in final_file_paths.items():
            try:
                 if os.path.exists(local_path):
                     os.remove(local_path)
                     logger.info(f"[{task_id}] Removed local file: {local_path}")
            except Exception as e:
                 logger.warning(f"[{task_id}] Could not remove local output file {local_path}: {e}")
                 
        # Return success indication (no path needed anymore)
        return {"status": "success", "redis_saved": redis_saved_types, "s3_urls": s3_remote_urls}

    except Exception as e:
        # Log the exception with traceback for better debugging
        logger.exception(f"[{task_id}] Error processing PDF {filename}: {e}") 
        # Update progress with error status - Use str(e) for the message
        update_progress(task_id, status=f'Error: {str(e)}', progress=100, error=True)
        # Force garbage collection on error
        gc.collect()
        # Re-raise the exception so Celery knows the task failed
        raise 