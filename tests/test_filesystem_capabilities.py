"""Tests for KIO filesystem capability primitives."""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Override conftest's KIO_TEST_MODE=1 so execute_action runs real handlers
os.environ.pop("KIO_TEST_MODE", None)


class TestWriteCSV:
    def test_write_csv_creates_file(self):
        from mini_kio.core.file_operator import write_csv
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.csv")
            result = write_csv(path, [["a", "b"], ["1", "2"]])
            assert result["success"]
            assert result["row_count"] == 2
            assert Path(path).exists()

    def test_write_csv_with_columns(self):
        from mini_kio.core.file_operator import write_csv
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.csv")
            result = write_csv(path, [["val1", "val2"]], columns=["col1", "col2"])
            assert result["success"]
            with open(path) as f:
                reader = csv.reader(f)
                rows = list(reader)
            assert rows[0] == ["col1", "col2"]
            assert rows[1] == ["val1", "val2"]

    def test_write_csv_overwrites_existing(self):
        from mini_kio.core.file_operator import write_csv
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.csv")
            write_csv(path, [["old"]])
            result = write_csv(path, [["new"]])
            assert result["success"]
            with open(path) as f:
                content = f.read()
            assert "new" in content
            assert "old" not in content

    def test_write_csv_blocks_oversized(self):
        from mini_kio.core.file_operator import write_csv, _MAX_CSV_ROWS
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.csv")
            rows = [["x"]] * (_MAX_CSV_ROWS + 1)
            result = write_csv(path, rows)
            assert not result["success"]
            assert "exceeds limit" in result["message"]

    def test_write_csv_empty_rows(self):
        from mini_kio.core.file_operator import write_csv
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.csv")
            result = write_csv(path, [])
            assert result["success"]


class TestReadFile:
    def test_read_file_returns_content(self):
        from mini_kio.core.file_operator import read_file
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "test.txt")
            Path(path).write_text("hello world", encoding="utf-8")
            result = read_file(path)
            assert result["success"]
            assert result["text"] == "hello world"

    def test_read_file_not_found(self):
        from mini_kio.core.file_operator import read_file
        result = read_file("/nonexistent/path/file.txt")
        assert not result["success"]
        assert "not found" in result["message"].lower()

    def test_read_file_bounded(self):
        from mini_kio.core.file_operator import read_file
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "big.txt")
            Path(path).write_text("x" * 200, encoding="utf-8")
            result = read_file(path, max_chars=50)
            assert result["success"]
            assert len(result["text"]) == 50
            assert result["truncated"] is True

    def test_read_file_directory_rejected(self):
        from mini_kio.core.file_operator import read_file
        with tempfile.TemporaryDirectory() as td:
            result = read_file(td)
            assert not result["success"]
            assert "not a file" in result["message"].lower()


class TestMoveFile:
    def test_move_file_success(self):
        from mini_kio.core.file_operator import move_file
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "a.txt")
            dest = os.path.join(td, "sub", "b.txt")
            Path(src).write_text("content", encoding="utf-8")
            result = move_file(src, dest)
            assert result["success"]
            assert Path(dest).exists()
            assert not Path(src).exists()

    def test_move_file_source_not_found(self):
        from mini_kio.core.file_operator import move_file
        with tempfile.TemporaryDirectory() as td:
            result = move_file(os.path.join(td, "nope.txt"), os.path.join(td, "dest.txt"))
            assert not result["success"]
            assert "not found" in result["message"].lower()

    def test_move_file_creates_parent_dirs(self):
        from mini_kio.core.file_operator import move_file
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "a.txt")
            dest = os.path.join(td, "deep", "nested", "b.txt")
            Path(src).write_text("x", encoding="utf-8")
            result = move_file(src, dest)
            assert result["success"]
            assert Path(dest).exists()


class TestFsExists:
    def test_exists_file(self):
        from mini_kio.core.file_operator import fs_exists
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "yes.txt")
            Path(path).write_text("x", encoding="utf-8")
            result = fs_exists(path)
            assert result["success"]
            assert result["exists"] is True
            assert result["is_file"] is True

    def test_exists_directory(self):
        from mini_kio.core.file_operator import fs_exists
        with tempfile.TemporaryDirectory() as td:
            result = fs_exists(td)
            assert result["success"]
            assert result["exists"] is True
            assert result["is_dir"] is True

    def test_exists_not_found(self):
        from mini_kio.core.file_operator import fs_exists
        result = fs_exists("/no/such/path/exists")
        assert result["success"]
        assert result["exists"] is False


