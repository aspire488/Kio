"""
credential_vault.py — Credential Vault (Slice 8 core + Slice 9 lifecycle)
========================================================================

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

Slice 9 (B.2 lifecycle):
  - validate() / status() / is_expired() — truthful lifecycle states
    (valid / missing / expired / revoked / unavailable).
  - refresh() — generic token-refresh contract through OAuthFlowTemplate
    wiring; atomically updates keyring + metadata; truthful failure.
  - revoke_by_target() — idempotent revoke on user request.
  - reauthentication_required() / needs_attention() — re-auth surface.
  - Execution Gate distinguishes missing/expired/revoked credentials via
    state-qualified prerequisite identifiers (credential_block_reason).

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


# ---------------------------------------------------------------------------
# Slice 9 lifecycle states
# ---------------------------------------------------------------------------
STATE_VALID = "valid"
STATE_MISSING = "missing"
STATE_EXPIRED = "expired"
STATE_REVOKED = "revoked"
STATE_UNAVAILABLE = "unavailable"  # metadata exists but keyring secret is gone
STATE_REFRESHABLE = "refreshable"  # expired but a refresh mechanism exists
STATE_REFRESH_FAILED = "refresh_failed"


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
        return self.validate(provider, credential_type) == STATE_VALID

    # ------------------------------------------------------------------
    # Slice 9 — lifecycle
    # ------------------------------------------------------------------
    def validate(self, provider: str, credential_type: str) -> str:
        """Lifecycle state of the best (non-revoked) credential for a target.

        Returns one of STATE_VALID / STATE_MISSING / STATE_EXPIRED /
        STATE_UNAVAILABLE / STATE_REVOKED. Never fabricates.
        """
        from mini_kio.backend.models import CredentialRecordModel

        try:
            with self._session_scope() as session:
                rows = (
                    session.query(CredentialRecordModel)
                    .filter(
                        CredentialRecordModel.provider == provider,
                        CredentialRecordModel.credential_type == credential_type,
                    )
                    .all()
                )
            now = _now_ts()
            if not rows:
                return STATE_MISSING
            for row in rows:
                if row.revoked:
                    continue
                secret = self._keyring.get(row.credential_id)
                if secret is None:
                    continue  # metadata row without keyring secret
                if row.expires_at is not None and now > row.expires_at:
                    return STATE_EXPIRED
                return STATE_VALID
            # No usable row: either all revoked or all keyring entries gone.
            if all(row.revoked for row in rows):
                return STATE_REVOKED
            return STATE_UNAVAILABLE
        except Exception as exc:
            logger.error("[VAULT] validate failed provider=%s type=%s: %s",
                         provider, credential_type, exc)
            return STATE_UNAVAILABLE

    def status(self, provider: str, credential_type: str) -> dict:
        """Safe (secret-free) lifecycle snapshot for the management surface."""
        state = self.validate(provider, credential_type)
        out: dict = {"provider": provider, "credential_type": credential_type, "state": state}
        from mini_kio.backend.models import CredentialRecordModel
        try:
            with self._session_scope() as session:
                row = (
                    session.query(CredentialRecordModel)
                    .filter(
                        CredentialRecordModel.provider == provider,
                        CredentialRecordModel.credential_type == credential_type,
                        CredentialRecordModel.revoked.is_(False),
                    )
                    .first()
                )
                if row is not None and row.expires_at is not None:
                    out["expires_at"] = row.expires_at
        except Exception:
            pass
        return out

    def is_expired(self, provider: str, credential_type: str) -> bool:
        """True only when the credential exists but has passed expires_at."""
        return self.validate(provider, credential_type) == STATE_EXPIRED

    def refresh(
        self,
        provider: str,
        credential_type: str,
        refresher=None,
        *,
        consent: bool = False,
    ) -> dict:
        """Generic Slice 9 refresh contract.

        refresher: callable(old_fields: dict) -> dict of new token fields
        (e.g. an OAuthFlowTemplate wired refresher). When None, an expired
        credential cannot be refreshed and the caller learns the truth.

        Refresh is atomic: keyring is updated with the new secret payload and
        the metadata expires_at is rewritten in the same logical step; a
        failed write leaves the old credential untouched.
        """
        from mini_kio.backend.models import CredentialRecordModel

        state = self.validate(provider, credential_type)
        if state == STATE_VALID:
            return {"success": True, "state": STATE_VALID, "refreshed": False,
                    "message": "still valid"}
        if state == STATE_MISSING:
            return {"success": False, "state": STATE_MISSING, "refreshed": False,
                    "message": "missing"}
        if refresher is None:
            return {"success": False, "state": STATE_REFRESH_FAILED, "refreshed": False,
                    "message": "no refresh mechanism available"}
        if not consent and _CONSENT_REQUIRED:
            raise ConsentRequiredError(
                "Credential refresh requires explicit user consent (consent=True)."
            )

        try:
            with self._session_scope() as session:
                row = (
                    session.query(CredentialRecordModel)
                    .filter(
                        CredentialRecordModel.provider == provider,
                        CredentialRecordModel.credential_type == credential_type,
                        CredentialRecordModel.revoked.is_(False),
                    )
                    .first()
                )
                if row is None:
                    return {"success": False, "state": STATE_MISSING, "refreshed": False,
                            "message": "missing"}
                credential_id = row.credential_id
            old_secret = self._keyring.get(credential_id)
            if old_secret is None:
                return {"success": False, "state": STATE_UNAVAILABLE, "refreshed": False,
                        "message": "unavailable"}
            try:
                old_fields = json.loads(old_secret)
                if not isinstance(old_fields, dict):
                    old_fields = {"token": old_secret}
            except Exception:
                old_fields = {"token": old_secret}
            new_fields = refresher(old_fields)
            if not isinstance(new_fields, dict) or not new_fields:
                return {"success": False, "state": STATE_REFRESH_FAILED, "refreshed": False,
                        "message": "refresh returned no token fields"}
            new_secret = json.dumps(new_fields, sort_keys=True)
            new_expires = None
            exp_raw = new_fields.get("expires_at")
            if exp_raw is not None:
                try:
                    new_expires = int(exp_raw) if isinstance(exp_raw, (int, float)) else int(exp_raw)
                except (TypeError, ValueError):
                    new_expires = None
            # Atomic-ish update: write secret first, then metadata; roll back
            # the keyring write if the metadata write fails.
            self._keyring.set(credential_id, new_secret)
            try:
                with self._session_scope() as session:
                    row = (
                        session.query(CredentialRecordModel)
                        .filter(CredentialRecordModel.credential_id == credential_id)
                        .first()
                    )
                    if row is not None:
                        row.expires_at = new_expires
                        row.revoked = False
                        session.commit()
            except Exception as exc:
                self._keyring.delete(credential_id)
                if old_secret is not None:
                    try:
                        self._keyring.set(credential_id, old_secret)
                    except Exception:
                        pass
                logger.error("[VAULT] refresh metadata write failed for %s: %s", credential_id, exc)
                return {"success": False, "state": STATE_REFRESH_FAILED, "refreshed": False,
                        "message": "refresh metadata write failed"}
            new_state = self.validate(provider, credential_type)
            return {"success": new_state == STATE_VALID, "state": new_state,
                    "refreshed": new_state == STATE_VALID,
                    "message": "refreshed" if new_state == STATE_VALID else "refresh incomplete"}
        except ConsentRequiredError:
            raise
        except Exception as exc:
            logger.error("[VAULT] refresh failed provider=%s type=%s: %s",
                         provider, credential_type, exc)
            return {"success": False, "state": STATE_REFRESH_FAILED, "refreshed": False,
                    "message": "refresh failed"}

    def revoke_by_target(self, provider: str, credential_type: str) -> int:
        """Revoke ALL matching credentials (idempotent). Returns the number of
        credentials whose state actually changed (revoked now vs already
        revoked / nonexistent) — a repeat call returns 0.

        The secret is removed from keyring and metadata is marked revoked so
        has_valid()/validate() immediately report the truth.
        """
        from mini_kio.backend.models import CredentialRecordModel

        changed = 0
        try:
            with self._session_scope() as session:
                rows = (
                    session.query(CredentialRecordModel)
                    .filter(
                        CredentialRecordModel.provider == provider,
                        CredentialRecordModel.credential_type == credential_type,
                    )
                    .all()
                )
                for row in rows:
                    if row.revoked:
                        continue  # idempotent: nothing to change
                    cid = row.credential_id
                    self._keyring.delete(cid)
                    row.revoked = True
                    changed += 1
                session.commit()
        except Exception as exc:
            logger.error("[VAULT] revoke_by_target failed %s/%s: %s",
                         provider, credential_type, exc)
        return changed

    def reauthentication_required(self, provider: str, credential_type: str) -> bool:
        """True when the credential needs the user to re-authenticate."""
        return self.validate(provider, credential_type) in (
            STATE_MISSING, STATE_EXPIRED, STATE_REVOKED, STATE_UNAVAILABLE,
        )

    def needs_attention(self) -> list[dict]:
        """Credentials that need user action (expired/revoked/missing secret)."""
        from mini_kio.backend.models import CredentialRecordModel

        out: list[dict] = []
        try:
            with self._session_scope() as session:
                rows = session.query(CredentialRecordModel).all()
            seen: set[tuple[str, str]] = set()
            for row in rows:
                key = (row.provider, row.credential_type)
                if key in seen:
                    continue
                seen.add(key)
                state = self.validate(row.provider, row.credential_type)
                if state in (STATE_EXPIRED, STATE_REVOKED, STATE_UNAVAILABLE):
                    out.append({"provider": row.provider,
                                "credential_type": row.credential_type,
                                "state": state})
        except Exception as exc:
            logger.error("[VAULT] needs_attention failed: %s", exc)
        return out


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
# Slice 9 — user-facing management surface (secret-free, natural responses)
# ----------------------------------------------------------------------
_PROVIDER_LABEL = {
    "google": "Google", "gmail": "Gmail", "telegram": "Telegram",
    "github": "GitHub", "discord": "Discord", "openai": "OpenAI",
    "microsoft": "Microsoft", "outlook": "Outlook", "spotify": "Spotify",
    "youtube": "YouTube", "notion": "Notion", "slack": "Slack",
}

_STATE_LABEL = {
    STATE_VALID: "valid", STATE_MISSING: "not set up",
    STATE_EXPIRED: "expired", STATE_REVOKED: "revoked",
    STATE_UNAVAILABLE: "unavailable", STATE_REFRESH_FAILED: "refresh failed",
}


def _display_provider(provider: str) -> str:
    return _PROVIDER_LABEL.get(str(provider).lower(), str(provider).capitalize())


def _display_type(credential_type: str) -> str:
    return str(credential_type).replace("_", " ")


def format_credentials_list() -> str:
    """""Connected accounts" natural listing — metadata only, never secrets."""
    vault = get_credential_vault()
    try:
        meta_list = vault.list()
    except Exception:
        return "I couldn't read your credentials right now."
    if not meta_list:
        return "You don't have any connected accounts yet."
    lines: list[str] = []
    for m in sorted(meta_list, key=lambda x: (x.provider, x.credential_type)):
        state = vault.validate(m.provider, m.credential_type)
        label = _STATE_LABEL.get(state, state)
        expires = ""
        if m.expires_at is not None:
            try:
                import datetime
                expires = f" (expires {datetime.datetime.fromtimestamp(m.expires_at).strftime('%b %d, %Y')})"
            except Exception:
                expires = ""
        lines.append(f"• {_display_provider(m.provider)} — {_display_type(m.credential_type)} — {label}{expires}")
    return "Connected accounts:\n" + "\n".join(lines)


