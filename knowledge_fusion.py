"""
Module 4: Knowledge Fusion - Tag Normalization, SKU Bucketing & Similarity Calculation

This module handles:
1. Tag Normalization: Unify applicable_objects and domain_tags across all SKUs
2. SKU Bucketing: Group SKUs by normalized tags/objects for efficient comparison
3. Similarity Calculation: Multi-dimensional similarity within buckets

Uses DeepSeek V3.2 from SiliconFlow for LLM tasks.
Uses BGE-M3 from SiliconFlow for embedding tasks.
"""

import os
import json
import time
import math
import uuid
import requests
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
from dotenv import load_dotenv
from pathlib import Path

# Load .env from pdf2skills directory
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)


# ============================================================================
# Configuration
# ============================================================================

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
OUTPUT_LANGUAGE = os.getenv("OUTPUT_LANGUAGE", "English")
BUCKET_THRESHOLD = float(os.getenv("BUCKET_THRESHOLD", "0.5"))

# Rate limiting
FUSION_RATE_LIMIT_SECONDS = float(os.getenv("FUSION_RATE_LIMIT_SECONDS", "2.0"))


# ============================================================================
# DeepSeek V3.2 Client
# ============================================================================

class DeepSeekClient:
    """Client for DeepSeek V3.2 via SiliconFlow API."""

    def __init__(self, api_key: str = None, base_url: str = None, rate_limit: float = None):
        self.api_key = api_key or SILICONFLOW_API_KEY
        self.base_url = base_url or SILICONFLOW_BASE_URL
        self.model = "deepseek-ai/DeepSeek-V3"
        self.rate_limit = rate_limit if rate_limit is not None else FUSION_RATE_LIMIT_SECONDS
        self._last_call_time = 0

        if not self.api_key:
            raise ValueError("SILICONFLOW_API_KEY not set in environment")

    def _apply_rate_limit(self):
        """Apply rate limiting between API calls."""
        if self.rate_limit > 0:
            elapsed = time.time() - self._last_call_time
            if elapsed < self.rate_limit:
                sleep_time = self.rate_limit - elapsed
                print(f"  [RATE LIMIT] Waiting {sleep_time:.1f}s...")
                time.sleep(sleep_time)
        self._last_call_time = time.time()

    def chat(self, messages: list, max_tokens: int = 4000, temperature: float = 0.3) -> str:
        """Send chat completion request to DeepSeek V3.2."""
        self._apply_rate_limit()

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        result = response.json()
        return result["choices"][0]["message"]["content"]


# ============================================================================
# Tag Normalization Prompts
# ============================================================================

# Location: pdf2skills/knowledge_fusion.py, line ~95
NORMALIZE_OBJECTS_PROMPT = '''You are a knowledge engineer normalizing terminology across a knowledge base.

## Task
Given a list of "applicable_objects" extracted from multiple knowledge units, identify groups that refer to the EXACT SAME concept and should be merged.

## Rules for applicable_objects (STRICT)
- Only merge items that are 100% semantically identical
- Different but related concepts should NOT be merged
- Preserve domain-specific precision
- When merging, choose the most precise/professional term as the canonical name

## Input
Here are all unique applicable_objects found across {sku_count} knowledge units:
{objects_list}

## Output Format
Return a JSON object mapping original terms to their canonical form.
- If a term should remain unchanged, map it to itself
- If multiple terms should merge, map them all to the same canonical term

```json
{{
  "original_term_1": "canonical_term",
  "original_term_2": "canonical_term",
  "term_that_stays": "term_that_stays"
}}
```

## Language
Use {output_language} for canonical terms.

Return ONLY the JSON object, no other text.'''


# Location: pdf2skills/knowledge_fusion.py, line ~130
NORMALIZE_TAGS_PROMPT = '''You are a knowledge engineer normalizing terminology across a knowledge base.

## Task
Given a list of "domain_tags" extracted from multiple knowledge units, identify groups that refer to similar concepts and could be merged into unified categories.

## Rules for domain_tags (FLEXIBLE)
- Merge synonyms, abbreviations, and closely related terms
- Create broader category names when appropriate
- Merge language variants (e.g., Chinese and English versions of same concept)
- When merging, choose a clear, professional canonical name

## Input
Here are all unique domain_tags found across {sku_count} knowledge units:
{tags_list}

## Output Format
Return a JSON object mapping original terms to their canonical form.
- If a term should remain unchanged, map it to itself
- If multiple terms should merge, map them all to the same canonical term

```json
{{
  "original_tag_1": "canonical_tag",
  "original_tag_2": "canonical_tag",
  "tag_that_stays": "tag_that_stays"
}}
```

## Language
Use {output_language} for canonical terms.

Return ONLY the JSON object, no other text.'''


# ============================================================================
# Tag Normalizer
# ============================================================================

