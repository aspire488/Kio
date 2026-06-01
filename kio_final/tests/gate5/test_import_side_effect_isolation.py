"""Verify import-time side-effect isolation for browser/runtime modules."""

import logging
import sys
import pytest
from unittest.mock import patch


def _clean_reimport(module_name):
    """Remove module from sys.modules so it can be re-imported cleanly."""
    for key in list(sys.modules):
        if key == module_name or key.startswith(f"{module_name}."):
            del sys.modules[key]


def test_config_env_loading_is_idempotent():
    """config._ensure_env_loaded() guard flag prevents double .env load."""
    from mini_kio.core import config

    assert config._is_dotenv_loaded is True
    flag_before = config._is_dotenv_loaded
    config._ensure_env_loaded()
    assert config._is_dotenv_loaded == flag_before


def test_config_reset_teardown():
    """Test that reset function clears the loaded flag."""
    from mini_kio.core import config

    config._reset_env_loaded()
    assert config._is_dotenv_loaded is False
    config._ensure_env_loaded()
    assert config._is_dotenv_loaded is True


def test_browser_registry_is_lazy():
    """_BROWSER_REGISTRY stays None until get_browser_registry() is called."""
    _clean_reimport("mini_kio.core.routing_utils")
    import mini_kio.core.routing_utils as ru

    assert ru._BROWSER_REGISTRY is None
    reg = ru.get_browser_registry()
    assert reg is not None
    assert ru._BROWSER_REGISTRY is reg


def test_capability_registry_is_lazy():
    """_CAPABILITY_REGISTRY stays None until get_capability_registry() is called."""
    _clean_reimport("mini_kio.core.capability_registry")
    import mini_kio.core.capability_registry as cr

    assert cr._CAPABILITY_REGISTRY is None
    reg = cr.get_capability_registry()
    assert reg is not None
    assert cr._CAPABILITY_REGISTRY is reg


def test_diagnostics_logging_not_configured_at_import():
    """kio_diagnostics no longer calls logging.basicConfig() at import."""
    root_logger = logging.getLogger()
    handlers_before = len(root_logger.handlers)

    import mini_kio.core.kio_diagnostics as diag

    assert diag._DIAGNOSTICS_INITIALIZED is False
    assert len(root_logger.handlers) == handlers_before


def test_diagnostics_init_activates_logging():
    """init_diagnostics() sets up logging."""
    import mini_kio.core.kio_diagnostics as diag

    diag.init_diagnostics()
    assert diag._DIAGNOSTICS_INITIALIZED is True


@pytest.fixture
def no_browser_registry_constructor():
    """Patch BrowserSessionRegistry to detect calls during import."""
    with patch("mini_kio.browser.browser_session_registry.BrowserSessionRegistry") as mock:
        yield mock


def test_import_routing_utils_does_not_construct_registry():
    """Pure import of routing_utils must NOT create BrowserSessionRegistry."""
    with patch("mini_kio.browser.browser_session_registry.BrowserSessionRegistry") as mock_cls:
        _clean_reimport("mini_kio.core.routing_utils")
        _clean_reimport("mini_kio.core.capability_registry")
        import mini_kio.core.routing_utils

        mock_cls.assert_not_called()


def test_import_capability_registry_does_not_construct_registry():
    """Pure import of capability_registry must NOT create CapabilityRegistry."""
    with patch(
        "mini_kio.core.capability_registry.CapabilityRegistry"
    ) as mock_cls:
        _clean_reimport("mini_kio.core.capability_registry")
        import mini_kio.core.capability_registry

        mock_cls.assert_not_called()


def test_get_browser_registry_triggers_construction():
    """get_browser_registry() creates BrowserSessionRegistry on first call."""
    with patch("mini_kio.browser.browser_session_registry.BrowserSessionRegistry") as mock_cls:
        _clean_reimport("mini_kio.core.routing_utils")
        import mini_kio.core.routing_utils as ru

        mock_cls.assert_not_called()
        ru.get_browser_registry()
        mock_cls.assert_called_once()


def test_get_capability_registry_triggers_construction():
    """get_capability_registry() creates CapabilityRegistry on first call."""
    _clean_reimport("mini_kio.core.capability_registry")
    import mini_kio.core.capability_registry as cr

    with patch.object(cr, "CapabilityRegistry") as mock_cls:
        mock_cls.assert_not_called()
        cr.get_capability_registry()
        mock_cls.assert_called_once()


@pytest.mark.parametrize("module_path", [
    "mini_kio.core.config",
    "mini_kio.core.routing_utils",
    "mini_kio.core.capability_registry",
    "mini_kio.core.kio_diagnostics",
])
def test_module_import_does_not_raise(module_path):
    """All patched modules compile and import without error."""
    _clean_reimport(module_path)
    __import__(module_path)


# ── OPERATIONAL EXECUTION ISOLATION (KIO_TEST_MODE) ──────────────────────


def _reset_test_mode_flag():
    import mini_kio.core.execution_boundary as eb
    eb._TEST_MODE = None


def _with_test_mode(val: str):
    """Temporarily set KIO_TEST_MODE for a test block."""
    import os
    old = os.environ.get("KIO_TEST_MODE")
    os.environ["KIO_TEST_MODE"] = val
    _reset_test_mode_flag()
    return old


def _restore_test_mode(old: str):
    """Restore KIO_TEST_MODE after test block."""
    import os
    if old is None:
        os.environ.pop("KIO_TEST_MODE", None)
    else:
        os.environ["KIO_TEST_MODE"] = old
    _reset_test_mode_flag()


def test_in_test_mode_true_during_tests():
    from mini_kio.core.execution_boundary import _in_test_mode
    _reset_test_mode_flag()
    assert _in_test_mode() is True


def test_in_test_mode_false_when_disabled():
    old = _with_test_mode("0")
    try:
        from mini_kio.core.execution_boundary import _in_test_mode
        assert _in_test_mode() is False
    finally:
        _restore_test_mode(old)


def test_execute_action_blocked_in_test_mode():
    from mini_kio.core.execution_boundary import execute_action
    result = execute_action("open_app", "chrome")
    assert result.get("test_mode") is True
    assert result.get("blocked") is True
    assert result.get("action") == "open_app"


def test_execute_action_unblocked_when_disabled():
    old = _with_test_mode("0")
    try:
        from mini_kio.core.execution_boundary import execute_action
        result = execute_action("open_app", "chrome")
        assert result.get("test_mode") is None
    finally:
        _restore_test_mode(old)


def test_safe_webbrowser_open_blocked_in_test_mode():
    from mini_kio.core.app_operator import _safe_webbrowser_open
    import webbrowser
    with patch.object(webbrowser, "open") as mock_open:
        result = _safe_webbrowser_open("https://example.com")
        assert result is True
        mock_open.assert_not_called()


def test_safe_webbrowser_open_normal_when_disabled():
    old = _with_test_mode("0")
    try:
        from mini_kio.core.app_operator import _safe_webbrowser_open
        import webbrowser
        with patch.object(webbrowser, "open", return_value=True) as mock_open:
            result = _safe_webbrowser_open("https://example.com")
            assert result is True
            mock_open.assert_called_once_with("https://example.com")
    finally:
        _restore_test_mode(old)


def test_browser_operator_safe_open_blocked_in_test_mode():
    from mini_kio.core.browser_operator import _safe_webbrowser_open
    import webbrowser
    with patch.object(webbrowser, "open") as mock_open:
        result = _safe_webbrowser_open("https://example.com")
        assert result is True
        mock_open.assert_not_called()
