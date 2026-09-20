"""KIO Automation Engine — generic executor for all 63 canonical YAML templates.

This module is the single entry point for the automation engine. It exposes
the AutomationEngine class and all supporting components.

Usage:
    from mini_kio.automation import create_automation_engine
    engine = create_automation_engine()
    result = await engine.execute("browser.structured_extract", inputs={...})
"""

from mini_kio.automation.engine import AutomationEngine, create_automation_engine

__all__ = ["AutomationEngine", "create_automation_engine"]
