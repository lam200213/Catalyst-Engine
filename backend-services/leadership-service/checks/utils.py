# backend-services/leadership-service/checks/utils.py
import logging

logger = logging.getLogger(__name__)

def failed_check(metric, message, **kwargs):
    """A consistent structure for failure responses."""
    logger.warning(f"Check failed for metric '{metric}': {message} | Details: {kwargs}")
    return {metric: {"pass": False, "message": message, **kwargs}}