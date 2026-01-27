"""
Skill Chaining Engine - Orchestrate skill execution

This module provides the core engine for executing skills in sequence,
managing data flow between them, and handling errors.

The engine:
1. Loads spec.json to understand execution order
2. Loads skills from both book-specific and fixed pools
3. Executes skills in order, passing context between them
4. Logs all execution via AuditLogger
5. Returns results and final context

Usage:
    engine = SkillChainEngine(
        spec_path="app_spec.json",
        skills_dir="path/to/generated_skills",
        fixed_skills_dir="path/to/skills_fixed"
    )
    results = engine.execute()
"""

import os
import json
import time
import requests
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Callable
from dotenv import load_dotenv

from .context import ExecutionContext, ScopedContext

# Import audit logger (assuming it's in sibling module)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from audit import AuditLogger, LoggedExecution


# Load environment
load_dotenv()

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
GLM_RATE_LIMIT_SECONDS = float(os.getenv("GLM_RATE_LIMIT_SECONDS", "3.0"))


@dataclass
class SkillResult:
    """Result of a single skill execution."""
    skill_id: str
    success: bool
    outputs: Dict[str, Any]
    error: Optional[str] = None
    duration_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "success": self.success,
            "outputs": self.outputs,
            "error": self.error,
            "duration_ms": self.duration_ms
        }


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


