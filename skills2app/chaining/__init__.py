"""
Chaining Module - Skill execution orchestration

This module provides the core engine for executing skills in sequence,
managing data flow between them via shared context.

Components:
- ExecutionContext: Shared data store for passing data between skills
- ScopedContext: Skill-local context with namespacing
- SkillChainEngine: Main orchestration engine
- SkillResult: Result of a single skill execution

Usage:
    from chaining import SkillChainEngine, ExecutionContext

    # Create engine from spec
    engine = SkillChainEngine(
        spec_path="my_app_spec.json",
        skills_dir="path/to/skills",
        fixed_skills_dir="path/to/skills_fixed"
    )

    # Execute with initial context
    results = engine.execute(initial_context={
        "input_file": "/path/to/data.pdf"
    })

    # Check results
    print(f"Successful: {results['successful']}/{results['total']}")
    print(f"Final context: {results['final_context']}")
"""

from .context import ExecutionContext, ScopedContext
from .engine import SkillChainEngine, SkillResult, run_from_spec

__all__ = [
    "ExecutionContext",
    "ScopedContext",
    "SkillChainEngine",
    "SkillResult",
    "run_from_spec"
]
