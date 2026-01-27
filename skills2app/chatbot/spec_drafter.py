"""
Spec Drafter Chatbot - Guide users to create application specifications

This chatbot:
1. Loads router.json to understand available skills and structure
2. Guides users through domain/skill selection with OPTIONS
3. CONFIRMS understanding at each step
4. Outputs structured JSON spec for app generation

Design for non-technical users:
- Always provide numbered options
- Use simple language
- Confirm before proceeding
- Break complex decisions into smaller steps
"""

import os
import json
import time
import requests
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Set
from datetime import datetime
from enum import Enum
from dotenv import load_dotenv

from . import prompts

# Import fixed skills loader
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from skills_fixed import load_fixed_skills, get_skill_by_id, format_skills_for_display

# Load .env from skills2app directory
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


# ============================================================================
# Configuration
# ============================================================================

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
GLM_RATE_LIMIT_SECONDS = float(os.getenv("GLM_RATE_LIMIT_SECONDS", "3.0"))
OUTPUT_LANGUAGE = os.getenv("OUTPUT_LANGUAGE", "English")


# ============================================================================
# Conversation State
# ============================================================================

class ConversationStage(Enum):
    WELCOME = "welcome"
    DOMAIN_SELECTION = "domain_selection"
    SKILL_BROWSING = "skill_browsing"
    SKILL_DETAILS = "skill_details"
    CAPABILITY_SELECTION = "capability_selection"
    COMPLETENESS_CHECK = "completeness_check"
    APP_DESCRIPTION = "app_description"
    CONFIRMATION = "confirmation"
    COMPLETE = "complete"


@dataclass
class ConversationState:
    """Tracks the current state of the conversation."""
    stage: ConversationStage = ConversationStage.WELCOME
    selected_domain: Optional[str] = None
    selected_skills: List[str] = field(default_factory=list)
    current_skill: Optional[str] = None
    app_name: str = ""
    main_goal: str = ""
    target_users: str = ""
    usage_frequency: str = ""
    history: List[Dict[str, str]] = field(default_factory=list)

    def add_message(self, role: str, content: str):
        self.history.append({"role": role, "content": content})


# ============================================================================
# GLM-4.7 Client
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

    def chat(self, messages: list, temperature: float = 0.3, max_tokens: int = 2000) -> str:
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
            timeout=60
        )
        response.raise_for_status()

        result = response.json()
        return result["choices"][0]["message"]["content"]


# ============================================================================
# Spec Drafter Chatbot
# ============================================================================

