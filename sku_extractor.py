"""
Module 3: SKU (Standardized Knowledge Unit) Extractor

Extracts structured knowledge units from chunks using GLM-4.7 via SiliconFlow.
Follows MECE principle for knowledge decomposition.
"""

import os
import json
import uuid
import time
import requests
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from dotenv import load_dotenv
from pathlib import Path

# Load .env from pdf2skills directory
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)


# ============================================================================
# Configuration
# ============================================================================

GLM_API_KEY = os.getenv("GLM_API_KEY")
GLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL")
OUTPUT_LANGUAGE = os.getenv("OUTPUT_LANGUAGE", "English")

# Rate limiting configuration (seconds between API calls)
GLM_RATE_LIMIT_SECONDS = float(os.getenv("GLM_RATE_LIMIT_SECONDS", "3.0"))


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class SKUMetadata:
    """Metadata for a knowledge unit."""
    uuid: str
    name: str
    source_ref: dict  # {"chunk_id": "...", "book_index": N, "snippet": "..."}


@dataclass
class SKUContext:
    """Contextual information for when the knowledge applies."""
    applicable_objects: list  # List of applicable objects
    prerequisites: list  # Data dependencies
    constraints: list  # Negative constraints / Out of bounds


@dataclass
class SKUTrigger:
    """Conditions that trigger this knowledge."""
    condition_logic: str  # Pseudocode description e.g., "IF (A > B) AND (C is True)"


@dataclass
class SKUCoreLogic:
    """The core logic of the knowledge unit."""
    logic_type: str  # "Formula" | "Decision_Tree" | "Heuristic" | "Process"
    execution_body: str  # Concrete calculation formula or step description
    variables: list  # [{"name": "var1", "type": "float", "description": "..."}]


@dataclass
class SKUOutput:
    """Expected output from applying this knowledge."""
    output_type: str  # "Value" | "Alert" | "Action"
    result_template: str  # Conclusion interpretation template


@dataclass
class SKU:
    """Standardized Knowledge Unit - Complete structure."""
    # Core Area (Invariant)
    metadata: SKUMetadata
    context: SKUContext
    trigger: SKUTrigger

    # Logic Area (The "How")
    core_logic: SKUCoreLogic
    output: SKUOutput

    # Flex Area (Variant - LLM Defined)
    custom_attributes: dict = field(default_factory=dict)
    schema_explanation: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "metadata": asdict(self.metadata),
            "context": asdict(self.context),
            "trigger": asdict(self.trigger),
            "core_logic": asdict(self.core_logic),
            "output": asdict(self.output),
            "custom_attributes": self.custom_attributes,
            "schema_explanation": self.schema_explanation
        }


# ============================================================================
# GLM-4.7 Client
# ============================================================================

