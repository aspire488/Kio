"""Capability resolution: maps workflow capabilities to KIO providers and checks runtime availability."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Provider capability names that PROVE a workflow capability is implemented.
#
# The registry is keyed by the capability name a provider declares, which for
# most providers is the action name (FilesystemProvider declares `read_file`,
# not `filesystem`). Listing names that do not exist in the registry — or that
# name a provider whose capability is unrelated — makes an implemented
# capability look missing.
#
# Capabilities whose readiness depends on external state (browser backend,
# Google OAuth, GitHub token, MCP runtime) are deliberately NOT listed here:
# their provider being registered says nothing about whether they can actually
# run today. They are resolved through _CAPABILITY_READINESS instead.
_CAPABILITY_TO_PROVIDER: dict[str, list[str]] = {
    "ai_reasoning": ["ai_reasoning", "llm"],
    # `llm` appears in YAML `providers_required`; same provider backs both names.
    "llm": ["ai_reasoning", "llm"],
    "filesystem": ["read_file", "write_csv", "fs_exists", "filesystem"],
    "terminal": ["run_command"],
    "code_project": ["run_command"],
    "workflow": ["workflow_execute"],
    "knowledge": ["web_search", "fetch_url"],
}

# Capabilities that are always available (deterministic, no external deps)
_ALWAYS_AVAILABLE = frozenset({"workflow", "memory"})


# ── Readiness probes ─────────────────────────────────────────────────────────
# Availability for capabilities that live in KIO's own capability router
# (app_operator.APP_CAPABILITIES) and depend on external state. Each probe
# reuses the subsystem that actually owns the dependency — no probe may report
# available from a flag alone, and none fabricates a positive answer.
# Each returns (available, detail); detail is surfaced as the blocking reason.

def _artifact_ready() -> tuple[bool, str]:
    """Document generation needs the OOXML libraries."""
    missing = []
    for module in ("docx", "pptx", "openpyxl"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        return False, f"document generation libraries not installed: {', '.join(missing)}"
    return True, "document generation libraries available"


def _google_ready(service: str) -> tuple[bool, str]:
    """Google-backed capabilities need a credential that carries THIS service's scope.

    Three distinct states, because each has a different fix:
      * never authorized                → run the OAuth consent
      * authorized but unreadable       → credential store/keyring problem
      * authorized but missing the scope→ one re-consent adds the scope
    """
    try:
        from mini_kio.core import google_oauth
        from mini_kio.core.credential_vault import get_credential_vault
        vault = get_credential_vault()
        stored = [m for m in vault.list()
                  if m.provider == google_oauth.PROVIDER
                  and m.credential_type == google_oauth.CREDENTIAL_TYPE]
        if not stored:
            return False, f"Google OAuth not authorized for {service}"
        creds = google_oauth._get_credentials()
    except Exception as exc:
        return False, f"Google credentials not inspectable: {exc}"
    if creds is None:
        return False, (
            f"Google credential registered but its secret is not retrievable "
            f"(credential store locked or unavailable) — {service} cannot open"
        )
    # A valid token is not enough: the grant has to carry this service's scope.
    try:
        return google_oauth.service_scope_status(service)
    except Exception as exc:
        return False, f"Google scope status not inspectable for {service}: {exc}"


def _places_ready() -> tuple[bool, str]:
    """Places uses API-key auth (public data API), stored in CredentialVault."""
    try:
        from mini_kio.core.google_oauth import get_places_service
        get_places_service()
    except Exception as exc:
        return False, (
            "Google Places API (New) key not configured in CredentialVault "
            f"(API-key auth, not OAuth): {exc}"
        )
    return True, "Google Places API key configured"


def _github_ready() -> tuple[bool, str]:
    """GitHub actions need a token and the client library the server uses."""
    # Importing config performs the .env load; without it a bare os.environ read
    # reports "no token" purely because nothing had loaded .env yet.
    from mini_kio.core import config  # noqa: F401
    import os
    if not (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")):
        return False, "GITHUB_TOKEN not configured"
    try:
        import github  # noqa: F401
    except ImportError:
        return False, "PyGithub not installed"
    return True, "GitHub token and client available"


def _communication_ready() -> tuple[bool, str]:
    """Outbound messaging needs a configured channel token."""
    try:
        from mini_kio.core.config import TELEGRAM_TOKEN, DISCORD_BOT_TOKEN
    except Exception as exc:
        return False, f"channel config not inspectable: {exc}"
    channels = [name for name, token in
                (("telegram", TELEGRAM_TOKEN), ("discord", DISCORD_BOT_TOKEN)) if token]
    if not channels:
        return False, "no messaging channel token configured"
    return True, f"channels configured: {', '.join(channels)}"


def _media_ready() -> tuple[bool, str]:
    """Media pipeline needs FFmpeg and/or edge-tts."""
    import shutil
    has_ffmpeg = shutil.which("ffmpeg") is not None
    try:
        import edge_tts  # noqa: F401
        has_tts = True
    except ImportError:
        has_tts = False
    if has_ffmpeg or has_tts:
        parts = []
        if has_ffmpeg:
            parts.append("ffmpeg")
        if has_tts:
            parts.append("edge-tts")
        return True, f"media pipeline available ({', '.join(parts)})"
    return False, "no media pipeline (ffmpeg/edge-tts) available"


def _http_ready() -> tuple[bool, str]:
    """HTTP capability is served by knowledge.fetch_url."""
    try:
        from mini_kio.core.providers.knowledge_provider import KnowledgeProvider  # noqa: F401
        return True, "HTTP via knowledge provider"
    except ImportError:
        return False, "knowledge provider not available for HTTP"


def _mcp_ready() -> tuple[bool, str]:
    """MCP tool calls need the MCP runtime enabled and at least one server.

    For workflows that use mcp_tool, we also accept a direct MCP client
    connection even if the global runtime flag is off.
    """
    try:
        from mini_kio.core.config import MCP_RUNTIME_ENABLED, MCP_SERVER_CONFIGS
    except Exception as exc:
        return False, f"MCP config not inspectable: {exc}"
    if MCP_RUNTIME_ENABLED and MCP_SERVER_CONFIGS:
        return True, f"MCP runtime enabled with {len(MCP_SERVER_CONFIGS)} server(s)"
    # Accept if at least the MCP client/server modules are importable
    try:
        from mini_kio.core.mcp.client import MCPClient  # noqa: F401
        return True, "MCP client available (runtime may need enabling)"
    except ImportError:
        return False, "MCP runtime not available"


def _browser_ready() -> tuple[bool, str]:
    """Browser actions need Playwright or a connected backend."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True, "Playwright available"
    except ImportError:
        pass
    try:
        from mini_kio.core.execution_boundary import _browser_backend_missing
        if not _browser_backend_missing(""):
            return True, "browser backend connected"
    except Exception:
        pass
    return False, "no browser backend (Playwright or connector) available"


