"""Google OAuth provider — Calendar, Drive, YouTube via CredentialVault.

Reads client secret from ~/.kio/credentials/google_client_secret.json.
Stores tokens in OS keyring via CredentialVault.
Never prints secrets.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CLIENT_SECRET_PATH = os.path.expanduser("~/.kio/credentials/google_client_secret.json")

# ── Google Scope Registry ──────────────────────────────────────────
# Centralized scope definitions. Every Google scope used by KIO lives here.
# When adding a new Google capability, add its scope here FIRST.

# The target Google ecosystem is EXACTLY five OAuth services:
#   Gmail, Calendar, Drive, People, Photos.
# YouTube stays API-key based (config.YOUTUBE_API_KEY) and Places API (New) is
# API-key based, so neither contributes an OAuth scope here — see
# `google_places_ops` for why public-data APIs use a key instead of the user's
# OAuth grant. Nothing else (Tasks, Sheets, Docs, Slides, Meet, Chat,
# BigQuery, Cloud Storage) is requested.
GOOGLE_SCOPES = {
    # ── Gmail ──
    "gmail":       "https://www.googleapis.com/auth/gmail.modify",
    "gmail_read":  "https://www.googleapis.com/auth/gmail.readonly",
    "gmail_send":  "https://www.googleapis.com/auth/gmail.send",

    # ── Google Calendar ──
    "calendar":      "https://www.googleapis.com/auth/calendar",
    "calendar_read": "https://www.googleapis.com/auth/calendar.readonly",

    # ── Google Drive ──
    "drive":      "https://www.googleapis.com/auth/drive",
    "drive_read": "https://www.googleapis.com/auth/drive.readonly",

    # ── People / Contacts ──
    "contacts":          "https://www.googleapis.com/auth/contacts",
    "contacts_readonly": "https://www.googleapis.com/auth/contacts.readonly",

    # ── Google Photos — ONLY the scopes that still exist after 2025-03-31.
    # `photoslibrary`, `photoslibrary.readonly` and `photoslibrary.sharing`
    # were removed by Google on that date and must never be requested again.
    "photos_append":          "https://www.googleapis.com/auth/photoslibrary.appendonly",
    "photos_read_appcreated": "https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata",
    "photos_edit_appcreated": "https://www.googleapis.com/auth/photoslibrary.edit.appcreateddata",
    "photos_picker":          "https://www.googleapis.com/auth/photospicker.mediaitems.readonly",
}

# Scopes used by the current KIO build (runtime) — SINGLE UNION.
# This is the authoritative list every Google consent request uses.
ACTIVE_SCOPES = [
    GOOGLE_SCOPES["gmail"],
    GOOGLE_SCOPES["calendar"],
    GOOGLE_SCOPES["drive"],
    GOOGLE_SCOPES["contacts"],
    GOOGLE_SCOPES["photos_append"],
    GOOGLE_SCOPES["photos_read_appcreated"],
    GOOGLE_SCOPES["photos_picker"],
]

# Legacy alias — keep existing code working
SCOPES = ACTIVE_SCOPES

PROVIDER = "google"
CREDENTIAL_TYPE = "oauth2"

# Service → the scope that proves it can actually be called. Used by readiness
# probes and by the credential checker so "authorized" is never confused with
# "authorized for this service".
SERVICE_SCOPES = {
    "gmail": GOOGLE_SCOPES["gmail"],
    "calendar": GOOGLE_SCOPES["calendar"],
    "drive": GOOGLE_SCOPES["drive"],
    "contacts": GOOGLE_SCOPES["contacts"],
    "photos": GOOGLE_SCOPES["photos_picker"],
}


def _load_client_config() -> dict:
    """Load OAuth client config from the copied JSON file."""
    with open(_CLIENT_SECRET_PATH) as f:
        data = json.load(f)
    # Handle both "installed" and "web" key formats
    return data.get("installed", data.get("web", {}))


def _get_vault():
    from mini_kio.core.credential_vault import get_credential_vault
    return get_credential_vault()


def granted_scopes() -> list[str]:
    """Return the scopes actually granted on the stored credential (never the secret)."""
    creds = _get_credentials()
    return sorted(list(creds.scopes or [])) if creds is not None else []


def service_scope_status(service: str) -> tuple[bool, str]:
    """Is *service* actually callable with the stored grant?

    Distinguishes "no credential", "credential unreadable", and "credential is
    valid but lacks this service's scope" — each has a different fix.
    """
    scope = SERVICE_SCOPES.get(service)
    if not scope:
        return False, f"unknown Google service '{service}'"
    try:
        creds = _get_credentials()
    except Exception as exc:
        return False, f"Google credential not inspectable: {exc}"
    if creds is None:
        return False, "Google OAuth not authorized (no retrievable credential)"
    granted = list(creds.scopes or [])
    if not granted:
        return False, "Google credential carries no scope information"
    if scope not in granted:
        return False, (
            f"Google credential is valid but lacks the {service} scope "
            f"({scope}); re-consent is required to add it"
        )
    return True, f"Google OAuth authorized and scoped for {service}"


def store_places_api_key(api_key: str, consent: bool = True) -> str:
    """Store the Places API (New) key in CredentialVault.

    Places uses API-key auth (public data API), so it is a separate credential
    of type `api_key` under the same provider — not a second OAuth identity.
    The value is written straight to the vault and never logged or returned.
    """
    if not api_key or not api_key.strip():
        raise ValueError("store_places_api_key: empty key")
    vault = _get_vault()
    vault.revoke_by_target(PROVIDER, "api_key")
    return vault.store(
        provider=PROVIDER,
        credential_type="api_key",
        secret=api_key.strip(),
        metadata={"service": "places", "name": "Google Places API (New)"},
        consent=consent,
    )


def _get_credentials():
    """Build google.oauth2.credentials.Credentials from stored tokens, or None."""
    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        return None

    vault = _get_vault()
    # Find stored Google OAuth token
    meta_list = vault.list()
    for m in meta_list:
        if m.provider == PROVIDER and m.credential_type == CREDENTIAL_TYPE:
            cred = vault.retrieve(m.credential_id)
            if cred is None:
                # An expired access token is normal for OAuth: the durable material
                # is the refresh_token, and google-auth refreshes lazily on the
                # first request. Without this the credential is unusable for an
                # hour after every authorization. A credential with no refresh
                # material still fails closed.
                cred = vault.retrieve_for_refresh(m.credential_id)
            if cred is None:
                continue
            token_data = json.loads(cred.secret)
            client_config = _load_client_config()
            return Credentials(
                token=token_data.get("access_token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_config.get("client_id"),
                client_secret=client_config.get("client_secret"),
                scopes=token_data.get("scopes", SCOPES),
            )
    return None


def build_auth_url(scopes: list[str] | None = None) -> str:
    """Build the Google OAuth authorization URL.

    Args:
        scopes: Override scopes. Defaults to ACTIVE_SCOPES.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise RuntimeError("google-auth-oauthlib not installed. Run: pip install google-auth-oauthlib")

    use_scopes = scopes or ACTIVE_SCOPES
    client_config = {"installed": _load_client_config()}
    flow = InstalledAppFlow.from_client_config(client_config, scopes=use_scopes)
    flow.oauth2session.redirect_uri = "http://localhost"
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    return auth_url


