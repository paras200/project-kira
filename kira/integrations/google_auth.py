"""Google OAuth2 authentication for Gmail and other Google APIs.

Setup flow:
1. User creates a Google Cloud project and enables Gmail API
2. User downloads OAuth2 credentials JSON (Desktop app type)
3. User saves it as ~/.kira/google_credentials.json
4. User runs `kira setup google` which opens browser for consent
5. Token is saved to ~/.kira/google_token.json (auto-refreshed)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

# Gmail scopes — read, send, modify labels, drafts
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.labels",
]

KIRA_HOME = Path.home() / ".kira"
CREDENTIALS_PATH = KIRA_HOME / "google_credentials.json"
TOKEN_PATH = KIRA_HOME / "google_token.json"


def get_credentials(
    scopes: Optional[list] = None,
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> Optional[Credentials]:
    """
    Get valid Google OAuth2 credentials.

    Returns existing token if valid, refreshes if expired,
    or None if no credentials are set up.
    """
    scopes = scopes or GMAIL_SCOPES
    credentials_path = credentials_path or CREDENTIALS_PATH
    token_path = token_path or TOKEN_PATH

    creds = None

    # Load existing token
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        except Exception as e:
            logger.warning(f"Failed to load token: {e}")
            creds = None

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds, token_path)
            logger.info("Google token refreshed")
        except Exception as e:
            logger.warning(f"Token refresh failed: {e}")
            creds = None

    return creds


def run_auth_flow(
    scopes: Optional[list] = None,
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> Credentials:
    """
    Run the full OAuth2 consent flow.

    Opens a browser window for the user to authorize access.
    Saves the resulting token for future use.
    """
    scopes = scopes or GMAIL_SCOPES
    credentials_path = credentials_path or CREDENTIALS_PATH
    token_path = token_path or TOKEN_PATH

    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Google credentials not found at {credentials_path}\n\n"
            "To set up Google integration:\n"
            "1. Go to https://console.cloud.google.com/\n"
            "2. Create a project (or use existing)\n"
            "3. Enable the Gmail API\n"
            "4. Go to Credentials > Create Credentials > OAuth Client ID\n"
            "5. Choose 'Desktop app' as application type\n"
            "6. Download the JSON file\n"
            "7. Save it as ~/.kira/google_credentials.json"
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_path), scopes
    )

    # Run local server for OAuth callback
    creds = flow.run_local_server(port=0)
    _save_token(creds, token_path)
    logger.info("Google OAuth2 authorization complete")
    return creds


def _save_token(creds: Credentials, token_path: Path):
    """Save credentials to token file."""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes and list(creds.scopes),
    }
    token_path.write_text(json.dumps(token_data, indent=2))
    # Restrict permissions
    token_path.chmod(0o600)


def is_configured() -> bool:
    """Check if Google credentials are set up."""
    return CREDENTIALS_PATH.exists()


def is_authenticated() -> bool:
    """Check if we have a valid token."""
    creds = get_credentials()
    return creds is not None and creds.valid
