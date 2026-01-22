#!/usr/bin/env python3
"""
Onion Peeler: Recursive Markdown Chunking Agent

This module implements a two-phase chunking strategy:
1. Chapter Split: Use LLM to analyze headers and decide where to split large documents
2. Recursive Peel: Iteratively split chunks using K-nearest-neighbor token anchors

Key concept: Instead of outputting full chunks, the LLM outputs "wedges" -
anchor tokens that mark where splits should occur.
"""

import os
import re
import json
import requests
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv
from Levenshtein import distance as levenshtein_distance
from pathlib import Path

# Load .env from pdf2skills directory
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Configuration
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL")
CHUNK_MAX_TOKENS = int(os.getenv("CHUNK_MAX_TOKENS", 8000))
CHUNK_MAX_ITERATIONS = int(os.getenv("CHUNK_MAX_ITERATIONS", 5))
CHUNK_ANCHOR_LENGTH = int(os.getenv("CHUNK_ANCHOR_LENGTH", 30))

# Global Settings
OUTPUT_LANGUAGE = os.getenv("OUTPUT_LANGUAGE", "English")

# Approximate tokens: 1 Chinese char ≈ 1.5 tokens, 1 English word ≈ 1.3 tokens
# For safety, use ~2 chars per token for Chinese text
CHARS_PER_TOKEN = 2


@dataclass
class Header:
    """Represents a markdown header."""
    level: int
    text: str
    line_number: int


@dataclass
class ChunkNode:
    """A node in the chunk tree."""
    id: str
    title: str
    parent_path: list[str] = field(default_factory=list)
    children: list["ChunkNode"] = field(default_factory=list)
    content: str = ""
    start_line: int = 0
    end_line: int = 0
    iteration: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "parent_path": self.parent_path,
            "children": [c.to_dict() for c in self.children],
            "content_preview": self.content[:200] + "..." if len(self.content) > 200 else self.content,
            "content_length": len(self.content),
            "line_range": [self.start_line, self.end_line],
            "iteration": self.iteration
        }


