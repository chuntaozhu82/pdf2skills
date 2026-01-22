"""
Module 5: Skill Generator - Convert SKUs to Claude Code Skills

This module handles:
1. Reading SKUs and bucket assignments
2. Converting SKUs to skills via GLM-4.7 on SiliconFlow (N:M mapping where M <= N)
3. Post-processing LLM output into proper folder structure
4. Generating top-level index.md for skill navigation

Output structure:
generated_skills/
├── index.md                    # Top-level router/instruction
├── skill-name-1/
│   ├── SKILL.md
│   └── references/
│       └── details.md
├── skill-name-2/
│   └── SKILL.md
└── ...
"""

import os
import json
import time
import re
import requests
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
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
GLM_RATE_LIMIT_SECONDS = float(os.getenv("GLM_RATE_LIMIT_SECONDS", "3.0"))
OUTPUT_LANGUAGE = os.getenv("OUTPUT_LANGUAGE", "English")

# Skill constraints
MAX_SKILL_LINES = 500
MAX_SKUS_PER_LLM_CALL = 15  # Limit to avoid context overflow


# ============================================================================
# GLM-4.7 Client (reuse from sku_extractor pattern)
# ============================================================================

class GLM4Client:
    """
    Client for GLM-4.7 API via SiliconFlow.
    
    BigModel is commented out - using SiliconFlow as sole provider.
    """

    def __init__(self, api_key: str = None, base_url: str = None, rate_limit: float = None):
        # BigModel configuration (commented out)
        # self.api_key = api_key or GLM_API_KEY
        # self.base_url = base_url or GLM_BASE_URL
        # self.model = "glm-4.7"
        
        # SiliconFlow configuration (sole provider)
        self.siliconflow_api_key = SILICONFLOW_API_KEY
        self.siliconflow_base_url = SILICONFLOW_BASE_URL
        self.siliconflow_model = "Pro/zai-org/GLM-4.7"
        
        self.rate_limit = rate_limit or GLM_RATE_LIMIT_SECONDS
        self.last_call_time = 0

        if not self.siliconflow_api_key:
            raise ValueError("SILICONFLOW_API_KEY must be set in environment")

    def _wait_for_rate_limit(self):
        elapsed = time.time() - self.last_call_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_call_time = time.time()

    def chat(self, messages: list, temperature: float = 0.3, max_tokens: int = 16000) -> str:
        """Send chat completion request via SiliconFlow."""
        self._wait_for_rate_limit()

        headers = {
            "Authorization": f"Bearer {self.siliconflow_api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.siliconflow_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        response = requests.post(
            f"{self.siliconflow_base_url}/chat/completions",
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

SKILL_GENERATION_PROMPT = '''You are converting Standardized Knowledge Units (SKUs) into Claude Code Skills.

## Background
SKUs are structured knowledge units extracted from a professional book. Your task is to convert them into Skills that Claude Code can use to help users with domain-specific tasks.

## Skill Format Requirements (from Anthropic's official guide)
1. Each skill has a SKILL.md with YAML frontmatter (name, description) and markdown body
2. SKILL.md should be < 500 lines, focusing on core workflows and procedures
3. Detailed reference material goes in references/ folder
4. Skill names use kebab-case (e.g., "financial-ratio-analysis")
5. Description must clearly state WHAT the skill does and WHEN to use it

## Your Task
Given these {sku_count} SKUs from the same domain bucket, create skills following these rules:

1. **Merge similar SKUs** into one skill if they:
   - Share the same applicable_objects
   - Form a logical workflow together
   - Cover related aspects of the same concept

2. **Keep separate** if they:
   - Apply to different objects/scenarios
   - Have conflicting logic that can't be combined
   - Are independently complete procedures

3. **For each skill, output:**
   - A descriptive kebab-case name
   - SKILL.md content (frontmatter + body)
   - Optional references/ content if details exceed 500 lines

## SKUs to Convert
{skus_json}

## Output Format
Return a JSON array where each element represents one skill:
```json
[
  {{
    "skill_name": "kebab-case-skill-name",
    "source_sku_uuids": ["uuid1", "uuid2"],
    "skill_md": "---\\nname: ...\\ndescription: ...\\n---\\n\\n# Skill Title\\n\\n...",
    "references": {{
      "filename.md": "content..."
    }}
  }}
]
```

## Writing Guidelines
1. Write in {output_language}
2. Use imperative form ("Analyze the data" not "Analyzing the data")
3. Keep SKILL.md focused on WHEN to use and HOW to execute
4. Put detailed examples, formulas, and edge cases in references/
5. The description field is CRITICAL - it determines when Claude triggers this skill
6. Include specific trigger phrases/contexts in the description

## Quality Checklist
- [ ] Each skill has clear, actionable procedures
- [ ] Description covers both WHAT and WHEN
- [ ] Core logic is in SKILL.md, details in references/
- [ ] No generic filler content - only add what Claude needs
- [ ] Skill names are descriptive and follow kebab-case

Now convert the SKUs into skills. Output ONLY the JSON array, no explanation.'''


INDEX_GENERATION_PROMPT = '''You are creating a top-level index file for a collection of Claude Code Skills.

## Background
These skills were generated from a professional book: "{book_title}"
The skills help Claude assist users with domain-specific tasks from this book.

## Skills Summary
{skills_summary}

## Your Task
Create an index.md file that:
1. Introduces this skill collection
2. Lists all available skills with brief descriptions
3. Provides guidance on which skill to use for different tasks
4. Acts as a router - helping users/Claude navigate to the right skill

## Output Format
Return ONLY the markdown content for index.md. Structure it as:

```markdown
# [Collection Title]

[Brief introduction - what domain this covers, what users can accomplish]

## Available Skills

| Skill | Description | Use When |
|-------|-------------|----------|
| [skill-name](skill-name/SKILL.md) | Brief description | Trigger scenarios |
| ... | ... | ... |

## Quick Navigation

### [Category 1]
- **[skill-name]**: One-line description

### [Category 2]
- **[skill-name]**: One-line description

## How to Use
[Brief instructions on how to invoke these skills]
```

Write in {output_language}. Output ONLY the markdown content.'''


INDEX_UPDATE_PROMPT = '''You are updating an existing index.md file for a collection of Claude Code Skills.

## Background
These skills were generated from a professional book: "{book_title}"
The index.md serves as a router - helping users/Claude navigate to the right skill.

## Existing index.md
```markdown
{existing_index}
```

## Current Skills in Directory
{skills_summary}

## Your Task
Update the index.md to reflect the CURRENT state of skills:
1. **Add** any new skills that appear in "Current Skills" but not in the existing index
2. **Remove** any skills from the index that no longer exist in "Current Skills"
3. **Preserve** the overall structure, introduction, and any manual edits the user may have made
4. **Keep** the categorization logic but adjust categories if new skills don't fit existing ones

## Important Rules
- DO NOT rewrite the entire document - only update what's necessary
- PRESERVE any custom sections or notes the user may have added
- PRESERVE the introduction/title if it's already good
- Only UPDATE the skills table and navigation sections
- If a skill was manually added by user (not in generation_metadata), KEEP it

## Output Format
Return ONLY the updated markdown content for index.md.

Write in {output_language}. Output ONLY the markdown content.'''


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class GeneratedSkill:
    """Represents a generated skill ready for packaging."""
    skill_name: str
    source_sku_uuids: List[str]
    skill_md: str
    references: Dict[str, str] = field(default_factory=dict)


# ============================================================================
# Skill Generator
# ============================================================================

class SkillGenerator:
    """Converts SKUs to Claude Code Skills via GLM-4.7."""

    def __init__(self, skus_dir: str, output_dir: str = None):
        self.skus_dir = Path(skus_dir)
        self.output_dir = Path(output_dir) if output_dir else self.skus_dir.parent / "generated_skills"
        self.client = GLM4Client()

        # Load data
        self.skus = self._load_skus()
        self.buckets = self._load_buckets()

        # Results
        self.generated_skills: List[GeneratedSkill] = []

    def _load_skus(self) -> Dict[str, dict]:
        """Load all SKUs from the skus directory."""
        skus = {}
        skus_path = self.skus_dir / "skus"

        if not skus_path.exists():
            raise FileNotFoundError(f"SKUs directory not found: {skus_path}")

        for sku_file in skus_path.glob("*.json"):
            with open(sku_file, 'r', encoding='utf-8') as f:
                sku = json.load(f)
                uuid = sku.get("metadata", {}).get("uuid", sku_file.stem)
                skus[uuid] = sku

        print(f"[SkillGenerator] Loaded {len(skus)} SKUs")
        return skus

    def _load_buckets(self) -> Dict[str, List[str]]:
        """Load bucket assignments."""
        buckets_file = self.skus_dir / "buckets.json"

        if not buckets_file.exists():
            # If no buckets, treat all SKUs as one bucket
            print("[SkillGenerator] No buckets.json found, using single bucket")
            return {"bucket_0": list(self.skus.keys())}

        with open(buckets_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Convert bucket data to uuid lists
        buckets = {}
        buckets_data = data.get("buckets", [])
        
        # Handle both list and dict formats
        if isinstance(buckets_data, list):
            for bucket_info in buckets_data:
                bucket_id = bucket_info.get("bucket_id", f"bucket_{len(buckets)}")
                uuids = bucket_info.get("sku_uuids", [])
                if uuids:
                    buckets[bucket_id] = uuids
        elif isinstance(buckets_data, dict):
            for bucket_id, bucket_info in buckets_data.items():
                uuids = bucket_info.get("sku_uuids", [])
                if uuids:
                    buckets[bucket_id] = uuids

        print(f"[SkillGenerator] Loaded {len(buckets)} buckets")
        return buckets

    def _prepare_skus_for_prompt(self, sku_uuids: List[str]) -> str:
        """Prepare SKUs as JSON for the prompt."""
        skus_data = []
        for uuid in sku_uuids:
            if uuid in self.skus:
                sku = self.skus[uuid]
                # Extract key fields for the prompt
                skus_data.append({
                    "uuid": uuid,
                    "name": sku.get("metadata", {}).get("name", "Unknown"),
                    "applicable_objects": sku.get("context", {}).get("applicable_objects", []),
                    "prerequisites": sku.get("context", {}).get("prerequisites", []),
                    "constraints": sku.get("context", {}).get("constraints", []),
                    "trigger_condition": sku.get("trigger", {}).get("condition_logic", ""),
                    "logic_type": sku.get("core_logic", {}).get("logic_type", ""),
                    "execution_body": sku.get("core_logic", {}).get("execution_body", ""),
                    "variables": sku.get("core_logic", {}).get("variables", []),
                    "output_type": sku.get("output", {}).get("output_type", ""),
                    "result_template": sku.get("output", {}).get("result_template", ""),
                    "custom_attributes": sku.get("custom_attributes", {})
                })

        return json.dumps(skus_data, ensure_ascii=False, indent=2)

    def _parse_skills_response(self, response: str) -> List[GeneratedSkill]:
        """Parse LLM response into GeneratedSkill objects."""
        # Extract JSON from response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if not json_match:
            print(f"  [WARN] Could not find JSON array in response")
            return []

        try:
            skills_data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            print(f"  [WARN] Failed to parse JSON: {e}")
            print(f"  Response preview: {response[:500]}")
            return []

        skills = []
        for skill_data in skills_data:
            skill = GeneratedSkill(
                skill_name=skill_data.get("skill_name", "unnamed-skill"),
                source_sku_uuids=skill_data.get("source_sku_uuids", []),
                skill_md=skill_data.get("skill_md", ""),
                references=skill_data.get("references", {})
            )
            skills.append(skill)

        return skills

    def generate_for_bucket(self, bucket_id: str, sku_uuids: List[str]) -> List[GeneratedSkill]:
        """Generate skills for a single bucket."""
        print(f"\n[Bucket {bucket_id}] Processing {len(sku_uuids)} SKUs")

        # If bucket is too large, split into chunks
        all_skills = []
        chunks = [sku_uuids[i:i + MAX_SKUS_PER_LLM_CALL]
                  for i in range(0, len(sku_uuids), MAX_SKUS_PER_LLM_CALL)]

        for chunk_idx, chunk in enumerate(chunks):
            if len(chunks) > 1:
                print(f"  [Chunk {chunk_idx + 1}/{len(chunks)}] Processing {len(chunk)} SKUs")

            skus_json = self._prepare_skus_for_prompt(chunk)

            prompt = SKILL_GENERATION_PROMPT.format(
                sku_count=len(chunk),
                skus_json=skus_json,
                output_language=OUTPUT_LANGUAGE
            )

            messages = [{"role": "user", "content": prompt}]

            try:
                response = self.client.chat(messages, temperature=0.3, max_tokens=16000)
                skills = self._parse_skills_response(response)
                print(f"  -> Generated {len(skills)} skills")
                all_skills.extend(skills)
            except Exception as e:
                print(f"  [ERROR] Failed to generate skills: {e}")

        return all_skills

    def generate_all(self):
        """Generate skills for all buckets."""
        print(f"\n[SkillGenerator] Starting skill generation")
        print(f"[SkillGenerator] Output language: {OUTPUT_LANGUAGE}")
        print(f"[SkillGenerator] Total SKUs: {len(self.skus)}")
        print(f"[SkillGenerator] Total buckets: {len(self.buckets)}")

        for bucket_id, sku_uuids in self.buckets.items():
            skills = self.generate_for_bucket(bucket_id, sku_uuids)
            self.generated_skills.extend(skills)

        print(f"\n[SkillGenerator] Total skills generated: {len(self.generated_skills)}")

    def _scan_existing_skills(self) -> List[dict]:
        """Scan output directory for all existing skill folders."""
        skills_summary = []

        if not self.output_dir.exists():
            return skills_summary

        for item in self.output_dir.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                skill_md_path = item / "SKILL.md"
                with open(skill_md_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Extract description from frontmatter
                desc_match = re.search(r'description:\s*(.+?)(?:\n|---)', content, re.DOTALL)
                description = desc_match.group(1).strip() if desc_match else "No description"

                skills_summary.append({
                    "name": item.name,
                    "description": description[:200],
                    "path": str(item.relative_to(self.output_dir))
                })

        return skills_summary

    def generate_index(self) -> str:
        """Generate or update top-level index.md."""
        index_path = self.output_dir / "index.md"
        existing_index = None

        # Check if index.md already exists
        if index_path.exists():
            with open(index_path, 'r', encoding='utf-8') as f:
                existing_index = f.read()
            print("\n[SkillGenerator] Updating existing index.md")
        else:
            print("\n[SkillGenerator] Creating new index.md")

        # Scan ALL skills in output directory (includes manually added ones)
        skills_summary = self._scan_existing_skills()

        # Also include newly generated skills not yet written
        existing_names = {s["name"] for s in skills_summary}
        for skill in self.generated_skills:
            if skill.skill_name not in existing_names:
                desc_match = re.search(r'description:\s*(.+?)(?:\n|---)', skill.skill_md, re.DOTALL)
                description = desc_match.group(1).strip() if desc_match else "No description"
                skills_summary.append({
                    "name": skill.skill_name,
                    "description": description[:200],
                    "path": skill.skill_name
                })

        # Infer book title from output path
        book_title = self.skus_dir.parent.name.replace("_output", "").replace("_", " ").title()

        # Choose prompt based on whether index exists
        if existing_index:
            prompt = INDEX_UPDATE_PROMPT.format(
                book_title=book_title,
                existing_index=existing_index,
                skills_summary=json.dumps(skills_summary, ensure_ascii=False, indent=2),
                output_language=OUTPUT_LANGUAGE
            )
        else:
            prompt = INDEX_GENERATION_PROMPT.format(
                book_title=book_title,
                skills_summary=json.dumps(skills_summary, ensure_ascii=False, indent=2),
                output_language=OUTPUT_LANGUAGE
            )

        messages = [{"role": "user", "content": prompt}]

        try:
            index_content = self.client.chat(messages, temperature=0.3, max_tokens=4000)
            return index_content
        except Exception as e:
            print(f"  [ERROR] Failed to generate/update index: {e}")
            return self._generate_fallback_index()

    def _generate_fallback_index(self) -> str:
        """Generate a simple fallback index if LLM fails."""
        lines = [
            "# Generated Skills",
            "",
            "Skills generated from book content.",
            "",
            "## Available Skills",
            ""
        ]

        for skill in self.generated_skills:
            lines.append(f"- [{skill.skill_name}]({skill.skill_name}/SKILL.md)")

        return "\n".join(lines)

    def package_skills(self):
        """Package generated skills into folder structure."""
        print(f"\n[SkillGenerator] Packaging skills to: {self.output_dir}")

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Write each skill
        for skill in self.generated_skills:
            skill_dir = self.output_dir / skill.skill_name
            skill_dir.mkdir(exist_ok=True)

            # Write SKILL.md
            skill_md_path = skill_dir / "SKILL.md"
            with open(skill_md_path, 'w', encoding='utf-8') as f:
                f.write(skill.skill_md)
            print(f"  Created: {skill.skill_name}/SKILL.md")

            # Write references if any
            if skill.references:
                refs_dir = skill_dir / "references"
                refs_dir.mkdir(exist_ok=True)
                for filename, content in skill.references.items():
                    ref_path = refs_dir / filename
                    with open(ref_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"  Created: {skill.skill_name}/references/{filename}")

        # Generate and write index.md
        index_content = self.generate_index()
        index_path = self.output_dir / "index.md"
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index_content)
        print(f"  Created: index.md")

        # Write generation metadata
        metadata = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source_skus_dir": str(self.skus_dir),
            "total_skus": len(self.skus),
            "total_skills": len(self.generated_skills),
            "skills": [
                {
                    "name": s.skill_name,
                    "source_sku_uuids": s.source_sku_uuids,
                    "has_references": bool(s.references)
                }
                for s in self.generated_skills
            ]
        }

        metadata_path = self.output_dir / "generation_metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"  Created: generation_metadata.json")

        print(f"\n[SkillGenerator] Packaging complete!")
        print(f"  Total skills: {len(self.generated_skills)}")
        print(f"  Output: {self.output_dir}")


# ============================================================================
# Pipeline Functions
# ============================================================================

def run_skill_generation(skus_dir: str, output_dir: str = None):
    """Run the complete skill generation pipeline."""
    generator = SkillGenerator(skus_dir, output_dir)
    generator.generate_all()
    generator.package_skills()
    return generator


def update_index_only(skills_dir: str):
    """Update index.md for an existing skills directory.

    Use this when you've manually added/removed skills and want to
    refresh the index without regenerating all skills.
    """
    skills_path = Path(skills_dir)

    if not skills_path.exists():
        raise FileNotFoundError(f"Skills directory not found: {skills_path}")

    # Create a minimal generator just for index update
    # We need a dummy skus_dir, but we'll only use output_dir
    class IndexUpdater:
        def __init__(self, output_dir: Path):
            self.output_dir = output_dir
            self.skus_dir = output_dir  # Dummy, for book title inference
            self.generated_skills = []  # Empty - we scan existing skills
            self.client = GLM4Client()

        def _scan_existing_skills(self) -> List[dict]:
            skills_summary = []
            for item in self.output_dir.iterdir():
                if item.is_dir() and (item / "SKILL.md").exists():
                    skill_md_path = item / "SKILL.md"
                    with open(skill_md_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    desc_match = re.search(r'description:\s*(.+?)(?:\n|---)', content, re.DOTALL)
                    description = desc_match.group(1).strip() if desc_match else "No description"
                    skills_summary.append({
                        "name": item.name,
                        "description": description[:200],
                        "path": str(item.relative_to(self.output_dir))
                    })
            return skills_summary

    updater = IndexUpdater(skills_path)
    skills_summary = updater._scan_existing_skills()

    print(f"[IndexUpdater] Found {len(skills_summary)} skills in {skills_path}")

    # Check for existing index
    index_path = skills_path / "index.md"
    existing_index = None
    if index_path.exists():
        with open(index_path, 'r', encoding='utf-8') as f:
            existing_index = f.read()
        print("[IndexUpdater] Updating existing index.md")
    else:
        print("[IndexUpdater] Creating new index.md")

    # Infer book title from path
    book_title = skills_path.name.replace("_", " ").replace("-", " ").title()

    # Choose prompt
    if existing_index:
        prompt = INDEX_UPDATE_PROMPT.format(
            book_title=book_title,
            existing_index=existing_index,
            skills_summary=json.dumps(skills_summary, ensure_ascii=False, indent=2),
            output_language=OUTPUT_LANGUAGE
        )
    else:
        prompt = INDEX_GENERATION_PROMPT.format(
            book_title=book_title,
            skills_summary=json.dumps(skills_summary, ensure_ascii=False, indent=2),
            output_language=OUTPUT_LANGUAGE
        )

    messages = [{"role": "user", "content": prompt}]

    try:
        index_content = updater.client.chat(messages, temperature=0.3, max_tokens=4000)
    except Exception as e:
        print(f"[ERROR] Failed to generate index: {e}")
        # Fallback
        lines = ["# Skills Collection", "", "## Available Skills", ""]
        for s in skills_summary:
            lines.append(f"- [{s['name']}]({s['path']}/SKILL.md): {s['description'][:50]}...")
        index_content = "\n".join(lines)

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_content)

    print(f"[IndexUpdater] Updated: {index_path}")
    print(f"[IndexUpdater] Total skills indexed: {len(skills_summary)}")


# ============================================================================
# CLI
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Module 5: Convert SKUs to Claude Code Skills"
    )
    parser.add_argument(
        "skus_dir",
        help="Directory containing SKUs (with skus/ subfolder and buckets.json)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output directory for generated skills (default: ../generated_skills)"
    )
    parser.add_argument(
        "--update-index",
        action="store_true",
        help="Only update index.md for existing skills directory (skus_dir is treated as skills_dir)"
    )

    args = parser.parse_args()

    if args.update_index:
        # In update-index mode, skus_dir is actually the skills directory
        update_index_only(args.skus_dir)
    else:
        run_skill_generation(args.skus_dir, args.output)


if __name__ == "__main__":
    main()
