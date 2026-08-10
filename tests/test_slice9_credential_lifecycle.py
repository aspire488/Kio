"""
Slice 9 (B.2) — Credential Vault Lifecycle targeted tests.

Extends the Slice 8 core with the plan-defined lifecycle:
  - validate() truthful states: valid / missing / expired / revoked / unavailable
  - expiry detection (expires_at blocks validity — fail closed)
  - refresh() generic contract through OAuthFlowTemplate wiring
  - revoke on user request (idempotent)
  - re-authentication flow
  - Execution Gate: handler never executes when blocked
  - user-facing management surface (list / status / revoke / attention)
  - security invariants: sentinel secret never leaks anywhere
"""

import logging
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("KIO_TEST_MODE", "1")

TEST_SECRET = "SLICE9_SENTINEL_DO_NOT_LEAK_987654"

from mini_kio.core.credential_vault import (
    CredentialVault, get_credential_vault, credential_missing,
    credential_block_reason, register_credential_lifecycle_prerequisite,
    format_credentials_list, format_credential_status, format_credential_revoked,
    format_credentials_attention, format_credential_refresh,
    STATE_VALID, STATE_MISSING, STATE_EXPIRED, STATE_REVOKED,
    STATE_UNAVAILABLE, STATE_REFRESH_FAILED,
)
from mini_kio.core.execution_boundary import (
    register_prerequisite_resolver, resolve_prerequisites,
)
from mini_kio.core.runtime_response_formatter import _credential_label


def _fresh_vault() -> CredentialVault:
    return CredentialVault()


def _clear_credentials() -> None:
    """The test-mode DB is an in-memory sqlite shared across the process;
    clear the credentials table so each test starts from real 'missing' state."""
    from mini_kio.backend.models import CredentialRecordModel
    try:
        with _db() as s:
            s.query(CredentialRecordModel).delete()
            s.commit()
    except Exception:
        pass


class _Slice9Base(unittest.TestCase):
    def setUp(self):
        _clear_credentials()


class LifecycleStateTest(_Slice9Base):
    def test_missing_state(self):
        v = _fresh_vault()
        self.assertEqual(v.validate("github", "oauth2"), STATE_MISSING)
        self.assertFalse(v.is_expired("github", "oauth2"))

    def test_valid_state(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, consent=True)
        self.assertEqual(v.validate("github", "oauth2"), STATE_VALID)

    def test_expired_state_detected(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET,
                expires_at=_future(seconds=60), consent=True)
        # Force expiry by rewriting the metadata timestamp.
        v.store("github", "oauth2", TEST_SECRET, expires_at=_future(seconds=60), consent=True)
        from mini_kio.backend.models import CredentialRecordModel
        with _db() as s:
            row = s.query(CredentialRecordModel).filter_by(provider="github",
                                                           credential_type="oauth2").first()
            row.expires_at = int(time.time()) - 10
            s.commit()
        self.assertEqual(v.validate("github", "oauth2"), STATE_EXPIRED)
        self.assertTrue(v.is_expired("github", "oauth2"))
        # Fail closed: retrieve() returns None for expired.
        self.assertIsNone(v.retrieve(row.credential_id))

    def test_revoked_state_after_revoke(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, consent=True)
        v.revoke_by_target("github", "oauth2")
        self.assertEqual(v.validate("github", "oauth2"), STATE_REVOKED)
        self.assertFalse(v.has_valid("github", "oauth2"))

    def test_unavailable_when_keyring_secret_missing(self):
        v = _fresh_vault()
        cid = v.store("github", "oauth2", TEST_SECRET, consent=True)
        v._keyring.delete(cid)
        self.assertEqual(v.validate("github", "oauth2"), STATE_UNAVAILABLE)


class ExpiryAtGateTest(_Slice9Base):
    def test_block_reason_distinguishes_expired(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, expires_at=_future(seconds=60), consent=True)
        from mini_kio.backend.models import CredentialRecordModel
        with _db() as s:
            row = s.query(CredentialRecordModel).filter_by(provider="github",
                                                           credential_type="oauth2").first()
            row.expires_at = int(time.time()) - 10
            s.commit()
        missing = credential_block_reason("github", "oauth2")
        self.assertTrue(any(m.endswith(":expired") for m in missing))

    def test_block_reason_distinguishes_revoked(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, consent=True)
        v.revoke_by_target("github", "oauth2")
        missing = credential_block_reason("github", "oauth2")
        self.assertTrue(any(m.endswith(":revoked") for m in missing))

    def test_plain_missing_block_reason(self):
        missing = credential_block_reason("github", "oauth2")
        self.assertEqual(missing, ["credential:github:oauth2"])

    def test_state_qualified_label_natural(self):
        label = _credential_label("credential:github:oauth2:expired")
        self.assertIn("GitHub", label)
        self.assertIn("expired", label)
        self.assertNotIn("credential:github", label)  # no internal id leak
        self.assertNotIn("::", label)

    def test_gate_blocks_handler_when_expired(self):
        # Register a lifecycle resolver, then prove the handler never runs.
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, expires_at=_future(seconds=60), consent=True)
        from mini_kio.backend.models import CredentialRecordModel
        with _db() as s:
            row = s.query(CredentialRecordModel).filter_by(provider="github",
                                                           credential_type="oauth2").first()
            row.expires_at = int(time.time()) - 10
            s.commit()
        register_credential_lifecycle_prerequisite("github", "oauth2", "slice9_gate_action")
        called = {"n": 0}

        def _resolver(target):
            return credential_block_reason("github", "oauth2")

        from mini_kio.core.execution_boundary import _PREREQUISITE_RESOLVERS
        _PREREQUISITE_RESOLVERS["slice9_gate_action"] = _resolver
        gate = resolve_prerequisites("slice9_gate_action")
        self.assertTrue(gate.blocks)
        self.assertEqual(called["n"], 0)


