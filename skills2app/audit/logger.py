"""
Audit Logger - Track all skill executions for compliance and debugging

This module provides comprehensive logging of skill execution for:
- Compliance tracking (who ran what, when, with what inputs/outputs)
- Debugging (trace execution flow, identify failures)
- Performance monitoring (duration, success rates)

Usage:
    logger = AuditLogger(output_dir="./logs")
    logger.log_skill_start("capital-ratio-calculation", {"tier1": 1000000})
    # ... skill executes ...
    logger.log_skill_end("capital-ratio-calculation", {"ratio": 0.20}, success=True)
    logger.save()
"""

import json
import os
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum


class LogEventType(Enum):
    """Types of audit log events."""
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SKILL_START = "skill_start"
    SKILL_END = "skill_end"
    SKILL_ERROR = "skill_error"
    CONTEXT_UPDATE = "context_update"
    USER_INPUT = "user_input"
    OUTPUT_GENERATED = "output_generated"


@dataclass
class LogEntry:
    """A single audit log entry."""
    event_type: LogEventType
    timestamp: str
    skill_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    success: Optional[bool] = None
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None

    def to_dict(self) -> dict:
        result = {
            "event": self.event_type.value,
            "timestamp": self.timestamp
        }
        if self.skill_id:
            result["skill_id"] = self.skill_id
        if self.data:
            result["data"] = self.data
        if self.success is not None:
            result["success"] = self.success
        if self.error_message:
            result["error_message"] = self.error_message
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        return result


