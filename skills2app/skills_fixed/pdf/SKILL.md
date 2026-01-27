---
name: pdf
description: Comprehensive PDF manipulation toolkit for extracting text and tables, creating new PDFs, merging/splitting documents, and handling forms. When Claude needs to fill in a PDF form or programmatically process, generate, or analyze PDF documents at scale.
license: Proprietary. LICENSE.txt has complete terms
---

# PDF Processing Guide

## Overview

This guide covers essential PDF processing operations using Python libraries and command-line tools. For advanced features, JavaScript libraries, and detailed examples, see reference.md. If you need to fill out a PDF form, read forms.md and follow its instructions.

## Quick Start

```python
from pypdf import PdfReader, PdfWriter

# Read a PDF
reader = PdfReader("document.pdf")
print(f"Pages: {len(reader.pages)}")

# Extract text
text = ""
for page in reader.pages:
    text += page.extract_text()
```

## Python Libraries

### pypdf - Basic Operations

#### Merge PDFs
```python
from pypdf import PdfWriter, PdfReader

writer = PdfWriter()
for pdf_file in ["doc1.pdf", "doc2.pdf", "doc3.pdf"]:
    reader = PdfReader(pdf_file)
    for page in reader.pages:
        writer.add_page(page)

with open("merged.pdf", "wb") as output:
    writer.write(output)
```

#### Split PDF
```python
reader = PdfReader("input.pdf")
for i, page in enumerate(reader.pages):
    writer = PdfWriter()
    writer.add_page(page)
    with open(f"page_{i+1}.pdf", "wb") as output:
        writer.write(output)
```

#### Extract Metadata
```python
reader = PdfReader("document.pdf")
meta = reader.metadata
print(f"Title: {meta.title}")
print(f"Author: {meta.author}")
print(f"Subject: {meta.subject}")
print(f"Creator: {meta.creator}")
```

#### Rotate Pages
```python
reader = PdfReader("input.pdf")
writer = PdfWriter()

page = reader.pages[0]
page.rotate(90)  # Rotate 90 degrees clockwise
writer.add_page(page)

with open("rotated.pdf", "wb") as output:
    writer.write(output)
```

### pdfplumber - Text and Table Extraction

#### Extract Text with Layout
```python
import pdfplumber

with pdfplumber.open("document.pdf") as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        print(text)
```

#### Extract Tables
```python
with pdfplumber.open("document.pdf") as pdf:
    for i, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        for j, table in enumerate(tables):
            print(f"Table {j+1} on page {i+1}:")
            for row in table:
                print(row)
```

#### Advanced Table Extraction
```python
import pandas as pd

with pdfplumber.open("document.pdf") as pdf:
    all_tables = []
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:  # Check if table is not empty
                df = pd.DataFrame(table[1:], columns=table[0])
                all_tables.append(df)

# Combine all tables
if all_tables:
    combined_df = pd.concat(all_tables, ignore_index=True)
    combined_df.to_excel("extracted_tables.xlsx", index=False)
```

### reportlab - Create PDFs

#### Basic PDF Creation
```python
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

c = canvas.Canvas("hello.pdf", pagesize=letter)
width, height = letter

# Add text
c.drawString(100, height - 100, "Hello World!")
c.drawString(100, height - 120, "This is a PDF created with reportlab")

# Add a line
c.line(100, height - 140, 400, height - 140)

# Save
c.save()
```

#### Create PDF with Multiple Pages
```python
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

doc = SimpleDocTemplate("report.pdf", pagesize=letter)
styles = getSampleStyleSheet()
story = []

# Add content
title = Paragraph("Report Title", styles['Title'])
story.append(title)
story.append(Spacer(1, 12))

body = Paragraph("This is the body of the report. " * 20, styles['Normal'])
story.append(body)
story.append(PageBreak())

# Page 2
story.append(Paragraph("Page 2", styles['Heading1']))
story.append(Paragraph("Content for page 2", styles['Normal']))

# Build PDF
doc.build(story)
```

## Command-Line Tools

### pdftotext (poppler-utils)
```bash
# Extract text
pdftotext input.pdf output.txt

# Extract text preserving layout
pdftotext -layout input.pdf output.txt

# Extract specific pages
pdftotext -f 1 -l 5 input.pdf output.txt  # Pages 1-5
```

### qpdf
```bash
# Merge PDFs
qpdf --empty --pages file1.pdf file2.pdf -- merged.pdf

# Split pages
qpdf input.pdf --pages . 1-5 -- pages1-5.pdf
qpdf input.pdf --pages . 6-10 -- pages6-10.pdf

# Rotate pages
qpdf input.pdf output.pdf --rotate=+90:1  # Rotate page 1 by 90 degrees

# Remove password
qpdf --password=mypassword --decrypt encrypted.pdf decrypted.pdf
```

