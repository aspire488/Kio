from __future__ import annotations

from system_operator import SystemOperator


class CommandRouter:
    def __init__(self) -> None:
        self.system = SystemOperator()

    def handle(self, command: str) -> str:
        command = command.strip()
        if not command:
            return 'No command entered'

        lower = command.lower()
        if lower == 'time':
            from datetime import datetime
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if lower.startswith('open '):
            return self.system.execute(command)

        if lower.startswith('echo '):
            return command[5:].strip()

        return 'Unknown command'
