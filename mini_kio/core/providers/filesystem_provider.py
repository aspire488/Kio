"""FilesystemProvider — wraps file_operator.py under ExecutionProvider contract."""

from __future__ import annotations

import logging
from typing import Any

from mini_kio.core.provider_contract import ExecutionProvider, ProviderHealth, ProviderCapability
from mini_kio.core.file_operator import (
    open_folder, create_file, list_directory, list_files,
    write_csv, read_file, move_file, fs_exists, hash_file, hash_tree, store_record,
)

logger = logging.getLogger(__name__)


class FilesystemProvider(ExecutionProvider):
    def id(self) -> str:
        return "filesystem"

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(name="open_folder", category="external_open", timeout_s=10, ram_budget_mb=5),
            ProviderCapability(name="list_files", category="external_open", timeout_s=10, ram_budget_mb=5),
            ProviderCapability(name="write_csv", category="external_open", timeout_s=10, ram_budget_mb=5),
            ProviderCapability(name="read_file", category="external_open", timeout_s=10, ram_budget_mb=5),
            ProviderCapability(name="move_file", category="external_open", timeout_s=10, ram_budget_mb=5),
            ProviderCapability(name="fs_exists", category="external_open", timeout_s=5, ram_budget_mb=2),
            ProviderCapability(name="hash_file", category="external_open", timeout_s=30, ram_budget_mb=10),
            ProviderCapability(name="hash_tree", category="external_open", timeout_s=60, ram_budget_mb=50),
            ProviderCapability(name="store_record", category="external_open", timeout_s=10, ram_budget_mb=5),
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

    def execute(self, action: str, target: str, **kwargs: Any) -> dict[str, Any]:
        _ACTIONS = {
            "open_folder": lambda: open_folder(target),
            "list_files": lambda: list_files(target),
            "write_csv": lambda: write_csv(target, kwargs.get("rows", []), kwargs.get("columns")),
            "read_file": lambda: read_file(target, kwargs.get("max_chars", 1_000_000)),
            "move_file": lambda: move_file(target, kwargs.get("dest", "")),
            "fs_exists": lambda: fs_exists(target),
            "hash_file": lambda: hash_file(target),
            "hash_tree": lambda: hash_tree(target, kwargs.get("min_size_kb", 0)),
            "store_record": lambda: store_record(target, kwargs.get("record", {})),
        }
        handler = _ACTIONS.get(action)
        if handler:
            return handler()
        return {"success": False, "message": f"FilesystemProvider: unknown action {action}"}

    def verify(self, action: str, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("probe_used", "filesystem_action")
        result.setdefault("verification_status", "passed" if result.get("success") else "failed")
        result.setdefault("outcome_class", "SUCCESS" if result.get("success") else "FAILURE")
        return result
