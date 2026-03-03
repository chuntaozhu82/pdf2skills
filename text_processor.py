"""
Text Processor - Convert TXT/Markdown files to Skills Pipeline format

This module handles:
1. Reading plain text files (.txt, .md)
2. Converting to markdown format compatible with the pipeline
3. Basic text cleaning and formatting

Supported formats:
- .txt: Plain text files
- .md: Markdown files (passed through with minimal processing)
"""

import os
import re
from pathlib import Path
from typing import Optional


class TextProcessor:
    """Process text files for the skills pipeline."""

    def __init__(self, input_path: str, output_dir: str = None):
        self.input_path = Path(input_path).resolve()
        self.output_dir = Path(output_dir) if output_dir else self.input_path.parent / f"{self.input_path.stem}_output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _detect_encoding(self, file_path: Path) -> str:
        """Detect file encoding."""
        encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'big5', 'latin-1']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    f.read(1024)
                return encoding
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        return 'utf-8'

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content."""
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.rstrip()
            if line.strip():
                cleaned_lines.append(line)
            elif cleaned_lines and cleaned_lines[-1].strip():
                cleaned_lines.append('')
        
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()
        
        return '\n'.join(cleaned_lines)

    def _txt_to_markdown(self, text: str) -> str:
        """Convert plain text to markdown format."""
        lines = text.split('\n')
        md_lines = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            if not stripped:
                md_lines.append('')
                continue
            
            if i == 0 and len(stripped) < 100:
                md_lines.append(f'# {stripped}')
                md_lines.append('')
                continue
            
            if re.match(r'^第[一二三四五六七八九十\d]+[章节篇部]', stripped):
                md_lines.append(f'## {stripped}')
                md_lines.append('')
                continue
            
            if re.match(r'^Chapter\s*\d+', stripped, re.IGNORECASE):
                md_lines.append(f'## {stripped}')
                md_lines.append('')
                continue
            
            if re.match(r'^[一二三四五六七八九十]+[、.．]', stripped):
                md_lines.append(f'### {stripped}')
                md_lines.append('')
                continue
            
            if re.match(r'^\d+[、.．]\s', stripped):
                md_lines.append(f'### {stripped}')
                md_lines.append('')
                continue
            
            if stripped.startswith('【') and stripped.endswith('】'):
                md_lines.append(f'### {stripped}')
                md_lines.append('')
                continue
            
            md_lines.append(line)
        
        return '\n'.join(md_lines)

    def process_txt(self) -> Path:
        """Process a .txt file and convert to markdown."""
        print(f"[TextProcessor] Processing TXT: {self.input_path}")
        
        encoding = self._detect_encoding(self.input_path)
        print(f"  Detected encoding: {encoding}")
        
        with open(self.input_path, 'r', encoding=encoding) as f:
            text = f.read()
        
        text = self._clean_text(text)
        markdown = self._txt_to_markdown(text)
        
        output_path = self.output_dir / "full.md"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
        
        print(f"  Output: {output_path}")
        print(f"  Lines: {len(markdown.splitlines())}")
        
        return output_path

    def process_markdown(self) -> Path:
        """Process a .md file (pass through with minimal processing)."""
        print(f"[TextProcessor] Processing Markdown: {self.input_path}")
        
        encoding = self._detect_encoding(self.input_path)
        
        with open(self.input_path, 'r', encoding=encoding) as f:
            content = f.read()
        
        content = self._clean_text(content)
        
        output_path = self.output_dir / "full.md"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"  Output: {output_path}")
        print(f"  Lines: {len(content.splitlines())}")
        
        return output_path

    def process(self) -> Path:
        """Process input file based on extension."""
        suffix = self.input_path.suffix.lower()
        
        if suffix == '.txt':
            return self.process_txt()
        elif suffix == '.md':
            return self.process_markdown()
        else:
            raise ValueError(f"Unsupported file format: {suffix}")


def process_text_file(input_path: str, output_dir: str = None) -> Path:
    """Convenience function to process a text file."""
    processor = TextProcessor(input_path, output_dir)
    return processor.process()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Process text files for skills pipeline")
    parser.add_argument("input", help="Input file path (.txt or .md)")
    parser.add_argument("-o", "--output", help="Output directory")
    
    args = parser.parse_args()
    
    process_text_file(args.input, args.output)