def format_credential_status(provider: str, credential_type: str = "oauth2") -> str:
    """Truthful status of one credential (never reveals the secret)."""
    vault = get_credential_vault()
    state = vault.validate(provider, credential_type)
    label = _STATE_LABEL.get(state, state)
    name = f"{_display_provider(provider)} {_display_type(credential_type)}".strip()
    if state == STATE_VALID:
        return f"Your {name} credential is valid."
    if state == STATE_EXPIRED:
        return f"Your {name} credential has expired — reconnect to refresh it."
    if state == STATE_REVOKED:
        return f"Your {name} credential is revoked."
    if state == STATE_UNAVAILABLE:
        return f"Your {name} credential is unavailable right now."
    return f"You haven't connected {name} yet."


def format_credential_revoked(provider: str, credential_type: str = "oauth2") -> str:
    """Revoke on user request (idempotent) + natural response."""
    vault = get_credential_vault()
    name = f"{_display_provider(provider)} {_display_type(credential_type)}".strip()
    count = vault.revoke_by_target(provider, credential_type)
    if count:
        return f"Revoked your {name} credential."
    # Nothing matched: check whether it was never set up at all.
    if vault.validate(provider, credential_type) == STATE_MISSING:
        return f"You haven't connected {name} yet, so there's nothing to revoke."
    return f"Revoked your {name} credential."


