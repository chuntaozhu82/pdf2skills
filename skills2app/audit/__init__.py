"""
Audit Module - Execution logging for compliance and debugging

This module provides comprehensive audit logging for skill execution:
- Track skill inputs/outputs
- Record execution duration
- Log errors and exceptions
- Generate compliance reports

Usage:
    from audit import AuditLogger, LoggedExecution

    logger = AuditLogger(output_dir="./logs", app_name="my-app")

    # Manual logging
    logger.log_skill_start("skill-1", {"input": "data"})
    result = execute_skill()
    logger.log_skill_end("skill-1", result)

    # Context manager (recommended)
    with LoggedExecution(logger, "skill-1", inputs={"x": 1}) as log:
        result = execute_skill()
        log.set_output(result)

    # Save log
    logger.save()
"""

from .logger import AuditLogger, LoggedExecution, LogEventType, LogEntry

__all__ = [
    "AuditLogger",
    "LoggedExecution",
    "LogEventType",
    "LogEntry"
]
