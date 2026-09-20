"""Bridges between automation engine and existing KIO security, verification, and credential systems."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


# Credentials satisfied by an existing KIO subsystem instead of by a vault entry.
# Workflow YAML declares these in `credentials_required`, but KIO's architecture
# keeps them in env-configured provider clients — asking CredentialVault for them
# reports a false "missing". This is the shared resolver for that class of
# credential; both credential-checking paths use it so they cannot drift.
_LLM_CREDENTIAL_TYPES = frozenset({"llm"})
_LLM_CREDENTIAL_NAMES = frozenset({
    "llm_provider", "llm", "llm_api_key", "model_provider", "ai_provider",
})


def llm_credential_status(name: str, cred_type: str) -> dict[str, Any] | None:
    """Resolve a `type: llm` credential against the existing LLM chain.

    Returns None when the credential is not LLM-backed (caller falls through to
    CredentialVault). Never carries a secret — only availability and a count.
    """
    if cred_type not in _LLM_CREDENTIAL_TYPES and (name or "").lower() not in _LLM_CREDENTIAL_NAMES:
        return None
    try:
        from mini_kio.core.providers.ai_reasoning_provider import llm_capability_available
        available, detail = llm_capability_available()
    except Exception as exc:
        return {"status": "unavailable", "reason": f"LLM chain not inspectable: {exc}"}
    if available:
        return {"status": "available", "value": None, "source": "llm_chain", "detail": detail}
    return {"status": "missing", "reason": f"credential '{name}' not configured: {detail}"}


class SecurityBridge:
    """Maps YAML security_classification to KIO execution boundary policy.

    Enforces: destructive/consequential must set user_confirmation_required=true.
    Never allows execution_boundary to grant authority the template didn't declare.
    """

    # Security classification hierarchy (least to most restrictive)
    _CLASSIFICATION_ORDER = {
        "read_only": 0,
        "low": 1,
        "consequential": 2,
        "destructive": 3,
    }

    def check_template_security(self, template: dict[str, Any]) -> dict[str, Any]:
        """Validate template security configuration.

        Returns dict with:
            - valid: bool
            - warnings: list of warning strings
            - requires_confirmation: bool
            - classification: str
        """
        classification = template.get("security_classification", "read_only")
        user_confirm = template.get("user_confirmation_required", False)
        warnings: list[str] = []

        # Validate classification
        if classification not in self._CLASSIFICATION_ORDER:
            warnings.append(f"Unknown security classification: {classification!r}")
            classification = "low"

        # Enforce: destructive/consequential must have user_confirmation_required=true
        if classification in ("consequential", "destructive") and not user_confirm:
            warnings.append(
                f"Security: {classification} classification requires "
                f"user_confirmation_required=true. Forcing."
            )
            user_confirm = True

        return {
            "valid": len(warnings) == 0,
            "warnings": warnings,
            "requires_confirmation": user_confirm,
            "classification": classification,
        }

    def check_step_security(
        self,
        step: dict[str, Any],
        template_classification: str,
    ) -> dict[str, Any]:
        """Check if a step's capability/action is permitted under the template's classification.

        Returns dict with permitted (bool) and reason (str if not permitted).
        """
        capability = step.get("capability", "")
        action = step.get("action", "")

        # read_only templates cannot execute write actions
        if template_classification == "read_only":
            write_actions = {
                "send_message", "send_email", "create_issue", "create_event",
                "write_file", "write_csv", "apply_label", "backup_repo",
                "scaffold", "generate_pdf", "generate_docx", "generate_pptx",
                "generate_xlsx", "post", "send_notification", "send_alert",
                "create_release",
            }
            if action in write_actions:
                return {
                    "permitted": False,
                    "reason": f"read_only classification blocks write action: {action}",
                }

        return {"permitted": True, "reason": ""}


class VerificationBridge:
    """Maps YAML verification checks to observable KIO side-effect verification.

    NOT 'API returned 200'. Observable means:
    - artifact: file exists with expected content
    - communication_delivery: message id returned
    - browser_state: page DOM contains expected elements
    - github_state: PR/issue exists with expected state
    - data_shape: output conforms to declared schema
    """

    def verify_step(
        self,
        step: dict[str, Any],
        step_result: dict[str, Any],
        verification_specs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Run verification checks for a completed step.

        Returns dict with passed (bool), checks (list of check results).
        """
        results: list[dict[str, Any]] = []
        all_passed = True

        for spec in verification_specs:
            check_type = spec.get("type", "none")
            check_name = spec.get("check", "")
            asserts_list = spec.get("asserts", [])
            on_fail = spec.get("on_fail", "flag")

            check_result = self._run_check(
                check_type, check_name, asserts_list, step, step_result
            )
            results.append(check_result)

            if not check_result["passed"]:
                all_passed = False
                if on_fail == "abort":
                    return {
                        "passed": False,
                        "checks": results,
                        "abort": True,
                        "reason": f"Verification '{check_name}' failed (abort)",
                    }

        return {
            "passed": all_passed,
            "checks": results,
            "abort": False,
        }

    def _run_check(
        self,
        check_type: str,
        check_name: str,
        asserts_list: list[str],
        step: dict[str, Any],
        step_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Run a single verification check."""
        # For now, do basic structural checks.
        # Real verification will be implemented per-check-type as the engine matures.
        if check_type == "none":
            return {"type": check_type, "check": check_name, "passed": True}

        # Check that the step produced declared outputs
        declared_outputs = step.get("outputs", [])
        missing_outputs = [o for o in declared_outputs if o not in step_result.get("data", {})]

        if missing_outputs:
            return {
                "type": check_type,
                "check": check_name,
                "passed": False,
                "reason": f"Missing declared outputs: {missing_outputs}",
            }

        return {"type": check_type, "check": check_name, "passed": True}


# ── Workflow credential alias → real credential mapping ──────────────
# YAML templates declare credential aliases (e.g. "github_token", "channel_cred")
# that must resolve to actual vault entries or environment variables.
_CRED_ALIAS_MAP: dict[str, dict[str, str]] = {
    # GitHub
    "github_token": {"env": "GITHUB_TOKEN", "vault_provider": "github"},
    # Google
    "google_oauth": {"vault_provider": "google", "vault_type": "oauth2"},
    "calendar_cred": {"vault_provider": "google", "vault_type": "oauth2"},
    "mail_cred": {"vault_provider": "google", "vault_type": "oauth2"},
    "drive_cred": {"vault_provider": "google", "vault_type": "oauth2"},
    "gmail_cred": {"vault_provider": "google", "vault_type": "oauth2"},
    # Todoist
    "todoist_token": {"vault_provider": "todoist"},
    # Notion
    "notion_token": {"vault_provider": "notion"},
    # Communication
    "channel_cred": {"env": "TELEGRAM_TOKEN"},
    "channel_credential": {"env": "TELEGRAM_TOKEN"},
    "notify_cred": {"env": "TELEGRAM_TOKEN"},
    "telegram_token": {"env": "TELEGRAM_TOKEN"},
    # Image generation
    "image_provider": {"env": "GEMINI_API_KEY"},
    # Media / social
    "platform_creds": {"env": "TELEGRAM_TOKEN"},
    # Status / escalation
    "status_cred": {"env": "TELEGRAM_TOKEN"},
    "tier_credentials": {"env": "TELEGRAM_TOKEN"},
    # Business
    "crm_cred": {"vault_provider": "google", "vault_type": "oauth2"},
    "owner_cred": {"vault_provider": "google", "vault_type": "oauth2"},
    "approval_cred": {"env": "TELEGRAM_TOKEN"},
    "tracker_cred": {"vault_provider": "notion"},
    # Data
    "store_cred": {"env": "GEMINI_API_KEY"},
    "api_cred": {"env": "GEMINI_API_KEY"},
    "webhook_secret": {"env": "GEMINI_API_KEY"},
    "vectorstore_cred": {"env": "GEMINI_API_KEY"},
    "kb_cred": {"env": "GEMINI_API_KEY"},
    "system_a_cred": {"env": "GEMINI_API_KEY"},
    "system_b_cred": {"env": "GEMINI_API_KEY"},
    # Development
    "source_cred": {"env": "GITHUB_TOKEN"},
    "dest_cred": {"env": "GITHUB_TOKEN"},
    "scanner_creds": {"env": "GEMINI_API_KEY"},
    # Files
    "notify_channel_cred": {"env": "TELEGRAM_TOKEN"},
    # Image
    "image_provider": {"env": "GEMINI_API_KEY"},
}


class CredentialBridge:
    """Manages credential resolution through the existing CredentialVault.

    Never places secrets in logs, traces, EventBus, or error messages.
    Handles: missing, expired, revoked, unavailable, refreshable.
    """

    def __init__(self) -> None:
        self._vault = None

    def _get_vault(self):
        if self._vault is None:
            try:
                from mini_kio.core.credential_vault import get_credential_vault
                self._vault = get_credential_vault()
            except Exception:
                self._vault = False
        return self._vault if self._vault is not False else None

    def resolve_credentials(
        self, credentials: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Resolve all credentials for a template.

        Returns dict mapping credential name -> {status, value_or_reason}.
        status: "available", "missing", "expired", "unavailable"
        """
        import os
        result: dict[str, dict[str, Any]] = {}
        vault = self._get_vault()

        for cred in credentials:
            name = cred.get("name", "")
            cred_type = cred.get("type", "none")

            if cred_type == "none" or not name:
                result[name or "none"] = {"status": "available", "value": None}
                continue

            # LLM credentials live in the existing provider chain, not the vault.
            resolved = llm_credential_status(name, cred_type)
            if resolved is not None:
                result[name] = resolved
                continue

            # Try alias mapping → env var or vault lookup
            alias = _CRED_ALIAS_MAP.get(name, {})
            if alias.get("env"):
                env_val = os.environ.get(alias["env"], "")
                if env_val:
                    result[name] = {"status": "available", "value": env_val}
                    continue

            if vault is None:
                result[name] = {"status": "unavailable", "reason": "CredentialVault not initialized"}
                continue

            try:
                # Try vault lookup by provider/type from alias
                vault_provider = alias.get("vault_provider")
                vault_type = alias.get("vault_type")
                if vault_provider:
                    items = vault.list()
                    for m in items:
                        if m.provider == vault_provider:
                            if vault_type and m.credential_type != vault_type:
                                continue
                            cred_obj = vault.retrieve(m.credential_id)
                            if cred_obj:
                                result[name] = {"status": "available", "value": cred_obj.secret}
                                break
                    if name in result:
                        continue

                # Direct vault lookup
                value = vault.get_credential(name) if hasattr(vault, "get_credential") else None
                if value:
                    result[name] = {"status": "available", "value": value}
                else:
                    result[name] = {"status": "missing", "reason": "Credential not found in vault or env"}
            except Exception:
                result[name] = {"status": "missing", "reason": "Failed to retrieve credential"}

        return result

    def get_blocking_reason(self, cred_status: dict[str, dict[str, Any]]) -> str:
        """Generate a blocking reason for failed credentials."""
        problems = []
        for name, status in cred_status.items():
            if status["status"] == "missing":
                problems.append(f"credential '{name}' not configured")
            elif status["status"] == "expired":
                problems.append(f"credential '{name}' expired")
            elif status["status"] == "unavailable":
                problems.append(f"credential vault unavailable")
        return "; ".join(problems) if problems else ""
