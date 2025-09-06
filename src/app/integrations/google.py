"""Google Workspace integration implementation."""

import logging
from typing import Any, Tuple

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import settings
from app.integrations.base import BaseIntegration, IntegrationException

logger = logging.getLogger(__name__)


class GoogleWorkspaceIntegration(BaseIntegration):
    """Google Workspace API integration."""

    def __init__(
        self, access_token: str, refresh_token: str | None = None
    ) -> None:
        """
        Initialize Google Workspace integration.

        Args:
            access_token: OAuth access token
            refresh_token: Optional refresh token for token renewal
        """
        super().__init__(access_token)
        self.refresh_token = refresh_token

        # Create credentials object
        self.credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )

        # Build service clients
        self.gmail_service = build("gmail", "v1", credentials=self.credentials)
        self.calendar_service = build(
            "calendar", "v3", credentials=self.credentials
        )
        self.people_service = build(
            "people", "v1", credentials=self.credentials
        )

    async def get_contacts(
        self, sync_token: str | None = None
    ) -> Tuple[list[dict[str, Any]], str | None]:
        """
        Fetch contacts from Google People API.

        Args:
            sync_token: Token for delta sync

        Returns:
            Tuple of (contacts list, next sync token)
        """
        try:
            contacts = []
            next_page_token = None
            next_sync_token = None

            while True:
                # Build request parameters
                params = {
                    "resourceName": "people/me",
                    "pageSize": 100,
                    "personFields": "names,emailAddresses,phoneNumbers,metadata",
                }

                if sync_token:
                    params["syncToken"] = sync_token
                elif next_page_token:
                    params["pageToken"] = next_page_token
                else:
                    params["requestSyncToken"] = True

                # Execute request
                try:
                    response = (
                        self.people_service.people()
                        .connections()
                        .list(**params)
                        .execute()
                    )
                except HttpError as e:
                    if e.resp.status == 410:  # Sync token expired
                        logger.warning(
                            "Sync token expired, performing full sync"
                        )
                        if sync_token:
                            return await self.get_contacts(sync_token=None)
                    raise

                # Process connections
                for connection in response.get("connections", []):
                    contact_data = self._parse_google_contact(connection)
                    if contact_data:
                        contacts.append(contact_data)

                # Check for more pages
                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    next_sync_token = response.get("nextSyncToken")
                    break

            return contacts, next_sync_token

        except Exception as e:
            logger.error(f"Failed to fetch Google contacts: {str(e)}")
            raise IntegrationException(
                f"Failed to fetch contacts: {str(e)}",
                provider="google_workspace",
                operation="get_contacts",
            )

    def _parse_google_contact(
        self, connection: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Parse Google contact data."""
        contact = {"id": connection.get("resourceName"), "identifiers": []}

        # Extract name
        names = connection.get("names", [])
        if names:
            contact["name"] = names[0].get("displayName")

        # Extract emails
        for email in connection.get("emailAddresses", []):
            contact["identifiers"].append(
                {"type": "email", "value": email.get("value")}
            )

        # Extract phone numbers
        for phone in connection.get("phoneNumbers", []):
            contact["identifiers"].append(
                {"type": "phone", "value": phone.get("value")}
            )

        # Only return if we have at least one identifier
        return contact if contact["identifiers"] else None

    async def get_email_content(self, email_id: str) -> dict[str, Any]:
        """
        Fetch full email content from Gmail.

        Args:
            email_id: Gmail message ID

        Returns:
            Email data including body and metadata
        """
        try:
            # Get message
            message = (
                self.gmail_service.users()
                .messages()
                .get(userId="me", id=email_id, format="full")
                .execute()
            )

            # Parse message
            return self._parse_gmail_message(message)

        except Exception as e:
            logger.error(f"Failed to fetch Gmail message: {str(e)}")
            raise IntegrationException(
                f"Failed to fetch email: {str(e)}",
                provider="google_workspace",
                operation="get_email_content",
            )

    def _parse_gmail_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Parse Gmail message data."""
        headers = message["payload"].get("headers", [])

        # Extract headers
        header_dict = {h["name"]: h["value"] for h in headers}

        # Extract body
        body = self._extract_message_body(message["payload"])

        has_attachments = False
        if "parts" in message["payload"]:
            for part in message["payload"]["parts"]:
                if part.get("filename") and part["filename"].strip():
                    has_attachments = True
                    break

        return {
            "id": message["id"],
            "thread_id": message.get("threadId"),
            "from": header_dict.get("From"),
            "to": header_dict.get("To"),
            "subject": header_dict.get("Subject"),
            "date": header_dict.get("Date"),
            "body": body,
            # "snippet": message.get("snippet"),
            "labels": message.get("labelIds", []),
            "has_attachments": has_attachments,
        }

    def _extract_message_body(self, payload: dict[str, Any]) -> str:
        """Extract body from Gmail message payload."""
        body = ""

        # Check for parts
        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    data = part["body"].get("data", "")
                    if data:
                        import base64

                        body += base64.urlsafe_b64decode(data).decode("utf-8")
        elif payload["body"].get("data"):
            import base64

            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode(
                "utf-8"
            )

        return body

    async def get_calendar_event(self, event_id: str) -> dict[str, Any]:
        """
        Fetch calendar event from Google Calendar.

        Args:
            event_id: Calendar event ID

        Returns:
            Event data
        """
        try:
            event = (
                self.calendar_service.events()
                .get(calendarId="primary", eventId=event_id)
                .execute()
            )

            return {
                "id": event["id"],
                "summary": event.get("summary"),
                "description": event.get("description"),
                "location": event.get("location"),
                "start": event.get("start"),
                "end": event.get("end"),
                "attendees": [
                    a.get("email") for a in event.get("attendees", [])
                ],
                "organizer": event.get("organizer", {}).get("email"),
                "status": event.get("status"),
                "isRecurring": "recurringEventId" in event,
                "eventType": event.get("eventType"),
                "isOnlineMeeting": event.get("conferenceData") is not None,
            }

        except Exception as e:
            logger.error(f"Failed to fetch calendar event: {str(e)}")
            raise IntegrationException(
                f"Failed to fetch event: {str(e)}",
                provider="google_workspace",
                operation="get_calendar_event",
            )

    async def subscribe_to_realtime_events(
        self, user_id: str, notification_url: str | None = None
    ) -> dict[str, Any]:
        """
        Set up Gmail and Calendar watch subscriptions.

        Args:
            user_id: User's UUID
            notification_url: Not used for Google (uses Pub/Sub)

        Returns:
            Subscription information
        """
        try:
            subscriptions = {}

            # Subscribe to Gmail
            gmail_watch = (
                self.gmail_service.users()
                .watch(
                    userId="me",
                    body={
                        "topicName": f"projects/{settings.GCP_PROJECT_ID}/topics/{settings.PUBSUB_TOPIC}",
                        "labelIds": ["INBOX"],
                        "labelFilterAction": "include",
                    },
                )
                .execute()
            )

            subscriptions["gmail"] = {
                "historyId": gmail_watch.get("historyId"),
                "expiration": gmail_watch.get("expiration"),
            }

            # Subscribe to Calendar
            # Note: Calendar uses a different watch mechanism
            import uuid

            channel_id = str(uuid.uuid4())

            calendar_watch = (
                self.calendar_service.events()
                .watch(
                    calendarId="primary",
                    body={
                        "id": channel_id,
                        "type": "web_hook",
                        "address": f"https://pubsub.googleapis.com/v1/projects/{settings.GCP_PROJECT_ID}/topics/{settings.PUBSUB_TOPIC}:publish",
                        "params": {"userId": user_id},
                    },
                )
                .execute()
            )

            subscriptions["calendar"] = {
                "channelId": calendar_watch.get("id"),
                "resourceId": calendar_watch.get("resourceId"),
                "expiration": calendar_watch.get("expiration"),
            }

            return subscriptions

        except Exception as e:
            logger.error(f"Failed to subscribe to Google events: {str(e)}")
            raise IntegrationException(
                f"Failed to subscribe: {str(e)}",
                provider="google_workspace",
                operation="subscribe_to_realtime_events",
            )

    async def renew_subscription(
        self, subscription_id: str, expiration_date: str
    ) -> dict[str, Any]:
        """
        Renew Google watch subscription.

        Note: Google watch subscriptions cannot be renewed directly.
        They must be recreated before expiration.

        Args:
            subscription_id: Not used for Google
            expiration_date: Not used for Google

        Returns:
            New subscription information
        """
        # For Google, we just create new subscriptions
        # The old ones will expire automatically
        return await self.subscribe_to_realtime_events(subscription_id, None)
