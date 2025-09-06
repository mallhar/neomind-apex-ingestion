"""Base integration abstract class."""

from abc import ABC, abstractmethod
from typing import Any, Tuple


class IntegrationException(Exception):
    """Base exception for integration errors."""

    def __init__(
        self, message: str, provider: str, operation: str | None = None
    ) -> None:
        """Initialize integration exception."""
        super().__init__(message)
        self.provider = provider
        self.operation = operation


class BaseIntegration(ABC):
    """Abstract base class for third-party integrations."""

    def __init__(self, access_token: str) -> None:
        """
        Initialize integration with access token.

        Args:
            access_token: OAuth access token
        """
        self.access_token = access_token

    @abstractmethod
    async def get_contacts(
        self, sync_token: str | None = None
    ) -> Tuple[list[dict[str, Any]], str | None]:
        """
        Fetch contacts from the service.

        Args:
            sync_token: Token for delta sync

        Returns:
            Tuple of (contacts list, next sync token)
        """
        pass

    @abstractmethod
    async def get_email_content(self, email_id: str) -> dict[str, Any]:
        """
        Fetch full content of a single email.

        Args:
            email_id: Email identifier

        Returns:
            Email data including body and metadata
        """
        pass

    @abstractmethod
    async def get_calendar_event(self, event_id: str) -> dict[str, Any]:
        """
        Fetch calendar event details.

        Args:
            event_id: Event identifier

        Returns:
            Event data including attendees and description
        """
        pass

    @abstractmethod
    async def subscribe_to_realtime_events(
        self, user_id: str, notification_url: str
    ) -> dict[str, Any]:
        """
        Set up real-time event subscription.

        Args:
            user_id: User's UUID
            notification_url: URL to receive notifications

        Returns:
            Subscription information
        """
        pass

    @abstractmethod
    async def renew_subscription(
        self, subscription_id: str, expiration_date: str
    ) -> dict[str, Any]:
        """
        Renew an existing subscription.

        Args:
            subscription_id: Subscription identifier
            expiration_date: New expiration date

        Returns:
            Updated subscription information
        """
        pass
