#!/usr/bin/env python3
"""
MinerU API Client
Converts PDF files to Markdown using MinerU's cloud API.

Usage:
    python mineru_client.py test_data/financial_statement_analysis_test1.pdf
"""

import os
import sys
import time
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
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

    def request_upload_url(self, filename: str) -> dict:
        """
        Request a presigned upload URL for a local file.

        Args:
            filename: Name of the file to upload

        Returns:
            dict with upload_url and batch_id
        """
        url = f"{MINERU_BASE_URL}/file-urls/batch"

        payload = {
            "files": [
                {
                    "name": filename,
                    "is_ocr": True,  # OCR enabled for better text quality
                    "enable_formula": True,
                    "enable_table": True,
                    "language": self.language
                }
            ]
        }

        print(f"Requesting upload URL for: {filename}")
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()

        data = response.json()
        if data.get("code") != 0:
            raise Exception(f"API error: {data.get('msg', 'Unknown error')}")

        # Response structure: {"batch_id": "...", "file_urls": ["url1", ...]}
        result = data["data"]
        return {
            "batch_id": result["batch_id"],
            "upload_url": result["file_urls"][0]  # First (and only) file URL
        }

    def upload_file(self, upload_url: str, file_path: Path) -> bool:
        """
        Upload file to the presigned URL using PUT.

        Args:
            upload_url: Presigned upload URL from request_upload_url
            file_path: Path to local file

        Returns:
            True if upload successful
        """
        print(f"Uploading file: {file_path.name} ({file_path.stat().st_size / 1024 / 1024:.1f} MB)")

        with open(file_path, "rb") as f:
            # No Content-Type header needed for presigned URL upload
            response = requests.put(upload_url, data=f)

        response.raise_for_status()
        print("Upload complete!")
        return True

    def get_batch_results(self, batch_id: str) -> dict:
        """
        Query batch extraction results.

        Args:
            batch_id: Batch ID from upload

        Returns:
            dict with extraction status and results
        """
        url = f"{MINERU_BASE_URL}/extract-results/batch/{batch_id}"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()

        data = response.json()
        if data.get("code") != 0:
            raise Exception(f"API error: {data.get('msg', 'Unknown error')}")

        return data["data"]

    def wait_for_completion(self, batch_id: str, poll_interval: int = 5, timeout: int = 600) -> dict:
        """
        Poll batch results until completion.

        Args:
            batch_id: Batch ID to monitor
            poll_interval: Seconds between polls
            timeout: Maximum wait time in seconds

        Returns:
            Final extraction results
        """
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Extraction timed out after {timeout} seconds")

            results = self.get_batch_results(batch_id)

            # Check if all files are done
            extract_results = results.get("extract_result", [])
            if not extract_results:
                print(f"Waiting for task to start... ({elapsed:.0f}s)")
                time.sleep(poll_interval)
                continue

            file_result = extract_results[0]
            state = file_result.get("state", "unknown")

            if state == "done":
                print(f"\nExtraction complete! ({elapsed:.0f}s)")
                return file_result
            elif state == "failed":
                raise Exception(f"Extraction failed: {file_result.get('err_msg', 'Unknown error')}")
            else:
                # Show progress
                progress = file_result.get("extract_progress", {})
                extracted = progress.get("extracted_pages", 0)
                total = progress.get("total_pages", "?")
                print(f"Status: {state} - Pages: {extracted}/{total} ({elapsed:.0f}s)")
                time.sleep(poll_interval)

    def download_results(self, zip_url: str, output_dir: Path) -> Path:
        """
        Download and extract the results ZIP file.

        Args:
            zip_url: URL to the results ZIP
            output_dir: Directory to save results

        Returns:
            Path to extracted directory
        """
        import zipfile
        import io

        print(f"Downloading results from: {zip_url[:50]}...")

        response = requests.get(zip_url)
        response.raise_for_status()

        output_dir.mkdir(parents=True, exist_ok=True)

        # Extract ZIP contents
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            zf.extractall(output_dir)

        print(f"Results extracted to: {output_dir}")
        return output_dir

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

        print(f"\n{'='*60}")
        print(f"MinerU PDF to Markdown Conversion")
        print(f"{'='*60}")
        print(f"Input:  {pdf_path}")
        print(f"Output: {output_dir}")
        print(f"OCR:    Enabled (better quality)")
        print(f"{'='*60}\n")

        # Step 1: Request upload URL
        upload_data = self.request_upload_url(pdf_path.name)
        batch_id = upload_data["batch_id"]
        upload_url = upload_data["upload_url"]

        print(f"Batch ID: {batch_id}")

        # Step 2: Upload file
        self.upload_file(upload_url, pdf_path)

        # Step 3: Wait for extraction
        print("\nWaiting for extraction...")
        result = self.wait_for_completion(batch_id)

        # Step 4: Download results
        zip_url = result.get("full_zip_url")
        if not zip_url:
            raise Exception("No download URL in results")

        self.download_results(zip_url, output_dir)

        # Show output files
        print(f"\n{'='*60}")
        print("Output files:")
        for f in output_dir.rglob("*"):
            if f.is_file():
                size = f.stat().st_size / 1024
                print(f"  {f.relative_to(output_dir)} ({size:.1f} KB)")
        print(f"{'='*60}\n")

        return output_dir


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        # Default to test file
        pdf_path = "test_data/financial_statement_analysis_test1.pdf"
    else:
        pdf_path = sys.argv[1]

    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    client = MineruClient()

    try:
        result_dir = client.convert_pdf(pdf_path, output_dir)
        print(f"Success! Results saved to: {result_dir}")

        # Show markdown preview if available
        md_files = list(result_dir.rglob("*.md"))
        if md_files:
            print(f"\nMarkdown preview ({md_files[0].name}):")
            print("-" * 40)
            content = md_files[0].read_text()[:1000]
            print(content)
            if len(md_files[0].read_text()) > 1000:
                print("...")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
