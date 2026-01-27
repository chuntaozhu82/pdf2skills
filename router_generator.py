"""
Module 7: Router Generator - Create hierarchical skill router from book structure

This module handles:
1. Loading all intermediate outputs (tree.json, buckets.json, skus, skills metadata)
2. Building hierarchical router from book structure (domains -> topics -> skills)
3. Building dependency graph from SKU prerequisites
4. Identifying completeness groups (skills that should be used together)
5. Output unified router.json for downstream skills2app consumption

Output:
router.json - Unified hierarchical router with dependency graph
"""

import os
import json
import time
import requests
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Set
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv

# Load .env from pdf2skills directory
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)


# ============================================================================
# Configuration
# ============================================================================

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
GLM_RATE_LIMIT_SECONDS = float(os.getenv("GLM_RATE_LIMIT_SECONDS", "3.0"))


# ============================================================================
# GLM-4.7 Client (via SiliconFlow)
# ============================================================================

class GLM4Client:
    """Client for GLM-4.7 API via SiliconFlow."""

    def __init__(self, rate_limit: float = None):
        self.api_key = SILICONFLOW_API_KEY
        self.base_url = SILICONFLOW_BASE_URL
        self.model = "Pro/zai-org/GLM-4.7"
        self.rate_limit = rate_limit or GLM_RATE_LIMIT_SECONDS
        self.last_call_time = 0

        if not self.api_key:
            raise ValueError("SILICONFLOW_API_KEY must be set in environment")

    def _wait_for_rate_limit(self):
        elapsed = time.time() - self.last_call_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_call_time = time.time()

    def chat(self, messages: list, temperature: float = 0.3, max_tokens: int = 8000) -> str:
        """Send chat completion request."""
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
            timeout=180
        )
        response.raise_for_status()

        result = response.json()
        return result["choices"][0]["message"]["content"]


# ============================================================================
# Prompts
# ============================================================================

COMPLETENESS_GROUPS_PROMPT = '''You are analyzing a set of professional skills extracted from a domain-specific book.

Your task is to identify "completeness groups" - sets of skills that should typically be used together to accomplish a complete workflow or task.

## Skills Summary
{skills_summary}

## Instructions
1. Analyze the skills and identify logical groupings where:
   - Skills form a sequential workflow (A must come before B)
   - Skills cover different aspects of the same task
   - Skills are commonly needed together for a complete outcome

2. For each group, provide:
   - A short group_id (snake_case)
   - A descriptive name
   - The list of skill IDs that belong to this group
   - The recommended order to use them (if sequential)

3. Output valid JSON only, no markdown fences:
{{
  "groups": [
    {{
      "group_id": "example_workflow",
      "name": "Example Complete Workflow",
      "description": "Brief description of what this group accomplishes",
      "skills": ["skill-a", "skill-b", "skill-c"],
      "recommended_order": ["skill-a", "skill-b", "skill-c"]
    }}
  ]
}}

Output JSON only:'''


# ============================================================================
# Router Generator
# ============================================================================