class DeepSeekClient:
    """Client for DeepSeek API via SiliconFlow."""

    def __init__(self, model: str = "deepseek-ai/DeepSeek-V3.2"):
        self.model = model
        self.api_key = SILICONFLOW_API_KEY
        self.base_url = SILICONFLOW_BASE_URL

    def chat(self, messages: list[dict], max_tokens: int = 2000, temperature: float = 0.3) -> str:
        """Send chat completion request."""
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class OnionPeeler:
    """
    Recursive markdown chunking agent.

    Phase 1 (chapter_split): Analyze headers to split into major sections
    Phase 2+ (recursive_peel): Split oversized chunks using anchor tokens
    """

    def __init__(self, markdown_path: str):
        self.markdown_path = Path(markdown_path)
        self.content = self.markdown_path.read_text(encoding="utf-8")
        self.lines = self.content.split("\n")
        self.llm = DeepSeekClient()
        self.headers: list[Header] = []
        self.chunk_counter = 0

    def extract_headers(self) -> list[Header]:
        """Extract all headers with their line numbers."""
        headers = []
        for i, line in enumerate(self.lines, 1):
            match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if match:
                level = len(match.group(1))
                text = match.group(2).strip()
                headers.append(Header(level=level, text=text, line_number=i))
        self.headers = headers
        return headers

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return len(text) // CHARS_PER_TOKEN

    def get_header_tree_text(self) -> str:
        """Generate a text representation of header tree for LLM."""
        if not self.headers:
            self.extract_headers()

        lines = []
        for h in self.headers:
            indent = "  " * (h.level - 1)
            lines.append(f"[Line {h.line_number}] {indent}{'#' * h.level} {h.text}")
        return "\n".join(lines)

    def _generate_chunk_id(self) -> str:
        """Generate unique chunk ID."""
        self.chunk_counter += 1
        return f"chunk_{self.chunk_counter:04d}"

    # =========================================================================
    # Phase 1: Chapter Split
    # =========================================================================

    def chapter_split(self) -> list[ChunkNode]:
        """
        Phase 1: Split document into major chapters/sections.

        Uses LLM to analyze the header structure and decide where to split
        the document into chunks small enough for further processing.
        """
        header_tree = self.get_header_tree_text()
        total_chars = len(self.content)
        estimated_tokens = self.estimate_tokens(self.content)

        prompt = f"""You are a document structure analyzer. Your task is to decide where to split a large markdown document into logical sections.

## Document Statistics
- Total characters: {total_chars:,}
- Estimated tokens: {estimated_tokens:,}
- Target chunk size: under 100,000 tokens (approximately {100000 * CHARS_PER_TOKEN:,} characters)
- Number of headers: {len(self.headers)}

## Header Structure (with line numbers)
```
{header_tree}
```

## Your Task
Analyze the header structure and identify SPLIT POINTS - places where the document should be divided into separate chunks.

Rules:
1. Each chunk should be under 100,000 tokens
2. Split at logical boundaries (between chapters, major sections)
3. Keep related content together - don't break in the middle of a topic
4. Prefer splitting at higher-level headers (chapters > sections > subsections)

## Output Format
Return a JSON array of split points. Each split point is the LINE NUMBER where a new chunk should START.
The first chunk always starts at line 1, so don't include line 1.

Example output:
```json
{{"split_points": [175, 788, 2836], "reasoning": "Split at Chapter 1, Chapter 2, Chapter 3 boundaries"}}
```

IMPORTANT: Your "reasoning" field MUST be written in {OUTPUT_LANGUAGE}.

Return ONLY the JSON object, no other text."""

        print("Phase 1: Analyzing document structure for chapter split...")
        response = self.llm.chat([{"role": "user", "content": prompt}], max_tokens=1000)

        # Parse response
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^{}]*"split_points"[^{}]*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(response)

            split_points = [1] + sorted(result.get("split_points", []))
            print(f"  Split points: {split_points}")
            if "reasoning" in result:
                print(f"  Reasoning: {result['reasoning']}")
        except json.JSONDecodeError:
            print(f"  Warning: Could not parse LLM response, using default splits")
            # Fallback: split at major chapter boundaries
            split_points = [1]
            for h in self.headers:
                if "第" in h.text and "章" in h.text:
                    split_points.append(h.line_number)
            split_points = sorted(set(split_points))

        # Create chunks based on split points
        chunks = []
        for i, start_line in enumerate(split_points):
            end_line = split_points[i + 1] - 1 if i + 1 < len(split_points) else len(self.lines)

            # Find title for this chunk
            title = "Document Start"
            for h in self.headers:
                if h.line_number >= start_line:
                    title = h.text
                    break

            chunk_content = "\n".join(self.lines[start_line - 1:end_line])

            chunk = ChunkNode(
                id=self._generate_chunk_id(),
                title=title,
                parent_path=[],
                content=chunk_content,
                start_line=start_line,
                end_line=end_line,
                iteration=1
            )
            chunks.append(chunk)
            print(f"  Chunk {chunk.id}: Lines {start_line}-{end_line}, ~{self.estimate_tokens(chunk_content):,} tokens, Title: {title[:50]}")

        return chunks

    # =========================================================================
    # Phase 2+: Recursive Peel with Anchor Tokens
    # =========================================================================

    def find_anchor_position(self, content: str, anchor: str) -> int:
        """
        Find the position of an anchor in content using fuzzy matching.
        Returns the character position, or -1 if not found.
        """
        anchor = anchor.strip()
        if not anchor:
            return -1

        # Try exact match first
        pos = content.find(anchor)
        if pos != -1:
            return pos

        # Fuzzy match using sliding window
        anchor_len = len(anchor)
        best_pos = -1
        best_distance = float('inf')
        threshold = max(3, anchor_len // 3)  # Allow ~33% edit distance

        for i in range(len(content) - anchor_len + 1):
            window = content[i:i + anchor_len]
            dist = levenshtein_distance(anchor, window)
            if dist < best_distance and dist <= threshold:
                best_distance = dist
                best_pos = i

        return best_pos

    def recursive_peel(self, chunk: ChunkNode, current_iteration: int = 2) -> list[ChunkNode]:
        """
        Recursively split a chunk using LLM-generated anchor tokens.

        The LLM reads the chunk and outputs K-nearest-neighbor tokens
        (anchors) marking where splits should occur.
        """
        if current_iteration > CHUNK_MAX_ITERATIONS:
            print(f"  Max iterations reached for {chunk.id}")
            return [chunk]

        estimated_tokens = self.estimate_tokens(chunk.content)
        if estimated_tokens <= CHUNK_MAX_TOKENS:
            print(f"  Chunk {chunk.id} is small enough ({estimated_tokens:,} tokens)")
            return [chunk]

        print(f"  Peeling {chunk.id} (iteration {current_iteration}, ~{estimated_tokens:,} tokens)...")

        prompt = f"""You are a document chunking assistant. Your task is to identify logical split points within this text.

## Chunk Information
- Parent path: {' > '.join(chunk.parent_path) if chunk.parent_path else 'Root'}
- Current title: {chunk.title}
- Content length: {len(chunk.content):,} characters (~{estimated_tokens:,} tokens)
- Target chunk size: {CHUNK_MAX_TOKENS:,} tokens

## Content to Split
```
{chunk.content}
```

## Your Task
Identify 2-4 split points where this content should be divided. For each split point, provide an ANCHOR - a sequence of {CHUNK_ANCHOR_LENGTH} characters that marks where the split should occur.

Rules:
1. Choose anchors at logical boundaries (between sections, topics, paragraphs)
2. The anchor should be EXACTLY {CHUNK_ANCHOR_LENGTH} characters from the text (copy directly, do not modify)
3. Choose unique, identifiable text sequences
4. Split into roughly equal-sized chunks when logical boundaries allow

## Output Format
Return a JSON object with anchors:
```json
{{
  "anchors": [
    {{"anchor": "exactly {CHUNK_ANCHOR_LENGTH} chars from text", "description": "After section X, before section Y"}},
    {{"anchor": "another {CHUNK_ANCHOR_LENGTH} char sequence", "description": "Between topic A and B"}}
  ]
}}
```

IMPORTANT: Your "description" fields MUST be written in {OUTPUT_LANGUAGE}.

Return ONLY the JSON object."""

        try:
            response = self.llm.chat([{"role": "user", "content": prompt}], max_tokens=1500)

            # Parse anchors
            json_match = re.search(r'\{[^{}]*"anchors"[^{}]*\[.*?\][^{}]*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(response)

            anchors = result.get("anchors", [])

        except (json.JSONDecodeError, Exception) as e:
            print(f"    Warning: Could not parse LLM response: {e}")
            return [chunk]

        if not anchors:
            print(f"    No anchors found, keeping chunk as-is")
            return [chunk]

        # Find anchor positions and split
        split_positions = [0]
        for anchor_info in anchors:
            anchor_text = anchor_info.get("anchor", "")
            pos = self.find_anchor_position(chunk.content, anchor_text)
            if pos > 0:
                split_positions.append(pos)
                print(f"    Found anchor at position {pos}: '{anchor_text[:30]}...'")
            else:
                print(f"    Warning: Could not find anchor: '{anchor_text[:30]}...'")

        split_positions.append(len(chunk.content))
        split_positions = sorted(set(split_positions))

        if len(split_positions) <= 2:
            print(f"    No valid split positions found")
            return [chunk]

        # Create child chunks
        child_chunks = []
        for i in range(len(split_positions) - 1):
            start_pos = split_positions[i]
            end_pos = split_positions[i + 1]

            sub_content = chunk.content[start_pos:end_pos].strip()
            if not sub_content:
                continue

            # Find title from first header in content
            title = f"{chunk.title} (Part {i + 1})"
            header_match = re.search(r'^#\s+(.+)$', sub_content, re.MULTILINE)
            if header_match:
                title = header_match.group(1)

            child = ChunkNode(
                id=self._generate_chunk_id(),
                title=title,
                parent_path=chunk.parent_path + [chunk.title],
                content=sub_content,
                start_line=chunk.start_line,  # Approximate
                end_line=chunk.end_line,
                iteration=current_iteration
            )
            child_chunks.append(child)

        # Recursively process children
        final_chunks = []
        for child in child_chunks:
            final_chunks.extend(self.recursive_peel(child, current_iteration + 1))

        # Update parent's children
        chunk.children = child_chunks

        return final_chunks

    # =========================================================================
    # Main Processing
    # =========================================================================

    def peel(self) -> tuple[list[ChunkNode], ChunkNode]:
        """
        Main entry point: Peel the markdown document into chunks.

        Returns:
            tuple: (flat list of final chunks, root node with tree structure)
        """
        print(f"\n{'='*60}")
        print(f"Onion Peeler: Processing {self.markdown_path.name}")
        print(f"{'='*60}")
        print(f"Total lines: {len(self.lines):,}")
        print(f"Total chars: {len(self.content):,}")
        print(f"Estimated tokens: {self.estimate_tokens(self.content):,}")
        print(f"Target chunk size: {CHUNK_MAX_TOKENS:,} tokens")
        print(f"Max iterations: {CHUNK_MAX_ITERATIONS}")
        print(f"Output language: {OUTPUT_LANGUAGE}")
        print()

        # Phase 1: Chapter split
        initial_chunks = self.chapter_split()

        # Create root node
        root = ChunkNode(
            id="root",
            title=self.markdown_path.stem,
            parent_path=[],
            content="",
            start_line=1,
            end_line=len(self.lines),
            iteration=0
        )
        root.children = initial_chunks

        # Phase 2+: Recursive peel
        print(f"\nPhase 2: Recursive peeling of oversized chunks...")
        final_chunks = []
        for chunk in initial_chunks:
            final_chunks.extend(self.recursive_peel(chunk))

        print(f"\n{'='*60}")
        print(f"Peeling Complete!")
        print(f"{'='*60}")
        print(f"Total chunks: {len(final_chunks)}")
        for chunk in final_chunks:
            tokens = self.estimate_tokens(chunk.content)
            path = " > ".join(chunk.parent_path + [chunk.title]) if chunk.parent_path else chunk.title
            print(f"  {chunk.id}: {tokens:,} tokens - {path[:60]}...")

        return final_chunks, root

    def save_results(self, output_dir: str | Path = None) -> Path:
        """Run peeling and save results to files."""
        if output_dir is None:
            output_dir = self.markdown_path.parent / f"{self.markdown_path.stem}_chunks"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        chunks, root = self.peel()

        # Save tree structure
        tree_path = output_dir / "tree.json"
        with open(tree_path, "w", encoding="utf-8") as f:
            json.dump(root.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"\nTree saved to: {tree_path}")

        # Save individual chunks
        chunks_dir = output_dir / "chunks"
        chunks_dir.mkdir(exist_ok=True)

        chunk_index = []
        for book_index, chunk in enumerate(chunks):
            # Save chunk content
            chunk_path = chunks_dir / f"{chunk.id}.md"

            # Add metadata header
            metadata = f"""---
id: {chunk.id}
book_index: {book_index}
title: {chunk.title}
parent_path: {' > '.join(chunk.parent_path) if chunk.parent_path else 'Root'}
start_line: {chunk.start_line}
end_line: {chunk.end_line}
iteration: {chunk.iteration}
tokens: ~{self.estimate_tokens(chunk.content)}
---

"""
            with open(chunk_path, "w", encoding="utf-8") as f:
                f.write(metadata + chunk.content)

            chunk_index.append({
                "id": chunk.id,
                "book_index": book_index,
                "title": chunk.title,
                "parent_path": chunk.parent_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "file": str(chunk_path.relative_to(output_dir)),
                "tokens": self.estimate_tokens(chunk.content)
            })

        # Save chunk index
        index_path = output_dir / "chunks_index.json"
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(chunk_index, f, ensure_ascii=False, indent=2)
        print(f"Chunks saved to: {chunks_dir}")
        print(f"Index saved to: {index_path}")

        return output_dir


def main():
    """CLI entry point."""
    import sys

    if len(sys.argv) < 2:
        # Default test file
        md_path = "test_data/financial_statement_analysis_test1_output/full.md"
    else:
        md_path = sys.argv[1]

    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    peeler = OnionPeeler(md_path)
    peeler.save_results(output_dir)


if __name__ == "__main__":
    main()
