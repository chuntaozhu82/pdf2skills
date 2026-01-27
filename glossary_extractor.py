"""
Glossary Extractor - Extract domain-specific terminology from SKUs

This module extracts domain terms from SKU outputs during the pdf2skills pipeline.
It creates a glossary.json that can be used by skills2app for runtime term lookup.

Extraction Sources:
- SKU metadata.name - skill names contain key concepts
- SKU context.applicable_objects - domain entities
- SKU core_logic.variables - domain variables with definitions
- SKU custom_attributes.domain_tags - domain categories

Output: glossary.json with structured terminology
"""

import os
import json
import time
import requests
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any
from collections import defaultdict
from dotenv import load_dotenv


# Load environment
load_dotenv()

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
GLM_RATE_LIMIT_SECONDS = float(os.getenv("GLM_RATE_LIMIT_SECONDS", "3.0"))
OUTPUT_LANGUAGE = os.getenv("OUTPUT_LANGUAGE", "Chinese")


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class GlossaryTerm:
    """A single glossary term."""
    term: str
    aliases: List[str] = field(default_factory=list)
    definition: str = ""
    source_skus: List[str] = field(default_factory=list)
    category: str = "general"
    term_type: str = "concept"  # concept, entity, variable, tag

    def to_dict(self) -> dict:
        return {
            "term": self.term,
            "aliases": self.aliases,
            "definition": self.definition,
            "source_skus": self.source_skus,
            "category": self.category,
            "term_type": self.term_type
        }


@dataclass
class GlossaryVariable:
    """A variable definition from SKU core_logic."""
    name: str
    var_type: str
    description: str
    source_sku: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.var_type,
            "description": self.description,
            "source_sku": self.source_sku
        }


# ============================================================================
# GLM Client (for optional LLM-assisted extraction)
# ============================================================================

class GLM4Client:
    """Client for GLM-4.7 API via SiliconFlow."""

    def __init__(self, rate_limit: float = None):
        self.api_key = SILICONFLOW_API_KEY
        self.base_url = SILICONFLOW_BASE_URL
        self.model = "Pro/zai-org/GLM-4.7"
        self.rate_limit = rate_limit or GLM_RATE_LIMIT_SECONDS
        self.last_call_time = 0

    def _wait_for_rate_limit(self):
        elapsed = time.time() - self.last_call_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_call_time = time.time()

    def chat(self, messages: list, temperature: float = 0.3, max_tokens: int = 2000) -> str:
        """Send chat completion request."""
        if not self.api_key:
            raise ValueError("SILICONFLOW_API_KEY not set")

        self._wait_for_rate_limit()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()

        result = response.json()
        return result["choices"][0]["message"]["content"]


# ============================================================================
# Glossary Extractor
# ============================================================================

