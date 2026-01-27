"""
Fixed Skills - Universal I/O skills from Claude Official Repository

These skills are available to all apps regardless of the book domain.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional


def get_skills_dir() -> Path:
    """Get the skills_fixed directory path."""
    return Path(__file__).parent


def load_index() -> dict:
    """Load the skills index."""
    index_path = get_skills_dir() / "index.json"
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_fixed_skills() -> List[dict]:
    """Load all fixed skills metadata."""
    index = load_index()
    return index.get("skills", [])


def get_skill_by_id(skill_id: str) -> Optional[dict]:
    """Get a specific skill by ID."""
    for skill in load_fixed_skills():
        if skill.get("id") == skill_id:
            return skill
    return None


def get_skills_by_category(category: str) -> List[dict]:
    """Get all skills in a category."""
    return [s for s in load_fixed_skills() if s.get("category") == category]


def get_categories() -> dict:
    """Get all skill categories."""
    index = load_index()
    return index.get("categories", {})


def load_skill_content(skill_id: str) -> Optional[str]:
    """Load the SKILL.md content for a skill."""
    skill = get_skill_by_id(skill_id)
    if not skill:
        return None

    skill_path = get_skills_dir() / skill.get("path", "")
    if skill_path.exists():
        with open(skill_path, "r", encoding="utf-8") as f:
            return f.read()
    return None


def format_skills_for_display(skills: List[dict] = None, language: str = "English") -> str:
    """Format skills as a display string for chatbot."""
    if skills is None:
        skills = load_fixed_skills()

    lines = []
    if language == "Chinese":
        lines.append("**\u901a\u7528\u6280\u80fd (\u53ef\u7528\u4e8e\u6240\u6709\u5e94\u7528):**")  # 通用技能 (可用于所有应用):
    else:
        lines.append("**Universal Skills (available for all apps):**")

    for i, skill in enumerate(skills, 1):
        name = skill.get("name", skill.get("id", "Unknown"))
        desc = skill.get("description", "")[:80]
        if len(skill.get("description", "")) > 80:
            desc += "..."
        lines.append(f"  {i}. {name}: {desc}")

    return "\n".join(lines)


# Convenience exports
__all__ = [
    "get_skills_dir",
    "load_index",
    "load_fixed_skills",
    "get_skill_by_id",
    "get_skills_by_category",
    "get_categories",
    "load_skill_content",
    "format_skills_for_display",
]