### pdftk (if available)
```bash
# Merge
pdftk file1.pdf file2.pdf cat output merged.pdf

# Split
pdftk input.pdf burst

# Rotate
pdftk input.pdf rotate 1east output rotated.pdf
```

## Common Tasks

### Extract Text from Scanned PDFs
```python
# Requires: pip install pytesseract pdf2image
import pytesseract
from pdf2image import convert_from_path

# Convert PDF to images
images = convert_from_path('scanned.pdf')

# OCR each page
text = ""
for i, image in enumerate(images):
    text += f"Page {i+1}:\n"
    text += pytesseract.image_to_string(image)
    text += "\n\n"

print(text)
```

### Add Watermark
```python
from pypdf import PdfReader, PdfWriter

# Create watermark (or load existing)
watermark = PdfReader("watermark.pdf").pages[0]

# Apply to all pages
reader = PdfReader("document.pdf")
writer = PdfWriter()

for page in reader.pages:
    page.merge_page(watermark)
    writer.add_page(page)

with open("watermarked.pdf", "wb") as output:
    writer.write(output)
```

### Extract Images
```bash
# Using pdfimages (poppler-utils)
pdfimages -j input.pdf output_prefix

# This extracts all images as output_prefix-000.jpg, output_prefix-001.jpg, etc.
```

### Password Protection
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("input.pdf")
writer = PdfWriter()

for page in reader.pages:
    writer.add_page(page)

# Add password
writer.encrypt("userpassword", "ownerpassword")

with open("encrypted.pdf", "wb") as output:
    writer.write(output)
```

## MinerU - Advanced PDF to Markdown Conversion

MinerU is a cloud-based API service that provides high-quality PDF to Markdown conversion with advanced features including OCR, formula extraction, table extraction, and layout preservation. It's ideal for converting complex academic papers, technical documents, and scanned PDFs into structured Markdown format.

### Features

- **OCR Support**: Automatically extracts text from scanned PDFs and images
- **Formula Extraction**: Preserves mathematical formulas and equations
- **Table Extraction**: Converts tables to Markdown format with structure preserved
- **Layout Preservation**: Maintains document structure, headings, and formatting
- **Multi-language Support**: Supports Chinese (`ch`) and English (`en`)
- **Image Extraction**: Extracts embedded images separately

### Setup

1. **Get API Key**: Sign up at [MinerU](https://mineru.net) to get your API key
2. **Install Dependencies**:
```bash
pip install requests python-dotenv
```

3. **Set Environment Variable**:
```bash
export MINERU_API_KEY="your_api_key_here"
```

Or create a `.env` file:
```
MINERU_API_KEY=your_api_key_here
```

### Basic Usage

```python
import os
import requests
from pathlib import Path
from dotenv import load_dotenv
import zipfile
import io
import time

load_dotenv()

MINERU_API_KEY = os.getenv("MINERU_API_KEY")
MINERU_BASE_URL = "https://mineru.net/api/v4"