class GlossaryExtractor:
    """
    Extract domain terminology from SKU outputs.

    This creates a glossary.json that can be used for:
    - Runtime term lookup in generated apps
    - Chatbot context enhancement
    - User guidance with domain-specific vocabulary
    """

    def __init__(self, output_dir: str, use_llm: bool = False):
        """
        Initialize the glossary extractor.

        Args:
            output_dir: Path to pdf2skills output directory (contains full_chunks_skus/)
            use_llm: Whether to use LLM for enhanced term extraction
        """
        self.output_dir = Path(output_dir)
        self.skus_dir = self.output_dir / "full_chunks_skus"
        self.use_llm = use_llm

        # Storage
        self.terms: Dict[str, GlossaryTerm] = {}
        self.variables: List[GlossaryVariable] = []
        self.categories: Set[str] = set()

        # LLM client (lazy init)
        self._llm_client = None

        # Validate paths
        if not self.skus_dir.exists():
            raise FileNotFoundError(f"SKUs directory not found: {self.skus_dir}")

    @property
    def llm_client(self):
        if self._llm_client is None:
            self._llm_client = GLM4Client()
        return self._llm_client

    # =========================================================================
    # Data Loaders
    # =========================================================================

    def _load_skus_index(self) -> dict:
        """Load SKUs index."""
        index_path = self.skus_dir / "skus_index.json"
        if not index_path.exists():
            return {"skus": []}

        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_sku(self, sku_file: str) -> Optional[dict]:
        """Load a single SKU file."""
        sku_path = self.skus_dir / sku_file
        if not sku_path.exists():
            return None

        with open(sku_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_all_skus(self) -> List[dict]:
        """Load all SKU files."""
        index = self._load_skus_index()
        skus = []

        for sku_entry in index.get("skus", []):
            sku_file = sku_entry.get("file", "")
            sku_data = self._load_sku(sku_file)
            if sku_data:
                skus.append(sku_data)

        return skus

    # =========================================================================
    # Term Extraction
    # =========================================================================

    def _normalize_term(self, term: str) -> str:
        """Normalize a term for deduplication."""
        return term.strip().lower()

    def _add_term(
        self,
        term: str,
        source_sku: str,
        category: str = "general",
        term_type: str = "concept",
        definition: str = ""
    ):
        """Add or update a term in the glossary."""
        normalized = self._normalize_term(term)

        if normalized in self.terms:
            # Update existing term
            existing = self.terms[normalized]
            if source_sku not in existing.source_skus:
                existing.source_skus.append(source_sku)
            if definition and not existing.definition:
                existing.definition = definition
        else:
            # Create new term
            self.terms[normalized] = GlossaryTerm(
                term=term,
                aliases=[],
                definition=definition,
                source_skus=[source_sku],
                category=category,
                term_type=term_type
            )

        self.categories.add(category)

    def _extract_from_sku(self, sku: dict):
        """Extract terms from a single SKU."""
        uuid = sku.get("metadata", {}).get("uuid", "unknown")
        sku_name = sku.get("metadata", {}).get("name", "")

        # 1. Extract from metadata.name (skill name = key concept)
        if sku_name:
            self._add_term(
                term=sku_name,
                source_sku=uuid,
                category="skill",
                term_type="concept"
            )

        # 2. Extract from context.applicable_objects (domain entities)
        applicable_objects = sku.get("context", {}).get("applicable_objects", [])
        for obj in applicable_objects:
            if obj and isinstance(obj, str):
                self._add_term(
                    term=obj,
                    source_sku=uuid,
                    category="entity",
                    term_type="entity"
                )

        # 3. Extract from core_logic.variables (domain variables)
        variables = sku.get("core_logic", {}).get("variables", [])
        for var in variables:
            if isinstance(var, dict):
                var_name = var.get("name", "")
                var_type = var.get("type", "unknown")
                var_desc = var.get("description", "")

                if var_name:
                    # Add as term
                    self._add_term(
                        term=var_name,
                        source_sku=uuid,
                        category="variable",
                        term_type="variable",
                        definition=var_desc
                    )

                    # Also store as variable
                    self.variables.append(GlossaryVariable(
                        name=var_name,
                        var_type=var_type,
                        description=var_desc,
                        source_sku=uuid
                    ))

        # 4. Extract from custom_attributes.domain_tags (domain categories)
        domain_tags = sku.get("custom_attributes", {}).get("domain_tags", [])
        for tag in domain_tags:
            if tag and isinstance(tag, str):
                self._add_term(
                    term=tag,
                    source_sku=uuid,
                    category="tag",
                    term_type="tag"
                )

        # 5. Extract from context.prerequisites (prerequisite concepts)
        prerequisites = sku.get("context", {}).get("prerequisites", [])
        for prereq in prerequisites:
            if prereq and isinstance(prereq, str):
                self._add_term(
                    term=prereq,
                    source_sku=uuid,
                    category="prerequisite",
                    term_type="concept"
                )

    def _extract_with_llm(self, sku: dict):
        """Use LLM to extract additional terms from execution body."""
        if not self.use_llm:
            return

        uuid = sku.get("metadata", {}).get("uuid", "unknown")
        execution_body = sku.get("core_logic", {}).get("execution_body", "")

        if not execution_body or len(execution_body) < 50:
            return

        # Truncate for context limits
        body_snippet = execution_body[:2000]

        prompt = f"""从以下专业文本中提取关键术语和概念。只提取专业领域特有的术语，不要提取通用词汇。

文本：
{body_snippet}

请以JSON格式返回，格式如下：
{{
  "terms": [
    {{"term": "术语名称", "category": "类别", "definition": "简短定义"}}
  ]
}}

类别可以是：concept（概念）、process（流程）、metric（指标）、regulation（法规）"""

        try:
            response = self.llm_client.chat([{"role": "user", "content": prompt}])

            # Parse response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                for term_data in result.get("terms", []):
                    term = term_data.get("term", "")
                    if term:
                        self._add_term(
                            term=term,
                            source_sku=uuid,
                            category=term_data.get("category", "concept"),
                            term_type="concept",
                            definition=term_data.get("definition", "")
                        )
        except Exception as e:
            print(f"    Warning: LLM extraction failed for {uuid}: {e}")

    # =========================================================================
    # Main Methods
    # =========================================================================

    def extract(self, use_llm_enhancement: bool = None) -> dict:
        """
        Extract glossary from all SKUs.

        Args:
            use_llm_enhancement: Override use_llm setting for this extraction

        Returns:
            Dictionary containing the extracted glossary
        """
        if use_llm_enhancement is not None:
            self.use_llm = use_llm_enhancement

        print(f"Loading SKUs from {self.skus_dir}...")
        skus = self._load_all_skus()
        print(f"Found {len(skus)} SKUs")

        # Extract from each SKU
        for i, sku in enumerate(skus):
            sku_name = sku.get("metadata", {}).get("name", "unknown")
            print(f"  [{i+1}/{len(skus)}] Extracting from: {sku_name[:40]}...")

            self._extract_from_sku(sku)

            if self.use_llm:
                self._extract_with_llm(sku)

        print(f"\nExtracted {len(self.terms)} unique terms")
        print(f"Categories: {', '.join(sorted(self.categories))}")

        return self._build_glossary()

    def _build_glossary(self) -> dict:
        """Build the final glossary structure."""
        # Get book name from index
        index = self._load_skus_index()
        book_source = index.get("metadata", {}).get("source_chunks_dir", "")

        # Try to extract book name from path
        book_name = "Unknown Book"
        if book_source:
            parts = book_source.split("/")
            for part in parts:
                if "_output" in part:
                    book_name = part.replace("_output", "").strip()
                    break

        # Group terms by category
        terms_by_category = defaultdict(list)
        for term in self.terms.values():
            terms_by_category[term.category].append(term.to_dict())

        return {
            "metadata": {
                "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source_book": book_name,
                "total_terms": len(self.terms),
                "total_variables": len(self.variables),
                "llm_enhanced": self.use_llm
            },
            "terms": [t.to_dict() for t in self.terms.values()],
            "terms_by_category": dict(terms_by_category),
            "variables": [v.to_dict() for v in self.variables],
            "categories": sorted(list(self.categories))
        }

    def save_results(self, output_path: Path = None) -> Path:
        """Save the glossary to JSON file."""
        if output_path is None:
            output_path = self.skus_dir / "glossary.json"

        glossary = self._build_glossary()

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(glossary, f, ensure_ascii=False, indent=2)

        print(f"\nGlossary saved to: {output_path}")
        return output_path


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract domain glossary from SKU outputs"
    )
    parser.add_argument(
        "output_dir",
        help="Path to pdf2skills output directory"
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use LLM for enhanced term extraction"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: output_dir/full_chunks_skus/glossary.json)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Glossary Extractor")
    print("=" * 60)
    print(f"Output dir: {args.output_dir}")
    print(f"LLM enhancement: {args.use_llm}")
    print("=" * 60)

    extractor = GlossaryExtractor(
        output_dir=args.output_dir,
        use_llm=args.use_llm
    )

    extractor.extract()

    output_path = Path(args.output) if args.output else None
    extractor.save_results(output_path)

    print("\nDone!")


if __name__ == "__main__":
    main()
