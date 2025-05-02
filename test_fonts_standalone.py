#!/usr/bin/env python
"""
Standalone Font Rendering Test Script for DocEcho

This script generates PDF files with text in various languages to test
the font rendering capabilities of the application without needing the full app.
"""

import os
import logging
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import textwrap

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure output directory exists
output_dir = "font_tests"
os.makedirs(output_dir, exist_ok=True)

def create_test_pdf(text, output_path, language_code='en'):
    """Create a PDF with the provided text using the appropriate font."""
    try:
        # Font path - make this relative to the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        font_path = os.path.join(script_dir, 'app', 'static', 'fonts')
        
        # Set default font
        font_name = 'Helvetica'  # Default fallback
        
        # Language-specific font mapping
        language_font_map = {
            'ja': {'file': 'NotoSansCJKjp-Regular.otf', 'name': 'NotoSansCJKjp'},
            'zh-CN': {'file': 'NotoSansCJKsc-Regular.otf', 'name': 'NotoSansCJKsc'},
            'ko': {'file': 'NotoSansCJKkr-Regular.otf', 'name': 'NotoSansCJKkr'},
        }
        
        # Register language-specific font if needed
        if language_code in language_font_map:
            font_info = language_font_map[language_code]
            font_file = os.path.join(font_path, font_info['file'])
            if os.path.exists(font_file):
                try:
                    pdfmetrics.registerFont(TTFont(font_info['name'], font_file))
                    font_name = font_info['name']
                    logger.info(f"Using {font_name} font for {language_code}")
                except Exception as e:
                    logger.warning(f"Error registering {font_name} font: {e}")
        
        # For all other languages, try DejaVu Sans
        if font_name == 'Helvetica':
            dejavu_path = os.path.join(font_path, 'DejaVuSans.ttf')
            if os.path.exists(dejavu_path):
                try:
                    pdfmetrics.registerFont(TTFont('DejaVuSans', dejavu_path))
                    font_name = 'DejaVuSans'
                    logger.info(f"Using DejaVu Sans font for {language_code}")
                except Exception as e:
                    logger.warning(f"Error registering DejaVu Sans font: {e}")
        
        # PDF settings
        font_size = 11
        line_height = font_size * 1.2
        
        # Create PDF
        c = canvas.Canvas(output_path, pagesize=A4)
        width, height = A4
        
        # Set margins
        left_margin = 72  # 1 inch in points
        right_margin = width - 72
        top_margin = height - 72
        bottom_margin = 72
        text_width = right_margin - left_margin
        
        # Set font
        c.setFont(font_name, font_size)
        
        # Add title
        c.setFont(font_name, 14)
        title = f"Font Test - {language_code}"
        c.drawString(left_margin, top_margin + 20, title)
        
        # Reset to normal font size
        c.setFont(font_name, font_size)
        
        # Current position on page
        y_position = top_margin - 20
        
        # Split text into paragraphs
        paragraphs = text.split('\n\n')
        
        for paragraph in paragraphs:
            # Wrap text to fit within margins
            wrapped_lines = textwrap.wrap(paragraph, width=int(text_width/6))
            
            # Add each line of the wrapped paragraph
            for line in wrapped_lines:
                if y_position < bottom_margin:
                    c.showPage()
                    c.setFont(font_name, font_size)
                    y_position = top_margin
                
                # Draw text
                c.drawString(left_margin, y_position, line)
                y_position -= line_height
            
            # Add space between paragraphs
            y_position -= line_height * 0.5
        
        # Add font information
        info_y = 30
        c.setFont('Helvetica', 8)
        c.drawString(left_margin, info_y, f"Font: {font_name}")
        
        # Save the PDF
        c.save()
        return True
    except Exception as e:
        logger.error(f"Error creating PDF: {e}")
        return False

# Test languages and sample text
test_cases = {
    'en': "Hello, this is English text! Testing 1, 2, 3.",
    'ja': "こんにちは、これは日本語のテキストです。テスト 1, 2, 3.",
    'zh-CN': "你好，这是中文文本！测试 1, 2, 3.",
    'ko': "안녕하세요, 이것은 한국어 텍스트입니다! 테스트 1, 2, 3.",
    'ru': "Привет, это русский текст! Тестирование 1, 2, 3.",
    'ar': "مرحبا، هذا هو النص العربي! اختبار 1، 2، 3.",
}

if __name__ == "__main__":
    print("DocEcho Font Rendering Test")
    print("--------------------------")
    
    for lang_code, text in test_cases.items():
        print(f"Testing {lang_code}...")
        output_path = os.path.join(output_dir, f"test_{lang_code}.pdf")
        
        if create_test_pdf(text, output_path, language_code=lang_code):
            print(f"  ✅ Generated PDF at {output_path}")
        else:
            print(f"  ❌ Error generating PDF for {lang_code}")
    
    print("\nTest completed. Check the PDFs in the 'font_tests' directory.") 