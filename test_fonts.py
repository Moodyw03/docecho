#!/usr/bin/env python
"""
Font Rendering Test Script for DocEcho

This script generates PDF files with text in various languages to test
the font rendering capabilities of the application.
"""

import os
from app.utils.pdf_processor import create_translated_pdf

# Ensure output directory exists
output_dir = "font_tests"
os.makedirs(output_dir, exist_ok=True)

# Test languages and sample text
test_cases = {
    'en': "Hello, this is English text! Testing 1, 2, 3.",
    'ja': "こんにちは、これは日本語のテキストです。テスト 1, 2, 3.",
    'zh-CN': "你好，这是中文文本！测试 1, 2, 3.",
    'ko': "안녕하세요, 이것은 한국어 텍스트입니다! 테스트 1, 2, 3.",
    'ru': "Привет, это русский текст! Тестирование 1, 2, 3.",
    'ar': "مرحبا، هذا هو النص العربي! اختبار 1، 2، 3.",
}

print("DocEcho Font Rendering Test")
print("--------------------------")

for lang_code, text in test_cases.items():
    print(f"Testing {lang_code}...")
    output_path = os.path.join(output_dir, f"test_{lang_code}.pdf")
    
    try:
        create_translated_pdf(text, output_path, language_code=lang_code)
        print(f"  ✅ Generated PDF at {output_path}")
    except Exception as e:
        print(f"  ❌ Error: {e}")

print("\nTest completed. Check the PDFs in the 'font_tests' directory.") 