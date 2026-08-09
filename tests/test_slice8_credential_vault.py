"""
Slice 8 (B.2) — Credential Vault Core targeted tests.

Covers the keyring-backed credential store added in mini_kio/core/credential_vault.py:
  - secure backend interaction (keyring round-trip)
  - metadata-only SQLite persistence (no plaintext secret in DB)
  - explicit-consent requirement
  - store/retrieve/revoke/list/has_valid
  - OAuth flow template shape
  - Slice 7 prerequisite integration (blocking gate when credential missing,
    execution allowed when present)
  - mandatory secret-leak proof: TEST_SECRET_DO_NOT_LEAK_123 must appear NOWHERE
"""

import logging
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("KIO_TEST_MODE", "1")

TEST_SECRET = "TEST_SECRET_DO_NOT_LEAK_123"

from mini_kio.core.credential_vault import (
    CredentialVault,
    OAuthFlowTemplate,
    get_credential_vault,
    credential_missing,
    register_credential_prerequisite,
    ConsentRequiredError,
    EmptySecretError,
)
from mini_kio.core.execution_boundary import (
    resolve_prerequisites,
    register_prerequisite_resolver,
)
from mini_kio.core.runtime_response_formatter import _credential_label, format_result


def _fresh_vault() -> CredentialVault:
    """A vault instance with isolated keyring/backend for the test."""
    vault = CredentialVault()
    # Isolate from any pre-existing records: revoke everything we create by id.
    return vault


class KeyringBackendTest(unittest.TestCase):
    def test_keyring_roundtrip(self):
        vault = _fresh_vault()
        cid = vault.store(
            "test_provider",
            "api_key",
            TEST_SECRET,
            consent=True,
        )
        cred = vault.retrieve(cid)
        self.assertIsNotNone(cred)
        self.assertEqual(cred.secret, TEST_SECRET)
        self.assertEqual(cred.provider, "test_provider")
        self.assertEqual(cred.credential_type, "api_key")
        vault.revoke(cid)

    def test_retrieve_after_revoke_is_none(self):
        vault = _fresh_vault()
        cid = vault.store("test_provider", "api_key", TEST_SECRET, consent=True)
        vault.revoke(cid)
        self.assertIsNone(vault.retrieve(cid))
        self.assertFalse(vault.has_valid("test_provider", "api_key"))


class ConsentTest(unittest.TestCase):
    def test_store_requires_explicit_consent(self):
        vault = _fresh_vault()
        with self.assertRaises(ConsentRequiredError):
            vault.store("test_provider", "api_key", TEST_SECRET, consent=False)
        # Without consent nothing may persist.
        self.assertFalse(vault.has_valid("test_provider", "api_key"))

    def test_store_empty_secret_raises(self):
        vault = _fresh_vault()
        with self.assertRaises(EmptySecretError):
            vault.store("test_provider", "api_key", "", consent=True)
        with self.assertRaises(EmptySecretError):
            vault.store("test_provider", "api_key", "   ", consent=True)