class TagNormalizer:
    """
    Normalizes applicable_objects and domain_tags across all SKUs.

    Process:
    1. Collect all unique objects and tags from all SKUs
    2. LLM decides which objects should merge (strict - only 100% identical)
    3. LLM decides which tags should merge (flexible - synonyms OK)
    4. Apply mappings back to all SKUs
    """

    def __init__(self, skus_dir: str):
        """
        Initialize with path to SKUs directory.

        Args:
            skus_dir: Path to directory containing skus_index.json and skus/
        """
        self.skus_dir = Path(skus_dir)
        self.index_file = self.skus_dir / "skus_index.json"
        self.skus_path = self.skus_dir / "skus"

        # Load index
        with open(self.index_file, 'r', encoding='utf-8') as f:
            self.index_data = json.load(f)

        self.llm = DeepSeekClient()
        self.output_language = OUTPUT_LANGUAGE

        # Collected terms
        self.all_objects: set = set()
        self.all_tags: set = set()

        # Mappings (original -> canonical)
        self.objects_mapping: dict = {}
        self.tags_mapping: dict = {}

    def collect_terms(self):
        """Collect all unique applicable_objects and domain_tags from all SKUs."""
        print("[TagNormalizer] Collecting terms from all SKUs...")

        for sku_info in self.index_data["skus"]:
            sku_file = self.skus_dir / sku_info["file"]

            with open(sku_file, 'r', encoding='utf-8') as f:
                sku = json.load(f)

            # Collect applicable_objects
            objects = sku.get("context", {}).get("applicable_objects", [])
            for obj in objects:
                if obj and obj.strip():
                    self.all_objects.add(obj.strip())

            # Collect domain_tags
            tags = sku.get("custom_attributes", {}).get("domain_tags", [])
            for tag in tags:
                if tag and tag.strip():
                    self.all_tags.add(tag.strip())

        print(f"  Found {len(self.all_objects)} unique applicable_objects")
        print(f"  Found {len(self.all_tags)} unique domain_tags")

    def normalize_objects(self):
        """Use LLM to create mapping for applicable_objects (strict merging)."""
        if not self.all_objects:
            print("[TagNormalizer] No applicable_objects to normalize")
            return

        print(f"[TagNormalizer] Normalizing {len(self.all_objects)} applicable_objects (strict)...")

        # Format objects list
        objects_list = "\n".join(f"- {obj}" for obj in sorted(self.all_objects))

        prompt = NORMALIZE_OBJECTS_PROMPT.format(
            sku_count=len(self.index_data["skus"]),
            objects_list=objects_list,
            output_language=self.output_language
        )

        messages = [{"role": "user", "content": prompt}]

        try:
            response = self.llm.chat(messages, max_tokens=4000, temperature=0.1)
            self.objects_mapping = self._parse_json_response(response)

            # Count merges
            canonical_count = len(set(self.objects_mapping.values()))
            merged_count = len(self.all_objects) - canonical_count
            print(f"  -> {len(self.all_objects)} objects normalized to {canonical_count} canonical terms ({merged_count} merged)")

        except Exception as e:
            print(f"  [ERROR] Failed to normalize objects: {e}")
            # Fallback: identity mapping
            self.objects_mapping = {obj: obj for obj in self.all_objects}

    def normalize_tags(self):
        """Use LLM to create mapping for domain_tags (flexible merging)."""
        if not self.all_tags:
            print("[TagNormalizer] No domain_tags to normalize")
            return

        print(f"[TagNormalizer] Normalizing {len(self.all_tags)} domain_tags (flexible)...")

        # Format tags list
        tags_list = "\n".join(f"- {tag}" for tag in sorted(self.all_tags))

        prompt = NORMALIZE_TAGS_PROMPT.format(
            sku_count=len(self.index_data["skus"]),
            tags_list=tags_list,
            output_language=self.output_language
        )

        messages = [{"role": "user", "content": prompt}]

        try:
            response = self.llm.chat(messages, max_tokens=4000, temperature=0.1)
            self.tags_mapping = self._parse_json_response(response)

            # Count merges
            canonical_count = len(set(self.tags_mapping.values()))
            merged_count = len(self.all_tags) - canonical_count
            print(f"  -> {len(self.all_tags)} tags normalized to {canonical_count} canonical terms ({merged_count} merged)")

        except Exception as e:
            print(f"  [ERROR] Failed to normalize tags: {e}")
            # Fallback: identity mapping
            self.tags_mapping = {tag: tag for tag in self.all_tags}

    def _parse_json_response(self, response: str) -> dict:
        """Parse JSON response from LLM."""
        response = response.strip()

        # Handle markdown code blocks
        if response.startswith("```"):
            lines = response.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            response = "\n".join(lines)

        return json.loads(response)

    def apply_mappings(self):
        """Apply normalization mappings to all SKU files."""
        print("[TagNormalizer] Applying mappings to SKU files...")

        updated_count = 0

        for sku_info in self.index_data["skus"]:
            sku_file = self.skus_dir / sku_info["file"]

            with open(sku_file, 'r', encoding='utf-8') as f:
                sku = json.load(f)

            modified = False

            # Normalize applicable_objects
            if "context" in sku and "applicable_objects" in sku["context"]:
                original_objects = sku["context"]["applicable_objects"]
                normalized_objects = []
                for obj in original_objects:
                    canonical = self.objects_mapping.get(obj.strip(), obj.strip()) if obj else obj
                    normalized_objects.append(canonical)

                # Deduplicate while preserving order
                seen = set()
                deduped_objects = []
                for obj in normalized_objects:
                    if obj not in seen:
                        seen.add(obj)
                        deduped_objects.append(obj)

                if deduped_objects != original_objects:
                    sku["context"]["applicable_objects"] = deduped_objects
                    modified = True

            # Normalize domain_tags
            if "custom_attributes" in sku and "domain_tags" in sku["custom_attributes"]:
                original_tags = sku["custom_attributes"]["domain_tags"]
                normalized_tags = []
                for tag in original_tags:
                    canonical = self.tags_mapping.get(tag.strip(), tag.strip()) if tag else tag
                    normalized_tags.append(canonical)

                # Deduplicate while preserving order
                seen = set()
                deduped_tags = []
                for tag in normalized_tags:
                    if tag not in seen:
                        seen.add(tag)
                        deduped_tags.append(tag)

                if deduped_tags != original_tags:
                    sku["custom_attributes"]["domain_tags"] = deduped_tags
                    modified = True

            # Save if modified
            if modified:
                with open(sku_file, 'w', encoding='utf-8') as f:
                    json.dump(sku, f, ensure_ascii=False, indent=2)
                updated_count += 1

        print(f"  -> Updated {updated_count} SKU files")

    def save_mappings(self, output_dir: str = None):
        """Save normalization mappings for reference."""
        output_path = Path(output_dir) if output_dir else self.skus_dir

        mappings_data = {
            "objects_mapping": self.objects_mapping,
            "tags_mapping": self.tags_mapping,
            "statistics": {
                "original_objects_count": len(self.all_objects),
                "canonical_objects_count": len(set(self.objects_mapping.values())) if self.objects_mapping else 0,
                "original_tags_count": len(self.all_tags),
                "canonical_tags_count": len(set(self.tags_mapping.values())) if self.tags_mapping else 0
            }
        }

        mappings_file = output_path / "normalization_mappings.json"
        with open(mappings_file, 'w', encoding='utf-8') as f:
            json.dump(mappings_data, f, ensure_ascii=False, indent=2)

        print(f"[TagNormalizer] Saved mappings to {mappings_file}")

    def normalize(self):
        """Run full normalization pipeline."""
        print("=" * 60)
        print("TAG NORMALIZATION")
        print("=" * 60)

        self.collect_terms()
        self.normalize_objects()
        self.normalize_tags()
        self.apply_mappings()
        self.save_mappings()

        print()
        print("[TagNormalizer] Normalization complete")


# ============================================================================
# SKU Bucketer
# ============================================================================

@dataclass
class Bucket:
    """A bucket containing related SKUs."""
    bucket_id: str
    sku_uuids: list = field(default_factory=list)
    shared_objects: set = field(default_factory=set)
    shared_tags: set = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "bucket_id": self.bucket_id,
            "sku_uuids": self.sku_uuids,
            "sku_count": len(self.sku_uuids),
            "shared_objects": list(self.shared_objects),
            "shared_tags": list(self.shared_tags)
        }