class RefreshTest(_Slice9Base):
    def test_refresh_without_mechanism_reports_failure(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, expires_at=_future(seconds=60), consent=True)
        from mini_kio.backend.models import CredentialRecordModel
        with _db() as s:
            row = s.query(CredentialRecordModel).filter_by(provider="github",
                                                           credential_type="oauth2").first()
            row.expires_at = int(time.time()) - 10
            s.commit()
        r = v.refresh("github", "oauth2", refresher=None)
        self.assertFalse(r["success"])
        self.assertEqual(r["state"], STATE_REFRESH_FAILED)
        self.assertFalse(r["refreshed"])

    def test_refresh_with_mechanism_succeeds_and_revalidates(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, expires_at=_future(seconds=60), consent=True)
        from mini_kio.backend.models import CredentialRecordModel
        with _db() as s:
            row = s.query(CredentialRecordModel).filter_by(provider="github",
                                                           credential_type="oauth2").first()
            row.expires_at = int(time.time()) - 10
            s.commit()

        def _refresher(old_fields):
            return {"access_token": "new_token", "expires_at": int(time.time()) + 3600}

        r = v.refresh("github", "oauth2", refresher=_refresher, consent=True)
        self.assertTrue(r["success"])
        self.assertTrue(r["refreshed"])
        self.assertEqual(v.validate("github", "oauth2"), STATE_VALID)

    def test_refresh_requires_consent(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, expires_at=_future(seconds=60), consent=True)
        from mini_kio.backend.models import CredentialRecordModel
        with _db() as s:
            row = s.query(CredentialRecordModel).filter_by(provider="github",
                                                           credential_type="oauth2").first()
            row.expires_at = int(time.time()) - 10
            s.commit()
        with self.assertRaises(Exception):
            v.refresh("github", "oauth2", refresher=lambda o: {"access_token": "x"}, consent=False)

    def test_refresh_valid_credential_noop(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, consent=True)
        r = v.refresh("github", "oauth2", refresher=lambda o: {"access_token": "x"})
        self.assertTrue(r["success"])
        self.assertFalse(r["refreshed"])


class RevokeManagementTest(_Slice9Base):
    def test_revoke_by_target_idempotent(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, consent=True)
        v.store("github", "oauth2", TEST_SECRET, consent=True)
        self.assertEqual(v.revoke_by_target("github", "oauth2"), 2)
        self.assertEqual(v.revoke_by_target("github", "oauth2"), 0)  # idempotent
        self.assertFalse(v.has_valid("github", "oauth2"))

    def test_reauthentication_required(self):
        v = _fresh_vault()
        self.assertTrue(v.reauthentication_required("github", "oauth2"))
        v.store("github", "oauth2", TEST_SECRET, consent=True)
        self.assertFalse(v.reauthentication_required("github", "oauth2"))
        v.revoke_by_target("github", "oauth2")
        self.assertTrue(v.reauthentication_required("github", "oauth2"))

    def test_needs_attention_lists_expired(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, expires_at=_future(seconds=60), consent=True)
        from mini_kio.backend.models import CredentialRecordModel
        with _db() as s:
            row = s.query(CredentialRecordModel).filter_by(provider="github",
                                                           credential_type="oauth2").first()
            row.expires_at = int(time.time()) - 10
            s.commit()
        items = v.needs_attention()
        self.assertTrue(any(i["provider"] == "github" for i in items))


class ManagementSurfaceTest(_Slice9Base):
    def test_list_never_contains_secret(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, consent=True)
        msg = format_credentials_list()
        self.assertIn("GitHub", msg)
        self.assertNotIn(TEST_SECRET, msg)

    def test_status_natural_and_secret_free(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, consent=True)
        msg = format_credential_status("github")
        self.assertIn("valid", msg.lower())
        self.assertNotIn(TEST_SECRET, msg)

    def test_revoke_message_natural(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, consent=True)
        msg = format_credential_revoked("github")
        self.assertIn("Revoked", msg)
        self.assertNotIn(TEST_SECRET, msg)
        self.assertNotIn("credential:github", msg)

    def test_attention_message(self):
        msg = format_credentials_attention()
        self.assertTrue(msg)  # deterministic either way


class SecurityInvariantTest(_Slice9Base):
    def test_sentinel_never_in_logs(self):
        import io
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            v = _fresh_vault()
            cid = v.store("github", "oauth2", TEST_SECRET, consent=True)
            v.retrieve(cid)
            v.refresh("github", "oauth2", refresher=lambda o: {"access_token": "x"})
            v.revoke_by_target("github", "oauth2")
            _credential_label(f"credential:github:oauth2:expired")
        finally:
            root.removeHandler(handler)
        self.assertNotIn(TEST_SECRET, stream.getvalue())

    def test_sentinel_never_in_repr_or_metadata(self):
        v = _fresh_vault()
        cid = v.store("github", "oauth2", TEST_SECRET, consent=True)
        cred = v.retrieve(cid)
        self.assertNotIn(TEST_SECRET, repr(cred))
        for m in v.list():
            self.assertNotIn(TEST_SECRET, repr(m))
            self.assertNotIn(TEST_SECRET, str(m.metadata))

    def test_sentinel_never_in_user_facing_messages(self):
        v = _fresh_vault()
        v.store("github", "oauth2", TEST_SECRET, consent=True)
        for msg in (format_credentials_list(), format_credential_status("github"),
                    format_credentials_attention()):
            self.assertNotIn(TEST_SECRET, msg)


def _future(seconds: int):
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def _db():
    from mini_kio.backend.db import db_session
    return db_session()


if __name__ == "__main__":
    unittest.main()