def exchange_code(auth_code: str, scopes: list[str] | None = None) -> str:
    """Exchange authorization code for tokens. Store in vault. Returns credential_id.

    Revokes the old credential (if any) and stores a fresh one with the new
    scopes. The vault keeps secrets in the OS keyring — never in SQLite.

    Args:
        auth_code: The authorization code from Google.
        scopes: Override scopes. Defaults to ACTIVE_SCOPES.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise RuntimeError("google-auth-oauthlib not installed")

    use_scopes = scopes or ACTIVE_SCOPES
    client_config = {"installed": _load_client_config()}
    flow = InstalledAppFlow.from_client_config(client_config, scopes=use_scopes)
    flow.oauth2session.redirect_uri = "http://localhost"
    flow.fetch_token(code=auth_code)

    token_data = {
        "access_token": flow.credentials.token,
        "refresh_token": flow.credentials.refresh_token,
        "scopes": list(flow.credentials.scopes or use_scopes),
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    vault = _get_vault()
    # Revoke old credential so only the new one is active
    vault.revoke_by_target(PROVIDER, CREDENTIAL_TYPE)

    credential_id = vault.store(
        provider=PROVIDER,
        credential_type=CREDENTIAL_TYPE,
        secret=json.dumps(token_data),
        expires_at=flow.credentials.expiry,
        metadata={"scopes": use_scopes, "consent": True},
        consent=True,
    )
    logger.info("[GOOGLE] OAuth tokens stored, credential_id=%s scopes=%s", credential_id, use_scopes)
    return credential_id


def get_calendar_service():
    """Build a Google Calendar API service."""
    from googleapiclient.discovery import build
    creds = _get_credentials()
    if creds is None:
        raise RuntimeError("Google OAuth not authorized. Run oauth_authorize first.")
    return build("calendar", "v3", credentials=creds)


def get_drive_service():
    """Build a Google Drive API service."""
    from googleapiclient.discovery import build
    creds = _get_credentials()
    if creds is None:
        raise RuntimeError("Google OAuth not authorized. Run oauth_authorize first.")
    return build("drive", "v3", credentials=creds)


def get_youtube_service():
    """Build a YouTube Data API service."""
    from googleapiclient.discovery import build
    creds = _get_credentials()
    if creds is None:
        raise RuntimeError("Google OAuth not authorized. Run oauth_authorize first.")
    return build("youtube", "v3", credentials=creds)


def get_gmail_service():
    """Build a Gmail API service."""
    from googleapiclient.discovery import build
    creds = _get_credentials()
    if creds is None:
        raise RuntimeError("Google OAuth not authorized. Run oauth_authorize first.")
    return build("gmail", "v1", credentials=creds)


def get_people_service():
    """Build a Google People API service."""
    from googleapiclient.discovery import build
    creds = _get_credentials()
    if creds is None:
        raise RuntimeError("Google OAuth not authorized. Run oauth_authorize first.")
    return build("people", "v1", credentials=creds, static_discovery=False)


def get_tasks_service():
    """Build a Google Tasks API service."""
    from googleapiclient.discovery import build
    creds = _get_credentials()
    if creds is None:
        raise RuntimeError("Google OAuth not authorized. Run oauth_authorize first.")
    return build("tasks", "v1", credentials=creds)


def get_photos_service():
    """Build a Google Photos Library API service."""
    from googleapiclient.discovery import build
    creds = _get_credentials()
    if creds is None:
        raise RuntimeError("Google OAuth not authorized. Run oauth_authorize first.")
    return build("photoslibrary", "v1", credentials=creds, static_discovery=False)


def get_sheets_service():
    """Build a Google Sheets API service."""
    from googleapiclient.discovery import build
    creds = _get_credentials()
    if creds is None:
        raise RuntimeError("Google OAuth not authorized. Run oauth_authorize first.")
    return build("sheets", "v4", credentials=creds)


def get_docs_service():
    """Build a Google Docs API service."""
    from googleapiclient.discovery import build
    creds = _get_credentials()
    if creds is None:
        raise RuntimeError("Google OAuth not authorized. Run oauth_authorize first.")
    return build("docs", "v1", credentials=creds)


def get_slides_service():
    """Build a Google Slides API service."""
    from googleapiclient.discovery import build
    creds = _get_credentials()
    if creds is None:
        raise RuntimeError("Google OAuth not authorized. Run oauth_authorize first.")
    return build("slides", "v1", credentials=creds)


def get_places_service():
    """Build a Google Places API (New) service.

    NOTE: Places uses API key auth, not OAuth. The API key is stored in
    CredentialVault as a separate credential (provider=google, type=api_key,
    with metadata["service"]="places"). This is NOT a second OAuth identity
    -- it's a different auth mechanism for a different API surface.
    """
    vault = _get_vault()
    meta_list = vault.list()
    for m in meta_list:
        if m.provider == PROVIDER and m.credential_type == "api_key":
            if m.metadata.get("service") == "places":
                cred = vault.retrieve(m.credential_id)
                if cred:
                    return {"api_key": cred.secret, "type": "api_key"}
    raise RuntimeError("Google Places API key not configured. Store via CredentialVault.")


def get_meet_service():
    """Build a Google Meet API service (Workspace-only)."""
    from googleapiclient.discovery import build
    creds = _get_credentials()
    if creds is None:
        raise RuntimeError("Google OAuth not authorized. Run oauth_authorize first.")
    return build("meet", "v2", credentials=creds)


def get_chat_service():
    """Build a Google Chat API service (Workspace-only)."""
    from googleapiclient.discovery import build
    creds = _get_credentials()
    if creds is None:
        raise RuntimeError("Google OAuth not authorized. Run oauth_authorize first.")
    return build("chat", "v1", credentials=creds)


def health_check() -> dict:
    """Check if Google OAuth is configured and tokens are valid."""
    vault = _get_vault()
    state = vault.validate(PROVIDER, CREDENTIAL_TYPE)
    return {
        "provider": "google",
        "state": state,
        "client_config_exists": os.path.exists(_CLIENT_SECRET_PATH),
        "has_valid_tokens": state == "valid",
    }