class SKUBucketer:
    """
    Groups SKUs into buckets based on normalized applicable_objects and domain_tags.

    Bucketing rules:
    - If >= threshold% of applicable_objects overlap, group together
    - OR if >= threshold% of domain_tags overlap, group together
    - Handles transitive grouping (A~B, B~C => A,B,C in same bucket)
    """

    def __init__(self, skus_dir: str, threshold: float = None):
        """
        Initialize bucketer.

        Args:
            skus_dir: Path to directory containing skus_index.json and skus/
            threshold: Overlap threshold (0-1), defaults to BUCKET_THRESHOLD env var
        """
        self.skus_dir = Path(skus_dir)
        self.index_file = self.skus_dir / "skus_index.json"
        self.skus_path = self.skus_dir / "skus"

        # Load index
        with open(self.index_file, 'r', encoding='utf-8') as f:
            self.index_data = json.load(f)

        self.threshold = threshold if threshold is not None else BUCKET_THRESHOLD

        # SKU data cache: uuid -> {objects: set, tags: set, trigger: str}
        self.sku_data: dict = {}

        # Bucketing results
        self.buckets: list[Bucket] = []

    def load_sku_data(self):
        """Load relevant fields from all SKUs for bucketing."""
        print(f"[SKUBucketer] Loading data from {len(self.index_data['skus'])} SKUs...")

        for sku_info in self.index_data["skus"]:
            sku_file = self.skus_dir / sku_info["file"]

            with open(sku_file, 'r', encoding='utf-8') as f:
                sku = json.load(f)

            uuid = sku["metadata"]["uuid"]

            self.sku_data[uuid] = {
                "objects": set(sku.get("context", {}).get("applicable_objects", [])),
                "tags": set(sku.get("custom_attributes", {}).get("domain_tags", [])),
                "trigger": sku.get("trigger", {}).get("condition_logic", ""),
                "name": sku["metadata"]["name"]
            }

        print(f"  Loaded {len(self.sku_data)} SKUs")

    def calculate_overlap(self, uuid1: str, uuid2: str) -> tuple[float, float]:
        """
        Calculate overlap ratios between two SKUs.

        Returns:
            (objects_overlap, tags_overlap) - each is 0-1
        """
        data1 = self.sku_data[uuid1]
        data2 = self.sku_data[uuid2]

        # Objects overlap
        obj1, obj2 = data1["objects"], data2["objects"]
        if obj1 and obj2:
            intersection = obj1 & obj2
            # Use the smaller set as denominator (if A has 2 objects, B has 5, and they share 2, that's 100% for A)
            min_size = min(len(obj1), len(obj2))
            objects_overlap = len(intersection) / min_size if min_size > 0 else 0
        else:
            objects_overlap = 0

        # Tags overlap
        tag1, tag2 = data1["tags"], data2["tags"]
        if tag1 and tag2:
            intersection = tag1 & tag2
            min_size = min(len(tag1), len(tag2))
            tags_overlap = len(intersection) / min_size if min_size > 0 else 0
        else:
            tags_overlap = 0

        return objects_overlap, tags_overlap

    def should_group(self, uuid1: str, uuid2: str) -> bool:
        """Check if two SKUs should be in the same bucket."""
        obj_overlap, tag_overlap = self.calculate_overlap(uuid1, uuid2)

        # Group if either overlap exceeds threshold
        return obj_overlap >= self.threshold or tag_overlap >= self.threshold

    def build_buckets(self):
        """
        Build buckets using Union-Find for transitive grouping.

        If A~B and B~C, then A, B, C should all be in the same bucket.
        """
        print(f"[SKUBucketer] Building buckets with threshold={self.threshold}...")

        uuids = list(self.sku_data.keys())
        n = len(uuids)

        # Union-Find data structure
        parent = {uuid: uuid for uuid in uuids}

        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])  # Path compression
            return parent[x]

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Compare all pairs and union if they should be grouped
        comparisons = 0
        unions = 0

        for i in range(n):
            for j in range(i + 1, n):
                comparisons += 1
                if self.should_group(uuids[i], uuids[j]):
                    union(uuids[i], uuids[j])
                    unions += 1

        print(f"  Performed {comparisons} comparisons, {unions} groupings")

        # Collect buckets
        bucket_members = defaultdict(list)
        for uuid in uuids:
            root = find(uuid)
            bucket_members[root].append(uuid)

        # Create Bucket objects
        self.buckets = []
        for bucket_id, (root, members) in enumerate(bucket_members.items()):
            # Find shared objects and tags
            if len(members) > 1:
                shared_objects = set.intersection(*[self.sku_data[uuid]["objects"] for uuid in members])
                shared_tags = set.intersection(*[self.sku_data[uuid]["tags"] for uuid in members])
            else:
                shared_objects = self.sku_data[members[0]]["objects"]
                shared_tags = self.sku_data[members[0]]["tags"]

            bucket = Bucket(
                bucket_id=f"bucket_{bucket_id:04d}",
                sku_uuids=members,
                shared_objects=shared_objects,
                shared_tags=shared_tags
            )
            self.buckets.append(bucket)

        # Sort buckets by size (largest first)
        self.buckets.sort(key=lambda b: len(b.sku_uuids), reverse=True)

        # Statistics
        multi_sku_buckets = [b for b in self.buckets if len(b.sku_uuids) > 1]
        print(f"  Created {len(self.buckets)} buckets")
        print(f"  - {len(multi_sku_buckets)} buckets with multiple SKUs (candidates for fusion)")
        print(f"  - {len(self.buckets) - len(multi_sku_buckets)} singleton buckets")

        if multi_sku_buckets:
            max_size = max(len(b.sku_uuids) for b in multi_sku_buckets)
            print(f"  - Largest bucket has {max_size} SKUs")

    def save_results(self, output_dir: str = None):
        """Save bucketing results."""
        output_path = Path(output_dir) if output_dir else self.skus_dir

        # Prepare results
        results = {
            "metadata": {
                "total_skus": len(self.sku_data),
                "total_buckets": len(self.buckets),
                "threshold": self.threshold,
                "multi_sku_buckets": len([b for b in self.buckets if len(b.sku_uuids) > 1]),
                "singleton_buckets": len([b for b in self.buckets if len(b.sku_uuids) == 1])
            },
            "buckets": [b.to_dict() for b in self.buckets]
        }

        # Add SKU names for readability
        for bucket in results["buckets"]:
            bucket["sku_names"] = [self.sku_data[uuid]["name"] for uuid in bucket["sku_uuids"]]

        output_file = output_path / "buckets.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"[SKUBucketer] Saved results to {output_file}")

    def bucket(self):
        """Run full bucketing pipeline."""
        print("=" * 60)
        print("SKU BUCKETING")
        print("=" * 60)

        self.load_sku_data()
        self.build_buckets()
        self.save_results()

        print()
        print("[SKUBucketer] Bucketing complete")

        return self.buckets


# ============================================================================
# Embedding Client (BGE-M3)
# ============================================================================

class EmbeddingClient:
    """Client for BGE-M3 embeddings via SiliconFlow API."""

    def __init__(self, api_key: str = None, base_url: str = None, rate_limit: float = None):
        self.api_key = api_key or SILICONFLOW_API_KEY
        self.base_url = base_url or SILICONFLOW_BASE_URL
        self.model = "Pro/BAAI/bge-m3"
        self.rate_limit = rate_limit if rate_limit is not None else FUSION_RATE_LIMIT_SECONDS
        self._last_call_time = 0

        if not self.api_key:
            raise ValueError("SILICONFLOW_API_KEY not set in environment")

    def _apply_rate_limit(self):
        """Apply rate limiting between API calls."""
        if self.rate_limit > 0:
            elapsed = time.time() - self._last_call_time
            if elapsed < self.rate_limit:
                sleep_time = self.rate_limit - elapsed
                time.sleep(sleep_time)
        self._last_call_time = time.time()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Get embeddings for a list of texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        self._apply_rate_limit()

        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float"
        }

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        result = response.json()
        # Sort by index to ensure correct order
        embeddings = sorted(result["data"], key=lambda x: x["index"])
        return [e["embedding"] for e in embeddings]

    def embed_single(self, text: str) -> list[float]:
        """Get embedding for a single text."""
        return self.embed([text])[0]


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if not vec1 or not vec2:
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


# ============================================================================
# Similarity Calculator
# ============================================================================

@dataclass
class SKUSimilarity:
    """Similarity scores between two SKUs."""
    uuid1: str
    uuid2: str
    s_anchor: float  # Anchor similarity (applicable_objects + trigger)
    s_logic: float   # Logic similarity (execution_body embedding)
    s_outcome: float  # Outcome similarity (output embedding)
    combined_score: float  # Weighted combination
    relationship: str  # "duplicate" | "conflict" | "independent"

    def to_dict(self) -> dict:
        return {
            "uuid1": self.uuid1,
            "uuid2": self.uuid2,
            "s_anchor": round(self.s_anchor, 4),
            "s_logic": round(self.s_logic, 4),
            "s_outcome": round(self.s_outcome, 4),
            "combined_score": round(self.combined_score, 4),
            "relationship": self.relationship
        }