class MetadataPersistenceTest(unittest.TestCase):
    def test_list_never_contains_secret(self):
        vault = _fresh_vault()
        cid = vault.store(
            "test_provider",
            "api_key",
            TEST_SECRET,
            metadata={"scope": "read"},
            consent=True,
        )
        entries = vault.list()
        self.assertTrue(any(e.credential_id == cid for e in entries))
        for entry in entries:
            raw = str(entry)
            self.assertNotIn(TEST_SECRET, raw)
            self.assertNotIn("secret", raw.lower())
        vault.revoke(cid)

    def test_sqlite_row_has_no_secret(self):
        vault = _fresh_vault()
        cid = vault.store("test_provider", "api_key", TEST_SECRET, consent=True)
        try:
            from mini_kio.backend.db import db_session
            from mini_kio.backend.models import CredentialRecordModel

            with db_session() as session:
                row = (
                    session.query(CredentialRecordModel)
                    .filter(CredentialRecordModel.credential_id == cid)
                    .first()
                )
                self.assertIsNotNone(row)
                # Metadata row must NOT carry the secret anywhere.
                row_blob = str(row.__dict__)
                self.assertNotIn(TEST_SECRET, row_blob)
                self.assertNotIn("secret", str(row.metadata_json))
        finally:
            vault.revoke(cid)

    def test_metadata_fields_present(self):
        vault = _fresh_vault()
        cid = vault.store(
            "test_provider",
            "oauth2",
            TEST_SECRET,
            metadata={"scope": "read write"},
            consent=True,
        )
        entries = vault.list()
        entry = next(e for e in entries if e.credential_id == cid)
        self.assertEqual(entry.provider, "test_provider")
        self.assertEqual(entry.credential_type, "oauth2")
        self.assertEqual(entry.metadata.get("scope"), "read write")
        self.assertTrue(entry.consent_recorded)
        self.assertGreater(entry.created_at, 0)
        vault.revoke(cid)

    def test_expires_at_enforced(self):
        from datetime import datetime, timedelta, timezone

        vault = _fresh_vault()
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        cid = vault.store(
            "test_provider",
            "api_key",
            TEST_SECRET,
            expires_at=past,
            consent=True,
        )
        self.assertIsNone(vault.retrieve(cid))
        self.assertFalse(vault.has_valid("test_provider", "api_key"))
        vault.revoke(cid)


class CredentialReprRedactionTest(unittest.TestCase):
    def test_repr_redacts_secret(self):
        from mini_kio.core.credential_vault import Credential

        cred = Credential(
            credential_id="abc",
            provider="p",
            credential_type="t",
            secret=TEST_SECRET,
        )
        self.assertNotIn(TEST_SECRET, repr(cred))
        self.assertIn("redacted", repr(cred))


class OAuthTemplateTest(unittest.TestCase):
    def test_auth_url_builder(self):
        tpl = OAuthFlowTemplate(provider="test", auth_url_builder=lambda state: f"https://auth.test/?state={state}")
        self.assertEqual(tpl.build_auth_url("s1"), "https://auth.test/?state=s1")

    def test_exchange_code(self):
        tpl = OAuthFlowTemplate(provider="test", token_exchanger=lambda code: {"access_token": f"tok_{code}", "refresh_token": "r"})
        fields = tpl.exchange_code("c1")
        self.assertEqual(fields["access_token"], "tok_c1")

    def test_store_tokens_requires_consent(self):
        tpl = OAuthFlowTemplate(provider="test")
        with self.assertRaises(ConsentRequiredError):
            tpl.store_tokens({"access_token": TEST_SECRET}, consent=False)


