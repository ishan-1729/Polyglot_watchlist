"""Explicit Project 1 public dependencies, checked by the interface contract tests.

Project 2 owns its authorization policy. Authentication, request telemetry and
portable workspace locks retain Project 1's public contracts.
"""

from watchlist.api import auth
from watchlist.observability import Observability, ObservabilityMiddleware
from watchlist.review.contracts import ReviewError
from watchlist.review.locking import create_lock_file, workspace_lock

__all__ = [
    "auth",
    "Observability",
    "ObservabilityMiddleware",
    "ReviewError",
    "create_lock_file",
    "workspace_lock",
]