class SimilarityCalculator:
    """
    Calculates multi-dimensional similarity between SKUs within buckets.

    Three dimensions (from spec):
    1. S_anchor: Comparison of applicable_objects and trigger conditions
    2. S_logic: Semantic similarity of execution_body (via embeddings)
    3. S_outcome: Semantic similarity of output/result_template (via embeddings)

    Relationship classification:
    - Duplicate: High anchor + High logic + High outcome
    - Conflict: High anchor + Low/opposite outcome
    - Independent: Low anchor
    """

    # Thresholds for relationship classification
    HIGH_THRESHOLD = 0.7
    LOW_THRESHOLD = 0.3

    def __init__(self, skus_dir: str, buckets_file: str = None):
        """
        Initialize calculator.

        Args:
            skus_dir: Path to SKUs directory
            buckets_file: Path to buckets.json (default: skus_dir/buckets.json)
        """
        self.skus_dir = Path(skus_dir)
        self.buckets_file = Path(buckets_file) if buckets_file else self.skus_dir / "buckets.json"

        # Load buckets
        with open(self.buckets_file, 'r', encoding='utf-8') as f:
            self.buckets_data = json.load(f)

        self.embedding_client = EmbeddingClient()

        # Cache: uuid -> full SKU data
        self.sku_cache: dict = {}

        # Cache: uuid -> embeddings
        self.embeddings_cache: dict = {}

        # Results
        self.similarities: list[SKUSimilarity] = []

    def load_sku(self, uuid: str) -> dict:
        """Load and cache a single SKU."""
        if uuid in self.sku_cache:
            return self.sku_cache[uuid]

        # Find SKU file
        for sku_info in self.buckets_data.get("buckets", []):
            if uuid in sku_info.get("sku_uuids", []):
                break

        # Load from file
        sku_file = self.skus_dir / "skus" / f"{uuid}.json"
        with open(sku_file, 'r', encoding='utf-8') as f:
            sku = json.load(f)

        self.sku_cache[uuid] = sku
        return sku

    def get_embeddings(self, uuid: str) -> dict:
        """
        Get embeddings for a SKU's key fields.

        Returns:
            {
                "trigger": [...],      # Embedding of trigger condition
                "execution": [...],    # Embedding of execution_body
                "outcome": [...]       # Embedding of output
            }
        """
        if uuid in self.embeddings_cache:
            return self.embeddings_cache[uuid]

        sku = self.load_sku(uuid)

        # Prepare texts for embedding
        trigger_text = sku.get("trigger", {}).get("condition_logic", "") or ""
        execution_text = sku.get("core_logic", {}).get("execution_body", "") or ""
        outcome_text = sku.get("output", {}).get("result_template", "") or ""

        # Combine execution with logic_type for better context
        logic_type = sku.get("core_logic", {}).get("logic_type", "")
        if logic_type:
            execution_text = f"[{logic_type}] {execution_text}"

        # Get embeddings (batch for efficiency)
        texts = [trigger_text, execution_text, outcome_text]
        # Replace empty strings with placeholder to avoid API errors
        texts = [t if t.strip() else "[empty]" for t in texts]

        try:
            embeddings = self.embedding_client.embed(texts)
            result = {
                "trigger": embeddings[0],
                "execution": embeddings[1],
                "outcome": embeddings[2]
            }
        except Exception as e:
            print(f"  [WARN] Failed to get embeddings for {uuid}: {e}")
            result = {
                "trigger": [],
                "execution": [],
                "outcome": []
            }

        self.embeddings_cache[uuid] = result
        return result

    def calculate_anchor_similarity(self, uuid1: str, uuid2: str) -> float:
        """
        Calculate anchor similarity (S_anchor).

        Combines:
        - Jaccard similarity of applicable_objects
        - Cosine similarity of trigger embeddings
        """
        sku1 = self.load_sku(uuid1)
        sku2 = self.load_sku(uuid2)

        # Jaccard similarity of applicable_objects
        obj1 = set(sku1.get("context", {}).get("applicable_objects", []))
        obj2 = set(sku2.get("context", {}).get("applicable_objects", []))

        if obj1 or obj2:
            jaccard = len(obj1 & obj2) / len(obj1 | obj2) if (obj1 | obj2) else 0
        else:
            jaccard = 0

        # Cosine similarity of trigger embeddings
        emb1 = self.get_embeddings(uuid1)
        emb2 = self.get_embeddings(uuid2)

        trigger_sim = cosine_similarity(emb1["trigger"], emb2["trigger"])

        # Weighted combination (objects more important for anchor)
        return 0.6 * jaccard + 0.4 * trigger_sim

    def calculate_logic_similarity(self, uuid1: str, uuid2: str) -> float:
        """
        Calculate logic similarity (S_logic).

        Based on cosine similarity of execution_body embeddings.
        """
        emb1 = self.get_embeddings(uuid1)
        emb2 = self.get_embeddings(uuid2)

        return cosine_similarity(emb1["execution"], emb2["execution"])

    def calculate_outcome_similarity(self, uuid1: str, uuid2: str) -> float:
        """
        Calculate outcome similarity (S_outcome).

        Based on cosine similarity of output/result_template embeddings.
        """
        emb1 = self.get_embeddings(uuid1)
        emb2 = self.get_embeddings(uuid2)

        return cosine_similarity(emb1["outcome"], emb2["outcome"])

    def classify_relationship(self, s_anchor: float, s_logic: float, s_outcome: float) -> str:
        """
        Classify the relationship between two SKUs.

        From spec:
        - Duplicate: High anchor + High logic + High outcome
        - Conflict: High anchor + Low/opposite outcome
        - Independent: Low anchor
        """
        if s_anchor < self.LOW_THRESHOLD:
            return "independent"

        if s_anchor >= self.HIGH_THRESHOLD:
            if s_logic >= self.HIGH_THRESHOLD and s_outcome >= self.HIGH_THRESHOLD:
                return "duplicate"
            elif s_outcome < self.LOW_THRESHOLD:
                return "conflict"

        # Medium similarity - potential relationship but needs review
        if s_anchor >= 0.5 and s_logic >= 0.5:
            if s_outcome < 0.5:
                return "conflict"
            else:
                return "duplicate"

        return "independent"

    def calculate_pair_similarity(self, uuid1: str, uuid2: str) -> SKUSimilarity:
        """Calculate all similarity dimensions for a pair of SKUs."""
        s_anchor = self.calculate_anchor_similarity(uuid1, uuid2)
        s_logic = self.calculate_logic_similarity(uuid1, uuid2)
        s_outcome = self.calculate_outcome_similarity(uuid1, uuid2)

        # Combined score (weighted average)
        combined = 0.3 * s_anchor + 0.4 * s_logic + 0.3 * s_outcome

        relationship = self.classify_relationship(s_anchor, s_logic, s_outcome)

        return SKUSimilarity(
            uuid1=uuid1,
            uuid2=uuid2,
            s_anchor=s_anchor,
            s_logic=s_logic,
            s_outcome=s_outcome,
            combined_score=combined,
            relationship=relationship
        )

    def process_bucket(self, bucket: dict) -> list[SKUSimilarity]:
        """Process all pairs within a single bucket."""
        uuids = bucket.get("sku_uuids", [])
        n = len(uuids)

        if n < 2:
            return []

        pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                sim = self.calculate_pair_similarity(uuids[i], uuids[j])
                pairs.append(sim)

        return pairs

    def calculate_all(self, verbose: bool = True) -> list[SKUSimilarity]:
        """
        Calculate similarities for all multi-SKU buckets.

        Only processes buckets with 2+ SKUs (candidates for fusion).
        """
        multi_buckets = [b for b in self.buckets_data.get("buckets", [])
                         if len(b.get("sku_uuids", [])) > 1]

        if verbose:
            print("=" * 60)
            print("SIMILARITY CALCULATION")
            print("=" * 60)
            print(f"Processing {len(multi_buckets)} multi-SKU buckets...")
            print()

        all_similarities = []

        for i, bucket in enumerate(multi_buckets):
            bucket_id = bucket.get("bucket_id", f"bucket_{i}")
            sku_count = len(bucket.get("sku_uuids", []))
            pair_count = sku_count * (sku_count - 1) // 2

            if verbose:
                print(f"[{i+1}/{len(multi_buckets)}] {bucket_id}: {sku_count} SKUs, {pair_count} pairs")

            pairs = self.process_bucket(bucket)
            all_similarities.extend(pairs)

            if verbose:
                # Count relationships
                duplicates = sum(1 for p in pairs if p.relationship == "duplicate")
                conflicts = sum(1 for p in pairs if p.relationship == "conflict")
                independent = sum(1 for p in pairs if p.relationship == "independent")
                print(f"  -> {duplicates} duplicates, {conflicts} conflicts, {independent} independent")

        self.similarities = all_similarities

        if verbose:
            print()
            print(f"Total: {len(all_similarities)} pairs analyzed")
            total_dup = sum(1 for s in all_similarities if s.relationship == "duplicate")
            total_conf = sum(1 for s in all_similarities if s.relationship == "conflict")
            print(f"  - {total_dup} duplicate pairs (candidates for merge)")
            print(f"  - {total_conf} conflict pairs (need resolution)")

        return all_similarities

    def save_results(self, output_dir: str = None):
        """Save similarity results."""
        output_path = Path(output_dir) if output_dir else self.skus_dir

        # Group by relationship
        duplicates = [s for s in self.similarities if s.relationship == "duplicate"]
        conflicts = [s for s in self.similarities if s.relationship == "conflict"]
        independent = [s for s in self.similarities if s.relationship == "independent"]

        results = {
            "metadata": {
                "total_pairs": len(self.similarities),
                "duplicates": len(duplicates),
                "conflicts": len(conflicts),
                "independent": len(independent),
                "thresholds": {
                    "high": self.HIGH_THRESHOLD,
                    "low": self.LOW_THRESHOLD
                }
            },
            "duplicates": [s.to_dict() for s in duplicates],
            "conflicts": [s.to_dict() for s in conflicts],
            "all_similarities": [s.to_dict() for s in self.similarities]
        }

        # Add SKU names for readability
        for sim_list in [results["duplicates"], results["conflicts"]]:
            for sim in sim_list:
                sku1 = self.load_sku(sim["uuid1"])
                sku2 = self.load_sku(sim["uuid2"])
                sim["name1"] = sku1["metadata"]["name"]
                sim["name2"] = sku2["metadata"]["name"]

        output_file = output_path / "similarities.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"[SimilarityCalculator] Saved results to {output_file}")

    def calculate(self, verbose: bool = True):
        """Run full similarity calculation pipeline."""
        self.calculate_all(verbose=verbose)
        self.save_results()

        if verbose:
            print()
            print("[SimilarityCalculator] Calculation complete")