class SkillChainEngine:
    """
    Engine for executing skills in sequence with shared context.

    The engine loads a spec.json and executes skills in the specified order,
    managing data flow between skills via the ExecutionContext.
    """

    def __init__(
        self,
        spec_path: str,
        skills_dir: str = None,
        fixed_skills_dir: str = None,
        output_dir: str = None
    ):
        """
        Initialize the chaining engine.

        Args:
            spec_path: Path to app spec.json
            skills_dir: Path to generated_skills directory
            fixed_skills_dir: Path to skills_fixed directory
            output_dir: Directory for outputs and logs
        """
        self.spec_path = Path(spec_path)
        self.skills_dir = Path(skills_dir) if skills_dir else None
        self.fixed_skills_dir = Path(fixed_skills_dir) if fixed_skills_dir else None
        self.output_dir = Path(output_dir) if output_dir else self.spec_path.parent / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load spec
        self.spec = self._load_spec()

        # Initialize context
        self.context = ExecutionContext()

        # Initialize audit logger
        app_name = self.spec.get("app", {}).get("name", "unnamed")
        self.audit = AuditLogger(
            output_dir=str(self.output_dir / "logs"),
            app_name=app_name,
            spec_file=str(self.spec_path)
        )

        # Load skills
        self.skills = self._load_skills()

        # LLM client (lazy init)
        self._llm_client = None

        # Execution state
        self.results: List[SkillResult] = []
        self._aborted = False

    @property
    def llm_client(self):
        if self._llm_client is None:
            self._llm_client = GLM4Client()
        return self._llm_client

    def _load_spec(self) -> dict:
        """Load the application spec."""
        if not self.spec_path.exists():
            raise FileNotFoundError(f"Spec not found: {self.spec_path}")

        with open(self.spec_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_skills(self) -> Dict[str, dict]:
        """Load all skills (book-specific and fixed)."""
        skills = {}

        # Load book-specific skills
        if self.skills_dir and self.skills_dir.exists():
            index_path = self.skills_dir / "index.md"
            if index_path.exists():
                # Parse skill directories
                for skill_dir in self.skills_dir.iterdir():
                    if skill_dir.is_dir():
                        skill_md = skill_dir / "SKILL.md"
                        if skill_md.exists():
                            skills[skill_dir.name] = {
                                "id": skill_dir.name,
                                "path": str(skill_md),
                                "source": "book",
                                "content": self._load_skill_content(skill_md)
                            }

        # Load fixed skills
        if self.fixed_skills_dir and self.fixed_skills_dir.exists():
            index_path = self.fixed_skills_dir / "index.json"
            if index_path.exists():
                with open(index_path, "r", encoding="utf-8") as f:
                    index = json.load(f)

                for skill_entry in index.get("skills", []):
                    skill_id = f"fixed:{skill_entry['id']}"
                    skill_path = self.fixed_skills_dir / skill_entry.get("path", "")

                    skills[skill_id] = {
                        "id": skill_id,
                        "name": skill_entry.get("name", ""),
                        "description": skill_entry.get("description", ""),
                        "capabilities": skill_entry.get("capabilities", []),
                        "path": str(skill_path) if skill_path.exists() else None,
                        "source": "fixed",
                        "content": self._load_skill_content(skill_path) if skill_path.exists() else ""
                    }

        return skills

    def _load_skill_content(self, path: Path) -> str:
        """Load skill SKILL.md content."""
        if not path.exists():
            return ""

        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _get_execution_order(self) -> List[str]:
        """Get the skill execution order from spec."""
        return self.spec.get("skills", {}).get("execution_order", [])

    def _execute_skill(self, skill_id: str) -> SkillResult:
        """
        Execute a single skill.

        This uses the LLM to interpret the skill's SKILL.md and apply it
        to the current context.

        Args:
            skill_id: ID of skill to execute

        Returns:
            SkillResult with outputs
        """
        start_time = time.time()

        skill = self.skills.get(skill_id)
        if not skill:
            return SkillResult(
                skill_id=skill_id,
                success=False,
                outputs={},
                error=f"Skill not found: {skill_id}"
            )

        # Create scoped context for this skill
        scoped_ctx = ScopedContext(self.context, skill_id)

        # Build prompt for skill execution
        skill_content = skill.get("content", "")
        current_context = self.context.to_dict()

        prompt = f"""You are executing a skill as part of an automated application.

SKILL DEFINITION:
{skill_content[:3000]}

CURRENT CONTEXT (data from previous skills):
{json.dumps(current_context, ensure_ascii=False, indent=2)[:2000]}

TASK:
Based on the skill definition above, determine what outputs this skill should produce
given the current context. If the skill requires input that isn't in the context,
note what's missing.

Respond in JSON format:
{{
    "can_execute": true/false,
    "missing_inputs": ["list of missing required inputs"],
    "outputs": {{
        "key": "value",
        ...
    }},
    "notes": "any relevant notes about execution"
}}

Only include realistic outputs based on what the skill is designed to do.
If this is a data processing skill and no input data is available, set can_execute to false."""

        try:
            # Log skill start
            self.audit.log_skill_start(skill_id, {"context_keys": list(current_context.keys())})

            # Execute via LLM
            response = self.llm_client.chat([{"role": "user", "content": prompt}])

            # Parse response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result_data = json.loads(json_match.group())
            else:
                result_data = {"can_execute": False, "error": "Could not parse LLM response"}

            duration_ms = (time.time() - start_time) * 1000

            if result_data.get("can_execute", True):
                # Update context with outputs
                outputs = result_data.get("outputs", {})
                for key, value in outputs.items():
                    self.context.set(key, value, skill_id)

                self.audit.log_skill_end(skill_id, outputs, success=True)

                return SkillResult(
                    skill_id=skill_id,
                    success=True,
                    outputs=outputs,
                    duration_ms=duration_ms
                )
            else:
                error_msg = result_data.get("notes", "Skill could not execute")
                missing = result_data.get("missing_inputs", [])
                if missing:
                    error_msg += f". Missing inputs: {missing}"

                self.audit.log_skill_end(skill_id, {}, success=False)

                return SkillResult(
                    skill_id=skill_id,
                    success=False,
                    outputs={},
                    error=error_msg,
                    duration_ms=duration_ms
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.audit.log_skill_error(skill_id, e)

            return SkillResult(
                skill_id=skill_id,
                success=False,
                outputs={},
                error=str(e),
                duration_ms=duration_ms
            )

    def execute(
        self,
        initial_context: Dict[str, Any] = None,
        stop_on_error: bool = False
    ) -> Dict[str, Any]:
        """
        Execute all skills in order.

        Args:
            initial_context: Initial context data (user inputs, etc.)
            stop_on_error: Whether to stop execution on first error

        Returns:
            Dictionary with results and final context
        """
        # Initialize context
        if initial_context:
            self.context.update(initial_context)
            self.audit.log_user_input("initial_context", initial_context)

        execution_order = self._get_execution_order()

        print(f"\nExecuting {len(execution_order)} skills...")
        print("=" * 50)

        for i, skill_id in enumerate(execution_order):
            if self._aborted:
                print(f"\n[ABORTED] Execution aborted by user")
                break

            print(f"\n[{i+1}/{len(execution_order)}] Executing: {skill_id}")

            result = self._execute_skill(skill_id)
            self.results.append(result)

            if result.success:
                print(f"  [OK] Outputs: {list(result.outputs.keys())}")
            else:
                print(f"  [FAILED] {result.error}")

                if stop_on_error:
                    print(f"\n[STOPPED] Execution stopped due to error")
                    break

        # Save audit log
        log_path = self.audit.save()
        print(f"\nAudit log saved to: {log_path}")

        # Print summary
        self.audit.print_summary()

        return {
            "results": [r.to_dict() for r in self.results],
            "final_context": self.context.to_dict(),
            "successful": sum(1 for r in self.results if r.success),
            "failed": sum(1 for r in self.results if not r.success),
            "total": len(self.results),
            "log_path": str(log_path)
        }

    def abort(self):
        """Abort execution after current skill completes."""
        self._aborted = True

    def add_skill_handler(self, skill_id: str, handler: Callable):
        """
        Register a custom handler for a specific skill.

        This allows Python code to be executed instead of LLM interpretation
        for certain skills (e.g., file I/O operations).

        Args:
            skill_id: Skill ID to handle
            handler: Callable(context: ExecutionContext) -> Dict[str, Any]
        """
        # This would be used for skills that need actual code execution
        # rather than LLM interpretation (e.g., PDF processing)
        pass  # TODO: Implement custom handlers


def run_from_spec(spec_path: str, **kwargs) -> dict:
    """
    Convenience function to run from a spec file.

    Args:
        spec_path: Path to spec.json
        **kwargs: Additional arguments for SkillChainEngine

    Returns:
        Execution results
    """
    engine = SkillChainEngine(spec_path, **kwargs)
    return engine.execute()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run skill chain from spec")
    parser.add_argument("spec", help="Path to spec.json")
    parser.add_argument("--skills-dir", help="Path to generated_skills")
    parser.add_argument("--fixed-skills-dir", help="Path to skills_fixed")
    parser.add_argument("--output-dir", help="Output directory")

    args = parser.parse_args()

    results = run_from_spec(
        args.spec,
        skills_dir=args.skills_dir,
        fixed_skills_dir=args.fixed_skills_dir,
        output_dir=args.output_dir
    )

    print(f"\n\nExecution complete!")
    print(f"Successful: {results['successful']}/{results['total']}")
