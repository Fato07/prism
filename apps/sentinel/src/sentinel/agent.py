"""Main sentinel agent loop."""

import structlog

logger = structlog.get_logger()


async def validate_trace(trace_uri: str, trace_hash: bytes) -> None:
    """Validate a trader's reasoning trace adversarially."""
    logger.info("validation_start", trace_uri=trace_uri)
    # TODO: Phase 0 Day 3 - implement adversarial validation
    raise NotImplementedError("Validation not yet implemented")
