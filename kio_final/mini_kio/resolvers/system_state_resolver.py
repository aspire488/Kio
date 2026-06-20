import logging
import asyncio
import re
from typing import Optional
from mini_kio.core.async_utils import safe_run_async
from mini_kio.resolvers.base import BaseResolver
from mini_kio.llm.session_state import SessionState
from mini_kio.llm.trace_context import TraceContext

logger = logging.getLogger(__name__)

class SystemStateResolver(BaseResolver):
    """Handles authoritative queries about local system state."""
    
    def resolve(self, text: str, state: SessionState, trace: TraceContext) -> Optional[str]:
        text_lower = text.lower()
        
        try:
            import psutil
            
            # 1. Browser Tabs (Authoritative via TabRegistry)
            if any(kw in text_lower for kw in ["tabs", "tab"]):
                from mini_kio.core.command_router import _get_connector
                conn = _get_connector()
                if conn and conn.is_connected():
                    trace.add_step("SystemStateResolver: querying TabRegistry")
                    try:
                        result = safe_run_async(conn.list_tabs())
                        if result.success and result.tabs:
                            titles = [t.title or t.url for t in result.tabs]
                            return f"Open browser tabs: {', '.join(titles)}."
                        elif result.success:
                            return "No browser tabs are currently open."
                    except Exception as e:
                        logger.warning(f"TabRegistry query failed: {e}")
                return "I cannot verify your browser tabs right now."

            # 2. Battery
            if "battery" in text_lower:
                trace.add_step("SystemStateResolver: checking battery")
                battery = psutil.sensors_battery()
                if battery:
                    status = "charging" if battery.power_plugged else "discharging"
                    return f"Battery is at {battery.percent}%, {status}."
                return "I cannot verify your battery status."

            # 3. RAM / Memory
            if any(kw in text_lower for kw in ["ram", "memory usage"]):
                trace.add_step("SystemStateResolver: checking RAM")
                ram = psutil.virtual_memory()
                return f"System RAM usage: {ram.percent}% ({ram.used // (1024**2)}MB used)."

            # 4. CPU
            if "cpu" in text_lower:
                trace.add_step("SystemStateResolver: checking CPU")
                cpu = psutil.cpu_percent(interval=0.1)
                return f"System CPU usage: {cpu}%."

            # 5. Running Applications
            if any(kw in text_lower for kw in ["apps", "applications", "running"]):
                trace.add_step("SystemStateResolver: checking running applications")
                procs = []
                for p in psutil.process_iter(['name']):
                    try:
                        name = p.info['name'].lower()
                        if any(x in name for x in ["chrome", "code", "spotify", "discord", "telegram", "notepad"]):
                            procs.append(p.info['name'])
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                if procs:
                    unique_procs = sorted(list(set(procs)))
                    return f"Verified running applications: {', '.join(unique_procs)}."
                return "I cannot verify your running applications right now."

        except Exception as e:
            logger.warning(f"System state resolution failed: {e}")

        return None
