"""Gmail tools — read, search, send, draft, label emails via Gmail API."""

from __future__ import annotations

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

from googleapiclient.discovery import build

from kira.core.models import ToolContext, ToolResult, ToolSchema
from kira.integrations.google_auth import get_credentials
from kira.tools.registry import Tool, ToolRegistry

logger = logging.getLogger(__name__)


def _get_gmail_service():
    """Build Gmail API service. Returns None if not authenticated."""
    creds = get_credentials()
    if not creds or not creds.valid:
        return None
    return build("gmail", "v1", credentials=creds)


def _decode_body(payload: dict) -> str:
    """Extract readable text from Gmail message payload."""
    body = ""

    if payload.get("body", {}).get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode(
            "utf-8", errors="replace"
        )
    elif payload.get("parts"):
        for part in payload["parts"]:
            mime = part.get("mimeType", "")
            if mime == "text/plain" and part.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode(
                    "utf-8", errors="replace"
                )
                break
            elif mime == "text/html" and not body and part.get("body", {}).get("data"):
                # Fallback to HTML if no plain text
                import re

                html = base64.urlsafe_b64decode(part["body"]["data"]).decode(
                    "utf-8", errors="replace"
                )
                body = re.sub(r"<[^>]+>", "", html)
            elif mime.startswith("multipart/") and part.get("parts"):
                # Nested multipart
                body = _decode_body(part)
                if body:
                    break

    return body.strip()


def _format_headers(headers: list[dict]) -> dict[str, str]:
    """Extract useful headers into a dict."""
    result = {}
    want = {"From", "To", "Subject", "Date", "Cc", "Reply-To"}
    for h in headers:
        if h["name"] in want:
            result[h["name"]] = h["value"]
    return result


class GmailSearchTool(Tool):
    schema = ToolSchema(
        name="gmail_search",
        description=(
            "Search Gmail inbox using Gmail search syntax. "
            "Examples: 'is:unread', 'from:boss@company.com', "
            "'subject:meeting after:2026/04/01', 'label:important is:unread'. "
            "Returns message summaries (sender, subject, snippet)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Gmail search query (same syntax as Gmail search bar)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 10, max: 25)",
                },
            },
            "required": ["query"],
        },
        category="email",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        service = _get_gmail_service()
        if not service:
            return ToolResult(
                success=False,
                output="Gmail not authenticated. Run `kira setup google` first.",
            )

        query = arguments["query"]
        max_results = min(arguments.get("max_results", 10), 25)

        try:
            results = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )

            messages = results.get("messages", [])
            if not messages:
                return ToolResult(
                    success=True,
                    output=f"No emails found for query: {query}",
                    outcome={"emails_found": 0},
                )

            output_lines = [f"Found {len(messages)} email(s) for: {query}\n"]

            for msg_ref in messages:
                msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg_ref["id"], format="metadata",
                         metadataHeaders=["From", "Subject", "Date"])
                    .execute()
                )
                headers = _format_headers(msg.get("payload", {}).get("headers", []))
                snippet = msg.get("snippet", "")
                labels = msg.get("labelIds", [])

                unread = "UNREAD" in labels
                marker = "[NEW] " if unread else ""

                output_lines.append(
                    f"{marker}ID: {msg['id']}\n"
                    f"  From: {headers.get('From', '?')}\n"
                    f"  Subject: {headers.get('Subject', '(no subject)')}\n"
                    f"  Date: {headers.get('Date', '?')}\n"
                    f"  Preview: {snippet[:120]}\n"
                )

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                outcome={"emails_found": len(messages)},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Gmail search failed: {e}")