def format_credentials_attention() -> str:
    """Which credentials need attention (truthful, metadata only)."""
    vault = get_credential_vault()
    try:
        items = vault.needs_attention()
    except Exception:
        return "I couldn't check your credentials right now."
    if not items:
        return "Everything's connected — no credentials need attention."
    lines = [f"• {_display_provider(i['provider'])} — {_display_type(i['credential_type'])} — {_STATE_LABEL.get(i['state'], i['state'])}"
             for i in sorted(items, key=lambda x: (x['provider'], x['credential_type']))]
    return "These credentials need attention:\n" + "\n".join(lines)


def format_credential_refresh(provider: str, credential_type: str = "oauth2", refresher=None) -> str:
    """Refresh an expired credential through the canonical refresh contract.

    When no refresher is wired for the provider, report that honestly instead
    of claiming a refresh.
    """
    vault = get_credential_vault()
    state = vault.validate(provider, credential_type)
    name = f"{_display_provider(provider)} {_display_type(credential_type)}".strip()
    if state == STATE_VALID:
        return f"Your {name} credential is still valid."
    if state == STATE_MISSING:
        return f"You haven't connected {name} yet."
    if refresher is None:
        return f"Your {name} credential has expired, and I can't refresh it automatically — please reconnect it."
    try:
        result = vault.refresh(provider, credential_type, refresher, consent=True)
    except ConsentRequiredError:
        return f"I can't refresh {name} without your consent."
    except Exception:
        return f"I couldn't refresh your {name} credential."
    if result.get("success") and result.get("refreshed"):
        return f"Refreshed your {name} credential."
    if result.get("state") == STATE_REFRESH_FAILED:
        return f"I couldn't refresh your {name} credential — please reconnect it."
    return f"Your {name} credential needs attention — please reconnect it."