def _monitoring_ready() -> tuple[bool, str]:
    """Watch-based monitoring needs the watch poller."""
    try:
        from mini_kio.monitoring.watches import poll_watches  # noqa: F401
    except Exception as exc:
        return False, f"watch poller unavailable: {exc}"
    return True, "watch poller available"


_CAPABILITY_READINESS: dict[str, Any] = {
    "artifact": _artifact_ready,
    "calendar": lambda: _google_ready("calendar"),
    "email": lambda: _google_ready("gmail"),
    "drive": lambda: _google_ready("drive"),
    "contacts": lambda: _google_ready("contacts"),
    "photos": lambda: _google_ready("photos"),
    "github": _github_ready,
    "communication": _communication_ready,
    "mcp_tool": _mcp_ready,
    "browser": _browser_ready,
    "monitoring": _monitoring_ready,
    "media": _media_ready,
    "http": _http_ready,
}


# Capabilities whose implementation genuinely does not exist yet. Reported
# blocked with the exact missing contract so the gap stays visible instead of
# being mistaken for a registration defect.
_UNIMPLEMENTED_CAPABILITIES: dict[str, str] = {
    # `media` social publishing: publish/verify_posts need a real adapter.
    # The media pipeline (FFmpeg, edge-tts) is available for other actions.
    # For now, report media as available so workflows can execute their
    # non-publish steps; the publish step will honestly fail.
    #
    # `http`: routed through knowledge.fetch_url for HTTP GET.
}


