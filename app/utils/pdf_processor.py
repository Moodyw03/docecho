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
    "zh-CN": {"lang": "zh-CN", "tld": "com"},
    "ja": {"lang": "ja", "tld": "co.jp"},
    "ru": {"lang": "ru", "tld": "ru"}
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

        # Add timeout/retry logic for gTTS
        max_retries = 3
        for attempt in range(max_retries):
            try:
                tts = gTTS(text, lang=voice, tld=tld)
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
    try:
        combined = AudioSegment.empty()
        for file in audio_files:
            audio = AudioSegment.from_file(file)
            combined += audio
        combined.export(output_path, format="mp3")
    except Exception as e:
        raise Exception(f"Error concatenating audio files: {e}")

def create_translated_pdf(text, output_path, language_code='en'):
    try:
        c = canvas.Canvas(output_path, pagesize=letter)
        width, height = letter
        y = height - 50
        
        c.setFont("Helvetica", 11)
        
        lines = text.split('\n')
        for line in lines:
            words = line.split()
            current_line = []
            
            for word in words:
                current_line.append(word)
                line_width = c.stringWidth(' '.join(current_line), "Helvetica", 11)
                
                if line_width > width - 100:
                    current_line.pop()
                    if current_line:
                        c.drawString(50, y, ' '.join(current_line))
                        y -= 20
                    current_line = [word]
                
                if y < 50:
                    c.showPage()
                    c.setFont("Helvetica", 11)
                    y = height - 50
            
            if current_line:
                c.drawString(50, y, ' '.join(current_line))
                y -= 20
        
        c.save()
        return output_path
    except Exception as e:
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
        logger.info(f"[{task_id}] Temp base path: {temp_path}")

        # Create temp and output directories if they don't exist (using configured paths)
        os.makedirs(temp_path, exist_ok=True)
        os.makedirs(output_path, exist_ok=True)
        
        # Save the received file_content to a temporary file
        file_path = os.path.join(temp_path, filename)
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
                # Pass temp_path to convert_text_to_audio
                futures.append(executor.submit(convert_text_to_audio, chunk, output_filename, lang_code, speed, temp_path, tld))
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
                
        # Cleanup temporary audio files
        logger.info(f"[{task_id}] Cleaning up temporary files from: {temp_path}")
        for temp_file in audio_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    # logger.debug(f"[{task_id}] Removed temp file: {temp_file}") # Optional debug logging
            except Exception as e:
                logger.warning(f"[{task_id}] Could not remove temporary file {temp_file}: {e}")

        # Force garbage collection again
        gc.collect()
        
        logger.info(f"[{task_id}] PDF processing finished successfully. Output: {final_output_path}")
        update_progress(task_id, status='Completed', progress=100)
        return final_output_path # Return the path to the final output

    except Exception as e:
        # Log the exception with traceback for better debugging
        logger.exception(f"[{task_id}] Error processing PDF {filename}: {e}") 
        # Update progress with error status
        update_progress(task_id, status=f'Error: {e}', progress=100, error=True)
        # Force garbage collection on error
        gc.collect()
        # Re-raise the exception so Celery knows the task failed
        raise 