# ============================================================================
# Combined Pipeline
# ============================================================================

def run_fusion_pipeline(skus_dir: str, normalize: bool = True, bucket: bool = True, similarity: bool = True):
    """
    Run the full knowledge fusion pipeline.

    Args:
        skus_dir: Path to SKUs directory
        normalize: Whether to run tag normalization
        bucket: Whether to run SKU bucketing
        similarity: Whether to run similarity calculation
    """
    print("=" * 60)
    print("KNOWLEDGE FUSION PIPELINE")
    print("=" * 60)
    print(f"SKUs directory: {skus_dir}")
    print()

    if normalize:
        normalizer = TagNormalizer(skus_dir)
        normalizer.normalize()
        print()

    if bucket:
        bucketer = SKUBucketer(skus_dir)
        bucketer.bucket()
        print()

    if similarity:
        calculator = SimilarityCalculator(skus_dir)
        calculator.calculate()
        print()

    print("=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)


# ============================================================================
# Bucket Refiner - Recursively divide large buckets
# ============================================================================

# Token limit for skill generation (GLM-4.7 context)
BUCKET_MAX_TOKENS = 32000
# Rough estimate: 1 token ≈ 4 characters for mixed Chinese/English
CHARS_PER_TOKEN = 4


class BucketRefiner:
    """Recursively divide large buckets until each fits within token limit.

    Uses similarity scores to guide division - SKUs with higher similarity
    stay together, while low-similarity SKUs are split apart.
    """

    def __init__(self, skus_dir: str, max_tokens: int = None):
        self.skus_dir = Path(skus_dir)
        self.max_tokens = max_tokens or BUCKET_MAX_TOKENS

        # Load data
        self.skus = self._load_skus()
        self.buckets = self._load_buckets()
        self.similarities = self._load_similarities()

        # Token estimates cache
        self.sku_tokens = {}
        self._estimate_all_tokens()

        # Results
        self.refined_buckets = {}

    def _load_skus(self) -> dict:
        """Load all SKUs."""
        skus = {}
        skus_path = self.skus_dir / "skus"
        for sku_file in skus_path.glob("*.json"):
            with open(sku_file, 'r', encoding='utf-8') as f:
                sku = json.load(f)
                sku_uuid = sku.get("metadata", {}).get("uuid", sku_file.stem)
                skus[sku_uuid] = sku
        return skus

    def _load_buckets(self) -> dict:
        """Load existing buckets."""
        buckets_file = self.skus_dir / "buckets.json"
        if not buckets_file.exists():
            raise FileNotFoundError(f"buckets.json not found in {self.skus_dir}")

        with open(buckets_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        buckets = {}
        for bucket_id, bucket_info in data.get("buckets", {}).items():
            uuids = bucket_info.get("sku_uuids", [])
            if uuids:
                buckets[bucket_id] = uuids
        return buckets

    def _load_similarities(self) -> dict:
        """Load similarity scores for guiding splits."""
        sim_file = self.skus_dir / "similarities.json"
        if not sim_file.exists():
            print("[BucketRefiner] No similarities.json found, will use random splits")
            return {}

        with open(sim_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _estimate_tokens(self, sku: dict) -> int:
        """Estimate token count for a single SKU in JSON format."""
        # Serialize to JSON and count characters
        json_str = json.dumps(sku, ensure_ascii=False)
        return len(json_str) // CHARS_PER_TOKEN

    def _estimate_all_tokens(self):
        """Pre-compute token estimates for all SKUs."""
        for sku_uuid, sku in self.skus.items():
            self.sku_tokens[sku_uuid] = self._estimate_tokens(sku)

        total = sum(self.sku_tokens.values())
        print(f"[BucketRefiner] Loaded {len(self.skus)} SKUs, total ~{total:,} tokens")

    def _get_bucket_tokens(self, sku_uuids: list) -> int:
        """Get total tokens for a bucket."""
        return sum(self.sku_tokens.get(uuid, 0) for uuid in sku_uuids)

    def _get_similarity_score(self, uuid1: str, uuid2: str) -> float:
        """Get similarity score between two SKUs (0 if not found)."""
        all_sims = self.similarities.get("all_similarities", [])
        for sim in all_sims:
            if (sim["uuid1"] == uuid1 and sim["uuid2"] == uuid2) or \
               (sim["uuid1"] == uuid2 and sim["uuid2"] == uuid1):
                # Use average of all dimensions
                return (sim.get("S_anchor", 0) + sim.get("S_logic", 0) + sim.get("S_outcome", 0)) / 3
        return 0.0

    def _build_similarity_matrix(self, sku_uuids: list) -> dict:
        """Build pairwise similarity lookup for a set of SKUs."""
        matrix = {}
        for i, uuid1 in enumerate(sku_uuids):
            for uuid2 in sku_uuids[i+1:]:
                score = self._get_similarity_score(uuid1, uuid2)
                matrix[(uuid1, uuid2)] = score
                matrix[(uuid2, uuid1)] = score
        return matrix

    def _split_bucket(self, sku_uuids: list) -> tuple:
        """Split a bucket into two halves based on similarity.

        Uses a greedy approach: start with two seeds (least similar pair),
        then assign remaining SKUs to the half they're more similar to.
        """
        if len(sku_uuids) <= 2:
            # Can't split further meaningfully
            mid = len(sku_uuids) // 2
            return sku_uuids[:max(1, mid)], sku_uuids[max(1, mid):]

        sim_matrix = self._build_similarity_matrix(sku_uuids)

        # Find least similar pair as seeds
        min_sim = float('inf')
        seed1, seed2 = sku_uuids[0], sku_uuids[1]

        for i, uuid1 in enumerate(sku_uuids):
            for uuid2 in sku_uuids[i+1:]:
                sim = sim_matrix.get((uuid1, uuid2), 0)
                if sim < min_sim:
                    min_sim = sim
                    seed1, seed2 = uuid1, uuid2

        # Initialize two groups with seeds
        group1 = [seed1]
        group2 = [seed2]
        remaining = [u for u in sku_uuids if u not in (seed1, seed2)]

        # Assign remaining SKUs to closest group
        for sku_uuid in remaining:
            # Average similarity to each group
            sim_to_1 = sum(sim_matrix.get((sku_uuid, g), 0) for g in group1) / len(group1) if group1 else 0
            sim_to_2 = sum(sim_matrix.get((sku_uuid, g), 0) for g in group2) / len(group2) if group2 else 0

            if sim_to_1 >= sim_to_2:
                group1.append(sku_uuid)
            else:
                group2.append(sku_uuid)

        return group1, group2

    def _refine_bucket(self, bucket_id: str, sku_uuids: list, depth: int = 0) -> dict:
        """Recursively refine a bucket until under token limit."""
        indent = "  " * depth
        tokens = self._get_bucket_tokens(sku_uuids)

        print(f"{indent}[{bucket_id}] {len(sku_uuids)} SKUs, ~{tokens:,} tokens", end="")

        if tokens <= self.max_tokens:
            print(" - OK")
            return {bucket_id: sku_uuids}

        print(f" - SPLIT (>{self.max_tokens:,})")

        # Split into two halves
        group1, group2 = self._split_bucket(sku_uuids)

        # Recursively refine each half
        results = {}
        sub1 = self._refine_bucket(f"{bucket_id}_a", group1, depth + 1)
        sub2 = self._refine_bucket(f"{bucket_id}_b", group2, depth + 1)

        results.update(sub1)
        results.update(sub2)

        return results

    def refine(self):
        """Refine all buckets."""
        print(f"\n[BucketRefiner] Starting bucket refinement")
        print(f"[BucketRefiner] Max tokens per bucket: {self.max_tokens:,}")
        print(f"[BucketRefiner] Original buckets: {len(self.buckets)}")

        for bucket_id, sku_uuids in self.buckets.items():
            refined = self._refine_bucket(bucket_id, sku_uuids)
            self.refined_buckets.update(refined)

        print(f"\n[BucketRefiner] Refined buckets: {len(self.refined_buckets)}")

        # Stats
        sizes = [len(uuids) for uuids in self.refined_buckets.values()]
        tokens = [self._get_bucket_tokens(uuids) for uuids in self.refined_buckets.values()]

        print(f"[BucketRefiner] Bucket sizes: min={min(sizes)}, max={max(sizes)}, avg={sum(sizes)/len(sizes):.1f}")
        print(f"[BucketRefiner] Bucket tokens: min={min(tokens):,}, max={max(tokens):,}, avg={sum(tokens)/len(tokens):,.0f}")

    def save_results(self):
        """Save refined buckets to buckets_refined.json."""
        output = {
            "metadata": {
                "max_tokens": self.max_tokens,
                "original_bucket_count": len(self.buckets),
                "refined_bucket_count": len(self.refined_buckets),
                "total_skus": len(self.skus)
            },
            "buckets": {
                bucket_id: {
                    "sku_uuids": sku_uuids,
                    "sku_count": len(sku_uuids),
                    "estimated_tokens": self._get_bucket_tokens(sku_uuids)
                }
                for bucket_id, sku_uuids in self.refined_buckets.items()
            }
        }

        output_file = self.skus_dir / "buckets_refined.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"[BucketRefiner] Saved to {output_file}")

        # Also update buckets.json with refined version
        buckets_file = self.skus_dir / "buckets.json"
        with open(buckets_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"[BucketRefiner] Updated {buckets_file}")


def refine_buckets(skus_dir: str, max_tokens: int = None):
    """Convenience function to refine buckets."""
    refiner = BucketRefiner(skus_dir, max_tokens)
    refiner.refine()
    refiner.save_results()
    return refiner


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Knowledge Fusion: Tag Normalization, Bucketing & Similarity")
    parser.add_argument("skus_dir", help="Path to SKUs directory")
    parser.add_argument("--normalize-only", action="store_true", help="Only run normalization")
    parser.add_argument("--bucket-only", action="store_true", help="Only run bucketing")
    parser.add_argument("--similarity-only", action="store_true", help="Only run similarity calculation")
    parser.add_argument("--refine-buckets", action="store_true", help="Refine large buckets to fit token limit")
    parser.add_argument("-t", "--threshold", type=float, help="Bucket threshold (0-1)")
    parser.add_argument("--max-tokens", type=int, default=32000, help="Max tokens per bucket (default: 32000)")

    args = parser.parse_args()

    if args.normalize_only:
        normalizer = TagNormalizer(args.skus_dir)
        normalizer.normalize()
    elif args.bucket_only:
        threshold = args.threshold if args.threshold else BUCKET_THRESHOLD
        bucketer = SKUBucketer(args.skus_dir, threshold=threshold)
        bucketer.bucket()
    elif args.similarity_only:
        calculator = SimilarityCalculator(args.skus_dir)
        calculator.calculate()
    elif args.refine_buckets:
        refine_buckets(args.skus_dir, args.max_tokens)
    else:
        run_fusion_pipeline(args.skus_dir)


# ============================================================================
# State Matrix & Resolution (Module 4.3)
# ============================================================================

# State codes
STATE_DUPLICATE = 1
STATE_CONFLICT = -1
STATE_INDEPENDENT = 0

STATE_NAMES = {
    STATE_DUPLICATE: "duplicate",
    STATE_CONFLICT: "conflict",
    STATE_INDEPENDENT: "independent"
}


@dataclass
class ResolutionTask:
    """A task for resolving a pair of SKUs."""
    task_id: str
    state: int  # STATE_DUPLICATE, STATE_CONFLICT, STATE_INDEPENDENT
    uuid1: str
    uuid2: str
    name1: str
    name2: str
    similarity: dict  # Original similarity scores
    action: str  # "merge" | "branch" | "keep"
    resolved: bool = False
    result: Optional[dict] = None  # Resolution result

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "state": STATE_NAMES.get(self.state, "unknown"),
            "state_code": self.state,
            "uuid1": self.uuid1,
            "uuid2": self.uuid2,
            "name1": self.name1,
            "name2": self.name2,
            "similarity": self.similarity,
            "action": self.action,
            "resolved": self.resolved,
            "result": self.result
        }


class StateMatrix:
    """
    State Matrix for SKU resolution.

    Categorizes similarity pairs into states and prepares resolution tasks.

    State Matrix (from spec):
    | State       | Condition                           | Action                    |
    |-------------|-------------------------------------|---------------------------|
    | Duplicate   | High Anchor + High Logic + High Out | Merge descriptions        |
    | Conflict    | High Anchor + Low/Opposite Outcome  | Generate branching logic  |
    | Independent | Low Anchor                          | Keep original             |
    """

    def __init__(self, skus_dir: str, similarities_file: str = None):
        """
        Initialize state matrix.

        Args:
            skus_dir: Path to SKUs directory
            similarities_file: Path to similarities.json (default: skus_dir/similarities.json)
        """
        self.skus_dir = Path(skus_dir)
        self.similarities_file = Path(similarities_file) if similarities_file else self.skus_dir / "similarities.json"

        # Load similarities
        with open(self.similarities_file, 'r', encoding='utf-8') as f:
            self.similarities_data = json.load(f)

        # Resolution tasks
        self.tasks: list[ResolutionTask] = []

        # Statistics
        self.state_counts = {
            STATE_DUPLICATE: 0,
            STATE_CONFLICT: 0,
            STATE_INDEPENDENT: 0
        }

    def build_matrix(self) -> list[ResolutionTask]:
        """
        Build state matrix from similarity data.

        Creates resolution tasks for duplicates and conflicts.
        Independent pairs are counted but not queued for resolution.
        """
        print("=" * 60)
        print("STATE MATRIX")
        print("=" * 60)

        all_sims = self.similarities_data.get("all_similarities", [])
        print(f"Processing {len(all_sims)} similarity pairs...")

        task_id = 0
        for sim in all_sims:
            relationship = sim.get("relationship", "independent")

            if relationship == "duplicate":
                state = STATE_DUPLICATE
                action = "merge"
            elif relationship == "conflict":
                state = STATE_CONFLICT
                action = "branch"
            else:
                state = STATE_INDEPENDENT
                action = "keep"

            self.state_counts[state] += 1

            # Only create tasks for duplicates and conflicts
            if state != STATE_INDEPENDENT:
                task = ResolutionTask(
                    task_id=f"task_{task_id:04d}",
                    state=state,
                    uuid1=sim["uuid1"],
                    uuid2=sim["uuid2"],
                    name1=sim.get("name1", ""),
                    name2=sim.get("name2", ""),
                    similarity={
                        "s_anchor": sim.get("s_anchor", 0),
                        "s_logic": sim.get("s_logic", 0),
                        "s_outcome": sim.get("s_outcome", 0),
                        "combined_score": sim.get("combined_score", 0)
                    },
                    action=action
                )
                self.tasks.append(task)
                task_id += 1

        # Print state matrix summary
        print()
        print("State Matrix Summary:")
        print(f"  | State       | Count | Action              |")
        print(f"  |-------------|-------|---------------------|")
        print(f"  | Duplicate   | {self.state_counts[STATE_DUPLICATE]:5d} | Merge descriptions  |")
        print(f"  | Conflict    | {self.state_counts[STATE_CONFLICT]:5d} | Branching logic     |")
        print(f"  | Independent | {self.state_counts[STATE_INDEPENDENT]:5d} | Keep original       |")
        print()
        print(f"Total resolution tasks: {len(self.tasks)}")

        return self.tasks

    def save_matrix(self, output_dir: str = None):
        """Save state matrix and resolution tasks."""
        output_path = Path(output_dir) if output_dir else self.skus_dir

        matrix_data = {
            "metadata": {
                "total_pairs": sum(self.state_counts.values()),
                "state_counts": {
                    "duplicate": self.state_counts[STATE_DUPLICATE],
                    "conflict": self.state_counts[STATE_CONFLICT],
                    "independent": self.state_counts[STATE_INDEPENDENT]
                },
                "resolution_tasks": len(self.tasks)
            },
            "tasks": [t.to_dict() for t in self.tasks]
        }

        output_file = output_path / "state_matrix.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(matrix_data, f, ensure_ascii=False, indent=2)

        print(f"[StateMatrix] Saved to {output_file}")

    def build(self):
        """Run full state matrix pipeline."""
        self.build_matrix()
        self.save_matrix()
        print()
        print("[StateMatrix] Complete")
        return self.tasks


# ============================================================================
# Resolution Prompts
# ============================================================================

# Location: pdf2skills/knowledge_fusion.py, line ~1200
MERGE_PROMPT = '''You are a knowledge engineer merging duplicate knowledge units.

## Task
Two knowledge units have been identified as duplicates (same concept, similar logic, similar outcome).
Merge them into a single, comprehensive knowledge unit that preserves ALL details from both.

## SKU 1: {name1}
```json
{sku1_json}
```

## SKU 2: {name2}
```json
{sku2_json}
```

## Merge Rules
1. **name**: Choose the more precise/professional name
2. **applicable_objects**: Union of both lists (no duplicates)
3. **prerequisites**: Union of both lists
4. **constraints**: Union of both lists
5. **condition_logic**: Combine if different, keep if same
6. **execution_body**: MERGE ALL DETAILS from both - do NOT lose any information
7. **variables**: Union of both lists
8. **result_template**: Combine if different
9. **domain_tags**: Union of both lists
10. **custom_attributes**: Merge, keeping all fields

## Output Format
Return the merged SKU as a single JSON object:
```json
{{
  "metadata": {{ "name": "...", "snippet": "..." }},
  "context": {{ ... }},
  "trigger": {{ ... }},
  "core_logic": {{ ... }},
  "output": {{ ... }},
  "custom_attributes": {{ ... }},
  "schema_explanation": "Merged from two duplicate SKUs"
}}
```

## Language
Use {output_language} for all text fields.

Return ONLY the JSON object, no other text.'''


# Location: pdf2skills/knowledge_fusion.py, line ~1250
BRANCH_PROMPT = '''You are a knowledge engineer resolving conflicting knowledge units.

## Task
Two knowledge units have been identified as conflicting (same applicable context but different outcomes).
Create a unified knowledge unit with BRANCHING LOGIC that handles both cases.

## SKU 1: {name1}
```json
{sku1_json}
```

## SKU 2: {name2}
```json
{sku2_json}
```

## Resolution Rules
1. Identify what distinguishes when SKU1 applies vs SKU2
2. Create a unified `condition_logic` with IF-ELSE branching
3. Merge `execution_body` with clear conditional sections
4. The result should handle BOTH scenarios correctly

## Output Format
Return the resolved SKU as a single JSON object with branching logic:
```json
{{
  "metadata": {{
    "name": "Combined name covering both cases",
    "snippet": "..."
  }},
  "context": {{
    "applicable_objects": ["union of both"],
    "prerequisites": ["union of both"],
    "constraints": ["union of both"]
  }},
  "trigger": {{
    "condition_logic": "IF (condition_for_sku1) THEN ... ELSE IF (condition_for_sku2) THEN ..."
  }},
  "core_logic": {{
    "logic_type": "Decision_Tree",
    "execution_body": "Branching logic:\n1. IF [condition1]:\n   - [steps from SKU1]\n2. ELSE IF [condition2]:\n   - [steps from SKU2]",
    "variables": ["union of both"]
  }},
  "output": {{
    "output_type": "Value|Alert|Action",
    "result_template": "Context-dependent result interpretation"
  }},
  "custom_attributes": {{
    "domain_tags": ["union"],
    "has_branching": true,
    "source_conflict": ["{uuid1}", "{uuid2}"]
  }},
  "schema_explanation": "Resolved from conflicting SKUs by adding branching logic"
}}
```

## Language
Use {output_language} for all text fields.

Return ONLY the JSON object, no other text.'''


# ============================================================================
# SKU Resolver
# ============================================================================

class SKUResolver:
    """
    Resolves duplicate and conflicting SKUs.

    Actions:
    - Merge: Combine duplicate SKUs into one comprehensive unit
    - Branch: Create branching logic for conflicting SKUs
    """

    def __init__(self, skus_dir: str, state_matrix_file: str = None):
        """
        Initialize resolver.

        Args:
            skus_dir: Path to SKUs directory
            state_matrix_file: Path to state_matrix.json (default: skus_dir/state_matrix.json)
        """
        self.skus_dir = Path(skus_dir)
        self.state_matrix_file = Path(state_matrix_file) if state_matrix_file else self.skus_dir / "state_matrix.json"

        # Load state matrix
        with open(self.state_matrix_file, 'r', encoding='utf-8') as f:
            self.matrix_data = json.load(f)

        self.llm = DeepSeekClient()
        self.output_language = OUTPUT_LANGUAGE

        # SKU cache
        self.sku_cache: dict = {}

        # Resolution results
        self.resolved_tasks: list[dict] = []
        self.merged_skus: list[dict] = []  # New SKUs from merging
        self.deprecated_uuids: set = set()  # UUIDs that were merged/resolved

    def load_sku(self, uuid: str) -> dict:
        """Load and cache a single SKU."""
        if uuid in self.sku_cache:
            return self.sku_cache[uuid]

        sku_file = self.skus_dir / "skus" / f"{uuid}.json"
        with open(sku_file, 'r', encoding='utf-8') as f:
            sku = json.load(f)

        self.sku_cache[uuid] = sku
        return sku

    def resolve_merge(self, task: dict) -> dict:
        """
        Merge two duplicate SKUs.

        Returns the merged SKU.
        """
        uuid1, uuid2 = task["uuid1"], task["uuid2"]
        sku1 = self.load_sku(uuid1)
        sku2 = self.load_sku(uuid2)

        prompt = MERGE_PROMPT.format(
            name1=task.get("name1", uuid1),
            name2=task.get("name2", uuid2),
            sku1_json=json.dumps(sku1, ensure_ascii=False, indent=2),
            sku2_json=json.dumps(sku2, ensure_ascii=False, indent=2),
            output_language=self.output_language
        )

        messages = [{"role": "user", "content": prompt}]

        try:
            response = self.llm.chat(messages, max_tokens=4000, temperature=0.2)
            merged_sku = self._parse_json_response(response)

            # Add merge metadata
            merged_sku["metadata"]["uuid"] = str(uuid.uuid4()) if "uuid" not in merged_sku.get("metadata", {}) else merged_sku["metadata"]["uuid"]
            merged_sku["metadata"]["source_ref"] = {
                "merged_from": [uuid1, uuid2],
                "original_names": [task.get("name1", ""), task.get("name2", "")]
            }

            return merged_sku

        except Exception as e:
            print(f"  [ERROR] Merge failed: {e}")
            return None

    def resolve_branch(self, task: dict) -> dict:
        """
        Create branching logic for conflicting SKUs.

        Returns the resolved SKU with branching.
        """
        uuid1, uuid2 = task["uuid1"], task["uuid2"]
        sku1 = self.load_sku(uuid1)
        sku2 = self.load_sku(uuid2)

        prompt = BRANCH_PROMPT.format(
            name1=task.get("name1", uuid1),
            name2=task.get("name2", uuid2),
            sku1_json=json.dumps(sku1, ensure_ascii=False, indent=2),
            sku2_json=json.dumps(sku2, ensure_ascii=False, indent=2),
            uuid1=uuid1,
            uuid2=uuid2,
            output_language=self.output_language
        )

        messages = [{"role": "user", "content": prompt}]

        try:
            response = self.llm.chat(messages, max_tokens=4000, temperature=0.2)
            resolved_sku = self._parse_json_response(response)

            # Add resolution metadata
            resolved_sku["metadata"]["uuid"] = str(uuid.uuid4()) if "uuid" not in resolved_sku.get("metadata", {}) else resolved_sku["metadata"]["uuid"]
            resolved_sku["metadata"]["source_ref"] = {
                "resolved_from": [uuid1, uuid2],
                "conflict_type": "outcome_divergence"
            }

            return resolved_sku

        except Exception as e:
            print(f"  [ERROR] Branch resolution failed: {e}")
            return None

    def _parse_json_response(self, response: str) -> dict:
        """Parse JSON response from LLM."""
        response = response.strip()

        if response.startswith("```"):
            lines = response.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            response = "\n".join(lines)

        return json.loads(response)

    def resolve_all(self, verbose: bool = True) -> list[dict]:
        """
        Resolve all tasks in the state matrix.

        Returns list of newly created SKUs.
        """
        tasks = self.matrix_data.get("tasks", [])

        if verbose:
            print("=" * 60)
            print("SKU RESOLUTION")
            print("=" * 60)
            print(f"Processing {len(tasks)} resolution tasks...")
            print()

        merge_count = sum(1 for t in tasks if t["action"] == "merge")
        branch_count = sum(1 for t in tasks if t["action"] == "branch")

        if verbose:
            print(f"  - {merge_count} merge tasks")
            print(f"  - {branch_count} branch tasks")
            print()

        for i, task in enumerate(tasks):
            action = task["action"]
            task_id = task["task_id"]

            if verbose:
                print(f"[{i+1}/{len(tasks)}] {task_id}: {action} - {task.get('name1', '')[:30]} + {task.get('name2', '')[:30]}")

            if action == "merge":
                result = self.resolve_merge(task)
            elif action == "branch":
                result = self.resolve_branch(task)
            else:
                result = None

            if result:
                self.merged_skus.append(result)
                self.deprecated_uuids.add(task["uuid1"])
                self.deprecated_uuids.add(task["uuid2"])

                task["resolved"] = True
                task["result"] = {
                    "new_uuid": result["metadata"].get("uuid", ""),
                    "new_name": result["metadata"].get("name", "")
                }

                if verbose:
                    print(f"  -> Created: {result['metadata'].get('name', 'Unnamed')[:50]}")
            else:
                task["resolved"] = False
                if verbose:
                    print(f"  -> FAILED")

            self.resolved_tasks.append(task)

        if verbose:
            print()
            success_count = sum(1 for t in self.resolved_tasks if t.get("resolved"))
            print(f"Resolution complete: {success_count}/{len(tasks)} successful")
            print(f"  - {len(self.merged_skus)} new SKUs created")
            print(f"  - {len(self.deprecated_uuids)} original SKUs deprecated")

        return self.merged_skus

    def save_results(self, output_dir: str = None):
        """Save resolution results."""
        output_path = Path(output_dir) if output_dir else self.skus_dir

        # Save new SKUs
        resolved_skus_dir = output_path / "resolved_skus"
        resolved_skus_dir.mkdir(exist_ok=True)

        for sku in self.merged_skus:
            sku_uuid = sku["metadata"].get("uuid", str(uuid.uuid4()))
            sku_file = resolved_skus_dir / f"{sku_uuid}.json"
            with open(sku_file, 'w', encoding='utf-8') as f:
                json.dump(sku, f, ensure_ascii=False, indent=2)

        # Save resolution summary
        summary = {
            "metadata": {
                "total_tasks": len(self.resolved_tasks),
                "successful": sum(1 for t in self.resolved_tasks if t.get("resolved")),
                "failed": sum(1 for t in self.resolved_tasks if not t.get("resolved")),
                "new_skus_created": len(self.merged_skus),
                "deprecated_uuids": list(self.deprecated_uuids)
            },
            "resolved_tasks": self.resolved_tasks,
            "new_skus": [
                {
                    "uuid": s["metadata"].get("uuid", ""),
                    "name": s["metadata"].get("name", ""),
                    "source": s["metadata"].get("source_ref", {})
                }
                for s in self.merged_skus
            ]
        }

        summary_file = output_path / "resolution_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        print(f"[SKUResolver] Saved {len(self.merged_skus)} resolved SKUs to {resolved_skus_dir}")
        print(f"[SKUResolver] Saved summary to {summary_file}")

    def resolve(self, verbose: bool = True):
        """Run full resolution pipeline."""
        self.resolve_all(verbose=verbose)
        self.save_results()

        if verbose:
            print()
            print("[SKUResolver] Resolution complete")


if __name__ == "__main__":
    main()
