import pytest
import asyncio
from unittest.mock import MagicMock, patch
from mini_kio.core.command_router import handle_command
from mini_kio.core import config

@pytest.fixture
def mock_connector():
    with patch("mini_kio.core.command_router._get_connector") as mock:
        conn = MagicMock()
        conn.is_connected.return_value = True
        mock.return_value = conn
        yield conn

async def mock_list_tabs(tabs_list):
    result_mock = MagicMock()
    result_mock.success = True
    result_mock.tabs = tabs_list
    return result_mock

def test_list_tabs_formatting(mock_connector):
    # Mock result with mixed ownership
    class Tab:
        def __init__(self, tab_id, title, url, is_owned=False):
            self.tab_id = tab_id
            self.title = title
            self.url = url
            self.is_owned = is_owned

    tabs = [
        Tab(1, "Telegram Web", "https://web.telegram.org"),
        Tab(2, "ChatGPT", "https://chat.openai.com"),
        Tab(3, "Extensions", "chrome://extensions"),
        Tab(4, "Google", "https://www.google.com", is_owned=True),
    ]
    
    mock_connector.list_tabs.return_value = mock_list_tabs(tabs)

    with patch.object(config, "BROWSER_CONNECTOR_ENABLED", True):
        result = handle_command("list tabs")
        
    assert result["success"] is True
    assert "Open tabs:" in result["message"]
    assert "1. Telegram Web" in result["message"]
    assert "2. ChatGPT" in result["message"]
    assert "3. Extensions" in result["message"]
    assert "4. Google [Opened by KIO]" in result["message"]
    # Verify no tab IDs are present in the output
    assert "1466022557" not in result["message"]
    assert "1: " not in result["message"] # The old format was "{id}: {title}"

def test_no_tabs_open(mock_connector):
    mock_connector.list_tabs.return_value = mock_list_tabs([])

    with patch.object(config, "BROWSER_CONNECTOR_ENABLED", True):
        result = handle_command("list tabs")
        
    assert result["success"] is True
    assert "No tabs open." in result["message"]