class GLM4Client:
    """
    Client for GLM-4.7 API via SiliconFlow.

    BigModel is disabled - using SiliconFlow as sole provider.
    Implements rate limiting to avoid API throttling.
    """

    def __init__(self, api_key: str = None, base_url: str = None, rate_limit: float = None):
        self.api_key = api_key or GLM_API_KEY
        self.base_url = base_url or GLM_BASE_URL

        # SiliconFlow fallback configuration
        self.siliconflow_api_key = SILICONFLOW_API_KEY
        self.siliconflow_base_url = SILICONFLOW_BASE_URL
        self.siliconflow_model = "Pro/zai-org/GLM-4.7"

        # Rate limiting
        self.rate_limit = rate_limit if rate_limit is not None else GLM_RATE_LIMIT_SECONDS
        self._last_call_time = 0

        # Require SiliconFlow API key (BigModel commented out)
        if not self.siliconflow_api_key:
            raise ValueError("SILICONFLOW_API_KEY must be set in environment")

    def _apply_rate_limit(self):
        """Apply rate limiting between API calls."""
        if self.rate_limit > 0:
            elapsed = time.time() - self._last_call_time
            if elapsed < self.rate_limit:
                sleep_time = self.rate_limit - elapsed
                print(f"  [RATE LIMIT] Waiting {sleep_time:.1f}s before next API call...")
                time.sleep(sleep_time)
        self._last_call_time = time.time()

    def _try_bigmodel(self, messages: list, max_tokens: int, temperature: float) -> str:
        """Try BigModel API."""
        if not self.api_key:
            raise ValueError("GLM_API_KEY not set")
        
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "glm-4.7",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        result = response.json()
        return result["choices"][0]["message"]["content"]

    def _try_siliconflow(self, messages: list, max_tokens: int, temperature: float) -> str:
        """Try SiliconFlow API as fallback."""
        if not self.siliconflow_api_key:
            raise ValueError("SILICONFLOW_API_KEY not set")
        
        url = f"{self.siliconflow_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.siliconflow_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.siliconflow_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        result = response.json()
        return result["choices"][0]["message"]["content"]

    def chat(self, messages: list, max_tokens: int = 8000, temperature: float = 0.3) -> str:
        """
        Send chat completion request to GLM-4.7 via SiliconFlow.
        
        Applies rate limiting to avoid API throttling.
        """
        # Apply rate limiting before making request
        self._apply_rate_limit()

        # Use SiliconFlow only (BigModel commented out for now)
        # # Try BigModel first if API key is available
        # if self.api_key:
        #     try:
        #         return self._try_bigmodel(messages, max_tokens, temperature)
        #     except (requests.exceptions.RequestException, ValueError, KeyError) as e:
        #         # If BigModel fails and SiliconFlow is available, try fallback
        #         if self.siliconflow_api_key:
        #             print(f"  [INFO] BigModel request failed, trying SiliconFlow fallback: {type(e).__name__}")
        #             try:
        #                 return self._try_siliconflow(messages, max_tokens, temperature)
        #             except Exception as fallback_error:
        #                 raise Exception(f"Both BigModel and SiliconFlow failed. BigModel: {e}, SiliconFlow: {fallback_error}")
        #         else:
        #             # No fallback available, raise original error
        #             raise
        
        # Use SiliconFlow directly
        if self.siliconflow_api_key:
            return self._try_siliconflow(messages, max_tokens, temperature)
        
        raise ValueError("SILICONFLOW_API_KEY must be set in environment")


# ============================================================================
# SKU Extraction Prompt
# ============================================================================

# NOTE: The extraction prompt is defined here for easy modification
# Location: pdf2skills/sku_extractor.py, line ~220
EXTRACTION_PROMPT_TEMPLATE = '''You are a knowledge engineer extracting structured knowledge units from technical documents.

## Task
Analyze the following text chunk and extract ALL distinct knowledge units following the MECE principle:
- **Mutually Exclusive**: Each knowledge unit should represent ONE distinct concept/rule/procedure
- **Collectively Exhaustive**: Together, all units should cover the full content of the chunk

## Target Count
Based on density analysis, aim to extract approximately {target_count} knowledge units from this chunk (use as reference, adjust based on actual content).

## Output Format
Return a JSON array of knowledge units. Each unit must follow this schema:

```json
[
  {{
    "metadata": {{
      "name": "Concise rule/concept name",
      "snippet": "Key sentence from source (max 100 chars)"
    }},
    "context": {{
      "applicable_objects": ["List of objects this applies to"],
      "prerequisites": ["Required data/conditions"],
      "constraints": ["When this does NOT apply"]
    }},
    "trigger": {{
      "condition_logic": "IF (condition) THEN apply this knowledge"
    }},
    "core_logic": {{
      "logic_type": "Formula|Decision_Tree|Heuristic|Process",
      "execution_body": "DETAILED step-by-step logic, formula, or procedure - see CRITICAL requirements below",
      "variables": [{{"name": "var_name", "type": "type", "description": "desc"}}]
    }},
    "output": {{
      "output_type": "Value|Alert|Action",
      "result_template": "How to interpret/use the result"
    }},
    "custom_attributes": {{
      "domain_tags": ["tag1", "tag2"],
      "importance": "high|medium|low",
      "any_other_relevant_field": "value"
    }},
    "schema_explanation": "Why specific custom fields were added"
  }}
]
```

## CRITICAL: execution_body Requirements
The `execution_body` field is the MOST IMPORTANT field. It must:
1. **Be COMPREHENSIVE**: Include ALL details from the original text - do NOT summarize or omit information
2. **Preserve specifics**: Keep all numbers, thresholds, percentages, formulas, and examples from the source
3. **Include reasoning**: Explain WHY each step matters if the source explains it
4. **Use structured format**: Use numbered steps for processes, bullet points for lists
5. **Quote key phrases**: When the source has important terminology or phrases, preserve them
6. **Include edge cases**: If the source mentions exceptions or special cases, include them

Example of GOOD execution_body:
"1. Calculate current ratio = Current Assets / Current Liabilities
2. Interpretation thresholds:
   - Ratio > 2.0: Strong liquidity position, company can easily meet short-term obligations
   - Ratio 1.0-2.0: Adequate liquidity, but monitor closely
   - Ratio < 1.0: WARNING - company may struggle to pay short-term debts
3. Industry adjustment: Manufacturing companies typically need higher ratios (>1.5) due to inventory cycles
4. Limitation: Does not account for quality of current assets (e.g., slow-moving inventory)"

Example of BAD execution_body (too vague):
"Calculate current ratio by dividing assets by liabilities and interpret the result"

## Language
Output all text fields in {output_language}.

## Source Content
Chunk Title: {chunk_title}
Parent Path: {parent_path}

---
{chunk_content}
---

## Instructions
1. Read the entire chunk carefully
2. Identify distinct knowledge units (rules, formulas, procedures, concepts)
3. For each unit, fill ALL schema fields - especially ensure execution_body is DETAILED and COMPLETE
4. Ensure units are MECE (no overlaps, no gaps)
5. Return ONLY the JSON array, no other text'''