class TestHashFile:
    def test_hash_file_returns_sha256(self):
        from mini_kio.core.file_operator import hash_file
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "data.bin")
            Path(path).write_bytes(b"test content")
            result = hash_file(path)
            assert result["success"]
            assert len(result["hash"]) == 64  # SHA-256 hex

    def test_hash_file_not_found(self):
        from mini_kio.core.file_operator import hash_file
        result = hash_file("/nonexistent/file")
        assert not result["success"]

    def test_hash_file_deterministic(self):
        from mini_kio.core.file_operator import hash_file
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "same.bin")
            Path(path).write_bytes(b"deterministic")
            r1 = hash_file(path)
            r2 = hash_file(path)
            assert r1["hash"] == r2["hash"]


class TestHashTree:
    def test_hash_tree_counts_files(self):
        from mini_kio.core.file_operator import hash_tree
        with tempfile.TemporaryDirectory() as td:
            for i in range(5):
                Path(os.path.join(td, f"f{i}.txt")).write_text(f"file{i}", encoding="utf-8")
            result = hash_tree(td)
            assert result["success"]
            assert result["file_count"] == 5

    def test_hash_tree_detects_duplicates(self):
        from mini_kio.core.file_operator import hash_tree
        with tempfile.TemporaryDirectory() as td:
            Path(os.path.join(td, "a.txt")).write_text("same", encoding="utf-8")
            Path(os.path.join(td, "b.txt")).write_text("same", encoding="utf-8")
            result = hash_tree(td)
            assert result["success"]
            # All hashes should share one key (identical content)
            assert len(result["hashes"]) == 1

    def test_hash_tree_not_a_dir(self):
        from mini_kio.core.file_operator import hash_tree
        result = hash_tree("/nonexistent/dir")
        assert not result["success"]


class TestStoreRecord:
    def test_store_record_appends_json(self):
        from mini_kio.core.file_operator import store_record
        with tempfile.TemporaryDirectory() as td:
            store = os.path.join(td, "records.jsonl")
            r1 = store_record(store, {"id": 1, "name": "a"})
            assert r1["success"]
            r2 = store_record(store, {"id": 2, "name": "b"})
            assert r2["success"]
            with open(store) as f:
                lines = f.readlines()
            assert len(lines) == 2
            assert json.loads(lines[0])["name"] == "a"
            assert json.loads(lines[1])["name"] == "b"

    def test_store_record_verification(self):
        from mini_kio.core.file_operator import store_record
        with tempfile.TemporaryDirectory() as td:
            store = os.path.join(td, "records.jsonl")
            result = store_record(store, {"key": "value"})
            assert result["success"]


class TestExecutionBoundaryIntegration:
    def test_execute_action_write_csv(self):
        from mini_kio.core.execution_boundary import execute_action
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.csv")
            result = execute_action("write_csv", path, rows=[["x", "y"]], columns=["c1", "c2"])
            assert result["success"]

    def test_execute_action_read_file(self):
        from mini_kio.core.execution_boundary import execute_action
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "read.txt")
            Path(path).write_text("test data", encoding="utf-8")
            result = execute_action("read_file", path)
            assert result["success"]
            assert result["text"] == "test data"

    def test_execute_action_move_file(self):
        from mini_kio.core.execution_boundary import execute_action
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "src.txt")
            dest = os.path.join(td, "dest.txt")
            Path(src).write_text("move me", encoding="utf-8")
            result = execute_action("move_file", src, dest=dest)
            assert result["success"]

    def test_execute_action_fs_exists(self):
        from mini_kio.core.execution_boundary import execute_action
        with tempfile.TemporaryDirectory() as td:
            result = execute_action("fs_exists", td)
            assert result["success"]
            assert result["exists"] is True

    def test_execute_action_hash_file(self):
        from mini_kio.core.execution_boundary import execute_action
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "hash.txt")
            Path(path).write_text("hash me", encoding="utf-8")
            result = execute_action("hash_file", path)
            assert result["success"]
            assert len(result["hash"]) == 64


class TestStepRunnerMapping:
    def test_filesystem_actions_resolve(self):
        from mini_kio.automation.step_runner import StepRunner
        runner = StepRunner()
        # YAML step action names map to boundary actions
        expected = [
            ("filesystem", "write_csv"),
            ("filesystem", "read_file"),
            ("filesystem", "move_file"),
            ("filesystem", "verify_csv"),
            ("filesystem", "hash_file"),
            ("filesystem", "hash_tree"),
            ("filesystem", "store_record"),
            ("filesystem", "verify_path"),
            ("filesystem", "organize_files"),
            ("filesystem", "list_files"),
        ]
        for key in expected:
            assert key in runner._ACTION_MAP, f"Missing: {key}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