class GmailReadTool(Tool):
    schema = ToolSchema(
        name="gmail_read",
        description=(
            "Read the full content of a specific email by its message ID. "
            "Use gmail_search first to find message IDs."
        ),
        parameters={
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The Gmail message ID to read",
                },
                "mark_read": {
                    "type": "boolean",
                    "description": "Mark the message as read (default: true)",
                },
            },
            "required": ["message_id"],
        },
        category="email",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        service = _get_gmail_service()
        if not service:
            return ToolResult(
                success=False,
                output="Gmail not authenticated. Run `kira setup google` first.",
            )

        msg_id = arguments["message_id"]
        mark_read = arguments.get("mark_read", True)

        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            headers = _format_headers(msg.get("payload", {}).get("headers", []))
            body = _decode_body(msg.get("payload", {}))

            # Truncate very long emails
            if len(body) > 8000:
                body = body[:8000] + "\n...(truncated)"

            # Get attachments info
            attachments = []
            for part in msg.get("payload", {}).get("parts", []):
                if part.get("filename"):
                    attachments.append(
                        f"{part['filename']} ({part.get('mimeType', 'unknown')})"
                    )

            output_parts = [
                f"From: {headers.get('From', '?')}",
                f"To: {headers.get('To', '?')}",
            ]
            if headers.get("Cc"):
                output_parts.append(f"Cc: {headers['Cc']}")
            output_parts.extend([
                f"Subject: {headers.get('Subject', '(no subject)')}",
                f"Date: {headers.get('Date', '?')}",
            ])
            if attachments:
                output_parts.append(f"Attachments: {', '.join(attachments)}")
            output_parts.extend(["", "--- Body ---", body])

            # Mark as read
            if mark_read and "UNREAD" in msg.get("labelIds", []):
                service.users().messages().modify(
                    userId="me",
                    id=msg_id,
                    body={"removeLabelIds": ["UNREAD"]},
                ).execute()

            return ToolResult(
                success=True,
                output="\n".join(output_parts),
                outcome={"message_read": msg_id},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to read email: {e}")


class GmailSendTool(Tool):
    schema = ToolSchema(
        name="gmail_send",
        description=(
            "Send an email via Gmail. IMPORTANT: This actually sends the email. "
            "Always confirm with the user before calling this tool."
        ),
        parameters={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address(es), comma-separated",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line",
                },
                "body": {
                    "type": "string",
                    "description": "Email body (plain text)",
                },
                "cc": {
                    "type": "string",
                    "description": "CC recipients, comma-separated (optional)",
                },
                "reply_to_message_id": {
                    "type": "string",
                    "description": "Message ID to reply to (optional, for threading)",
                },
            },
            "required": ["to", "subject", "body"],
        },
        requires_approval=True,
        category="email",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        service = _get_gmail_service()
        if not service:
            return ToolResult(
                success=False,
                output="Gmail not authenticated. Run `kira setup google` first.",
            )

        to = arguments["to"]
        subject = arguments["subject"]
        body = arguments["body"]
        cc = arguments.get("cc")
        reply_to_id = arguments.get("reply_to_message_id")

        try:
            message = MIMEMultipart()
            message["to"] = to
            message["subject"] = subject
            if cc:
                message["cc"] = cc
            message.attach(MIMEText(body, "plain"))

            # Handle reply threading
            if reply_to_id:
                orig = (
                    service.users()
                    .messages()
                    .get(userId="me", id=reply_to_id, format="metadata",
                         metadataHeaders=["Message-ID", "References", "Subject"])
                    .execute()
                )
                orig_headers = _format_headers(
                    orig.get("payload", {}).get("headers", [])
                )
                for h in orig.get("payload", {}).get("headers", []):
                    if h["name"] == "Message-ID":
                        message["In-Reply-To"] = h["value"]
                        message["References"] = h["value"]
                        break
                message["threadId"] = orig.get("threadId")

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            send_body = {"raw": raw}
            if reply_to_id:
                orig_msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=reply_to_id, format="minimal")
                    .execute()
                )
                send_body["threadId"] = orig_msg.get("threadId")

            sent = (
                service.users()
                .messages()
                .send(userId="me", body=send_body)
                .execute()
            )

            return ToolResult(
                success=True,
                output=f"Email sent to {to} (ID: {sent['id']})",
                outcome={"email_sent": True, "message_id": sent["id"], "to": to},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to send email: {e}")


class GmailDraftTool(Tool):
    schema = ToolSchema(
        name="gmail_draft",
        description=(
            "Create a draft email in Gmail. Does NOT send it — "
            "saves it in the Drafts folder for review."
        ),
        parameters={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address(es)",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line",
                },
                "body": {
                    "type": "string",
                    "description": "Email body (plain text)",
                },
                "cc": {
                    "type": "string",
                    "description": "CC recipients (optional)",
                },
            },
            "required": ["to", "subject", "body"],
        },
        category="email",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        service = _get_gmail_service()
        if not service:
            return ToolResult(
                success=False,
                output="Gmail not authenticated. Run `kira setup google` first.",
            )

        to = arguments["to"]
        subject = arguments["subject"]
        body = arguments["body"]
        cc = arguments.get("cc")

        try:
            message = MIMEText(body, "plain")
            message["to"] = to
            message["subject"] = subject
            if cc:
                message["cc"] = cc

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            draft = (
                service.users()
                .drafts()
                .create(userId="me", body={"message": {"raw": raw}})
                .execute()
            )

            return ToolResult(
                success=True,
                output=(
                    f"Draft created (ID: {draft['id']})\n"
                    f"  To: {to}\n"
                    f"  Subject: {subject}\n"
                    f"  Body preview: {body[:200]}"
                ),
                outcome={"draft_created": True, "draft_id": draft["id"]},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to create draft: {e}")


class GmailLabelTool(Tool):
    schema = ToolSchema(
        name="gmail_label",
        description=(
            "Add or remove labels from an email. "
            "Common labels: INBOX, UNREAD, STARRED, IMPORTANT, SPAM, TRASH. "
            "Use this to archive (remove INBOX), star, or organize emails."
        ),
        parameters={
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The Gmail message ID",
                },
                "add_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels to add (e.g., ['STARRED', 'IMPORTANT'])",
                },
                "remove_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels to remove (e.g., ['INBOX'] to archive)",
                },
            },
            "required": ["message_id"],
        },
        category="email",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        service = _get_gmail_service()
        if not service:
            return ToolResult(
                success=False,
                output="Gmail not authenticated. Run `kira setup google` first.",
            )

        msg_id = arguments["message_id"]
        add_labels = arguments.get("add_labels", [])
        remove_labels = arguments.get("remove_labels", [])

        if not add_labels and not remove_labels:
            return ToolResult(
                success=False,
                output="Must specify add_labels or remove_labels (or both)",
            )

        try:
            body = {}
            if add_labels:
                body["addLabelIds"] = add_labels
            if remove_labels:
                body["removeLabelIds"] = remove_labels

            service.users().messages().modify(
                userId="me", id=msg_id, body=body
            ).execute()

            actions = []
            if add_labels:
                actions.append(f"added: {', '.join(add_labels)}")
            if remove_labels:
                actions.append(f"removed: {', '.join(remove_labels)}")

            return ToolResult(
                success=True,
                output=f"Labels updated for {msg_id}: {'; '.join(actions)}",
                outcome={"labels_modified": True, "message_id": msg_id},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to modify labels: {e}")


class GmailListLabelsTool(Tool):
    schema = ToolSchema(
        name="gmail_list_labels",
        description="List all Gmail labels/folders available in the account.",
        parameters={
            "type": "object",
            "properties": {},
        },
        category="email",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        service = _get_gmail_service()
        if not service:
            return ToolResult(
                success=False,
                output="Gmail not authenticated. Run `kira setup google` first.",
            )

        try:
            results = service.users().labels().list(userId="me").execute()
            labels = results.get("labels", [])

            output_lines = [f"Gmail Labels ({len(labels)} total):\n"]
            # Sort: system labels first, then user labels
            system_labels = [l for l in labels if l.get("type") == "system"]
            user_labels = [l for l in labels if l.get("type") != "system"]

            if system_labels:
                output_lines.append("System labels:")
                for label in sorted(system_labels, key=lambda l: l["name"]):
                    output_lines.append(f"  - {label['name']} (id: {label['id']})")

            if user_labels:
                output_lines.append("\nUser labels:")
                for label in sorted(user_labels, key=lambda l: l["name"]):
                    output_lines.append(f"  - {label['name']} (id: {label['id']})")

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                outcome={"labels_count": len(labels)},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to list labels: {e}")


def register(registry: ToolRegistry):
    registry.register(GmailSearchTool())
    registry.register(GmailReadTool())
    registry.register(GmailSendTool())
    registry.register(GmailDraftTool())
    registry.register(GmailLabelTool())
    registry.register(GmailListLabelsTool())