# ============================================================================
# SKU Extractor
# ============================================================================

class SKUExtractor:
    """Extracts SKUs from chunks using GLM-4.7."""

    def __init__(self, chunks_dir: str, density_file: str = None, output_dir: str = None):
        """
        Initialize the extractor.

        Args:
            chunks_dir: Path to chunks directory (contains chunks/ and chunks_index.json)
            density_file: Optional path to density_scores.json for target counts
            output_dir: Optional output directory for immediate SKU saving
        """
        self.chunks_dir = Path(chunks_dir)
        self.chunks_path = self.chunks_dir / "chunks"
        self.index_file = self.chunks_dir / "chunks_index.json"

        # Load chunks index
        with open(self.index_file, 'r', encoding='utf-8') as f:
            self.chunks_index = json.load(f)

        # Load density scores if provided
        self.density_data = None
        if density_file:
            density_path = Path(density_file)
            if density_path.exists():
                with open(density_path, 'r', encoding='utf-8') as f:
                    self.density_data = json.load(f)

        self.llm = GLM4Client()
        self.skus: list[SKU] = []
        self.output_language = OUTPUT_LANGUAGE
        
        # Setup output directory for immediate saving
        self.output_dir = Path(output_dir) if output_dir else None
        self.skus_dir = None
        self.sku_index = []
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.skus_dir = self.output_dir / "skus"
            self.skus_dir.mkdir(exist_ok=True)
            # Load existing index if it exists
            index_file = self.output_dir / "skus_index.json"
            if index_file.exists():
                with open(index_file, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
                    self.sku_index = index_data.get("skus", [])

    def estimate_target_count(self, chunk_id: str, token_count: int) -> int:
        """
        Estimate target SKU count for a chunk.

        Uses density score if available, otherwise uses token-based heuristic.
        """
        # Base estimate: ~1 SKU per 1500 tokens
        base_count = max(1, token_count // 1500)

        if self.density_data:
            # Find chunk in density data
            for chunk in self.density_data.get("chunks", []):
                if chunk["chunk_id"] == chunk_id:
                    # Adjust based on density score
                    # Higher density = more knowledge units
                    score = chunk.get("final_score", 20)
                    mean = self.density_data.get("statistics", {}).get("mean_score", 20)

                    # Scale factor: score/mean gives relative density
                    scale = score / mean if mean > 0 else 1.0
                    adjusted = int(base_count * scale * 1.2)  # 1.2 redundancy factor
                    return max(1, adjusted)

        return base_count

    def extract_from_chunk(self, chunk_info: dict, verbose: bool = False) -> list[SKU]:
        """Extract SKUs from a single chunk."""
        chunk_id = chunk_info["id"]
        chunk_file = self.chunks_dir / chunk_info["file"]

        # Read chunk content
        with open(chunk_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Estimate target count
        token_count = chunk_info.get("tokens", len(content) // 2)
        target_count = self.estimate_target_count(chunk_id, token_count)

        # Prepare prompt
        parent_path = " > ".join(chunk_info.get("parent_path", [])) or "Root"
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            target_count=target_count,
            output_language=self.output_language,
            chunk_title=chunk_info.get("title", "Untitled"),
            parent_path=parent_path,
            chunk_content=content[:50000]  # Limit content length for API
        )

        # Call LLM
        messages = [{"role": "user", "content": prompt}]

        try:
            response = self.llm.chat(messages, max_tokens=8000, temperature=0.3)

            # Parse JSON response
            # Handle potential markdown code blocks
            response = response.strip()
            if response.startswith("```"):
                # Remove markdown code block
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                response = "\n".join(lines)

            sku_list = json.loads(response)

            # Convert to SKU objects and save immediately if output_dir is set
            skus = []
            for i, sku_data in enumerate(sku_list):
                sku = self._parse_sku(sku_data, chunk_info, i)
                skus.append(sku)
                
                # Save SKU immediately if output directory is configured
                if self.output_dir and self.skus_dir:
                    self._save_sku_immediately(sku)

            return skus

        except json.JSONDecodeError as e:
            if verbose:
                print(f"  [WARN] Failed to parse JSON for {chunk_id}: {e}")
                print(f"  Response preview: {response[:200]}...")
            return []
        except Exception as e:
            if verbose:
                print(f"  [ERROR] Failed to extract from {chunk_id}: {e}")
            return []

    def _parse_sku(self, data: dict, chunk_info: dict, index: int) -> SKU:
        """Parse a dictionary into an SKU object."""
        # Generate UUID
        sku_uuid = str(uuid.uuid4())

        # Build metadata
        metadata = SKUMetadata(
            uuid=sku_uuid,
            name=data.get("metadata", {}).get("name", f"SKU_{index}"),
            source_ref={
                "chunk_id": chunk_info["id"],
                "book_index": chunk_info.get("book_index", 0),
                "start_line": chunk_info.get("start_line", 0),
                "end_line": chunk_info.get("end_line", 0),
                "snippet": data.get("metadata", {}).get("snippet", "")
            }
        )

        # Build context
        ctx = data.get("context", {})
        context = SKUContext(
            applicable_objects=ctx.get("applicable_objects", []),
            prerequisites=ctx.get("prerequisites", []),
            constraints=ctx.get("constraints", [])
        )

        # Build trigger
        trigger = SKUTrigger(
            condition_logic=data.get("trigger", {}).get("condition_logic", "")
        )

        # Build core logic
        logic = data.get("core_logic", {})
        core_logic = SKUCoreLogic(
            logic_type=logic.get("logic_type", "Heuristic"),
            execution_body=logic.get("execution_body", ""),
            variables=logic.get("variables", [])
        )

        # Build output
        out = data.get("output", {})
        output = SKUOutput(
            output_type=out.get("output_type", "Value"),
            result_template=out.get("result_template", "")
        )

        # Build full SKU
        return SKU(
            metadata=metadata,
            context=context,
            trigger=trigger,
            core_logic=core_logic,
            output=output,
            custom_attributes=data.get("custom_attributes", {}),
            schema_explanation=data.get("schema_explanation", "")
        )

    def _save_sku_immediately(self, sku: SKU):
        """Save a single SKU immediately to disk."""
        if not self.skus_dir:
            return
        
        # Save SKU file
        filename = f"{sku.metadata.uuid}.json"
        filepath = self.skus_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(sku.to_dict(), f, ensure_ascii=False, indent=2)
        
        # Add to index
        sku_entry = {
            "uuid": sku.metadata.uuid,
            "name": sku.metadata.name,
            "source_chunk": sku.metadata.source_ref.get("chunk_id"),
            "book_index": sku.metadata.source_ref.get("book_index"),
            "logic_type": sku.core_logic.logic_type,
            "domain_tags": sku.custom_attributes.get("domain_tags", []),
            "file": f"skus/{filename}"
        }
        
        # Check if already in index (avoid duplicates)
        existing_uuids = {entry["uuid"] for entry in self.sku_index}
        if sku.metadata.uuid not in existing_uuids:
            self.sku_index.append(sku_entry)
        
        # Update index file immediately
        index_data = {
            "metadata": {
                "total_skus": len(self.sku_index),
                "source_chunks_dir": str(self.chunks_dir),
                "output_language": self.output_language
            },
            "skus": self.sku_index
        }
        
        index_file = self.output_dir / "skus_index.json"
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)

    def extract_all(self, verbose: bool = True) -> list[SKU]:
        """Extract SKUs from all chunks."""
        if verbose:
            print(f"[SKUExtractor] Starting extraction from {len(self.chunks_index)} chunks")
            print(f"[SKUExtractor] Output language: {self.output_language}")
            print(f"[SKUExtractor] Using GLM-4.7 for extraction")
            print()

        all_skus = []

        for i, chunk_info in enumerate(self.chunks_index):
            chunk_id = chunk_info["id"]
            title = chunk_info.get("title", "Untitled")[:40]
            tokens = chunk_info.get("tokens", 0)

            if verbose:
                print(f"[{i+1}/{len(self.chunks_index)}] Processing {chunk_id}: {title}... ({tokens} tokens)")

            skus = self.extract_from_chunk(chunk_info)
            all_skus.extend(skus)

            if verbose:
                print(f"  -> Extracted {len(skus)} SKUs")

        self.skus = all_skus
        if verbose:
            print()
            print(f"[SKUExtractor] Total: {len(all_skus)} SKUs extracted")

        return all_skus

    def save_results(self, output_dir: str = None):
        """
        Save extracted SKUs to output directory.

        If output_dir was set during initialization, SKUs are already saved incrementally.
        This method finalizes the index.

        Creates:
        - skus_index.json: Index of all SKUs with summary
        - skus/: Directory with individual SKU JSON files
        """
        # If output_dir was provided during init, use it; otherwise use provided arg
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            skus_dir = output_path / "skus"
            skus_dir.mkdir(exist_ok=True)
        elif self.output_dir:
            output_path = self.output_dir
            skus_dir = self.skus_dir
        else:
            raise ValueError("output_dir must be provided either in __init__ or save_results()")

        # If SKUs weren't saved incrementally, save them now
        if not self.output_dir or output_dir:
            sku_index = []
            for sku in self.skus:
                # Use UUID as filename
                filename = f"{sku.metadata.uuid}.json"
                filepath = skus_dir / filename

                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(sku.to_dict(), f, ensure_ascii=False, indent=2)

                # Add to index
                sku_index.append({
                    "uuid": sku.metadata.uuid,
                    "name": sku.metadata.name,
                    "source_chunk": sku.metadata.source_ref.get("chunk_id"),
                    "book_index": sku.metadata.source_ref.get("book_index"),
                    "logic_type": sku.core_logic.logic_type,
                    "domain_tags": sku.custom_attributes.get("domain_tags", []),
                    "file": f"skus/{filename}"
                })

            # Save index
            index_data = {
                "metadata": {
                    "total_skus": len(self.skus),
                    "source_chunks_dir": str(self.chunks_dir),
                    "output_language": self.output_language
                },
                "skus": sku_index
            }

            with open(output_path / "skus_index.json", 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
        else:
            # SKUs were saved incrementally, just update final count
            index_data = {
                "metadata": {
                    "total_skus": len(self.sku_index),
                    "source_chunks_dir": str(self.chunks_dir),
                    "output_language": self.output_language
                },
                "skus": self.sku_index
            }
            with open(output_path / "skus_index.json", 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)

        print(f"[SKUExtractor] Saved {len(self.skus) if self.skus else len(self.sku_index)} SKUs to {output_path}")
        print(f"  - Index: {output_path / 'skus_index.json'}")
        print(f"  - SKUs:  {skus_dir}/")


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract SKUs from chunks")
    parser.add_argument("chunks_dir", help="Path to chunks directory")
    parser.add_argument("-d", "--density", help="Path to density_scores.json")
    parser.add_argument("-o", "--output", help="Output directory (default: <chunks_dir>_skus)")

    args = parser.parse_args()

    chunks_dir = Path(args.chunks_dir)
    output_dir = args.output or f"{chunks_dir}_skus"

    extractor = SKUExtractor(
        chunks_dir=str(chunks_dir),
        density_file=args.density
    )

    extractor.extract_all()
    extractor.save_results(output_dir)


if __name__ == "__main__":
    main()