class RouterGenerator:
    """
    Generates hierarchical router.json from pdf2skills intermediate outputs.

    Uses book structure (tree.json) as primary routing backbone,
    with dependency graph from SKU prerequisites and bucket references.
    """

    def __init__(self, output_dir: str):
        """
        Initialize router generator.

        Args:
            output_dir: Path to pdf2skills output directory (contains full_chunks/, full_chunks_skus/)
        """
        self.output_dir = Path(output_dir)
        self.chunks_dir = self.output_dir / "full_chunks"
        self.skus_dir = self.output_dir / "full_chunks_skus"
        self.skills_dir = self.skus_dir / "generated_skills"

        # Validate paths
        if not self.chunks_dir.exists():
            raise FileNotFoundError(f"Chunks directory not found: {self.chunks_dir}")
        if not self.skus_dir.exists():
            raise FileNotFoundError(f"SKUs directory not found: {self.skus_dir}")
        if not self.skills_dir.exists():
            raise FileNotFoundError(f"Skills directory not found: {self.skills_dir}")

        # Load all data sources
        self.tree = self._load_tree()
        self.chunks_index = self._load_chunks_index()
        self.skus_index = self._load_skus_index()
        self.buckets = self._load_buckets()
        self.similarities = self._load_similarities()
        self.skills_metadata = self._load_skills_metadata()
        self.all_skus = self._load_all_skus()

        # Build mappings
        self.sku_to_skill = self._build_sku_to_skill_map()
        self.skill_to_skus = self._build_skill_to_skus_map()
        self.chunk_to_skus = self._build_chunk_to_skus_map()

        # LLM client (lazy init)
        self._llm_client = None

        # Result
        self.router = None

    # =========================================================================
    # Data Loaders
    # =========================================================================

    def _load_tree(self) -> dict:
        """Load tree.json - book hierarchical structure."""
        tree_file = self.chunks_dir / "tree.json"
        if tree_file.exists():
            with open(tree_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _load_chunks_index(self) -> list:
        """Load chunks_index.json - chunk metadata."""
        index_file = self.chunks_dir / "chunks_index.json"
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # chunks_index.json is a list directly
                if isinstance(data, list):
                    return data
                return data.get("chunks", [])
        return []

    def _load_skus_index(self) -> dict:
        """Load skus_index.json - SKU registry."""
        index_file = self.skus_dir / "skus_index.json"
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _load_buckets(self) -> dict:
        """Load buckets.json - SKU groupings."""
        buckets_file = self.skus_dir / "buckets.json"
        if buckets_file.exists():
            with open(buckets_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _load_similarities(self) -> dict:
        """Load similarities.json - SKU relationships."""
        sim_file = self.skus_dir / "similarities.json"
        if sim_file.exists():
            with open(sim_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _load_skills_metadata(self) -> dict:
        """Load generation_metadata.json - skill generation info."""
        meta_file = self.skills_dir / "generation_metadata.json"
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _load_all_skus(self) -> Dict[str, dict]:
        """Load all individual SKU files."""
        skus = {}
        skus_folder = self.skus_dir / "skus"
        if skus_folder.exists():
            for sku_file in skus_folder.glob("*.json"):
                with open(sku_file, "r", encoding="utf-8") as f:
                    sku = json.load(f)
                    uuid = sku.get("metadata", {}).get("uuid", sku_file.stem)
                    skus[uuid] = sku
        return skus

    # =========================================================================
    # Mapping Builders
    # =========================================================================

    def _build_sku_to_skill_map(self) -> Dict[str, str]:
        """Map SKU UUID -> skill name."""
        mapping = {}
        for skill_info in self.skills_metadata.get("skills", []):
            skill_name = skill_info.get("name", "")
            for uuid in skill_info.get("source_sku_uuids", []):
                mapping[uuid] = skill_name
        return mapping

    def _build_skill_to_skus_map(self) -> Dict[str, List[str]]:
        """Map skill name -> list of SKU UUIDs."""
        mapping = defaultdict(list)
        for skill_info in self.skills_metadata.get("skills", []):
            skill_name = skill_info.get("name", "")
            for uuid in skill_info.get("source_sku_uuids", []):
                mapping[skill_name].append(uuid)
        return dict(mapping)

    def _build_chunk_to_skus_map(self) -> Dict[str, List[str]]:
        """Map chunk ID -> list of SKU UUIDs."""
        mapping = defaultdict(list)
        for sku_info in self.skus_index.get("skus", []):
            chunk_id = sku_info.get("source_chunk", "")
            uuid = sku_info.get("uuid", "")
            if chunk_id and uuid:
                mapping[chunk_id].append(uuid)
        return dict(mapping)

    # =========================================================================
    # Hierarchy Builder (from tree.json)
    # =========================================================================

    def build_hierarchy(self) -> dict:
        """
        Build hierarchical router structure from book's tree.json.

        Maps: book chapters -> domains -> topics -> skills
        """
        domains = []

        # Process root's children as top-level domains
        for child in self.tree.get("children", []):
            domain = self._process_tree_node(child, level="domain")
            if domain and (domain.get("topics") or domain.get("skills")):
                domains.append(domain)

        return {"domains": domains}

    def _process_tree_node(self, node: dict, level: str = "domain") -> dict:
        """
        Recursively process a tree node into router hierarchy.

        Args:
            node: Tree node from tree.json
            level: Current hierarchy level ("domain" or "topic")
        """
        node_id = node.get("id", "")
        title = node.get("title", "Untitled")
        children = node.get("children", [])
        parent_path = node.get("parent_path", [])

        # Find skills that originated from this chunk
        chunk_skills = self._find_skills_for_chunk(node_id)

        if level == "domain":
            # Domain level: process children as topics
            topics = []
            direct_skills = []

            if children:
                for child in children:
                    topic = self._process_tree_node(child, level="topic")
                    if topic and (topic.get("skills") or topic.get("subtopics")):
                        topics.append(topic)

            # Skills directly under this domain (no children)
            if not children and chunk_skills:
                direct_skills = chunk_skills

            # Calculate book_index_range
            book_index_range = self._get_book_index_range(node_id)

            return {
                "domain_id": f"domain_{node_id}",
                "name": title,
                "source_chunk": node_id,
                "book_index_range": book_index_range,
                "parent_path": parent_path,
                "topics": topics,
                "skills": direct_skills  # Skills directly under domain (if no topics)
            }

        else:  # topic level
            # Topic level: collect skills
            subtopics = []
            all_skills = list(chunk_skills)

            if children:
                for child in children:
                    subtopic = self._process_tree_node(child, level="topic")
                    if subtopic:
                        subtopics.append(subtopic)

            return {
                "topic_id": f"topic_{node_id}",
                "name": title,
                "source_chunk": node_id,
                "parent_path": parent_path,
                "skills": all_skills,
                "subtopics": subtopics if subtopics else None
            }

    def _find_skills_for_chunk(self, chunk_id: str) -> List[str]:
        """Find all skills that originated from a specific chunk."""
        skills = set()
        sku_uuids = self.chunk_to_skus.get(chunk_id, [])
        for uuid in sku_uuids:
            skill_name = self.sku_to_skill.get(uuid)
            if skill_name:
                skills.add(skill_name)
        return list(skills)

    def _get_book_index_range(self, chunk_id: str) -> List[int]:
        """Get the book_index range for a chunk and its descendants."""
        indices = []

        # Get indices from SKUs in this chunk
        for sku_info in self.skus_index.get("skus", []):
            if sku_info.get("source_chunk") == chunk_id:
                book_idx = sku_info.get("book_index")
                if book_idx is not None:
                    indices.append(book_idx)

        if indices:
            return [min(indices), max(indices)]
        return []

    # =========================================================================
    # Dependency Graph Builder (from SKU prerequisites)
    # =========================================================================

    def build_dependency_graph(self) -> dict:
        """
        Build dependency graph from SKU prerequisites.

        Maps skill dependencies based on their source SKU prerequisites.
        """
        nodes = []
        edges = []
        skill_prereqs = defaultdict(set)
        skill_enables = defaultdict(set)

        # Collect prerequisites from all SKUs
        for skill_name, sku_uuids in self.skill_to_skus.items():
            all_prereqs = set()

            for uuid in sku_uuids:
                sku = self.all_skus.get(uuid, {})
                prereqs = sku.get("context", {}).get("prerequisites", [])
                all_prereqs.update(prereqs)

            # Try to match prerequisites to other skills
            for prereq_text in all_prereqs:
                matched_skill = self._match_prereq_to_skill(prereq_text, skill_name)
                if matched_skill:
                    skill_prereqs[skill_name].add(matched_skill)
                    skill_enables[matched_skill].add(skill_name)
                    edges.append({
                        "from": matched_skill,
                        "to": skill_name,
                        "type": "prerequisite"
                    })

        # Build co_required from buckets (skills in same bucket)
        skill_co_required = self._build_co_required_from_buckets()

        # Create nodes
        all_skills = set(self.skill_to_skus.keys())
        for skill_name in all_skills:
            nodes.append({
                "skill_id": skill_name,
                "prerequisites": list(skill_prereqs.get(skill_name, [])),
                "enables": list(skill_enables.get(skill_name, [])),
                "co_required": list(skill_co_required.get(skill_name, []))
            })

        return {
            "nodes": nodes,
            "edges": edges
        }

    def _match_prereq_to_skill(self, prereq_text: str, exclude_skill: str) -> Optional[str]:
        """
        Try to match a prerequisite text to an existing skill.

        Uses simple text matching on skill names and SKU names.
        """
        prereq_lower = prereq_text.lower()

        for skill_name in self.skill_to_skus.keys():
            if skill_name == exclude_skill:
                continue

            # Match skill name
            skill_words = skill_name.replace("-", " ").lower()
            if skill_words in prereq_lower or prereq_lower in skill_words:
                return skill_name

            # Match SKU names
            for uuid in self.skill_to_skus[skill_name]:
                sku = self.all_skus.get(uuid, {})
                sku_name = sku.get("metadata", {}).get("name", "").lower()
                if sku_name and (sku_name in prereq_lower or prereq_lower in sku_name):
                    return skill_name

        return None

    def _build_co_required_from_buckets(self) -> Dict[str, Set[str]]:
        """Build co_required relationships from bucket assignments."""
        co_required = defaultdict(set)

        for bucket in self.buckets.get("buckets", []):
            sku_uuids = bucket.get("sku_uuids", [])
            bucket_skills = set()

            for uuid in sku_uuids:
                skill_name = self.sku_to_skill.get(uuid)
                if skill_name:
                    bucket_skills.add(skill_name)

            # Skills in same bucket are co_required
            for skill in bucket_skills:
                co_required[skill].update(bucket_skills - {skill})

        return co_required

    # =========================================================================
    # Completeness Groups Builder (LLM-assisted)
    # =========================================================================

    @property
    def llm_client(self):
        """Lazy-init LLM client."""
        if self._llm_client is None:
            self._llm_client = GLM4Client()
        return self._llm_client

    def build_completeness_groups(self) -> list:
        """
        Use LLM to identify skill groups that should be used together.
        """
        # Prepare skills summary for LLM
        skills_summary = self._prepare_skills_summary()

        if not skills_summary:
            return []

        prompt = COMPLETENESS_GROUPS_PROMPT.format(skills_summary=skills_summary)

        try:
            print("  Calling LLM to identify completeness groups...")
            response = self.llm_client.chat([
                {"role": "user", "content": prompt}
            ])

            # Parse JSON response
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]

            result = json.loads(response)
            return result.get("groups", [])

        except Exception as e:
            print(f"  Warning: LLM call failed for completeness groups: {e}")
            return []

    def _prepare_skills_summary(self) -> str:
        """Prepare skills summary for LLM."""
        summaries = []

        for skill_info in self.skills_metadata.get("skills", []):
            skill_name = skill_info.get("name", "")

            # Get SKU info for this skill
            sku_names = []
            applicable_objects = set()

            for uuid in skill_info.get("source_sku_uuids", []):
                sku = self.all_skus.get(uuid, {})
                sku_name = sku.get("metadata", {}).get("name", "")
                if sku_name:
                    sku_names.append(sku_name)

                objects = sku.get("context", {}).get("applicable_objects", [])
                applicable_objects.update(objects)

            summary = f"- {skill_name}: {', '.join(sku_names[:2])}"
            if applicable_objects:
                summary += f" (applies to: {', '.join(list(applicable_objects)[:3])})"
            summaries.append(summary)

        return "\n".join(summaries)

    # =========================================================================
    # Bucket References Builder
    # =========================================================================

    def build_bucket_references(self) -> dict:
        """Build bucket references for semantic grouping hints."""
        references = {}

        for bucket in self.buckets.get("buckets", []):
            bucket_id = bucket.get("bucket_id", "")
            shared_objects = bucket.get("shared_objects", [])
            shared_tags = bucket.get("shared_tags", [])
            sku_uuids = bucket.get("sku_uuids", [])

            # Map to skills
            skills = set()
            for uuid in sku_uuids:
                skill_name = self.sku_to_skill.get(uuid)
                if skill_name:
                    skills.add(skill_name)

            if skills:
                references[bucket_id] = {
                    "shared_objects": shared_objects,
                    "shared_tags": shared_tags,
                    "skills": list(skills)
                }

        return references

    # =========================================================================
    # Main Generation
    # =========================================================================

    def generate(self) -> dict:
        """Generate complete router.json structure."""
        print("Generating router...")

        # Build hierarchy from book structure
        print("  Building hierarchy from book structure...")
        hierarchy = self.build_hierarchy()

        # Build dependency graph
        print("  Building dependency graph from SKU prerequisites...")
        dependency_graph = self.build_dependency_graph()

        # Build completeness groups (LLM-assisted)
        completeness_groups = self.build_completeness_groups()

        # Build bucket references
        print("  Building bucket references...")
        bucket_references = self.build_bucket_references()

        # Extract book title from tree
        book_title = self.tree.get("title", "Unknown Book")

        # Assemble router
        self.router = {
            "metadata": {
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source_book": book_title,
                "source_dir": str(self.output_dir),
                "total_skills": len(self.skill_to_skus),
                "total_domains": len(hierarchy.get("domains", [])),
                "version": "1.0"
            },
            "hierarchy": hierarchy,
            "dependency_graph": dependency_graph,
            "completeness_groups": completeness_groups,
            "bucket_references": bucket_references
        }

        print(f"  Router generated: {self.router['metadata']['total_skills']} skills, "
              f"{self.router['metadata']['total_domains']} domains")

        return self.router

    def save_results(self) -> Path:
        """Save router.json to output directory."""
        if self.router is None:
            self.generate()

        output_file = self.skus_dir / "router.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.router, f, ensure_ascii=False, indent=2)

        print(f"  Saved: {output_file}")
        return output_file


# ============================================================================
# CLI
# ============================================================================

def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate hierarchical router from pdf2skills output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate router for existing output
  python -m router_generator ./book_output

  # Generate router from test data
  python -m router_generator ./test_data/book_output
"""
    )

    parser.add_argument(
        "output_dir",
        help="Path to pdf2skills output directory"
    )

    args = parser.parse_args()

    try:
        generator = RouterGenerator(args.output_dir)
        generator.generate()
        generator.save_results()
        print("\nRouter generation complete!")

    except Exception as e:
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    main()
