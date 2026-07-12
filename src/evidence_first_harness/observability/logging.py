"""Observability — structured logging and metrics for the harness.

Section 27 of the spec. Every workflow node emits start/completion time,
status, retry count, artifact IDs, token usage, and routing decisions.
"""

from __future__ import annotations

import structlog

# Configure structlog for JSON output in production, console in dev
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def log_node_start(node_name: str, run_id: str, **kwargs: object) -> None:
    """Log the start of a workflow node."""
    logger.info(
        "node_start",
        node=node_name,
        run_id=run_id,
        **kwargs,
    )


def log_node_complete(
    node_name: str,
    run_id: str,
    status: str,
    duration_ms: float,
    retry_count: int = 0,
    artifact_ids: list[str] | None = None,
    **kwargs: object,
) -> None:
    """Log the completion of a workflow node."""
    logger.info(
        "node_complete",
        node=node_name,
        run_id=run_id,
        status=status,
        duration_ms=duration_ms,
        retry_count=retry_count,
        artifact_ids=artifact_ids or [],
        **kwargs,
    )


def log_evidence_result(
    executor: str,
    run_id: str,
    status: str,
    duration_ms: float,
    **kwargs: object,
) -> None:
    """Log an evidence execution result."""
    logger.info(
        "evidence_result",
        executor=executor,
        run_id=run_id,
        status=status,
        duration_ms=duration_ms,
        **kwargs,
    )


def log_decision(
    run_id: str,
    decision: str,
    risk_tier: int,
    **kwargs: object,
) -> None:
    """Log a decision engine result."""
    logger.info(
        "decision",
        run_id=run_id,
        decision=decision,
        risk_tier=risk_tier,
        **kwargs,
    )