class MineruClient:
    """Client for MinerU PDF to Markdown API."""
    
    def __init__(self, api_key: str = None, language: str = "ch"):
        self.api_key = api_key or MINERU_API_KEY
        if not self.api_key:
            raise ValueError("MINERU_API_KEY not found in environment")
        self.language = language  # "ch" for Chinese, "en" for English
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def convert_pdf(self, pdf_path: str | Path, output_dir: str | Path = None) -> Path:
        """
        Full pipeline: upload PDF, wait for conversion, download results.
        
        Args:
            pdf_path: Path to PDF file
            output_dir: Directory for output (default: same as PDF)
        
        Returns:
            Path to output directory with markdown results
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        if output_dir is None:
            output_dir = pdf_path.parent / f"{pdf_path.stem}_output"
        output_dir = Path(output_dir)
        
        # Step 1: Request upload URL
        url = f"{MINERU_BASE_URL}/file-urls/batch"
        payload = {
            "files": [{
                "name": pdf_path.name,
                "is_ocr": True,  # Enable OCR for better text quality
                "enable_formula": True,
                "enable_table": True,
                "language": self.language
            }]
        }
        
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"API error: {data.get('msg', 'Unknown error')}")
        
        result = data["data"]
        batch_id = result["batch_id"]
        upload_url = result["file_urls"][0]
        
        # Step 2: Upload file
        print(f"Uploading {pdf_path.name}...")
        with open(pdf_path, "rb") as f:
            requests.put(upload_url, data=f)
        
        # Step 3: Wait for extraction
        print("Waiting for extraction...")
        while True:
            url = f"{MINERU_BASE_URL}/extract-results/batch/{batch_id}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != 0:
                raise Exception(f"API error: {data.get('msg', 'Unknown error')}")
            
            results = data["data"]
            extract_results = results.get("extract_result", [])
            
            if extract_results:
                file_result = extract_results[0]
                state = file_result.get("state", "unknown")
                
                if state == "done":
                    print("Extraction complete!")
                    break
                elif state == "failed":
                    raise Exception(f"Extraction failed: {file_result.get('err_msg', 'Unknown error')}")
                else:
                    progress = file_result.get("extract_progress", {})
                    extracted = progress.get("extracted_pages", 0)
                    total = progress.get("total_pages", "?")
                    print(f"Status: {state} - Pages: {extracted}/{total}")
            
            time.sleep(5)  # Poll every 5 seconds
        
        # Step 4: Download results
        zip_url = file_result.get("full_zip_url")
        if not zip_url:
            raise Exception("No download URL in results")
        
        print("Downloading results...")
        response = requests.get(zip_url)
        response.raise_for_status()
        
        output_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            zf.extractall(output_dir)
        
        print(f"Results saved to: {output_dir}")
        return output_dir

# Usage example
client = MineruClient(language="ch")  # Use "en" for English
result_dir = client.convert_pdf("document.pdf")
markdown_file = result_dir / "full.md"
print(f"Markdown saved to: {markdown_file}")
```

### Output Structure

MinerU extracts PDFs into a structured directory:

```
output_directory/
├── full.md                    # Main markdown file with all content
├── layout.json                # Document layout structure
├── content_list.json          # Content hierarchy and metadata
├── images/                    # Extracted images
│   ├── image1.jpg
│   └── image2.jpg
└── [original_pdf].pdf        # Original PDF copy
```

### Advanced Options

```python
# Custom language setting
client = MineruClient(language="en")  # English
client = MineruClient(language="ch")  # Chinese

# Custom output directory
result_dir = client.convert_pdf(
    "document.pdf",
    output_dir="custom_output_folder"
)

# Access extracted markdown
markdown_path = result_dir / "full.md"
with open(markdown_path, "r", encoding="utf-8") as f:
    markdown_content = f.read()
```

### When to Use MinerU

Use MinerU when you need:
- **High-quality OCR**: Better than pytesseract for complex documents
- **Formula preservation**: Mathematical formulas in academic papers
- **Table structure**: Complex tables with merged cells
- **Layout preservation**: Document structure and formatting
- **Large documents**: Handles multi-page documents efficiently
- **Scanned PDFs**: OCR-enabled extraction from image-based PDFs

### Limitations

- **API-based**: Requires internet connection and API key
- **Rate limits**: May have rate limits depending on your plan
- **Page limits**: Large PDFs (>400 pages) may need to be split first
- **Processing time**: Can take several minutes for large documents

### Comparison with Other Tools

| Feature | MinerU | pdfplumber | pytesseract |
|---------|--------|------------|-------------|
| OCR Quality | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| Formula Extraction | ✅ | ❌ | ❌ |
| Table Structure | ✅ | ✅ | ❌ |
| Layout Preservation | ✅ | ⚠️ Partial | ❌ |
| Scanned PDFs | ✅ | ❌ | ✅ |
| Offline Support | ❌ | ✅ | ✅ |

## Quick Reference

| Task | Best Tool | Command/Code |
|------|-----------|--------------|
| Merge PDFs | pypdf | `writer.add_page(page)` |
| Split PDFs | pypdf | One page per file |
| Extract text | pdfplumber | `page.extract_text()` |
| Extract tables | pdfplumber | `page.extract_tables()` |
| Create PDFs | reportlab | Canvas or Platypus |
| Command line merge | qpdf | `qpdf --empty --pages ...` |
| OCR scanned PDFs | pytesseract | Convert to image first |
| **PDF to Markdown (OCR + formulas)** | **MinerU** | `MineruClient().convert_pdf()` |
| Fill PDF forms | pdf-lib or pypdf (see forms.md) | See forms.md |

## Next Steps

- For advanced pypdfium2 usage, see reference.md
- For JavaScript libraries (pdf-lib), see reference.md
- If you need to fill out a PDF form, follow the instructions in forms.md
- For high-quality PDF to Markdown conversion with OCR and formula extraction, use MinerU (see MinerU section above)
- For troubleshooting guides, see reference.md
