"""CodeProjectProvider — project scaffolding operations."""
from __future__ import annotations
import logging, os
from typing import Any
from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth, ProviderCapability

logger = logging.getLogger(__name__)


class CodeProjectProvider(ExecutionProvider):
    def id(self) -> str:
        return "code_project"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name="scaffold", category="development", timeout_s=30, ram_budget_mb=20),
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str = "", **kwargs: Any) -> dict[str, Any]:
        try:
            if action == "scaffold":
                project_name = kwargs.get("project_name", target or "new_project")
                language = kwargs.get("language", "python")
                template = kwargs.get("template", "basic")
                base_dir = os.path.expanduser("~/KIO/projects")
                project_dir = os.path.join(base_dir, project_name)
                os.makedirs(project_dir, exist_ok=True)
                if language == "python":
                    with open(os.path.join(project_dir, "main.py"), "w") as f:
                        f.write(f'"""Main module for {project_name}."""\n\n\ndef main():\n    print("Hello from {project_name}")\n\n\nif __name__ == "__main__":\n    main()\n')
                    with open(os.path.join(project_dir, "requirements.txt"), "w") as f:
                        f.write("# Add dependencies here\n")
                    with open(os.path.join(project_dir, "README.md"), "w") as f:
                        f.write(f"# {project_name}\n\nScaffolded by KIO.\n")
                return {"success": True, "project_dir": project_dir, "language": language,
                        "files_created": os.listdir(project_dir),
                        "message": f"Scaffolded {language} project: {project_name}"}
            return {"success": False, "message": f"CodeProjectProvider: unknown action {action}"}
        except Exception as exc:
            return {"success": False, "message": f"CodeProjectProvider.{action} failed: {exc}"}
