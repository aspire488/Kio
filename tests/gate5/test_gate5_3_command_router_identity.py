import pytest
from mini_kio.core.command_router import handle_command


def test_command_router_identity():
    queries = [
        ("who are you", "KIO \u2014 Kernel for Intelligent Orchestration."),
        ("what are you", "KIO \u2014 Kernel for Intelligent Orchestration."),
        ("identify yourself", "KIO \u2014 Kernel for Intelligent Orchestration."),
        ("what is kio", "KIO \u2014 Kernel for Intelligent Orchestration."),
        ("who created you", "Joel built KIO."),
        ("who built you", "Joel built KIO."),
        ("why were you created", "KIO was built as a personal operating companion"),
        ("what can you do", "I can open and close applications"),
        ("what are your limitations", "I operate within the capabilities available"),
    ]

    for q, expected in queries:
        result = handle_command(q)
        assert result["success"] is True
        assert expected in result["message"]
        # Verify the response matches the canonical identity format
        if "KIO" in expected:
            assert "KIO" in result["message"]


def test_command_router_identity_via_pipeline():
    """Identity queries must be handled by the pipeline conversation capability."""
    queries = [
        ("tell me about yourself", "KIO \u2014 Kernel for Intelligent Orchestration."),
    ]

    for q, expected in queries:
        result = handle_command(q)
        assert expected in result.get("message", "")