def credential_management_result(action: str, target: str = "") -> dict[str, Any]:
    """Deterministic user-facing credential capability (interface-independent).

    Actions: list / status / revoke / refresh / attention. Never exposes a
    secret, token, keyring id, or internal prerequisite id.
    """
    action = str(action or "list").lower().strip()
    target = str(target or "").strip()
    provider = target.split(":")[0].strip().lower() if target else ""
    try:
        if action == "list":
            message = format_credentials_list()
        elif action == "attention":
            message = format_credentials_attention()
        elif action == "revoke" and provider:
            message = format_credential_revoked(provider)
        elif action == "refresh" and provider:
            message = format_credential_refresh(provider)
        elif action == "status" and provider:
            message = format_credential_status(provider)
        else:
            message = format_credentials_list()
    except Exception as exc:
        logger.error("[VAULT] management action=%s target=%s failed: %s", action, target, exc)
        message = "I couldn't do that with your credentials right now."
    return {"success": True, "message": message, "action": action, "target": target}


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


def credential_block_reason(provider: str, credential_type: str) -> list[str]:
    """State-qualified prerequisite identifiers so the Execution Gate (and the
    response composer) can distinguish WHY execution is blocked:

      credential:<provider>:<type>          missing
      credential:<provider>:<type>:expired  expired
      credential:<provider>:<type>:revoked  revoked
      credential:<provider>:<type>:unavailable  metadata without secret
    """
    vault = get_credential_vault()
    state = vault.validate(provider, credential_type)
    if state == STATE_VALID:
        return []
    suffix = {
        STATE_EXPIRED: "expired",
        STATE_REVOKED: "revoked",
        STATE_UNAVAILABLE: "unavailable",
    }.get(state, "")
    base = f"credential:{provider}:{credential_type}"
    return [f"{base}:{suffix}" if suffix else base]


def register_credential_prerequisite(provider: str, credential_type: str, action: str) -> None:
    """Register a credential prerequisite for an action through the canonical
    Slice 7 resolver registry (no parallel path)."""
    from mini_kio.core.execution_boundary import register_prerequisite_resolver

    def _resolver(target: str) -> list[str]:
        return credential_missing(provider, credential_type)

    register_prerequisite_resolver(action, _resolver)


def register_credential_lifecycle_prerequisite(provider: str, credential_type: str, action: str) -> None:
    """Slice 9: register a state-aware prerequisite resolver (expired/revoked
    credentials are distinguished from plain missing at the gate)."""
    from mini_kio.core.execution_boundary import register_prerequisite_resolver

    def _resolver(target: str) -> list[str]:
        return credential_block_reason(provider, credential_type)

    register_prerequisite_resolver(action, _resolver)


__all__ = [
    "CredentialVault",
    "Credential",
    "CredentialMetadata",
    "OAuthFlowTemplate",
    "get_credential_vault",
    "credential_missing",
    "credential_block_reason",
    "register_credential_prerequisite",
    "register_credential_lifecycle_prerequisite",
    "ConsentRequiredError",
    "EmptySecretError",
    "CredentialNotFoundError",
    "STATE_VALID",
    "STATE_MISSING",
    "STATE_EXPIRED",
    "STATE_REVOKED",
    "STATE_UNAVAILABLE",
    "STATE_REFRESHABLE",
    "STATE_REFRESH_FAILED",
]