class SpecDrafter:
    """
    Interactive chatbot for drafting application specifications.

    Guides non-technical users through:
    1. Domain selection (book topics)
    2. Skill/capability selection
    3. Completeness validation
    4. App description
    5. Spec generation
    """

    def __init__(self, router_path: str, output_dir: str = None):
        """
        Initialize the spec drafter.

        Args:
            router_path: Path to router.json from pdf2skills
            output_dir: Directory to save generated specs
        """
        self.router_path = Path(router_path)
        self.output_dir = Path(output_dir) if output_dir else self.router_path.parent / "specs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load router
        self.router = self._load_router()

        # Initialize state
        self.state = ConversationState()

        # Language
        self.lang = OUTPUT_LANGUAGE

        # LLM client (lazy init)
        self._llm_client = None

        # Load fixed skills (universal skills available to all apps)
        self.fixed_skills = load_fixed_skills()

        # Build skill lookup (includes both book-specific and fixed skills)
        self.skill_info = self._build_skill_lookup()

    def _load_router(self) -> dict:
        """Load router.json."""
        if not self.router_path.exists():
            raise FileNotFoundError(f"Router not found: {self.router_path}")

        with open(self.router_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _build_skill_lookup(self) -> Dict[str, dict]:
        """Build a lookup dict for skill information (book-specific + fixed skills)."""
        lookup = {}

        # Add book-specific skills from router
        for domain in self.router.get("hierarchy", {}).get("domains", []):
            for skill_id in domain.get("skills", []):
                lookup[skill_id] = {
                    "domain": domain.get("name", ""),
                    "domain_id": domain.get("domain_id", ""),
                    "source": "book"
                }

            for topic in domain.get("topics", []):
                for skill_id in topic.get("skills", []):
                    lookup[skill_id] = {
                        "domain": domain.get("name", ""),
                        "topic": topic.get("name", ""),
                        "domain_id": domain.get("domain_id", ""),
                        "topic_id": topic.get("topic_id", ""),
                        "source": "book"
                    }

        # Add dependency info for book skills
        for node in self.router.get("dependency_graph", {}).get("nodes", []):
            skill_id = node.get("skill_id", "")
            if skill_id in lookup:
                lookup[skill_id]["prerequisites"] = node.get("prerequisites", [])
                lookup[skill_id]["co_required"] = node.get("co_required", [])
                lookup[skill_id]["enables"] = node.get("enables", [])

        # Add fixed skills (universal skills)
        for fixed_skill in self.fixed_skills:
            skill_id = f"fixed:{fixed_skill['id']}"
            lookup[skill_id] = {
                "name": fixed_skill.get("name", ""),
                "description": fixed_skill.get("description", ""),
                "capabilities": fixed_skill.get("capabilities", []),
                "category": fixed_skill.get("category", ""),
                "source": "fixed",
                "prerequisites": [],
                "co_required": [],
                "enables": []
            }

        return lookup

    @property
    def llm_client(self):
        """Lazy-init LLM client."""
        if self._llm_client is None:
            self._llm_client = GLM4Client()
        return self._llm_client

    def get_prompt(self, prompt_dict: dict) -> str:
        """Get prompt in current language."""
        return prompt_dict.get(self.lang, prompt_dict.get("English", ""))

    # =========================================================================
    # Message Formatting
    # =========================================================================

    def format_domains_list(self) -> str:
        """Format domains as numbered list, including fixed skills option."""
        domains = self.router.get("hierarchy", {}).get("domains", [])
        total_skills = self._count_all_skills()
        lines = []

        # Recommended: Use all skills
        if self.lang == "Chinese":
            lines.append("**推荐选项:**")
            lines.append(f"A. 使用全部技能 ({total_skills} 个技能) - 将整本书转化为应用 (推荐)")
            lines.append("")
            lines.append("**或选择特定领域:**")
        else:
            lines.append("**Recommended:**")
            lines.append(f"A. Use ALL Skills ({total_skills} skills) - Turn entire book into app (Recommended)")
            lines.append("")
            lines.append("**Or select specific domain:**")

        for i, domain in enumerate(domains, 1):
            name = domain.get("name", "Unknown")
            skill_count = len(domain.get("skills", []))
            topic_count = len(domain.get("topics", []))

            if topic_count > 0:
                lines.append(f"{i}. {name} ({topic_count} subtopics)")
            else:
                lines.append(f"{i}. {name} ({skill_count} capabilities)")

        # Fixed skills option
        lines.append("")
        if self.lang == "Chinese":
            lines.append("**通用技能 (可选):**")
            lines.append(f"F. 文档处理技能 (PDF, Excel, Word, PPT)")
        else:
            lines.append("**Universal Skills (Optional):**")
            lines.append(f"F. Document Processing Skills (PDF, Excel, Word, PPT)")

        return "\n".join(lines)

    def _count_all_skills(self) -> int:
        """Count total skills from all domains."""
        count = 0
        for domain in self.router.get("hierarchy", {}).get("domains", []):
            count += len(domain.get("skills", []))
            for topic in domain.get("topics", []):
                count += len(topic.get("skills", []))
        return count

    def get_all_book_skills(self) -> List[str]:
        """Get all skills from all domains (entire book)."""
        skills = []
        for domain in self.router.get("hierarchy", {}).get("domains", []):
            skills.extend(domain.get("skills", []))
            for topic in domain.get("topics", []):
                skills.extend(topic.get("skills", []))
        return skills

    def format_skills_list(self, skills: List[str], selected: List[str] = None) -> str:
        """Format skills as numbered list with selection markers."""
        selected = selected or []
        lines = []
        for i, skill_id in enumerate(skills, 1):
            marker = "[x]" if skill_id in selected else "[ ]"
            display_name = skill_id.replace("-", " ").title()
            lines.append(f"{i}. {marker} {display_name}")

        return "\n".join(lines)

    def get_domain_skills(self, domain_index: int) -> List[str]:
        """Get all skills for a domain (including from topics)."""
        domains = self.router.get("hierarchy", {}).get("domains", [])
        if domain_index < 0 or domain_index >= len(domains):
            return []

        domain = domains[domain_index]
        skills = list(domain.get("skills", []))

        for topic in domain.get("topics", []):
            skills.extend(topic.get("skills", []))

        return skills

    # =========================================================================
    # Completeness Checking
    # =========================================================================

    def check_completeness(self, selected: List[str]) -> Dict[str, Any]:
        """Check if selected skills are complete (no missing dependencies)."""
        missing = set()

        for skill_id in selected:
            info = self.skill_info.get(skill_id, {})

            # Check prerequisites
            for prereq in info.get("prerequisites", []):
                if prereq not in selected:
                    missing.add(prereq)

            # Check co_required
            for co_req in info.get("co_required", []):
                if co_req not in selected:
                    missing.add(co_req)

        # Also check completeness groups
        for group in self.router.get("completeness_groups", []):
            group_skills = set(group.get("skills", []))
            overlap = group_skills & set(selected)

            # If user selected some skills from a group, suggest the rest
            if overlap and overlap != group_skills:
                missing.update(group_skills - set(selected))

        return {
            "is_complete": len(missing) == 0,
            "missing": list(missing),
            "selected": selected
        }

    def get_recommended_order(self, skills: List[str]) -> List[str]:
        """Get recommended execution order for skills."""
        # Check if skills match a completeness group
        for group in self.router.get("completeness_groups", []):
            group_skills = set(group.get("skills", []))
            if set(skills) <= group_skills:
                order = group.get("recommended_order", [])
                return [s for s in order if s in skills]

        # Default: order by prerequisites
        ordered = []
        remaining = set(skills)

        while remaining:
            for skill in list(remaining):
                info = self.skill_info.get(skill, {})
                prereqs = set(info.get("prerequisites", []))

                # Add if all prerequisites are already ordered or not in our list
                if prereqs <= (set(ordered) | (prereqs - set(skills))):
                    ordered.append(skill)
                    remaining.remove(skill)
                    break
            else:
                # No progress - just add remaining
                ordered.extend(remaining)
                break

        return ordered

    # =========================================================================
    # Conversation Flow
    # =========================================================================

    def start(self) -> str:
        """Start the conversation with welcome message."""
        self.state = ConversationState()
        self.state.stage = ConversationStage.WELCOME

        book_name = self.router.get("metadata", {}).get("source_book", "the book")
        domains_list = self.format_domains_list()

        message = self.get_prompt(prompts.WELCOME_MESSAGE).format(
            book_name=book_name,
            domains_list=domains_list
        )

        self.state.add_message("assistant", message)
        return message

    def process_input(self, user_input: str) -> str:
        """Process user input and return response."""
        user_input = user_input.strip()
        self.state.add_message("user", user_input)

        # Handle special commands
        if user_input.lower() in ["help", "帮助"]:
            return self.get_prompt(prompts.HELP_MESSAGE)

        if user_input.lower() in ["quit", "exit", "退出"]:
            return "Goodbye! / 再见！"

        if user_input.lower() in ["back", "返回"]:
            return self._go_back()

        # Route based on current stage
        handlers = {
            ConversationStage.WELCOME: self._handle_domain_selection,
            ConversationStage.DOMAIN_SELECTION: self._handle_domain_selection,
            ConversationStage.SKILL_BROWSING: self._handle_skill_browsing,
            ConversationStage.SKILL_DETAILS: self._handle_skill_details,
            ConversationStage.CAPABILITY_SELECTION: self._handle_capability_selection,
            ConversationStage.COMPLETENESS_CHECK: self._handle_completeness_check,
            ConversationStage.APP_DESCRIPTION: self._handle_app_description,
            ConversationStage.CONFIRMATION: self._handle_confirmation,
        }

        handler = handlers.get(self.state.stage, self._handle_unknown)
        response = handler(user_input)

        self.state.add_message("assistant", response)
        return response

    def _go_back(self) -> str:
        """Go back to previous stage."""
        stage_order = [
            ConversationStage.WELCOME,
            ConversationStage.DOMAIN_SELECTION,
            ConversationStage.SKILL_BROWSING,
            ConversationStage.CAPABILITY_SELECTION,
            ConversationStage.COMPLETENESS_CHECK,
            ConversationStage.APP_DESCRIPTION,
            ConversationStage.CONFIRMATION,
        ]

        try:
            current_index = stage_order.index(self.state.stage)
            if current_index > 0:
                self.state.stage = stage_order[current_index - 1]
                return f"Going back... / 返回中...\n\n" + self._get_current_stage_prompt()
        except ValueError:
            pass

        return self.start()

    def _get_current_stage_prompt(self) -> str:
        """Get the prompt for current stage."""
        if self.state.stage == ConversationStage.WELCOME:
            return self.start()

        if self.state.stage == ConversationStage.DOMAIN_SELECTION:
            return self.start()

        if self.state.stage == ConversationStage.SKILL_BROWSING:
            # Handle fixed skills
            if self.state.selected_domain == "fixed_skills":
                return self._show_fixed_skills()

            domains = self.router.get("hierarchy", {}).get("domains", [])
            for i, domain in enumerate(domains):
                if domain.get("domain_id") == self.state.selected_domain:
                    return self._show_domain_skills(i)
            return self.start()

        return self.get_prompt(prompts.INVALID_INPUT)

    def _handle_unknown(self, user_input: str) -> str:
        """Handle unknown stage."""
        return self.start()

    # =========================================================================
    # Stage Handlers
    # =========================================================================

    def _handle_domain_selection(self, user_input: str) -> str:
        """Handle domain selection input."""
        domains = self.router.get("hierarchy", {}).get("domains", [])

        # Handle "A" for ALL skills (recommended)
        if user_input.upper() == "A":
            return self._select_all_skills()

        # Handle "F" for fixed skills
        if user_input.upper() == "F":
            self.state.selected_domain = "fixed_skills"
            self.state.stage = ConversationStage.SKILL_BROWSING
            return self._show_fixed_skills()

        # Try to parse as number
        try:
            index = int(user_input) - 1
            if 0 <= index < len(domains):
                self.state.selected_domain = domains[index].get("domain_id")
                self.state.stage = ConversationStage.SKILL_BROWSING
                return self._show_domain_skills(index)
        except ValueError:
            pass

        # Try to match by name or use LLM to interpret
        for i, domain in enumerate(domains):
            if user_input.lower() in domain.get("name", "").lower():
                self.state.selected_domain = domain.get("domain_id")
                self.state.stage = ConversationStage.SKILL_BROWSING
                return self._show_domain_skills(i)

        # Use LLM to suggest based on user's description
        return self._suggest_from_goal(user_input)

    def _select_all_skills(self) -> str:
        """Select all skills from the entire book."""
        # Get all book skills
        all_skills = self.get_all_book_skills()
        self.state.selected_skills = all_skills
        self.state.selected_domain = "all_domains"

        # Skip directly to app description
        self.state.stage = ConversationStage.APP_DESCRIPTION

        total = len(all_skills)

        if self.lang == "Chinese":
            return f"""## 已选择全部技能

已自动选择本书中的全部 **{total}** 个技能。

您的应用将包含本书涵盖的所有功能和知识。

---

现在，请简单描述您想要构建的应用：

**您想用这个应用做什么？**
(例如：'帮助分析客户信用风险' 或 '自动化贷款审批流程')

您的描述："""
        else:
            return f"""## All Skills Selected

Automatically selected all **{total}** skills from this book.

Your app will include all capabilities and knowledge covered in the book.

---

Now, please briefly describe the app you want to build:

**What do you want this app to do?**
(Example: 'Help analyze customer credit risk' or 'Automate loan approval process')

Your description:"""

    def _show_domain_skills(self, domain_index: int) -> str:
        """Show skills for selected domain."""
        domains = self.router.get("hierarchy", {}).get("domains", [])
        domain = domains[domain_index]

        domain_name = domain.get("name", "Unknown")
        skills = self.get_domain_skills(domain_index)
        skills_list = self.format_skills_list(skills, self.state.selected_skills)

        return self.get_prompt(prompts.DOMAIN_SELECTED).format(
            domain_name=domain_name,
            skills_list=skills_list
        )

    def _show_fixed_skills(self) -> str:
        """Show fixed/universal skills."""
        lines = []

        if self.lang == "Chinese":
            lines.append("## 通用技能 (文档处理)")
            lines.append("")
            lines.append("这些技能可用于任何应用，与专业领域无关：")
            lines.append("")
        else:
            lines.append("## Universal Skills (Document Processing)")
            lines.append("")
            lines.append("These skills are available for any app, regardless of domain:")
            lines.append("")

        # Group by category
        categories = {}
        for skill in self.fixed_skills:
            cat = skill.get("category", "other")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(skill)

        skill_index = 1
        self._fixed_skills_map = {}  # Map index to skill id

        for cat_id, cat_skills in categories.items():
            cat_name = cat_id.replace("_", " ").title()
            if self.lang == "Chinese":
                cat_names = {"document": "文档处理", "design": "设计", "development": "开发"}
                cat_name = cat_names.get(cat_id, cat_name)

            lines.append(f"**{cat_name}:**")

            for skill in cat_skills:
                skill_id = f"fixed:{skill['id']}"
                marker = "[x]" if skill_id in self.state.selected_skills else "[ ]"
                name = skill.get("name", skill["id"])
                desc = skill.get("description", "")[:60]
                if len(skill.get("description", "")) > 60:
                    desc += "..."

                lines.append(f"  {skill_index}. {marker} {name}")
                lines.append(f"      {desc}")

                self._fixed_skills_map[skill_index] = skill_id
                skill_index += 1

            lines.append("")

        # Options
        lines.append("---")
        if self.lang == "Chinese":
            lines.append("**选项:**")
            lines.append("- 输入数字查看技能详情")
            lines.append("- A: 添加所有已选技能并继续")
            lines.append("- B: 返回领域选择")
        else:
            lines.append("**Options:**")
            lines.append("- Enter a number to view skill details")
            lines.append("- A: Add selected skills and continue")
            lines.append("- B: Back to domain selection")

        return "\n".join(lines)

    def get_fixed_skills_list(self) -> List[str]:
        """Get list of all fixed skill IDs."""
        return [f"fixed:{s['id']}" for s in self.fixed_skills]

    def _handle_skill_browsing(self, user_input: str) -> str:
        """Handle skill browsing input."""
        # Check if browsing fixed skills
        if self.state.selected_domain == "fixed_skills":
            return self._handle_fixed_skills_browsing(user_input)

        domains = self.router.get("hierarchy", {}).get("domains", [])

        # Find current domain
        domain_index = None
        for i, domain in enumerate(domains):
            if domain.get("domain_id") == self.state.selected_domain:
                domain_index = i
                break

        if domain_index is None:
            return self.start()

        skills = self.get_domain_skills(domain_index)

        # Handle menu options
        if user_input == "1":
            self.state.stage = ConversationStage.CAPABILITY_SELECTION
            return self._show_capability_selection(skills)

        if user_input == "3":
            self.state.selected_domain = None
            self.state.stage = ConversationStage.DOMAIN_SELECTION
            return self.start()

        if user_input == "4":
            return self._suggest_from_goal_prompt()

        # Try to show skill details (option 2 or direct number)
        try:
            index = int(user_input) - 1
            if 0 <= index < len(skills):
                self.state.current_skill = skills[index]
                self.state.stage = ConversationStage.SKILL_DETAILS
                return self._show_skill_details(skills[index])
        except ValueError:
            pass

        return self.get_prompt(prompts.INVALID_INPUT)

    def _handle_fixed_skills_browsing(self, user_input: str) -> str:
        """Handle browsing of fixed/universal skills."""
        # Handle "A" - add selected and continue
        if user_input.upper() == "A":
            if self.state.selected_skills:
                self.state.stage = ConversationStage.COMPLETENESS_CHECK
                return self._show_completeness_check()
            else:
                if self.lang == "Chinese":
                    return "请至少选择一个技能。\n\n" + self._show_fixed_skills()
                return "Please select at least one skill.\n\n" + self._show_fixed_skills()

        # Handle "B" - back to domain selection
        if user_input.upper() == "B":
            self.state.selected_domain = None
            self.state.stage = ConversationStage.DOMAIN_SELECTION
            return self.start()

        # Try to parse as number for skill selection/details
        try:
            index = int(user_input)
            if hasattr(self, '_fixed_skills_map') and index in self._fixed_skills_map:
                skill_id = self._fixed_skills_map[index]

                # Toggle selection
                if skill_id in self.state.selected_skills:
                    self.state.selected_skills.remove(skill_id)
                else:
                    self.state.selected_skills.append(skill_id)

                return self._show_fixed_skills()
        except ValueError:
            pass

        return self.get_prompt(prompts.INVALID_INPUT)

    def _show_skill_details(self, skill_id: str) -> str:
        """Show details for a skill."""
        info = self.skill_info.get(skill_id, {})

        # Handle fixed skills differently
        if info.get("source") == "fixed":
            display_name = info.get("name", skill_id.replace("fixed:", "").replace("-", " ").title())
            description = info.get("description", "Universal skill")

            # Show capabilities for fixed skills
            capabilities = info.get("capabilities", [])
            caps_str = ", ".join(capabilities) if capabilities else "General purpose"

            if self.lang == "Chinese":
                return f"""## {display_name}

**类型:** 通用技能
**描述:** {description}
**功能:** {caps_str}

---
**选项:**
1. 添加此技能
2. 返回技能列表"""
            return f"""## {display_name}

**Type:** Universal Skill
**Description:** {description}
**Capabilities:** {caps_str}

---
**Options:**
1. Add this skill
2. Back to skill list"""

        # Book-specific skill
        display_name = skill_id.replace("-", " ").title()
        description = f"From {info.get('domain', 'Unknown')}"
        if info.get("topic"):
            description += f" > {info.get('topic')}"

        related = info.get("co_required", [])
        related_str = ", ".join([s.replace("-", " ").title() for s in related[:3]]) if related else "None"

        prereqs = info.get("prerequisites", [])
        prereqs_str = ", ".join([s.replace("-", " ").title() for s in prereqs]) if prereqs else "None"

        return self.get_prompt(prompts.SKILL_DETAILS).format(
            skill_name=display_name,
            description=description,
            related_skills=related_str,
            prerequisites=prereqs_str
        )

    def _handle_skill_details(self, user_input: str) -> str:
        """Handle skill details input."""
        skill_id = self.state.current_skill
        info = self.skill_info.get(skill_id, {})

        # Fixed skills have simpler options (1=Add, 2=Back)
        if info.get("source") == "fixed":
            if user_input == "1":
                if skill_id not in self.state.selected_skills:
                    self.state.selected_skills.append(skill_id)
                self.state.stage = ConversationStage.SKILL_BROWSING
                return self._show_fixed_skills()

            if user_input == "2":
                self.state.stage = ConversationStage.SKILL_BROWSING
                return self._show_fixed_skills()

            return self.get_prompt(prompts.INVALID_INPUT)

        # Book-specific skills have more options
        if user_input == "1":
            # Add just this skill
            if skill_id not in self.state.selected_skills:
                self.state.selected_skills.append(skill_id)
            self.state.stage = ConversationStage.SKILL_BROWSING
            return self._go_back()

        if user_input == "2":
            # Add skill and related
            if skill_id not in self.state.selected_skills:
                self.state.selected_skills.append(skill_id)

            for related in info.get("co_required", []):
                if related not in self.state.selected_skills:
                    self.state.selected_skills.append(related)

            self.state.stage = ConversationStage.SKILL_BROWSING
            return self._go_back()

        if user_input == "3":
            self.state.stage = ConversationStage.SKILL_BROWSING
            return self._go_back()

        # Handle question (option 4 or free text)
        return self._answer_skill_question(user_input)

    def _show_capability_selection(self, available_skills: List[str]) -> str:
        """Show capability selection screen."""
        selected_str = ", ".join([s.replace("-", " ").title() for s in self.state.selected_skills]) or "None"
        available_list = self.format_skills_list(available_skills, self.state.selected_skills)

        return self.get_prompt(prompts.SELECT_CAPABILITIES).format(
            selected_list=selected_str,
            available_list=available_list
        )

    def _handle_capability_selection(self, user_input: str) -> str:
        """Handle capability selection input."""
        domains = self.router.get("hierarchy", {}).get("domains", [])

        # Find current domain
        domain_index = None
        for i, domain in enumerate(domains):
            if domain.get("domain_id") == self.state.selected_domain:
                domain_index = i
                break

        skills = self.get_domain_skills(domain_index) if domain_index is not None else []

        if user_input == "2":
            # Remove a capability - show which to remove
            if self.state.selected_skills:
                return self._show_remove_selection()
            return self._show_capability_selection(skills)

        if user_input == "3":
            # Show recommended combination
            return self._show_recommended_combination()

        if user_input == "4":
            # Done selecting
            if self.state.selected_skills:
                self.state.stage = ConversationStage.COMPLETENESS_CHECK
                return self._show_completeness_check()
            else:
                if self.lang == "Chinese":
                    return "请至少选择一个功能。/ Please select at least one capability."
                return "Please select at least one capability."

        # Try to add by number
        try:
            index = int(user_input) - 1
            if 0 <= index < len(skills):
                skill_id = skills[index]
                if skill_id not in self.state.selected_skills:
                    self.state.selected_skills.append(skill_id)
                return self._show_capability_selection(skills)
        except ValueError:
            pass

        return self.get_prompt(prompts.INVALID_INPUT)

    def _show_remove_selection(self) -> str:
        """Show removal selection."""
        lines = ["Which capability do you want to remove? / 你想移除哪个功能？\n"]
        for i, skill in enumerate(self.state.selected_skills, 1):
            lines.append(f"{i}. {skill.replace('-', ' ').title()}")
        lines.append("\n0. Cancel / 取消")
        return "\n".join(lines)

    def _show_recommended_combination(self) -> str:
        """Show recommended skill combination."""
        # Find a completeness group that includes any selected skills
        for group in self.router.get("completeness_groups", []):
            group_skills = set(group.get("skills", []))
            if any(s in group_skills for s in self.state.selected_skills):
                name = group.get("name", "Recommended Combination")
                skills_list = self.format_skills_list(group.get("skills", []), self.state.selected_skills)

                if self.lang == "Chinese":
                    return f"推荐组合：**{name}**\n\n{skills_list}\n\n输入数字添加功能，或输入 '4' 继续"
                return f"Recommended combination: **{name}**\n\n{skills_list}\n\nEnter a number to add, or '4' to continue"

        if self.lang == "Chinese":
            return "暂无特定推荐。请继续选择您需要的功能。"
        return "No specific recommendation. Please continue selecting capabilities you need."

    def _show_completeness_check(self) -> str:
        """Show completeness check results."""
        result = self.check_completeness(self.state.selected_skills)

        selected_str = ", ".join([s.replace("-", " ").title() for s in self.state.selected_skills])

        if result["is_complete"]:
            completeness_message = self.get_prompt(prompts.COMPLETENESS_OK)
            recommendation = ""
        else:
            completeness_message = self.get_prompt(prompts.COMPLETENESS_MISSING)
            missing_str = ", ".join([s.replace("-", " ").title() for s in result["missing"]])
            recommendation = self.get_prompt(prompts.COMPLETENESS_RECOMMENDATION).format(
                missing_skills=missing_str
            )

        return self.get_prompt(prompts.COMPLETENESS_CHECK).format(
            selected_skills=selected_str,
            completeness_message=completeness_message,
            recommendation=recommendation
        )

    def _handle_completeness_check(self, user_input: str) -> str:
        """Handle completeness check input."""
        result = self.check_completeness(self.state.selected_skills)

        if user_input == "1":
            # Accept recommendation
            for skill in result.get("missing", []):
                if skill not in self.state.selected_skills:
                    self.state.selected_skills.append(skill)
            self.state.stage = ConversationStage.APP_DESCRIPTION
            return self._show_app_description()

        if user_input == "2":
            # Keep current selection
            self.state.stage = ConversationStage.APP_DESCRIPTION
            return self._show_app_description()

        if user_input == "3":
            # Explain recommendations
            return self._explain_recommendations(result.get("missing", []))

        return self.get_prompt(prompts.INVALID_INPUT)

    def _explain_recommendations(self, missing: List[str]) -> str:
        """Explain why skills are recommended."""
        explanations = []

        for skill in missing:
            info = self.skill_info.get(skill, {})
            display_name = skill.replace("-", " ").title()

            # Check if it's a prerequisite
            for selected in self.state.selected_skills:
                sel_info = self.skill_info.get(selected, {})
                if skill in sel_info.get("prerequisites", []):
                    if self.lang == "Chinese":
                        explanations.append(f"- **{display_name}**: 是 {selected.replace('-', ' ').title()} 的前置要求")
                    else:
                        explanations.append(f"- **{display_name}**: Required before {selected.replace('-', ' ').title()}")
                    break

                if skill in sel_info.get("co_required", []):
                    if self.lang == "Chinese":
                        explanations.append(f"- **{display_name}**: 与 {selected.replace('-', ' ').title()} 配合使用效果更好")
                    else:
                        explanations.append(f"- **{display_name}**: Works well with {selected.replace('-', ' ').title()}")
                    break
            else:
                if self.lang == "Chinese":
                    explanations.append(f"- **{display_name}**: 推荐用于完整的工作流程")
                else:
                    explanations.append(f"- **{display_name}**: Recommended for a complete workflow")

        result = "\n".join(explanations)
        result += "\n\n" + self._show_completeness_check()
        return result

    def _show_app_description(self) -> str:
        """Show app description questions."""
        selected_str = ", ".join([s.replace("-", " ").title() for s in self.state.selected_skills])
        return self.get_prompt(prompts.DESCRIBE_APP).format(selected_skills=selected_str)

    def _handle_app_description(self, user_input: str) -> str:
        """Handle app description input."""
        if user_input.lower() in ["skip", "跳过"]:
            user_input = "General purpose application"

        # Determine which question we're on based on state
        if not self.state.main_goal:
            self.state.main_goal = user_input
            return self.get_prompt(prompts.DESCRIBE_APP_USERS)

        if not self.state.target_users:
            self.state.target_users = user_input
            return self.get_prompt(prompts.DESCRIBE_APP_FREQUENCY)

        if not self.state.usage_frequency:
            freq_map = {"1": "Daily", "2": "Weekly", "3": "Monthly", "4": "As needed"}
            freq_map_cn = {"1": "每天", "2": "每周", "3": "每月", "4": "按需"}

            self.state.usage_frequency = freq_map.get(user_input, user_input)
            if self.lang == "Chinese":
                self.state.usage_frequency = freq_map_cn.get(user_input, user_input)

            # Generate app name from goal
            self.state.app_name = self._generate_app_name()

            self.state.stage = ConversationStage.CONFIRMATION
            return self._show_confirmation()

        return self.get_prompt(prompts.INVALID_INPUT)

    def _generate_app_name(self) -> str:
        """Generate an app name from the goal."""
        # Simple name generation - could use LLM for better names
        goal_words = self.state.main_goal.split()[:3]
        return "-".join(goal_words).lower().replace(",", "").replace(".", "") + "-app"

    def _show_confirmation(self) -> str:
        """Show confirmation screen."""
        # Separate book skills and fixed skills for display
        book_skills = [s for s in self.state.selected_skills if not s.startswith("fixed:")]
        fixed_skills = [s for s in self.state.selected_skills if s.startswith("fixed:")]

        capabilities_lines = []

        if book_skills:
            if self.lang == "Chinese":
                capabilities_lines.append("  **专业技能:**")
            else:
                capabilities_lines.append("  **Domain Skills:**")
            for s in book_skills:
                capabilities_lines.append(f"    - {s.replace('-', ' ').title()}")

        if fixed_skills:
            if self.lang == "Chinese":
                capabilities_lines.append("  **通用技能:**")
            else:
                capabilities_lines.append("  **Universal Skills:**")
            for s in fixed_skills:
                # Get the display name from skill info
                info = self.skill_info.get(s, {})
                display_name = info.get("name", s.replace("fixed:", "").replace("-", " ").title())
                capabilities_lines.append(f"    - {display_name}")

        capabilities_summary = "\n".join(capabilities_lines)

        ordered = self.get_recommended_order(self.state.selected_skills)
        execution_order_lines = []
        for i, s in enumerate(ordered, 1):
            if s.startswith("fixed:"):
                info = self.skill_info.get(s, {})
                display_name = info.get("name", s.replace("fixed:", "").replace("-", " ").title())
                execution_order_lines.append(f"  {i}. {display_name} (Universal)")
            else:
                execution_order_lines.append(f"  {i}. {s.replace('-', ' ').title()}")

        execution_order = "\n".join(execution_order_lines)

        return self.get_prompt(prompts.CONFIRM_SPEC).format(
            app_name=self.state.app_name,
            main_goal=self.state.main_goal,
            target_users=self.state.target_users,
            frequency=self.state.usage_frequency,
            capabilities_summary=capabilities_summary,
            execution_order=execution_order
        )

    def _handle_confirmation(self, user_input: str) -> str:
        """Handle confirmation input."""
        if user_input == "1":
            # Create spec
            spec_path = self._create_spec()
            self.state.stage = ConversationStage.COMPLETE
            return self.get_prompt(prompts.SPEC_CREATED).format(output_path=spec_path)

        if user_input == "2":
            # Make changes - go back to capability selection
            self.state.stage = ConversationStage.CAPABILITY_SELECTION
            return self._go_back()

        if user_input == "3":
            # Add more details - restart app description
            self.state.main_goal = ""
            self.state.target_users = ""
            self.state.usage_frequency = ""
            self.state.stage = ConversationStage.APP_DESCRIPTION
            return self._show_app_description()

        return self.get_prompt(prompts.INVALID_INPUT)

    def _create_spec(self) -> Path:
        """Create and save the specification."""
        ordered_skills = self.get_recommended_order(self.state.selected_skills)

        # Separate book skills and fixed skills
        book_skills = [s for s in self.state.selected_skills if not s.startswith("fixed:")]
        fixed_skills = [s for s in self.state.selected_skills if s.startswith("fixed:")]

        spec = {
            "metadata": {
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "language": self.lang,
                "router_source": str(self.router_path)
            },
            "app": {
                "name": self.state.app_name,
                "goal": self.state.main_goal,
                "target_users": self.state.target_users,
                "usage_frequency": self.state.usage_frequency
            },
            "skills": {
                "selected": self.state.selected_skills,
                "book_skills": book_skills,
                "fixed_skills": [s.replace("fixed:", "") for s in fixed_skills],
                "execution_order": ordered_skills,
                "skill_details": {
                    skill: self.skill_info.get(skill, {})
                    for skill in self.state.selected_skills
                }
            },
            "completeness": self.check_completeness(self.state.selected_skills)
        }

        # Save spec
        filename = f"{self.state.app_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        spec_path = self.output_dir / filename

        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)

        return spec_path

    # =========================================================================
    # LLM-Assisted Methods
    # =========================================================================

    def _suggest_from_goal(self, goal: str) -> str:
        """Use LLM to suggest skills based on user's goal."""
        # Build skills list
        all_skills = []
        for domain in self.router.get("hierarchy", {}).get("domains", []):
            for skill in domain.get("skills", []):
                all_skills.append(f"- {skill}: from {domain.get('name', 'Unknown')}")
            for topic in domain.get("topics", []):
                for skill in topic.get("skills", []):
                    all_skills.append(f"- {skill}: from {topic.get('name', 'Unknown')}")

        skills_list = "\n".join(all_skills[:50])  # Limit for context

        prompt = self.get_prompt(prompts.SUGGEST_SKILLS_FOR_GOAL).format(
            goal=goal,
            skills_list=skills_list
        )

        try:
            response = self.llm_client.chat([{"role": "user", "content": prompt}])
            result = json.loads(response.strip())

            suggested = result.get("suggested_skills", [])
            explanation = result.get("explanation", "")

            if suggested:
                # Add suggested skills
                for skill in suggested:
                    if skill not in self.state.selected_skills:
                        self.state.selected_skills.append(skill)

                if self.lang == "Chinese":
                    return f"根据你的描述，我建议这些功能：\n\n{explanation}\n\n已添加：{', '.join(suggested)}\n\n你想继续选择更多功能，还是进入下一步？\n1. 继续选择\n2. 进入下一步"
                return f"Based on your description, I suggest these capabilities:\n\n{explanation}\n\nAdded: {', '.join(suggested)}\n\nWould you like to select more, or move to the next step?\n1. Continue selecting\n2. Move to next step"
        except Exception:
            pass

        return self.get_prompt(prompts.INVALID_INPUT)

    def _suggest_from_goal_prompt(self) -> str:
        """Prompt user to describe their goal."""
        if self.lang == "Chinese":
            return "请描述你想要实现什么，我会推荐合适的功能。\n\n例如：'我想要分析财务报表' 或 '我需要检查合规性'\n\n你的描述："
        return "Please describe what you want to accomplish, and I'll suggest suitable capabilities.\n\nExample: 'I want to analyze financial reports' or 'I need to check compliance'\n\nYour description:"

    def _answer_skill_question(self, question: str) -> str:
        """Use LLM to answer a question about a skill."""
        skill_id = self.state.current_skill
        info = self.skill_info.get(skill_id, {})

        prompt = self.get_prompt(prompts.ANSWER_USER_QUESTION).format(
            question=question,
            current_skill=skill_id.replace("-", " ").title(),
            skill_info=json.dumps(info, ensure_ascii=False)
        )

        try:
            response = self.llm_client.chat([{"role": "user", "content": prompt}])
            return response + "\n\n" + self._show_skill_details(skill_id)
        except Exception:
            return self._show_skill_details(skill_id)


# ============================================================================
# Interactive Session
# ============================================================================

def run_interactive(router_path: str, output_dir: str = None):
    """Run an interactive chatbot session."""
    drafter = SpecDrafter(router_path, output_dir)

    print("\n" + "=" * 60)
    print(drafter.start())
    print("=" * 60 + "\n")

    while drafter.state.stage != ConversationStage.COMPLETE:
        try:
            user_input = input("\n> ").strip()
            if not user_input:
                continue

            response = drafter.process_input(user_input)
            print("\n" + response)

            if "Goodbye" in response or "再见" in response:
                break

        except KeyboardInterrupt:
            print("\n\nGoodbye! / 再见！")
            break
        except EOFError:
            break

    print("\n" + "=" * 60)
    print("Session ended. / 会话结束。")
    print("=" * 60 + "\n")
