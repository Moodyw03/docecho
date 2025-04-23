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

def convert_text_to_audio(text, output_filename, voice, speed, tld='com'):
    try:
        temp_dir = os.path.join(os.getcwd(), 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        temp_output = os.path.join(temp_dir, output_filename.replace(".mp3", "_temp.mp3"))
        output_path = os.path.join(temp_dir, output_filename)
        
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
            sound.export(output_path, format="mp3")
            if os.path.exists(temp_output):
                os.remove(temp_output)
        else:
            os.rename(temp_output, output_path)

        return output_path
    except Exception as e:
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
def process_pdf(self, filename, file_path, voice, speed, output_format, output_path):
    # Use self.request.id as the task_id
    task_id = self.request.id
    try:
        # Force garbage collection at start
        gc.collect()
        logger.info(f"[{task_id}] Starting PDF processing for: {filename}")

        # Create temp and output directories
        output_dir = os.path.dirname(output_path)
        temp_dir = os.path.join(output_dir, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        update_progress(task_id, status='Extracting text from PDF...', progress=0)
        text_chunks = extract_text_chunks_from_pdf(file_path)
        total_chunks = len(text_chunks)

        if total_chunks == 0:
            raise Exception("No text could be extracted from the PDF")

        logger.info(f"[{task_id}] Extracted {total_chunks} text chunks.")
        # Use the original translator
        translator = Translator()
        # Reduce batch size for better memory management
        batch_size = 2
        audio_chunks = []
        translated_text = []
        
        lang_settings = language_map.get(voice, {"lang": "en", "tld": "com"})
        
        for batch_start in range(0, total_chunks, batch_size):
            # Garbage collection between batches
            gc.collect()
            
            batch_end = min(batch_start + batch_size, total_chunks)
            batch = text_chunks[batch_start:batch_end]
            
            # Track if this is the last batch
            is_last_batch = batch_end == total_chunks
            
            for i, chunk in enumerate(batch):
                chunk_index = batch_start + i
                is_last_chunk = (chunk_index == total_chunks - 1)
                overall_progress = int((chunk_index / total_chunks) * 100)
                
                # More detailed status reporting
                chunk_message = f'Processing chunk {chunk_index + 1} of {total_chunks}'
                if is_last_chunk:
                    chunk_message += ' (final chunk)'
                
                logger.info(f"[{task_id}] {chunk_message}")

                update_progress(
                    task_id,
                    status=chunk_message,
                    progress=overall_progress
                )

                try:
                    # Add delay to avoid API rate limits
                    time.sleep(1)  # Increased from 0.5
                    
                    logger.info(f"[{task_id}] Translating chunk {chunk_index + 1}...")
                    # Use the timeout version of translate
                    translated_chunk, error = translate_with_timeout(
                        translator, 
                        chunk, 
                        lang_settings["lang"],
                        timeout=15  # 15 second timeout for translation
                    )
                    
                    # Handle translation error/timeout
                    if error:
                        logger.error(f"[{task_id}] Translation error on chunk {chunk_index + 1}: {str(error)}")
                        # Fallback for translation failure
                        translated_chunk = chunk  # Use original text as fallback
                        update_progress(
                            task_id,
                            status=f'Warning: Using original text for chunk {chunk_index + 1} (translation failed)',
                            progress=overall_progress
                        )
                        logger.info(f"[{task_id}] Translation successful for chunk {chunk_index + 1}.")
                    
                    # Add extra timeout after the last chunk translation
                    if is_last_chunk:
                        time.sleep(1)  # Extra delay for last chunk
                    
                    translated_text.append(translated_chunk)
                    
                    # Clear the original chunk from memory
                    chunk = None
                    
                    if output_format in ["audio", "both"]:
                        # Add delay to avoid gTTS API rate limits
                        time.sleep(1)  # Increased from 0.5
                        
                        chunk_filename = f"{task_id}_chunk_{chunk_index}.mp3"
                        
                        logger.info(f"[{task_id}] Converting chunk {chunk_index + 1} to audio...")
                        # Add timeout handling for audio conversion
                        try:
                            audio_chunk_path = convert_text_to_audio(
                                translated_chunk,
                                chunk_filename,
                                lang_settings["lang"],
                                speed,
                                lang_settings["tld"]
                            )
                            audio_chunks.append(audio_chunk_path)
                            logger.info(f"[{task_id}] Audio conversion successful for chunk {chunk_index + 1}.")
                            
                            # Extra delay after the last chunk audio conversion
                            if is_last_chunk:
                                time.sleep(1)  # Extra delay for last chunk
                                
                        except Exception as audio_error:
                            logger.error(f"[{task_id}] Audio conversion error on chunk {chunk_index + 1}: {str(audio_error)}")
                            # Continue without this audio chunk
                            update_progress(
                                task_id,
                                status=f'Warning: Skipped audio for chunk {chunk_index + 1} due to error',
                                progress=overall_progress
                            )
                            continue
                        
                        # Clear the translated chunk to free memory
                        translated_chunk = None
                        
                        # Garbage collection after each audio processing
                        gc.collect()

                except Exception as e:
                    # Log error but continue
                    logger.error(f"[{task_id}] Error processing chunk {chunk_index + 1}: {str(e)}", exc_info=True)
                    # Update progress to show error on specific chunk
                    update_progress(
                        task_id,
                        status=f'Error on chunk {chunk_index + 1}: {str(e)[:50]}...',
                        progress=overall_progress
                    )
                    # Add delay before continuing to next chunk
                    time.sleep(2)  # Increased from 1
                    continue
            
            # Clean up batch to free memory
            batch = None
            gc.collect()
            
            # Add checkpoint progress update after each batch
            update_progress(
                task_id,
                status=f'Completed batch {batch_end}/{total_chunks}',
                progress=int((batch_end / total_chunks) * 100)
            )
            
            # Add a small delay between batches to prevent API overload
            time.sleep(2)

        # Handle PDF output
        if output_format in ["pdf", "both"]:
            # Free up some memory before PDF generation
            gc.collect()
            logger.info(f"[{task_id}] Starting PDF creation...")
            
            update_progress(task_id, status='Creating PDF file...', progress=95)
            
            base_filename = os.path.splitext(os.path.basename(filename))[0]
            pdf_filename = f"{base_filename}_translated_{task_id}.pdf"
            pdf_path = os.path.join(output_dir, pdf_filename)
            
            try:
                create_translated_pdf('\n'.join(translated_text), pdf_path, lang_settings["lang"])
                logger.info(f"[{task_id}] PDF creation successful: {pdf_path}")
                
                # Update progress with PDF path
                update_data = {
                    'pdf_file': pdf_path,
                    'status': 'completed',
                    'progress': 100
                }
                
                # Add PDF path if both formats requested
                if output_format == "both" and 'pdf_path' in locals():
                    update_data['pdf_file'] = pdf_path
                    
                update_progress(task_id, **update_data)
            except Exception as pdf_error:
                logger.error(f"[{task_id}] PDF creation error: {str(pdf_error)}", exc_info=True)
                update_progress(task_id, status=f'PDF creation failed: {str(pdf_error)[:50]}...', progress=95)
            
        # Handle audio output
        if audio_chunks and output_format in ["audio", "both"]:
            # Free up memory before audio concatenation
            gc.collect()
            logger.info(f"[{task_id}] Starting audio concatenation...")
            
            update_progress(task_id, status='Finalizing audio...', progress=98)
            
            try:
                concatenate_audio_files(audio_chunks, output_path)
                logger.info(f"[{task_id}] Audio concatenation successful: {output_path}")
                
                # Always update with audio path first
                update_data = {
                    'audio_file': output_path,
                    'status': 'completed',
                    'progress': 100
                }
                
                # Add PDF path if both formats requested
                if output_format == "both" and 'pdf_path' in locals():
                    update_data['pdf_file'] = pdf_path
                    
                update_progress(task_id, **update_data)
                
                # Clean up temporary files
                for chunk in audio_chunks:
                    if os.path.exists(chunk):
                        os.remove(chunk)
            except Exception as audio_error:
                logger.error(f"[{task_id}] Audio finalization error: {str(audio_error)}", exc_info=True)
                update_progress(task_id, status=f'Audio finalization failed: {str(audio_error)[:50]}...', progress=98)
                    
        # Final garbage collection
        gc.collect()
        logger.info(f"[{task_id}] PDF processing finished.")

    except Exception as e:
        logger.error(f"[{task_id}] Error processing PDF: {str(e)}", exc_info=True)
        update_progress(task_id, status='error', error=str(e), progress=0)
        # Re-raise the exception so Celery knows the task failed
        raise 