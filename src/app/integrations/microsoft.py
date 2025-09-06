"""Microsoft 365 integration implementation."""

import logging
from datetime import datetime, timedelta
from typing import Any, Tuple

import httpx

from app.core.security import generate_client_state
from app.integrations.base import BaseIntegration, IntegrationException

logger = logging.getLogger(__name__)


class Microsoft365Integration(BaseIntegration):
    """Microsoft Graph API integration."""

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, access_token: str) -> None:
        """
        Initialize Microsoft 365 integration.

        Args:
            access_token: OAuth access token
        """
        super().__init__(access_token)
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def get_contacts(
        self, sync_token: str | None = None
    ) -> Tuple[list[dict[str, Any]], str | None]:
        """
        Fetch contacts from Microsoft Graph.

        Args:
            sync_token: Delta token for incremental sync

        Returns:
            Tuple of (contacts list, next sync token)
        """
        try:
            contacts = []
            delta_link = None

            # Build initial URL
            if sync_token:
                url = f"{self.GRAPH_BASE_URL}/me/contacts/delta?$deltatoken={sync_token}"
            else:
                url = f"{self.GRAPH_BASE_URL}/me/contacts?$top=100"

            async with httpx.AsyncClient() as client:
                while url:
                    response = await client.get(url, headers=self.headers)
                    response.raise_for_status()
                    data = response.json()

                    # Process contacts
                    for contact in data.get("value", []):
                        contact_data = self._parse_microsoft_contact(contact)
                        if contact_data:
                            contacts.append(contact_data)

                    # Check for next page or delta link
                    url = data.get("@odata.nextLink")
                    if not url:
                        delta_link = data.get("@odata.deltaLink")
                        break

            # Extract delta token from delta link
            next_sync_token = None
            if delta_link:
                # Parse delta token from URL
                import urllib.parse

                parsed = urllib.parse.urlparse(delta_link)
                params = urllib.parse.parse_qs(parsed.query)
                next_sync_token = params.get("$deltatoken", [None])[0]

            return contacts, next_sync_token

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error fetching Microsoft contacts: {e.response.status_code}"
            )
            raise IntegrationException(
                f"Failed to fetch contacts: HTTP {e.response.status_code}",
                provider="microsoft_365",
                operation="get_contacts",
            )
        except Exception as e:
            logger.error(f"Failed to fetch Microsoft contacts: {str(e)}")
            raise IntegrationException(
                f"Failed to fetch contacts: {str(e)}",
                provider="microsoft_365",
                operation="get_contacts",
            )

    def _parse_microsoft_contact(
        self, contact: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Parse Microsoft contact data."""
        contact_data = {
            "id": contact.get("id"),
            "name": contact.get("displayName"),
            "identifiers": [],
        }

        # Extract emails
        for email in contact.get("emailAddresses", []):
            if email.get("address"):
                contact_data["identifiers"].append(
                    {"type": "email", "value": email["address"]}
                )

        # Extract phone numbers
        for phone_type in ["businessPhones", "homePhones", "mobilePhone"]:
            phones = contact.get(phone_type)
            if isinstance(phones, list):
                for phone in phones:
                    if phone:
                        contact_data["identifiers"].append(
                            {"type": "phone", "value": phone}
                        )
            elif phones:  # mobilePhone is a string
                contact_data["identifiers"].append(
                    {"type": "phone", "value": phones}
                )

        # Only return if we have at least one identifier
        return contact_data if contact_data["identifiers"] else None

    async def get_email_content(self, email_id: str) -> dict[str, Any]:
        """
        Fetch email content from Microsoft Graph.

        Args:
            email_id: Message ID

        Returns:
            Email data including body and metadata
        """
        try:
            url = f"{self.GRAPH_BASE_URL}/me/messages/{email_id}"

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                message = response.json()

            recepients = [
                r.get("emailAddress", {}).get("address")
                for r in message.get("toRecipients", [])
            ]
            recepients.extend(
                [
                    r.get("emailAddress", {}).get("address")
                    for r in message.get("ccRecipients", [])
                ]
            )
            recepients.extend(
                [
                    r.get("emailAddress", {}).get("address")
                    for r in message.get("bccRecipients", [])
                ]
            )

            return {
                "id": message["id"],
                "conversationId": message.get("conversationId"),
                "from": message.get("from", {})
                .get("emailAddress", {})
                .get("address"),
                "to": recepients,
                "subject": message.get("subject"),
                "date": message.get("receivedDateTime"),
                "content": message.get("body", {}).get("content"),
                "contentType": message.get("body", {}).get("contentType"),
                # "contentPreview": message.get("bodyPreview"),
                "importance": message.get("importance"),
                "isDraft": message.get("isDraft"),
                "isRead": message.get("isRead"),
                "hasAttachments": message.get("hasAttachments"),
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error fetching email: {e.response.status_code}"
            )
            raise IntegrationException(
                f"Failed to fetch email: HTTP {e.response.status_code}",
                provider="microsoft_365",
                operation="get_email_content",
            )
        except Exception as e:
            logger.error(f"Failed to fetch email: {str(e)}")
            raise IntegrationException(
                f"Failed to fetch email: {str(e)}",
                provider="microsoft_365",
                operation="get_email_content",
            )

    async def get_calendar_event(self, event_id: str) -> dict[str, Any]:
        """
        Fetch calendar event from Microsoft Graph.

        Args:
            event_id: Event ID

        Returns:
            Event data
        """
        try:
            url = f"{self.GRAPH_BASE_URL}/me/events/{event_id}"

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                event = response.json()

            return {
                "id": event["id"],
                "summary": event.get("subject"),
                "description": event.get("body", {}).get("content"),
                "location": event.get("location", {}).get("displayName"),
                "start": event.get("start"),
                "end": event.get("end"),
                "attendees": [
                    a.get("emailAddress", {}).get("address")
                    for a in event.get("attendees", [])
                ],
                "organizer": event.get("organizer", {})
                .get("emailAddress", {})
                .get("address"),
                "isOrganizer": event.get("isOrganizer"),
                "content": event.get("body", {}).get("content"),
                "contentType": event.get("body", {}).get("contentType"),
                # "contentPreview": message.get("bodyPreview"),
                "isAllDay": event.get("isAllDay"),
                "isCancelled": event.get("isCancelled"),
                "isRecurring": event.get("recurrence") is not None,
                "isDraft": event.get("isDraft"),
                "importance": event.get("importance"),
                "sensitivity": event.get("sensitivity"),
                "recurrence": event.get("recurrence"),
                "isOnlineMeeting": event.get("isOnlineMeeting"),
                "response": event.get("responseStatus", {}).get("response"),
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error fetching event: {e.response.status_code}"
            )
            raise IntegrationException(
                f"Failed to fetch event: HTTP {e.response.status_code}",
                provider="microsoft_365",
                operation="get_calendar_event",
            )
        except Exception as e:
            logger.error(f"Failed to fetch event: {str(e)}")
            raise IntegrationException(
                f"Failed to fetch event: {str(e)}",
                provider="microsoft_365",
                operation="get_calendar_event",
            )

    async def subscribe_to_realtime_events(
        self, user_id: str, notification_url: str
    ) -> dict[str, Any]:
        """
        Create Microsoft Graph webhook subscriptions.

        Args:
            user_id: User's UUID
            notification_url: URL to receive notifications

        Returns:
            Subscription information
        """
        try:
            subscriptions = {}

            # Generate client state for validation
            client_state = generate_client_state()

            # Calculate expiration (max 3 days for messages)
            expiration = (
                datetime.utcnow() + timedelta(days=3)
            ).isoformat() + "Z"

            async with httpx.AsyncClient() as client:
                # Subscribe to email messages
                email_sub = await self._create_subscription(
                    client,
                    resource="/me/messages",
                    change_types=["created", "updated"],
                    notification_url=notification_url,
                    client_state=client_state,
                    expiration=expiration,
                )
                subscriptions["email"] = email_sub

                # Subscribe to calendar events
                calendar_sub = await self._create_subscription(
                    client,
                    resource="/me/events",
                    change_types=["created", "updated", "deleted"],
                    notification_url=notification_url,
                    client_state=client_state,
                    expiration=expiration,
                )
                subscriptions["calendar"] = calendar_sub

            return subscriptions

        except Exception as e:
            logger.error(f"Failed to create subscriptions: {str(e)}")
            raise IntegrationException(
                f"Failed to subscribe: {str(e)}",
                provider="microsoft_365",
                operation="subscribe_to_realtime_events",
            )

    async def _create_subscription(
        self,
        client: httpx.AsyncClient,
        resource: str,
        change_types: list[str],
        notification_url: str,
        client_state: str,
        expiration: str,
    ) -> dict[str, Any]:
        """Create a single Microsoft Graph subscription."""
        url = f"{self.GRAPH_BASE_URL}/subscriptions"

        body = {
            "changeType": ",".join(change_types),
            "notificationUrl": notification_url,
            "resource": resource,
            "expirationDateTime": expiration,
            "clientState": client_state,
            "latestSupportedTlsVersion": "v1_2",
        }

        response = await client.post(url, headers=self.headers, json=body)
        response.raise_for_status()

        subscription = response.json()

        # Store client state for validation
        # This would be stored in the database
        return {
            "id": subscription["id"],
            "resource": subscription["resource"],
            "expirationDateTime": subscription["expirationDateTime"],
            "clientState": client_state,  # Store for validation
        }

    async def renew_subscription(
        self, subscription_id: str, expiration_date: str
    ) -> dict[str, Any]:
        """
        Renew Microsoft Graph subscription.

        Args:
            subscription_id: Subscription ID
            expiration_date: New expiration date

        Returns:
            Updated subscription information
        """
        try:
            url = f"{self.GRAPH_BASE_URL}/subscriptions/{subscription_id}"

            body = {"expirationDateTime": expiration_date}

            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    url, headers=self.headers, json=body
                )
                response.raise_for_status()

                return response.json()

        except Exception as e:
            logger.error(f"Failed to renew subscription: {str(e)}")
            raise IntegrationException(
                f"Failed to renew subscription: {str(e)}",
                provider="microsoft_365",
                operation="renew_subscription",
            )
