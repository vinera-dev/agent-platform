from .celery import app as celery_app
from .logs import install_log_context

install_log_context()

__all__ = ["celery_app"]
