"""
Execution Context - Manage shared context between skills

This module provides a context manager for passing data between skills
during execution. Skills can read from and write to the shared context.

Usage:
    ctx = ExecutionContext()
    ctx.set("input_file", "/path/to/file.pdf")
    ctx.set("extracted_data", {"tables": [...], "text": "..."})

    # Later skills can access
    data = ctx.get("extracted_data")
"""

import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path


@dataclass
class ContextChange:
    """Record of a single context change."""
    action: str  # "set", "delete", "update"
    key: str
    timestamp: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    skill_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "key": self.key,
            "timestamp": self.timestamp,
            "old_value": self._serialize(self.old_value),
            "new_value": self._serialize(self.new_value),
            "skill_id": self.skill_id
        }

    def _serialize(self, value: Any) -> Any:
        """Serialize value for JSON storage."""
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool, list, dict)):
            return value
        if isinstance(value, Path):
            return str(value)
        return str(value)[:500]


class ExecutionContext:
    """
    Shared context for passing data between skills.

    Features:
    - Key-value store for skill data
    - History tracking for debugging
    - Scoped contexts (skill-local vs global)
    - Serialization for persistence
    """

    def __init__(self, initial_data: Dict[str, Any] = None):
        """
        Initialize execution context.

        Args:
            initial_data: Optional initial context data
        """
        self._data: Dict[str, Any] = initial_data or {}
        self._history: List[ContextChange] = []
        self._metadata: Dict[str, Any] = {
            "created_at": datetime.now().isoformat(),
            "total_changes": 0
        }

    def _now(self) -> str:
        """Get current timestamp."""
        return datetime.now().isoformat()

    def set(self, key: str, value: Any, skill_id: str = None):
        """
        Set a value in the context.

        Args:
            key: Context key
            value: Value to store
            skill_id: ID of skill making the change
        """
        old_value = self._data.get(key)

        change = ContextChange(
            action="set",
            key=key,
            timestamp=self._now(),
            old_value=old_value,
            new_value=value,
            skill_id=skill_id
        )
        self._history.append(change)
        self._metadata["total_changes"] += 1

        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the context.

        Args:
            key: Context key
            default: Default value if key not found

        Returns:
            The value or default
        """
        return self._data.get(key, default)

    def has(self, key: str) -> bool:
        """Check if key exists in context."""
        return key in self._data

    def delete(self, key: str, skill_id: str = None) -> bool:
        """
        Delete a key from context.

        Args:
            key: Key to delete
            skill_id: ID of skill making the change

        Returns:
            True if key was deleted, False if not found
        """
        if key not in self._data:
            return False

        old_value = self._data.pop(key)

        change = ContextChange(
            action="delete",
            key=key,
            timestamp=self._now(),
            old_value=old_value,
            skill_id=skill_id
        )
        self._history.append(change)
        self._metadata["total_changes"] += 1

        return True

    def update(self, data: Dict[str, Any], skill_id: str = None):
        """
        Update multiple values at once.

        Args:
            data: Dictionary of key-value pairs to update
            skill_id: ID of skill making the change
        """
        for key, value in data.items():
            self.set(key, value, skill_id)

    def keys(self) -> List[str]:
        """Get all context keys."""
        return list(self._data.keys())

    def items(self) -> List[tuple]:
        """Get all context items."""
        return list(self._data.items())

    def to_dict(self) -> dict:
        """Export context as dictionary."""
        return dict(self._data)

    def get_history(self, key: str = None) -> List[dict]:
        """
        Get change history.

        Args:
            key: Optional key to filter history

        Returns:
            List of changes
        """
        if key:
            return [c.to_dict() for c in self._history if c.key == key]
        return [c.to_dict() for c in self._history]

    def get_changes_by_skill(self, skill_id: str) -> List[dict]:
        """Get all changes made by a specific skill."""
        return [c.to_dict() for c in self._history if c.skill_id == skill_id]

    def clear(self, keep_history: bool = True):
        """
        Clear all context data.

        Args:
            keep_history: Whether to keep change history
        """
        self._data = {}
        if not keep_history:
            self._history = []
            self._metadata["total_changes"] = 0

    def save(self, path: Path) -> Path:
        """
        Save context to JSON file.

        Args:
            path: Path to save file

        Returns:
            Path to saved file
        """
        export = {
            "metadata": self._metadata,
            "data": self._serialize_for_export(self._data),
            "history": [c.to_dict() for c in self._history]
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(export, f, ensure_ascii=False, indent=2)

        return path

    def _serialize_for_export(self, data: Any) -> Any:
        """Serialize data for JSON export."""
        if data is None:
            return None
        if isinstance(data, (str, int, float, bool)):
            return data
        if isinstance(data, Path):
            return str(data)
        if isinstance(data, list):
            return [self._serialize_for_export(item) for item in data]
        if isinstance(data, dict):
            return {k: self._serialize_for_export(v) for k, v in data.items()}
        return str(data)

    @classmethod
    def load(cls, path: Path) -> "ExecutionContext":
        """
        Load context from JSON file.

        Args:
            path: Path to JSON file

        Returns:
            ExecutionContext instance
        """
        with open(path, "r", encoding="utf-8") as f:
            export = json.load(f)

        ctx = cls(initial_data=export.get("data", {}))
        ctx._metadata = export.get("metadata", ctx._metadata)

        # Restore history
        for change_dict in export.get("history", []):
            change = ContextChange(
                action=change_dict.get("action", "set"),
                key=change_dict.get("key", ""),
                timestamp=change_dict.get("timestamp", ""),
                old_value=change_dict.get("old_value"),
                new_value=change_dict.get("new_value"),
                skill_id=change_dict.get("skill_id")
            )
            ctx._history.append(change)

        return ctx

    def __repr__(self) -> str:
        return f"ExecutionContext(keys={list(self._data.keys())}, changes={len(self._history)})"


class ScopedContext:
    """
    A scoped view of the execution context for a specific skill.

    Provides isolation and namespacing for skill-local data while
    still allowing access to global context.
    """

    def __init__(
        self,
        parent: ExecutionContext,
        skill_id: str,
        namespace: str = None
    ):
        """
        Initialize scoped context.

        Args:
            parent: Parent execution context
            skill_id: ID of the skill using this context
            namespace: Optional namespace prefix for local keys
        """
        self._parent = parent
        self._skill_id = skill_id
        self._namespace = namespace or skill_id
        self._local: Dict[str, Any] = {}

    def _local_key(self, key: str) -> str:
        """Convert local key to namespaced key."""
        return f"{self._namespace}:{key}"

    def set_local(self, key: str, value: Any):
        """Set a skill-local value (namespaced)."""
        namespaced_key = self._local_key(key)
        self._parent.set(namespaced_key, value, self._skill_id)
        self._local[key] = value

    def get_local(self, key: str, default: Any = None) -> Any:
        """Get a skill-local value."""
        return self._local.get(key, default)

    def set_global(self, key: str, value: Any):
        """Set a global value (accessible by other skills)."""
        self._parent.set(key, value, self._skill_id)

    def get_global(self, key: str, default: Any = None) -> Any:
        """Get a global value."""
        return self._parent.get(key, default)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value, checking local first then global."""
        if key in self._local:
            return self._local[key]
        return self._parent.get(key, default)

    def export_outputs(self) -> Dict[str, Any]:
        """Export all local values as outputs."""
        return dict(self._local)
