"""
credential_vault.py — Credential Vault Core (Slice 8 / B.2)
===========================================================

Canonical KIO credential owner. Holds the actual secret material in the
platform keyring (Windows Credential Manager / macOS Keychain / Linux Secret
Service) and ONLY metadata in SQLite via the existing backend engine.

Security invariants:
  - NEVER store secrets in SQLite (metadata only).
  - NEVER log / print / return secret material.
  - NEVER fabricate a missing credential.
  - Storage requires EXPLICIT user consent (consent=True).
  - Retrieval is gated: only the Execution Gate consumes secrets; never the
    LLM context or user-facing response layer.

The Execution Gate (Slice 7) consumes this via credential prerequisite
resolvers registered through `_PREREQUISITE_RESOLVERS` — no parallel
credential-checking path.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "kio_credential_vault"
_CONSENT_REQUIRED = True  # explicit-consent policy (Slice 8 hard requirement)

# Defensive: metadata persisted to SQLite must NEVER carry secret-shaped values,
# even if a caller (or a future OAuth metadata bag) passes them. Slice 8 hard
# requirement: SQLite holds metadata only, never plaintext secrets.
_SECRET_LIKE_KEYS = frozenset(
    {
        "secret", "password", "passwd", "api_key", "apikey",
        "access_token", "refresh_token", "token", "authorization",
        "client_secret", "auth_token", "id_token",
    }
)


class ConsentRequiredError(RuntimeError):
    """Raised when a credential store is attempted without explicit consent."""


class EmptySecretError(ValueError):
    """Raised when an empty/blank secret is presented for storage."""


class CredentialNotFoundError(KeyError):
    """Raised when a credential_id is unknown or revoked."""


@dataclass
class Credential:
    """A resolved credential (metadata + secret material).

    Internal only — never passed to the LLM context or serialized into
    user-facing responses. The secret field is redacted by __repr__.
    """

    credential_id: str
    provider: str
    credential_type: str
    secret: str
    expires_at: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: int = 0

    def __repr__(self) -> str:
        return (
            f"Credential(credential_id={self.credential_id!r}, "
            f"provider={self.provider!r}, credential_type={self.credential_type!r}, "
            f"secret=<redacted>, expires_at={self.expires_at!r})"
        )


@dataclass
class CredentialMetadata:
    """Non-secret vault record for listing / UI. Never contains the secret."""

    credential_id: str
    provider: str
    credential_type: str
    expires_at: Optional[int] = None
    created_at: int = 0
    consent_recorded: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def _now_ts() -> int:
    return int(time.time())


def _sanitize_metadata(metadata: Optional[dict]) -> dict:
    """Return a metadata copy with secret-shaped keys removed.

    Defends the 'never plaintext secrets in SQLite' invariant against caller
    error: keys like access_token / password are dropped before persistence.
    Raises on a metadata value that itself equals a secret-shaped key name's
    payload only when the key is secret-like (the key is simply dropped).
    """
    out: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if str(key).strip().lower() in _SECRET_LIKE_KEYS:
            continue
        out[key] = value
    return out


def _unix_from_datetime(value: Optional[datetime]) -> Optional[int]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp())


class _KeyringBackend:
    """Thin keyring adapter. All exceptions are isolated so a backend failure
    never crashes the runtime; callers treat it as 'no secret available'."""

    def set(self, credential_id: str, secret: str) -> None:
        try:
            import keyring
            keyring.set_password(_KEYRING_SERVICE, credential_id, secret)
        except Exception as exc:
            logger.error("[VAULT] keyring write failed for %s: %s", credential_id, exc)
            raise

    def get(self, credential_id: str) -> Optional[str]:
        try:
            import keyring
            return keyring.get_password(_KEYRING_SERVICE, credential_id)
        except Exception as exc:
            logger.error("[VAULT] keyring read failed for %s: %s", credential_id, exc)
            return None

    def delete(self, credential_id: str) -> None:
        try:
            import keyring
            keyring.delete_password(_KEYRING_SERVICE, credential_id)
        except Exception:
            pass  # already gone


class CredentialVault:
    """Canonical credential store. Metadata in SQLite; secrets in keyring.

    API per KIO_Implementation_Plan.md Slice 8.
    """

    def __init__(self) -> None:
        self._keyring = _KeyringBackend()
        self._ensure_table()

    # ------------------------------------------------------------------
    # Persistence (canonical backend engine — no new DB)
    # ------------------------------------------------------------------
    def _session_scope(self):
        from mini_kio.backend.db import db_session

        return db_session()

    def _ensure_table(self) -> None:
        try:
            from mini_kio.backend.db import init_db

            init_db()
        except Exception as exc:
            logger.warning("[VAULT] backend init failed (metadata store unavailable): %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def store(
        self,
        provider: str,
        credential_type: str,
        secret: str,
        expires_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
        *,
        consent: bool = False,
    ) -> str:
        """Store a credential. Returns the credential_id.

        Requires explicit `consent=True` (Slice 8 consent policy). Raises on
        empty secret. The secret goes to keyring only; SQLite holds metadata.
        """
        if _CONSENT_REQUIRED and not consent:
            raise ConsentRequiredError(
                "Credential storage requires explicit user consent (consent=True)."
            )
        if not secret or not str(secret).strip():
            raise EmptySecretError("Cannot store an empty secret.")
        if not provider or not credential_type:
            raise ValueError("provider and credential_type are required.")

        credential_id = str(uuid.uuid4())
        created = _now_ts()
        expires = _unix_from_datetime(expires_at)
        meta = _sanitize_metadata(metadata)

        self._keyring.set(credential_id, str(secret))

        try:
            from mini_kio.backend.models import CredentialRecordModel

            with self._session_scope() as session:
                row = CredentialRecordModel(
                    credential_id=credential_id,
                    provider=provider,
                    credential_type=credential_type,
                    metadata_json=meta,
                    expires_at=expires,
                    created_at=created,
                    consent_recorded=True,
                    revoked=False,
                )
                session.add(row)
                session.commit()
        except Exception as exc:
            # Roll back the keyring write to avoid an orphan secret.
            self._keyring.delete(credential_id)
            logger.error("[VAULT] metadata write failed for %s: %s", credential_id, exc)
            raise

        logger.info("[VAULT] stored credential provider=%s type=%s id=%s consent=%s",
                    provider, credential_type, credential_id, True)
        return credential_id

    def retrieve(self, credential_id: str) -> Optional[Credential]:
        """Return the Credential (metadata + secret) or None if missing/expired.

        Internal only — consumed by the Execution Gate, never the LLM context
        or user-facing responses.
        """
        from mini_kio.backend.models import CredentialRecordModel

        with self._session_scope() as session:
            row = (
                session.query(CredentialRecordModel)
                .filter(CredentialRecordModel.credential_id == credential_id)
                .first()
            )
            if row is None or row.revoked:
                return None
            expires = row.expires_at
            if expires is not None and _now_ts() > expires:
                return None
            secret = self._keyring.get(credential_id)
            if secret is None:
                return None
            return Credential(
                credential_id=row.credential_id,
                provider=row.provider,
                credential_type=row.credential_type,
                secret=secret,
                expires_at=expires,
                metadata=dict(row.metadata_json or {}),
                created_at=row.created_at,
            )

    def revoke(self, credential_id: str) -> None:
        """Revoke a credential: drop the secret and mark revoked. Next access
        will re-prompt. (Lifecycle surface used by Slice 9; core revocation is
        safe to expose now.)"""
        from mini_kio.backend.models import CredentialRecordModel

        self._keyring.delete(credential_id)
        try:
            with self._session_scope() as session:
                row = (
                    session.query(CredentialRecordModel)
                    .filter(CredentialRecordModel.credential_id == credential_id)
                    .first()
                )
                if row is not None:
                    row.revoked = True
                    session.commit()
        except Exception as exc:
            logger.error("[VAULT] revoke metadata update failed for %s: %s", credential_id, exc)

    def list(self) -> list[CredentialMetadata]:
        """Return metadata only (never secrets) for /credentials UI."""
        from mini_kio.backend.models import CredentialRecordModel

        out: list[CredentialMetadata] = []
        try:
            with self._session_scope() as session:
                rows = session.query(CredentialRecordModel).all()
                for row in rows:
                    if row.revoked:
                        continue
                    out.append(
                        CredentialMetadata(
                            credential_id=row.credential_id,
                            provider=row.provider,
                            credential_type=row.credential_type,
                            expires_at=row.expires_at,
                            created_at=row.created_at,
                            consent_recorded=row.consent_recorded,
                            metadata=dict(row.metadata_json or {}),
                        )
                    )
        except Exception as exc:
            logger.error("[VAULT] list failed: %s", exc)
        return out

    def has_valid(self, provider: str, credential_type: str) -> bool:
        """Quick non-exposing check for the Execution Gate."""
        from mini_kio.backend.models import CredentialRecordModel

        try:
            with self._session_scope() as session:
                rows = (
                    session.query(CredentialRecordModel)
                    .filter(
                        CredentialRecordModel.provider == provider,
                        CredentialRecordModel.credential_type == credential_type,
                        CredentialRecordModel.revoked.is_(False),
                    )
                    .all()
                )
                now = _now_ts()
                for row in rows:
                    if row.expires_at is not None and now > row.expires_at:
                        continue
                    secret = self._keyring.get(row.credential_id)
                    if secret is not None:
                        return True
                return False
        except Exception as exc:
            logger.error("[VAULT] has_valid failed provider=%s type=%s: %s",
                         provider, credential_type, exc)
            return False


# ----------------------------------------------------------------------
# Singleton accessor (canonical owner)
# ----------------------------------------------------------------------
import threading as _threading

_VAULT_INSTANCE: Optional[CredentialVault] = None
_VAULT_LOCK = _threading.Lock()


def get_credential_vault() -> CredentialVault:
    """Return the canonical singleton CredentialVault."""
    global _VAULT_INSTANCE
    if _VAULT_INSTANCE is None:
        with _VAULT_LOCK:
            if _VAULT_INSTANCE is None:
                _VAULT_INSTANCE = CredentialVault()
    return _VAULT_INSTANCE


# ----------------------------------------------------------------------
# OAuth flow template (Slice 8 scope: canonical foundation only)
# ----------------------------------------------------------------------
@dataclass
class OAuthFlowTemplate:
    """Generic OAuth2 authorization-code flow template.

    Provider-specific wiring plugs into these callables; Slice 8 provides the
    canonical shape (auth URL -> callback -> token exchange -> secure storage),
    NOT per-provider integrations. Resulting tokens are stored through the
    Vault with explicit consent.
    """

    provider: str
    auth_url_builder: Any = None  # callable(state) -> str auth URL
    token_exchanger: Any = None  # callable(code, **kwargs) -> dict {access_token, ...}
    credential_type: str = "oauth2"

    def build_auth_url(self, state: str) -> str:
        if self.auth_url_builder is None:
            raise NotImplementedError("auth_url_builder not configured for this provider.")
        return str(self.auth_url_builder(state))

    def exchange_code(self, code: str, **kwargs: Any) -> dict[str, Any]:
        if self.token_exchanger is None:
            raise NotImplementedError("token_exchanger not configured for this provider.")
        result = self.token_exchanger(code, **kwargs)
        if not isinstance(result, dict):
            raise ValueError("token_exchanger must return a dict of token fields.")
        return result

    def store_tokens(
        self,
        token_fields: dict[str, Any],
        *,
        consent: bool = False,
        metadata: Optional[dict] = None,
    ) -> str:
        """Store the exchanged token payload in the Vault (explicit consent)."""
        secret = json.dumps(token_fields, sort_keys=True)
        return get_credential_vault().store(
            provider=self.provider,
            credential_type=self.credential_type,
            secret=secret,
            metadata=metadata,
            consent=consent,
        )


# ----------------------------------------------------------------------
# Slice 7 Execution Gate integration — credential prerequisite resolvers
# ----------------------------------------------------------------------
def credential_missing(provider: str, credential_type: str) -> list[str]:
    """Return ['credential:<provider>:<type>'] when the credential is not
    valid; [] when it is. Registered as a Slice 7 prerequisite resolver."""
    vault = get_credential_vault()
    if vault.has_valid(provider, credential_type):
        return []
    return [f"credential:{provider}:{credential_type}"]


def register_credential_prerequisite(provider: str, credential_type: str, action: str) -> None:
    """Register a credential prerequisite for an action through the canonical
    Slice 7 resolver registry (no parallel path)."""
    from mini_kio.core.execution_boundary import register_prerequisite_resolver

    def _resolver(target: str) -> list[str]:
        return credential_missing(provider, credential_type)

    register_prerequisite_resolver(action, _resolver)


__all__ = [
    "CredentialVault",
    "Credential",
    "CredentialMetadata",
    "OAuthFlowTemplate",
    "get_credential_vault",
    "credential_missing",
    "register_credential_prerequisite",
    "ConsentRequiredError",
    "EmptySecretError",
    "CredentialNotFoundError",
]