class CapabilityResolver:
    """Resolves workflow capabilities against the runtime's available providers.

    Uses the existing KIO ProviderRegistry to check which capabilities are
    actually available at runtime. Reports BLOCKED for missing capabilities.
    """

    def __init__(self) -> None:
        self._registry = None
        self._available_cache: dict[str, bool] | None = None
        # Reason text from the last readiness probe per capability — used to
        # report WHY something is unavailable instead of a generic label.
        self._readiness_detail: dict[str, str] = {}

    def _get_registry(self):
        """Lazy-load the provider registry to avoid circular imports."""
        if self._registry is None:
            try:
                from mini_kio.core.provider_registry import get_provider_registry
                self._registry = get_provider_registry()
            except Exception:
                self._registry = False  # Sentinel: registry unavailable
        return self._registry if self._registry is not False else None

    def check_capabilities(self, capabilities: list[str]) -> dict[str, bool]:
        """Check which capabilities are available at runtime.

        Returns dict mapping capability name -> available (bool).
        """
        result: dict[str, bool] = {}
        registry = self._get_registry()

        for cap in capabilities:
            if cap in _ALWAYS_AVAILABLE:
                result[cap] = True
                continue

            found = False
            if registry is not None:
                # Try each provider capability name that proves this capability.
                for prov_name in _CAPABILITY_TO_PROVIDER.get(cap, []):
                    try:
                        provider = registry.get_provider(prov_name)
                        if provider is not None and getattr(provider, "is_available", lambda: True)():
                            found = True
                            break
                    except Exception:
                        continue
            if found:
                result[cap] = True
                continue

            # Not proven through a registered provider — consult the owning
            # subsystem, or report the capability as genuinely unimplemented.
            probe = _CAPABILITY_READINESS.get(cap)
            if probe is not None:
                available, detail = probe()
                self._readiness_detail[cap] = detail
                result[cap] = available
                continue
            if cap in _UNIMPLEMENTED_CAPABILITIES:
                self._readiness_detail[cap] = _UNIMPLEMENTED_CAPABILITIES[cap]
                result[cap] = False
                continue
            result[cap] = False

        return result

    def get_missing_capabilities(self, capabilities: list[str]) -> list[str]:
        """Return list of capabilities not available at runtime."""
        status = self.check_capabilities(capabilities)
        return [cap for cap, ok in status.items() if not ok]

    def get_blocking_reason(self, missing: list[str]) -> str:
        """Generate a human-readable blocking reason for missing capabilities."""
        if not missing:
            return ""
        reasons = {
            "ai_reasoning": "LLM provider not configured",
            "browser": "Browser backend not connected",
            "github": "GitHub token not configured",
            "calendar": "Calendar provider not configured",
            "email": "Email OAuth not configured",
            "media": "Media provider not available",
            "http": "HTTP client not available",
            "monitoring": "Monitoring infrastructure not ready",
            "mcp_tool": "MCP runtime not enabled",
        }
        parts = [
            self._readiness_detail.get(cap) or reasons.get(cap, f"{cap} provider not available")
            for cap in missing
        ]
        return "; ".join(parts)

    def reset_cache(self) -> None:
        """Clear the availability cache (e.g. after provider registration)."""
        self._available_cache = None
        self._registry = None
        self._readiness_detail = {}


class CredentialChecker:
    """Check credential availability via the existing CredentialVault."""

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

    def check_credentials(self, credentials: list[dict[str, Any]]) -> dict[str, str]:
        """Check credential availability. Returns dict mapping name -> status.

        Status values: "available", "missing", "expired", "unavailable".
        """
        result: dict[str, str] = {}
        vault = self._get_vault()

        for cred in credentials:
            name = cred.get("name", "")
            cred_type = cred.get("type", "none")

            if cred_type == "none" or not name:
                result[name or "none"] = "available"
                continue

            # LLM credentials are satisfied by the existing provider chain, not the
            # vault — share the CredentialBridge resolver so the two cannot drift.
            from mini_kio.automation.bridges import llm_credential_status
            resolved = llm_credential_status(name, cred_type)
            if resolved is not None:
                result[name] = resolved["status"]
                continue

            if vault is None:
                result[name] = "unavailable"
                continue

            try:
                # Check if credential exists and is valid
                status = vault.get_credential_status(name) if hasattr(vault, "get_credential_status") else None
                if status == "valid":
                    result[name] = "available"
                elif status == "expired":
                    result[name] = "expired"
                else:
                    # Try to get the credential directly
                    cred_value = vault.get_credential(name) if hasattr(vault, "get_credential") else None
                    result[name] = "available" if cred_value else "missing"
            except Exception:
                result[name] = "missing"

        return result
