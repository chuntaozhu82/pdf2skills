"""
Web Scraper - Convert Web Pages to Skills Pipeline format

This module handles:
1. Fetching web page content from URLs
2. Extracting main content (article body)
3. Converting HTML to Markdown
4. Handling multiple pages (crawling)

Supported sources:
- Single URL: Any web page
- URL list file: .txt file with one URL per line
- Sitemap: XML sitemap for batch processing
"""

import os
import re
import time
import json
import requests
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse


class WebScraper:
    """Scrape web pages and convert to markdown for the skills pipeline."""

    def __init__(self, output_dir: str = None, rate_limit: float = 1.0):
        self.output_dir = Path(output_dir) if output_dir else Path("./web_output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limit = rate_limit
        self.last_request_time = 0
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })

    def _wait_for_rate_limit(self):
        """Wait to respect rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    def _fetch_page(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Fetch a web page and return (html, final_url)."""
        self._wait_for_rate_limit()
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            encoding = response.encoding or 'utf-8'
            html = response.content.decode(encoding, errors='replace')
            
            return html, response.url
        except Exception as e:
            print(f"  [ERROR] Failed to fetch {url}: {e}")
            return None, None

    def _extract_title(self, html: str) -> str:
        """Extract title from HTML."""
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = title_match.group(1).strip()
            title = re.sub(r'\s+', ' ', title)
            if '|' in title:
                title = title.split('|')[0].strip()
            if '-' in title and len(title) > 20:
                title = title.split('-')[0].strip()
            return title[:100]
        return "Untitled"

    def _html_to_markdown(self, html: str, url: str = "") -> str:
        """Convert HTML to Markdown."""
        html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
        
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r'<aside[^>]*>.*?</aside>', '', html, flags=re.IGNORECASE | re.DOTALL)
        
        title = self._extract_title(html)
        
        body_match = re.search(r'<(?:article|main)[^>]*>(.*?)</(?:article|main)>', html, re.IGNORECASE | re.DOTALL)
        if body_match:
            content = body_match.group(1)
        else:
            body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.IGNORECASE | re.DOTALL)
            content = body_match.group(1) if body_match else html
        
        content = re.sub(r'<br\s*/?>\s*<br\s*/?>', '\n\n', content)
        content = re.sub(r'<br\s*/?>', '\n', content)
        content = re.sub(r'</p>', '\n\n', content, flags=re.IGNORECASE)
        content = re.sub(r'</div>', '\n', content, flags=re.IGNORECASE)
        content = re.sub(r'</li>', '\n', content, flags=re.IGNORECASE)
        
        content = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<h4[^>]*>(.*?)</h4>', r'\n#### \1\n', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<h5[^>]*>(.*?)</h5>', r'\n##### \1\n', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<h6[^>]*>(.*?)</h6>', r'\n###### \1\n', content, flags=re.IGNORECASE | re.DOTALL)
        
        content = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', content, flags=re.IGNORECASE | re.DOTALL)
        
        content = re.sub(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', r'[\2](\1)', content, flags=re.IGNORECASE | re.DOTALL)
        
        content = re.sub(r'<li[^>]*>', '\n- ', content, flags=re.IGNORECASE)
        
        content = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<pre[^>]*>(.*?)</pre>', r'\n```\n\1\n```\n', content, flags=re.IGNORECASE | re.DOTALL)
        
        content = re.sub(r'<[^>]+>', '', content)
        
        content = content.replace('&nbsp;', ' ')
        content = content.replace('&amp;', '&')
        content = content.replace('&lt;', '<')
        content = content.replace('&gt;', '>')
        content = content.replace('&quot;', '"')
        content = content.replace('&#39;', "'")
        content = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), content)
        
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = re.sub(r' {2,}', ' ', content)
        
        lines = content.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line:
                cleaned_lines.append(line)
            elif cleaned_lines and cleaned_lines[-1]:
                cleaned_lines.append('')
        
        markdown = '\n'.join(cleaned_lines)
        
        header = f"# {title}\n\n"
        if url:
            header += f"Source: {url}\n\n"
        
        return header + markdown

    def scrape_url(self, url: str) -> Optional[Path]:
        """Scrape a single URL and save as markdown."""
        print(f"[WebScraper] Scraping: {url}")
        
        html, final_url = self._fetch_page(url)
        if not html:
            return None
        
        markdown = self._html_to_markdown(html, final_url or url)
        
        parsed = urlparse(final_url or url)
        safe_name = re.sub(r'[^\w\-]', '_', parsed.path.strip('/').replace('/', '_') or 'index')
        if len(safe_name) > 50:
            safe_name = safe_name[:50]
        
        output_path = self.output_dir / "full.md"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
        
        print(f"  Output: {output_path}")
        print(f"  Lines: {len(markdown.splitlines())}")
        
        return output_path

    def scrape_urls(self, urls: List[str], combine: bool = True) -> Optional[Path]:
        """Scrape multiple URLs and optionally combine into one file."""
        print(f"[WebScraper] Scraping {len(urls)} URLs")
        
        all_markdown = []
        
        for i, url in enumerate(urls, 1):
            print(f"\n  [{i}/{len(urls)}] {url}")
            
            html, final_url = self._fetch_page(url)
            if html:
                markdown = self._html_to_markdown(html, final_url or url)
                all_markdown.append(markdown)
            else:
                print(f"    [SKIP] Failed to fetch")
        
        if not all_markdown:
            print("[WebScraper] No content scraped")
            return None
        
        if combine:
            combined = "\n\n---\n\n".join(all_markdown)
            output_path = self.output_dir / "full.md"
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(combined)
            
            print(f"\n[WebScraper] Combined output: {output_path}")
            print(f"  Total pages: {len(all_markdown)}")
            print(f"  Total lines: {len(combined.splitlines())}")
            
            return output_path
        else:
            for i, markdown in enumerate(all_markdown, 1):
                output_path = self.output_dir / f"page_{i:03d}.md"
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(markdown)
            
            print(f"\n[WebScraper] Saved {len(all_markdown)} individual files")
            return self.output_dir / "page_001.md"

    def scrape_url_list_file(self, file_path: str, combine: bool = True) -> Optional[Path]:
        """Scrape URLs from a text file (one URL per line)."""
        with open(file_path, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and line.strip().startswith('http')]
        
        if not urls:
            print(f"[WebScraper] No URLs found in {file_path}")
            return None
        
        print(f"[WebScraper] Found {len(urls)} URLs in {file_path}")
        return self.scrape_urls(urls, combine=combine)


def scrape_web(url: str, output_dir: str = None) -> Path:
    """Convenience function to scrape a single URL."""
    scraper = WebScraper(output_dir)
    return scraper.scrape_url(url)


def scrape_multiple_urls(urls: List[str], output_dir: str = None, combine: bool = True) -> Path:
    """Convenience function to scrape multiple URLs."""
    scraper = WebScraper(output_dir)
    return scraper.scrape_urls(urls, combine=combine)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape web pages for skills pipeline")
    parser.add_argument("input", help="URL or path to URL list file")
    parser.add_argument("-o", "--output", help="Output directory")
    parser.add_argument("--no-combine", action="store_true", help="Don't combine multiple pages")
    parser.add_argument("--rate-limit", type=float, default=1.0, help="Seconds between requests")
    
    args = parser.parse_args()
    
    scraper = WebScraper(args.output, rate_limit=args.rate_limit)
    
    if args.input.startswith('http'):
        scraper.scrape_url(args.input)
    else:
        scraper.scrape_url_list_file(args.input, combine=not args.no_combine)
