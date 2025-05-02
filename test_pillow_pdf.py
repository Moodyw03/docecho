#!/usr/bin/env python
"""
Pillow-based PDF Generator Test Script

This script tests the new Pillow-based PDF generation with better font support
for CJK and other non-Latin scripts.
"""

import os
import sys
import logging
from PIL import Image, ImageDraw, ImageFont
import textwrap

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure output directory exists
output_dir = "pillow_tests"
os.makedirs(output_dir, exist_ok=True)

# Font paths
font_path = os.path.join('app', 'static', 'fonts')
noto_sans_path = os.path.join(font_path, 'NotoSans-Regular.ttf')
noto_cjk_path = os.path.join(font_path, 'NotoSansCJK-Regular.ttc')

# Test languages and sample text
test_cases = {
    'en': {
        'text': "Hello, this is English text! Testing 1, 2, 3.",
        'font_path': noto_sans_path,
        'font_index': 0,
        'desc': 'English - Noto Sans'
    },
    'ja': {
        'text': "こんにちは、これは日本語のテキストです。テスト 1, 2, 3.",
        'font_path': noto_cjk_path,
        'font_index': 0,  # Japanese index in the TTC file
        'desc': 'Japanese - Noto Sans CJK'
    },
    'zh-CN': {
        'text': "你好，这是中文文本！测试 1, 2, 3.",
        'font_path': noto_cjk_path,
        'font_index': 1,  # Simplified Chinese index in the TTC file
        'desc': 'Chinese - Noto Sans CJK'
    },
    'ru': {
        'text': "Привет, это русский текст! Тестирование 1, 2, 3.",
        'font_path': noto_sans_path,
        'font_index': 0,
        'desc': 'Russian - Noto Sans'
    },
    'ko': {
        'text': "안녕하세요, 이것은 한국어 텍스트입니다! 테스트 1, 2, 3.",
        'font_path': noto_cjk_path,
        'font_index': 2,  # Korean index in the TTC file
        'desc': 'Korean - Noto Sans CJK'
    },
}

def generate_pdf(language, case):
    """Generate a PDF using Pillow for the given language case"""
    output_file = os.path.join(output_dir, f"pillow_{language}.pdf")
    
    # Page dimensions (A4 at 72 dpi)
    page_width, page_height = 595, 842
    
    # Create a new white image
    img = Image.new('RGB', (page_width, page_height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Try to load the font
    font_size = 16
    try:
        if case['font_path'].endswith('.ttc'):
            font = ImageFont.truetype(case['font_path'], 
                                     size=font_size, 
                                     index=case['font_index'])
        else:
            font = ImageFont.truetype(case['font_path'], size=font_size)
        logger.info(f"Loaded font for {language}: {case['font_path']}")
    except Exception as e:
        logger.error(f"Error loading font for {language}: {e}")
        font = ImageFont.load_default()
    
    # Page margins
    left_margin = 72
    top_margin = 72
    
    # Draw the title
    title = f"Pillow PDF Test: {case['desc']}"
    draw.text((left_margin, top_margin), title, font=font, fill='black')
    
    # Draw the sample text
    sample_text = case['text']
    draw.text((left_margin, top_margin + 40), sample_text, font=font, fill='black')
    
    # Save as PDF
    try:
        img.save(output_file, "PDF", resolution=72.0)
        logger.info(f"Created PDF for {language} at {output_file}")
        return True
    except Exception as e:
        logger.error(f"Error saving PDF for {language}: {e}")
        return False

def main():
    """Run the PDF generation tests"""
    logger.info("Starting Pillow PDF tests")
    
    # Check that fonts exist
    if not os.path.exists(noto_sans_path):
        logger.error(f"Noto Sans font not found at {noto_sans_path}")
    if not os.path.exists(noto_cjk_path):
        logger.error(f"Noto CJK font not found at {noto_cjk_path}")
    
    # Generate PDFs for each language
    success_count = 0
    for lang, case in test_cases.items():
        logger.info(f"Processing {lang} ({case['desc']})")
        if generate_pdf(lang, case):
            success_count += 1
    
    logger.info(f"PDF generation completed: {success_count}/{len(test_cases)} successful")

if __name__ == "__main__":
    main() 