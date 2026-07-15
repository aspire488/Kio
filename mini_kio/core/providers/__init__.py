"""Provider implementations. Each wraps an operator module under the ExecutionProvider contract."""

from mini_kio.core.providers.browser_provider import BrowserProvider
from mini_kio.core.providers.desktop_provider import DesktopProvider
from mini_kio.core.providers.system_provider import SystemProvider
from mini_kio.core.providers.filesystem_provider import FilesystemProvider
from mini_kio.core.providers.terminal_provider import TerminalProvider
from mini_kio.core.providers.workflow_provider import WorkflowExecutionProvider


def register_all_providers() -> None:
    from mini_kio.core.provider_registry import get_provider_registry
    registry = get_provider_registry()
    for provider_cls in (BrowserProvider, DesktopProvider, SystemProvider,
                         FilesystemProvider, TerminalProvider,
                         WorkflowExecutionProvider):
        try:
            registry.register(provider_cls())
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to register provider %s: %s", provider_cls.__name__, exc
            )
    # Register MCP-backed providers
    try:
        from mini_kio.core.mcp import register_all_mcp_servers
        register_all_mcp_servers()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to register MCP providers: %s", exc)
