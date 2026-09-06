"""Structured metadata-only application logging."""

import logging

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Emit JSON events without request bodies, prompts, URLs or credentials."""
    logging.basicConfig(format="%(message)s", level=getattr(logging, level))
    for name in ("httpx", "httpcore", "chromadb", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
