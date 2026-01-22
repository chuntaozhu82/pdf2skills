#!/usr/bin/env python3
"""
PDF Splitter: Split large PDFs into smaller chunks for processing.

Used when PDFs exceed MinerU's page limit.
"""

import sys
from pathlib import Path
try:
    from PyPDF2 import PdfReader, PdfWriter
except ImportError:
    print("PyPDF2 not installed. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyPDF2"])
    from PyPDF2 import PdfReader, PdfWriter


def split_pdf(pdf_path: Path, pages_per_split: int = 400, output_dir: Path = None):
    """
    Split a PDF into smaller chunks.
    
    Args:
        pdf_path: Path to PDF file
        pages_per_split: Number of pages per split (default: 400, under MinerU limit)
        output_dir: Directory to save splits (default: same as PDF parent)
    
    Returns:
        List of split PDF paths
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    if output_dir is None:
        output_dir = pdf_path.parent / f"{pdf_path.stem}_splits"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    
    print(f"Splitting {pdf_path.name} ({total_pages} pages) into chunks of {pages_per_split} pages...")
    
    split_files = []
    num_splits = (total_pages + pages_per_split - 1) // pages_per_split
    
    for i in range(num_splits):
        start_page = i * pages_per_split
        end_page = min((i + 1) * pages_per_split, total_pages)
        
        writer = PdfWriter()
        for page_num in range(start_page, end_page):
            writer.add_page(reader.pages[page_num])
        
        split_filename = f"{pdf_path.stem}_part{i+1:02d}.pdf"
        split_path = output_dir / split_filename
        
        with open(split_path, "wb") as output_file:
            writer.write(output_file)
        
        split_files.append(split_path)
        print(f"  Created {split_filename}: pages {start_page+1}-{end_page} ({end_page-start_page} pages)")
    
    print(f"Split complete: {len(split_files)} files created in {output_dir}")
    return split_files


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python pdf_splitter.py <pdf_path> [pages_per_split]")
        sys.exit(1)
    
    pdf_path = Path(sys.argv[1])
    pages_per_split = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    
    split_pdf(pdf_path, pages_per_split)


if __name__ == "__main__":
    main()
