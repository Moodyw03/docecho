#!/usr/bin/env python
"""
Font Encoding Test Script for DocEcho

This script tests PDF generation with various languages to ensure
proper font encoding and rendering.
"""

import os
import logging
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure output directory exists
output_dir = "font_tests"
os.makedirs(output_dir, exist_ok=True)

def test_font_encoding():
    """Test various font encodings for different languages"""
    # Font registration
    fonts_dir = os.path.join('app', 'static', 'fonts')
    
    # Register all available fonts
    for font_file in os.listdir(fonts_dir):
        if font_file.endswith(('.ttf', '.otf')):
            font_name = os.path.splitext(font_file)[0]
            try:
                full_path = os.path.join(fonts_dir, font_file)
                pdfmetrics.registerFont(TTFont(font_name, full_path))
                logger.info(f"Registered font: {font_name} from {font_file}")
            except Exception as e:
                logger.warning(f"Failed to register font {font_file}: {str(e)}")
    
    # Test cases for different languages
    test_cases = {
        'en': {
            'text': "Hello, this is English text! Testing 1, 2, 3.",
            'font': 'NotoSans-Regular',
            'desc': 'English - Noto Sans'
        },
        'ja': {
            'text': "こんにちは、これは日本語のテキストです。テスト 1, 2, 3.",
            'font': 'NotoSansJP-Regular',
            'desc': 'Japanese - Noto Sans JP'
        },
        'zh-CN': {
            'text': "你好，这是中文文本！测试 1, 2, 3.",
            'font': 'NotoSansSC-Regular',
            'desc': 'Chinese - Noto Sans SC'
        },
        'ru': {
            'text': "Привет, это русский текст! Тестирование 1, 2, 3.",
            'font': 'NotoSans-Regular',
            'desc': 'Russian - Noto Sans'
        },
        'ko': {
            'text': "안녕하세요, 이것은 한국어 텍스트입니다! 테스트 1, 2, 3.",
            'font': 'NotoSansKR-Regular',
            'desc': 'Korean - Noto Sans KR'
        },
    }
    
    # Create a PDF for each test case
    for lang, case in test_cases.items():
        output_file = os.path.join(output_dir, f"test_{lang}.pdf")
        
        # Create PDF
        c = canvas.Canvas(output_file, pagesize=A4)
        width, height = A4
        
        # Try to set encoding to UTF-8
        try:
            c.setEncoding('utf-8')
        except:
            logger.warning("Failed to set encoding to UTF-8")
        
        # Set font
        try:
            c.setFont(case['font'], 12)
        except:
            logger.warning(f"Failed to set font to {case['font']}, using Helvetica")
            c.setFont('Helvetica', 12)
        
        # Draw title
        c.drawString(72, height - 72, f"Font Test: {case['desc']}")
        
        # Draw text with explicit UTF-8 encoding
        try:
            c.drawString(72, height - 100, case['text'])
            logger.info(f"Drawing text for {lang} using {case['font']}")
        except Exception as e:
            logger.error(f"Failed to draw text for {lang}: {str(e)}")
            # Try alternative drawing method
            try:
                c.drawString(72, height - 100, case['text'].encode('utf-8').decode('utf-8'))
            except:
                c.drawString(72, height - 100, f"[Error rendering {lang} text]")
        
        # Save the PDF
        c.save()
        logger.info(f"Created test PDF for {lang} at {output_file}")

if __name__ == "__main__":
    logger.info("Starting font encoding tests...")
    test_font_encoding()
    logger.info("Font encoding tests completed. Check the font_tests directory for results.") 