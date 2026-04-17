from __future__ import annotations

import subprocess
import os


class SystemOperator:
    def execute(self, command: str) -> str:
        command = command.strip().lower()

        if command.startswith("open "):
            app = command[5:].strip()

            try:
                # Windows built-in apps
                if app in ["notepad", "calc", "calculator"]:
                    subprocess.Popen(app, shell=True)
                    return f"Opened: {app}"

                # Chrome handling (common install paths)
                if app in ["chrome", "google chrome"]:
                    paths = [
                        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
                    ]

                    for path in paths:
                        if os.path.exists(path):
                            subprocess.Popen(path)
                            return "Opened: Chrome"

                    return "Chrome not found on system"

                # Fallback (try generic open)
                subprocess.Popen(app, shell=True)
                return f"Opened: {app}"

            except Exception as e:
                return f"Failed to open {app}: {e}"

        return f"Executing: {command}"
