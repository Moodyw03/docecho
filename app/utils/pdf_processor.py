from PyPDF2 import PdfReader
from gtts import gTTS
from pydub import AudioSegment
from googletrans import Translator
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from app.utils.progress import update_progress
import os

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

def extract_text_chunks_from_pdf(pdf_path, max_chunk_length=500):
    try:
        reader = PdfReader(pdf_path)
        chunks = []
        current_chunk = ''
        
        total_pages = len(reader.pages)
        for page_num, page in enumerate(reader.pages):
            if page_num % 10 == 0:
                import gc
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
                    
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks
    except Exception as e:
        raise Exception(f"Error extracting text from PDF: {e}")

def convert_text_to_audio(text, output_filename, voice, speed, tld='com'):
    try:
        temp_dir = os.path.join(os.getcwd(), 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        temp_output = os.path.join(temp_dir, output_filename.replace(".mp3", "_temp.mp3"))
        output_path = os.path.join(temp_dir, output_filename)
        
        tts = gTTS(text, lang=voice, tld=tld)
        tts.save(temp_output)

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

def process_pdf(filename, file_path, voice, speed, task_id, output_format, output_path):
    try:
        # Create temp and output directories
        output_dir = os.path.dirname(output_path)  # Get the output directory from the audio path
        temp_dir = os.path.join(output_dir, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        update_progress(task_id, status='Extracting text from PDF...', progress=0)
        text_chunks = extract_text_chunks_from_pdf(file_path)
        total_chunks = len(text_chunks)

        if total_chunks == 0:
            raise Exception("No text could be extracted from the PDF")

        translator = Translator()
        batch_size = 10
        audio_chunks = []
        translated_text = []
        
        lang_settings = language_map.get(voice, {"lang": "en", "tld": "com"})
        
        for batch_start in range(0, total_chunks, batch_size):
            batch_end = min(batch_start + batch_size, total_chunks)
            batch = text_chunks[batch_start:batch_end]
            
            for i, chunk in enumerate(batch):
                overall_progress = int(((batch_start + i) / total_chunks) * 100)
                update_progress(
                    task_id,
                    status=f'Processing chunk {batch_start + i + 1} of {total_chunks}...',
                    progress=overall_progress
                )

                try:
                    translated_chunk = translator.translate(chunk, dest=lang_settings["lang"]).text
                    translated_text.append(translated_chunk)
                    
                    if output_format in ["audio", "both"]:
                        chunk_filename = f"{task_id}_chunk_{batch_start + i}.mp3"
                        audio_chunk_path = convert_text_to_audio(
                            translated_chunk,
                            chunk_filename,
                            lang_settings["lang"],
                            speed,
                            lang_settings["tld"]
                        )
                        audio_chunks.append(audio_chunk_path)

                except Exception as e:
                    continue

        # Handle PDF output
        if output_format in ["pdf", "both"]:
            base_filename = os.path.splitext(os.path.basename(filename))[0]
            pdf_filename = f"{base_filename}_translated_{task_id}.pdf"
            pdf_path = os.path.join(output_dir, pdf_filename)
            
            create_translated_pdf('\n'.join(translated_text), pdf_path, lang_settings["lang"])
            
            # Update progress with PDF path
            update_progress(
                task_id,
                pdf_file=pdf_path,
                status='completed' if output_format == "pdf" else None,
                progress=100 if output_format == "pdf" else None
            )
            
        # Handle audio output
        if audio_chunks and output_format in ["audio", "both"]:
            concatenate_audio_files(audio_chunks, output_path)
            
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

    except Exception as e:
        update_progress(task_id, status='error', error=str(e), progress=0)
        raise Exception(f"Error processing PDF: {str(e)}") 