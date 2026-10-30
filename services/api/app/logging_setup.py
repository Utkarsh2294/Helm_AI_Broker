"""Operation metadata only: request queries, bodies, cookies and source text are never logged."""

import logging
import structlog


def configure_logging():
    # Uvicorn's default access log includes query strings, which can contain client names.
    logging.getLogger("uvicorn.access").disabled = True
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