class AuditLogger:
    """
    Comprehensive audit logger for skill execution tracking.

    Features:
    - Track skill start/end with inputs/outputs
    - Record errors and exceptions
    - Calculate execution duration
    - Generate summary statistics
    - Save to JSON for compliance
    """

    def __init__(
        self,
        output_dir: str,
        app_name: str = "unnamed-app",
        spec_file: str = None
    ):
        """
        Initialize the audit logger.

        Args:
            output_dir: Directory to save audit logs
            app_name: Name of the application being logged
            spec_file: Path to the spec.json that defines the app
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.app_name = app_name
        self.spec_file = spec_file

        # Session tracking
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_start = datetime.now()

        # Log storage
        self.entries: List[LogEntry] = []

        # Skill timing tracking
        self._skill_start_times: Dict[str, datetime] = {}

        # Statistics
        self._stats = {
            "total_skills": 0,
            "successful": 0,
            "failed": 0,
            "total_duration_ms": 0
        }

        # Log session start
        self._log_session_start()

    def _now(self) -> str:
        """Get current timestamp as ISO string."""
        return datetime.now().isoformat()

    def _log_session_start(self):
        """Log session start event."""
        entry = LogEntry(
            event_type=LogEventType.SESSION_START,
            timestamp=self._now(),
            data={
                "session_id": self.session_id,
                "app_name": self.app_name,
                "spec_file": self.spec_file
            }
        )
        self.entries.append(entry)

    def log_skill_start(self, skill_id: str, inputs: Dict[str, Any] = None):
        """
        Log the start of a skill execution.

        Args:
            skill_id: ID of the skill being executed
            inputs: Input data passed to the skill
        """
        self._skill_start_times[skill_id] = datetime.now()
        self._stats["total_skills"] += 1

        # Sanitize inputs (remove sensitive data if needed)
        safe_inputs = self._sanitize_data(inputs or {})

        entry = LogEntry(
            event_type=LogEventType.SKILL_START,
            timestamp=self._now(),
            skill_id=skill_id,
            data={"inputs": safe_inputs}
        )
        self.entries.append(entry)

    def log_skill_end(
        self,
        skill_id: str,
        outputs: Dict[str, Any] = None,
        success: bool = True
    ):
        """
        Log the end of a skill execution.

        Args:
            skill_id: ID of the skill that finished
            outputs: Output data from the skill
            success: Whether execution was successful
        """
        # Calculate duration
        duration_ms = None
        if skill_id in self._skill_start_times:
            start_time = self._skill_start_times.pop(skill_id)
            duration = datetime.now() - start_time
            duration_ms = duration.total_seconds() * 1000
            self._stats["total_duration_ms"] += duration_ms

        # Update stats
        if success:
            self._stats["successful"] += 1
        else:
            self._stats["failed"] += 1

        # Sanitize outputs
        safe_outputs = self._sanitize_data(outputs or {})

        entry = LogEntry(
            event_type=LogEventType.SKILL_END,
            timestamp=self._now(),
            skill_id=skill_id,
            data={"outputs": safe_outputs},
            success=success,
            duration_ms=duration_ms
        )
        self.entries.append(entry)

    def log_skill_error(
        self,
        skill_id: str,
        error: Exception,
        context: Dict[str, Any] = None
    ):
        """
        Log a skill execution error.

        Args:
            skill_id: ID of the skill that failed
            error: The exception that occurred
            context: Additional context about the error
        """
        # Calculate duration if we have start time
        duration_ms = None
        if skill_id in self._skill_start_times:
            start_time = self._skill_start_times.pop(skill_id)
            duration = datetime.now() - start_time
            duration_ms = duration.total_seconds() * 1000
            self._stats["total_duration_ms"] += duration_ms

        self._stats["failed"] += 1

        entry = LogEntry(
            event_type=LogEventType.SKILL_ERROR,
            timestamp=self._now(),
            skill_id=skill_id,
            data={"context": self._sanitize_data(context or {})},
            success=False,
            error_message=str(error),
            duration_ms=duration_ms
        )
        self.entries.append(entry)

    def log_context_update(self, key: str, value: Any, skill_id: str = None):
        """
        Log a context update (data passing between skills).

        Args:
            key: Context key being updated
            value: New value
            skill_id: Skill that made the update (if any)
        """
        entry = LogEntry(
            event_type=LogEventType.CONTEXT_UPDATE,
            timestamp=self._now(),
            skill_id=skill_id,
            data={"key": key, "value": self._sanitize_data(value)}
        )
        self.entries.append(entry)

    def log_user_input(self, input_type: str, data: Any):
        """
        Log user input to the application.

        Args:
            input_type: Type of input (file, text, selection, etc.)
            data: Input data (sanitized)
        """
        entry = LogEntry(
            event_type=LogEventType.USER_INPUT,
            timestamp=self._now(),
            data={"input_type": input_type, "data": self._sanitize_data(data)}
        )
        self.entries.append(entry)

    def log_output(self, output_type: str, data: Any, skill_id: str = None):
        """
        Log generated output.

        Args:
            output_type: Type of output (file, report, etc.)
            data: Output data/metadata
            skill_id: Skill that generated the output
        """
        entry = LogEntry(
            event_type=LogEventType.OUTPUT_GENERATED,
            timestamp=self._now(),
            skill_id=skill_id,
            data={"output_type": output_type, "data": self._sanitize_data(data)}
        )
        self.entries.append(entry)

    def _sanitize_data(self, data: Any, max_depth: int = 3) -> Any:
        """
        Sanitize data for logging (remove sensitive info, truncate large values).

        Args:
            data: Data to sanitize
            max_depth: Maximum nesting depth to preserve

        Returns:
            Sanitized data safe for logging
        """
        if max_depth <= 0:
            return "<truncated>"

        if data is None:
            return None

        if isinstance(data, (str, int, float, bool)):
            # Truncate long strings
            if isinstance(data, str) and len(data) > 1000:
                return data[:1000] + "...<truncated>"
            return data

        if isinstance(data, (list, tuple)):
            if len(data) > 100:
                return [self._sanitize_data(item, max_depth - 1) for item in data[:100]] + ["...<truncated>"]
            return [self._sanitize_data(item, max_depth - 1) for item in data]

        if isinstance(data, dict):
            # Check for sensitive keys
            sensitive_keys = {"password", "secret", "token", "key", "credential", "auth"}
            result = {}
            for k, v in data.items():
                if any(s in k.lower() for s in sensitive_keys):
                    result[k] = "<redacted>"
                else:
                    result[k] = self._sanitize_data(v, max_depth - 1)
            return result

        # For other types, convert to string
        return str(data)[:500]

    def get_summary(self) -> dict:
        """Get execution summary statistics."""
        session_duration = datetime.now() - self.session_start

        return {
            "session_id": self.session_id,
            "app_name": self.app_name,
            "total_skills_executed": self._stats["total_skills"],
            "successful": self._stats["successful"],
            "failed": self._stats["failed"],
            "success_rate": (
                self._stats["successful"] / self._stats["total_skills"]
                if self._stats["total_skills"] > 0 else 0
            ),
            "total_skill_duration_ms": self._stats["total_duration_ms"],
            "session_duration_seconds": session_duration.total_seconds()
        }

    def save(self, filename: str = None) -> Path:
        """
        Save the audit log to a JSON file.

        Args:
            filename: Custom filename (default: audit_{session_id}.json)

        Returns:
            Path to saved log file
        """
        # Log session end
        session_end = LogEntry(
            event_type=LogEventType.SESSION_END,
            timestamp=self._now(),
            data=self.get_summary()
        )
        self.entries.append(session_end)

        # Build full log structure
        log_data = {
            "metadata": {
                "app_name": self.app_name,
                "spec_file": self.spec_file,
                "session_id": self.session_id,
                "started_at": self.session_start.isoformat(),
                "completed_at": datetime.now().isoformat()
            },
            "entries": [e.to_dict() for e in self.entries],
            "summary": self.get_summary()
        }

        # Save to file
        if filename is None:
            filename = f"audit_{self.session_id}.json"

        log_path = self.output_dir / filename

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)

        return log_path

    def print_summary(self):
        """Print a human-readable summary to stdout."""
        summary = self.get_summary()

        print("\n" + "=" * 50)
        print("Execution Summary")
        print("=" * 50)
        print(f"App: {summary['app_name']}")
        print(f"Session: {summary['session_id']}")
        print(f"Skills executed: {summary['total_skills_executed']}")
        print(f"  Successful: {summary['successful']}")
        print(f"  Failed: {summary['failed']}")
        print(f"  Success rate: {summary['success_rate']:.1%}")
        print(f"Total skill time: {summary['total_skill_duration_ms']:.0f}ms")
        print(f"Session duration: {summary['session_duration_seconds']:.1f}s")
        print("=" * 50)


# Convenience context manager
class LoggedExecution:
    """
    Context manager for logging skill execution.

    Usage:
        with LoggedExecution(logger, "my-skill", inputs={"x": 1}) as log:
            result = my_skill()
            log.set_output(result)
    """

    def __init__(
        self,
        logger: AuditLogger,
        skill_id: str,
        inputs: Dict[str, Any] = None
    ):
        self.logger = logger
        self.skill_id = skill_id
        self.inputs = inputs
        self.outputs = None
        self.success = True
        self.error = None

    def __enter__(self):
        self.logger.log_skill_start(self.skill_id, self.inputs)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.logger.log_skill_error(self.skill_id, exc_val)
            return False  # Re-raise exception

        self.logger.log_skill_end(self.skill_id, self.outputs, self.success)
        return False

    def set_output(self, outputs: Dict[str, Any]):
        """Set the outputs to be logged."""
        self.outputs = outputs

    def set_failed(self):
        """Mark this execution as failed."""
        self.success = False