class PrerequisiteIntegrationTest(unittest.TestCase):
    def test_credential_missing_reports_blocking(self):
        vault = _fresh_vault()
        missing = credential_missing("no_such_provider", "api_key")
        self.assertIn("credential:no_such_provider:api_key", missing)

    def test_credential_present_returns_empty(self):
        vault = _fresh_vault()
        cid = vault.store("test_provider", "api_key", TEST_SECRET, consent=True)
        try:
            self.assertEqual(credential_missing("test_provider", "api_key"), [])
        finally:
            vault.revoke(cid)

    def test_registered_resolver_flows_through_gate(self):
        # Register a credential prerequisite for an action, then confirm
        # resolve_prerequisites reports it blocking when missing.
        register_credential_prerequisite("missing_provider", "api_key", "open_app")
        try:
            gate = resolve_prerequisites("open_app", "anything")
            self.assertIn("credential:missing_provider:api_key", gate.missing)
            self.assertTrue(gate.blocks)
        finally:
            from mini_kio.core import execution_boundary

            execution_boundary._PREREQUISITE_RESOLVERS.pop("open_app", None)

    def test_registered_resolver_satisfied_when_credential_stored(self):
        vault = _fresh_vault()
        cid = vault.store("test_provider", "api_key", TEST_SECRET, consent=True)
        register_credential_prerequisite("test_provider", "api_key", "open_app")
        try:
            gate = resolve_prerequisites("open_app", "anything")
            self.assertEqual(gate.missing, [])
            self.assertFalse(gate.blocks)
        finally:
            from mini_kio.core import execution_boundary

            execution_boundary._PREREQUISITE_RESOLVERS.pop("open_app", None)
            vault.revoke(cid)

    def test_fail_closed_execution_when_credential_missing(self):
        """A missing credential prerequisite blocks execute_action (Slice 7)."""
        from mini_kio.core import execution_boundary

        handler_called = []
        original = execution_boundary.STATIC_ACTION_TABLE["open_app"]["handler"]

        def fake_handler(target):
            handler_called.append(target)
            return {"success": True, "message": "SHOULD NOT RUN"}

        execution_boundary.STATIC_ACTION_TABLE["open_app"]["handler"] = fake_handler
        register_credential_prerequisite("missing_provider", "api_key", "open_app")
        with mock.patch.object(execution_boundary, "_in_test_mode", return_value=False):
            try:
                result = execution_boundary.execute_action("open_app", "telegram")
            finally:
                execution_boundary.STATIC_ACTION_TABLE["open_app"]["handler"] = original
                execution_boundary._PREREQUISITE_RESOLVERS.pop("open_app", None)

        self.assertEqual(handler_called, [])
        self.assertFalse(result.get("success"))
        self.assertTrue(result.get("blocked"))
        self.assertEqual(result.get("failure_class"), "missing_prerequisite")
        self.assertIn("credential:missing_provider:api_key", result.get("prerequisite_gate", {}).get("missing", []))


class ResponseRenderingTest(unittest.TestCase):
    def test_credential_prerequisite_renders_naturally(self):
        details = {
            "success": False,
            "message": "no",
            "prerequisite_gate": {
                "action": "open_app",
                "missing": ["credential:google:oauth2"],
                "severity": "blocking",
            },
        }
        text = format_result("open_app", "calendar", False, details)
        self.assertIn("I need", text)
        self.assertIn("Google", text)
        self.assertNotIn("credential:", text)
        self.assertNotIn("google:oauth2", text)
        self.assertNotIn("prerequisite_gate", text)

    def test_credential_label_mapping(self):
        self.assertEqual(
            _credential_label("credential:telegram:api_hash"),
            "your Telegram api hash credentials",
        )
        self.assertEqual(_credential_label("browser_backend"), "")


class SecretLeakProofTest(unittest.TestCase):
    """Mandatory: the synthetic secret must NEVER appear in logs, traces,
    responses, SQLite rows, or test capture."""

    def test_secret_absent_from_log_capture(self):
        import io

        vault = _fresh_vault()
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger("mini_kio.core.credential_vault")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        try:
            cid = vault.store("leak_probe", "api_key", TEST_SECRET, metadata={"k": TEST_SECRET[:10]}, consent=True)
            vault.retrieve(cid)
            vault.list()
            vault.has_valid("leak_probe", "api_key")
            vault.revoke(cid)
        finally:
            logger.removeHandler(handler)

        captured = log_capture.getvalue()
        self.assertNotIn(TEST_SECRET, captured)

    def test_secret_absent_from_user_response(self):
        text = format_result(
            "open_app", "x", False,
            {"prerequisite_gate": {"action": "open_app", "missing": ["credential:google:oauth2"], "severity": "blocking"}},
        )
        self.assertNotIn(TEST_SECRET, text)

    def test_secret_absent_from_credential_repr_and_metadata(self):
        vault = _fresh_vault()
        cid = vault.store("leak_probe", "api_key", TEST_SECRET, consent=True)
        try:
            cred = vault.retrieve(cid)
            self.assertNotIn(TEST_SECRET, repr(cred))
            self.assertNotIn(TEST_SECRET, str(vault.list()))
        finally:
            vault.revoke(cid)


if __name__ == "__main__":
    unittest.main()
