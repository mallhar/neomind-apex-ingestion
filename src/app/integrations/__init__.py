"""Integration modules for external services."""

from .base import BaseIntegration, IntegrationException
from .google import GoogleWorkspaceIntegration
from .microsoft import Microsoft365Integration

__all__ = [
    "BaseIntegration",
    "GoogleWorkspaceIntegration",
    "IntegrationException",
    "Microsoft365Integration",
]
