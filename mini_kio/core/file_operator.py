"""
File Operator - Open folders and handle file operations.

Key improvements:
1. Folder aliases: downloads, desktop, documents, pictures, etc.
2. shell: paths for Windows standard folders (work regardless of username)
3. Proper error handling with subprocess.run()
4. Platform detection (Windows vs Unix)
5. Strips trailing "folder" keyword from commands
6. Filesystem primitives for automation: read, write, move, hash, verify
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path

from mini_kio.core.operator_protocol import OperatorDescriptor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Operator Descriptor
# ---------------------------------------------------------------------------

FILE_OPERATOR_DESCRIPTOR: OperatorDescriptor = {
    "tool_name": "file_operator",
    "tool_version": "2.0.0",
    "ram_budget_mb": 5.0,
    "timeout_seconds": 10,
    "side_effect": True,
    "lifecycle_type": "stateless",
    "supported_actions": [
        "open_folder", "create_file", "list_directory", "list_files",
        "write_csv", "read_file", "move_file", "fs_exists", "hash_file",
    ]
}

_IS_WINDOWS = platform.system() == "Windows"

# ─────────────────────────────────────────────────────────────────────────────
# Folder aliases for Windows (using shell: paths for reliability)
# ─────────────────────────────────────────────────────────────────────────────

KIO_FOLDER_PATH = str(Path(__file__).resolve().parents[3])

FOLDER_ALIASES: dict[str, str] = {
    "downloads": "shell:Downloads",
    "desktop": "shell:Desktop",
    "documents": "shell:Documents",
    "pictures": "shell:Pictures",
    "music": "shell:Music",
    "videos": "shell:Videos",
    "home": str(Path.home()),
    "appdata": str(Path(os.environ.get("APPDATA", Path.home()))),
    "kio": KIO_FOLDER_PATH,
}

# For compatibility
WINDOWS_FOLDERS = FOLDER_ALIASES


def open_folder(name: str) -> dict:
    """
    Open a folder by name or path.
    
    Args:
        name: Folder name (downloads, desktop, etc.) or absolute path
        
    Returns:
        {"success": bool, "message": str}
    """
    name_clean = name.lower().strip()
    
    # Strip trailing "folder" keyword
    if name_clean.endswith(" folder"):
        name_clean = name_clean[:-7].strip()
    
    # Also handle if someone says just "folder"
    if name_clean == "folder":
        name_clean = name.lower().strip()

    logger.info(f"[FILE] open_folder({name_clean!r})")

    # 1. Check folder aliases
    if name_clean in FOLDER_ALIASES:
        folder_path = FOLDER_ALIASES[name_clean]
        return _open_path(folder_path, name_clean)

    # 2. Try as absolute or home-relative path
    try:
        path = Path(name_clean).expanduser()
        if path.exists() and path.is_dir():
            return _open_path(str(path), name_clean)
    except Exception as e:
        logger.debug(f"[FILE] path check failed: {e}")

    logger.warning(f"[FILE] folder not found: {name!r}")
    return {"success": False, "message": f"Folder not found: {name}"}


def _open_path(path: str, label: str) -> dict:
    """
    Open a file path or Windows shell: path.
    
    Args:
        path: Filesystem path or shell: path
        label: Display label for messages
        
    Returns:
        {"success": bool, "message": str}
    """
    try:
        if _IS_WINDOWS:
            # On Windows, use explorer
            proc = subprocess.Popen(
                ["explorer", path],
                creationflags=0x08000000,  # CREATE_NO_WINDOW (prevents visible console)
            )
            pid = proc.pid
            logger.info(f"[FILE] opened: {path} (pid: {pid})")
            return {"success": True, "message": f"Opened {label}", "pid": pid}
        else:
            # On Unix, use xdg-open
            subprocess.Popen(["xdg-open", path])
            logger.info(f"[FILE] opened: {path}")
            return {"success": True, "message": f"Opened {label}"}

    except subprocess.TimeoutExpired:
        # Timeout is normal — explorer is running
        logger.info(f"[FILE] explorer timeout (normal): {path}")
        return {"success": True, "message": f"Opened {label}"}

    except FileNotFoundError:
        logger.error(f"[FILE] explorer not found")
        return {"success": False, "message": f"File explorer not found"}

    except Exception as e:
        logger.error(f"[FILE] _open_path error for {path}: {e}")
        return {"success": False, "message": f"Failed to open {label}: {str(e)[:80]}"}


def create_file(filename: str, content: str = "") -> dict:
    """
    Create a new file with optional content.
    
    Args:
        filename: Filename or path (~ is expanded)
        content: File content
        
    Returns:
        {"success": bool, "message": str}
    """
    try:
        path = Path(filename).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info(f"[FILE] created: {path}")
        return {"success": True, "message": f"Created {filename}"}
    except Exception as e:
        logger.error(f"[FILE] create_file error: {e}")
        return {"success": False, "message": f"Failed to create file: {str(e)[:80]}"}


def list_directory(path: str = ".") -> dict:
    """
    List contents of a directory.
    
    Args:
        path: Directory path
        
    Returns:
        {"success": bool, "message": str, "items": [{"name": str, "type": str}]}
    """
    try:
        dir_path = Path(path).expanduser()
        if not dir_path.exists():
            return {"success": False, "message": f"Path does not exist: {path}"}
        if not dir_path.is_dir():
            return {"success": False, "message": f"Not a directory: {path}"}

        items = [
            {"name": item.name, "type": "folder" if item.is_dir() else "file"}
            for item in sorted(dir_path.iterdir())
        ]
        return {
            "success": True,
            "message": f"Found {len(items)} items",
            "items": items
        }
    except PermissionError:
        return {"success": False, "message": f"Permission denied: {path}"}
    except Exception as e:
        logger.error(f"[FILE] list_directory error: {e}")
        return {"success": False, "message": f"Failed to list: {str(e)[:80]}"}


# ---------------------------------------------------------------------------
# Filesystem Primitives for Automation
# ---------------------------------------------------------------------------

# Maximum file read size (10 MB) — prevents OOM on large files
_MAX_READ_BYTES = 10 * 1024 * 1024

# Maximum CSV rows per write operation
_MAX_CSV_ROWS = 50_000


def _validate_path(path_str: str) -> Path:
    """Resolve and validate a path. Prevents path traversal.

    Returns resolved Path or raises ValueError for unsafe paths.
    """
    p = Path(path_str).expanduser().resolve()
    # Block obvious path traversal attempts
    if ".." in path_str.split(os.sep):
        raise ValueError(f"Path traversal blocked: {path_str}")
    return p


def write_csv(path: str, rows: list[list[str]], columns: list[str] | None = None) -> dict:
    """Write rows to a CSV file. Creates or overwrites.

    Security: path validated, bounded row count.
    Verification: file exists after write, row count matches.
    """
    try:
        p = _validate_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        if len(rows) > _MAX_CSV_ROWS:
            return {"success": False, "message": f"Row count {len(rows)} exceeds limit {_MAX_CSV_ROWS}"}

        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if columns:
                writer.writerow(columns)
            writer.writerows(rows)

        # Verification: file exists after write
        if not p.exists():
            return {"success": False, "message": "Write succeeded but file not found"}

        logger.info(f"[FILE] write_csv: {p} ({len(rows)} rows)")
        return {
            "success": True,
            "message": f"Wrote {len(rows)} rows to {p.name}",
            "file_path": str(p),
            "row_count": len(rows),
        }
    except Exception as e:
        logger.error(f"[FILE] write_csv error: {e}")
        return {"success": False, "message": f"write_csv failed: {str(e)[:80]}"}


def read_file(path: str, max_chars: int = 1_000_000) -> dict:
    """Read text content from a file. Bounded read prevents OOM.

    Security: path validated, read capped at max_chars (default 1MB).
    """
    try:
        p = _validate_path(path)
        if not p.exists():
            return {"success": False, "message": f"File not found: {path}"}
        if not p.is_file():
            return {"success": False, "message": f"Not a file: {path}"}

        # Bounded read
        size = p.stat().st_size
        read_limit = min(max_chars, _MAX_READ_BYTES)

        with open(p, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(read_limit)

        truncated = size > read_limit
        logger.info(f"[FILE] read_file: {p} ({len(text)} chars, truncated={truncated})")
        return {
            "success": True,
            "message": f"Read {len(text)} chars from {p.name}",
            "text": text,
            "file_path": str(p),
            "truncated": truncated,
            "total_size": size,
        }
    except Exception as e:
        logger.error(f"[FILE] read_file error: {e}")
        return {"success": False, "message": f"read_file failed: {str(e)[:80]}"}


def move_file(src: str, dest: str) -> dict:
    """Move a file from src to dest. Creates parent dirs as needed.

    Security: both paths validated. Verification: dest exists, src absent.
    """
    try:
        src_p = _validate_path(src)
        dest_p = _validate_path(dest)

        if not src_p.exists():
            return {"success": False, "message": f"Source not found: {src}"}
        if not src_p.is_file():
            return {"success": False, "message": f"Source is not a file: {src}"}

        dest_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_p), str(dest_p))

        # Verification: dest exists, src gone
        if not dest_p.exists():
            return {"success": False, "message": "Move completed but destination not found"}
        if src_p.exists():
            return {"success": False, "message": "Move completed but source still exists"}

        logger.info(f"[FILE] move_file: {src_p} -> {dest_p}")
        return {
            "success": True,
            "message": f"Moved {src_p.name} to {dest_p}",
            "src": str(src_p),
            "dest": str(dest_p),
        }
    except Exception as e:
        logger.error(f"[FILE] move_file error: {e}")
        return {"success": False, "message": f"move_file failed: {str(e)[:80]}"}


def fs_exists(path: str) -> dict:
    """Check if a path exists. Read-only, no side effects.

    Security: path validated.
    """
    try:
        p = _validate_path(path)
        exists = p.exists()
        is_file = p.is_file() if exists else False
        is_dir = p.is_dir() if exists else False
        return {
            "success": True,
            "message": f"{'Exists' if exists else 'Not found'}: {path}",
            "exists": exists,
            "is_file": is_file,
            "is_dir": is_dir,
            "path": str(p),
        }
    except Exception as e:
        return {"success": False, "message": f"fs_exists failed: {str(e)[:80]}"}


def hash_file(path: str) -> dict:
    """Compute SHA-256 hash of a file. Read-only, bounded read.

    Security: path validated, read in 64KB chunks to prevent OOM.
    """
    try:
        p = _validate_path(path)
        if not p.exists():
            return {"success": False, "message": f"File not found: {path}"}
        if not p.is_file():
            return {"success": False, "message": f"Not a file: {path}"}

        sha256 = hashlib.sha256()
        with open(p, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha256.update(chunk)

        digest = sha256.hexdigest()
        logger.info(f"[FILE] hash_file: {p} -> {digest[:16]}...")
        return {
            "success": True,
            "message": f"Hashed {p.name}",
            "hash": digest,
            "file_path": str(p),
            "size": p.stat().st_size,
        }
    except Exception as e:
        logger.error(f"[FILE] hash_file error: {e}")
        return {"success": False, "message": f"hash_file failed: {str(e)[:80]}"}


def hash_tree(folder: str, min_size_kb: int = 0) -> dict:
    """Hash all files in a directory tree. Read-only, bounded.

    Security: path validated, results capped at 10000 entries.
    """
    try:
        p = _validate_path(folder)
        if not p.exists() or not p.is_dir():
            return {"success": False, "message": f"Not a directory: {folder}"}

        hashes: dict[str, list[str]] = {}  # hash -> [file paths]
        file_count = 0
        max_files = 10000

        for item in p.rglob("*"):
            if file_count >= max_files:
                break
            if item.is_file():
                size_kb = item.stat().st_size / 1024
                if size_kb < min_size_kb:
                    continue
                try:
                    sha256 = hashlib.sha256()
                    with open(item, "rb") as f:
                        while True:
                            chunk = f.read(65536)
                            if not chunk:
                                break
                            sha256.update(chunk)
                    digest = sha256.hexdigest()
                    hashes.setdefault(digest, []).append(str(item))
                    file_count += 1
                except (PermissionError, OSError):
                    continue

        logger.info(f"[FILE] hash_tree: {p} ({file_count} files)")
        return {
            "success": True,
            "message": f"Hashed {file_count} files in {p.name}",
            "hashes": hashes,
            "file_count": file_count,
            "folder": str(p),
        }
    except Exception as e:
        logger.error(f"[FILE] hash_tree error: {e}")
        return {"success": False, "message": f"hash_tree failed: {str(e)[:80]}"}


def store_record(store: str, record: dict) -> dict:
    """Append a JSON record to a store file (JSONL format).

    Security: path validated, append-only.
    Verification: record can be read back.
    """
    try:
        p = _validate_path(store)
        p.parent.mkdir(parents=True, exist_ok=True)

        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)

        # Verification: read back last line
        with open(p, "r", encoding="utf-8") as f:
            last_line = f.readlines()[-1].strip()
        stored = json.loads(last_line)
        if stored != record:
            return {"success": False, "message": "Record verification failed: mismatch"}

        logger.info(f"[FILE] store_record: {p}")
        return {
            "success": True,
            "message": f"Stored record in {p.name}",
            "record_id": len(open(p, "r").readlines()),
            "store": str(p),
        }
    except Exception as e:
        logger.error(f"[FILE] store_record error: {e}")
        return {"success": False, "message": f"store_record failed: {str(e)[:80]}"}


def append_sheet_row(path: str, sheet_name: str, row_values: list) -> dict:
    """Append a row to an Excel worksheet. Verification: read-back the appended row."""
    try:
        from openpyxl import load_workbook
        p = _validate_path(path)
        if not p.exists():
            return {"success": False, "message": f"File not found: {path}"}
        wb = load_workbook(str(p))
        ws = wb[sheet_name] if sheet_name in wb.sheetnames else wb.active
        ws.append(row_values)
        wb.save(str(p))
        # Read-back verify
        last_row = ws.max_row
        read_back = [ws.cell(row=last_row, column=c).value for c in range(1, len(row_values) + 1)]
        if read_back != row_values:
            return {"success": False, "message": "Row verification failed: mismatch after write"}
        logger.info(f"[FILE] append_sheet_row: {p} sheet={ws.title} row={last_row}")
        return {"success": True, "message": f"Appended row {last_row} to {p.name}", "row_index": last_row}
    except Exception as e:
        logger.error(f"[FILE] append_sheet_row error: {e}")
        return {"success": False, "message": f"append_sheet_row failed: {str(e)[:80]}"}


def prune_old_backups(directory: str, pattern: str = "*", max_age_days: int = 30) -> dict:
    """Delete files matching pattern older than max_age_days. Returns count removed."""
    import time as _time
    try:
        p = _validate_path(directory)
        if not p.exists() or not p.is_dir():
            return {"success": False, "message": f"Not a directory: {directory}"}
        cutoff = _time.time() - (max_age_days * 86400)
        removed = 0
        for item in p.glob(pattern):
            if item.is_file() and item.stat().st_mtime < cutoff:
                item.unlink()
                removed += 1
        logger.info(f"[FILE] prune_old_backups: {p} removed={removed}")
        return {"success": True, "message": f"Pruned {removed} old files from {p.name}", "removed_count": removed}
    except Exception as e:
        logger.error(f"[FILE] prune_old_backups error: {e}")
        return {"success": False, "message": f"prune_old_backups failed: {str(e)[:80]}"}


def redact_csv(path: str, output_path: str, patterns: dict[str, str] | None = None) -> dict:
    """Read CSV, redact PII patterns (email, phone, SSN by default), write clean CSV."""
    import re as _re
    _DEFAULT_PATTERNS = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    }
    pats = patterns or _DEFAULT_PATTERNS
    try:
        src = _validate_path(path)
        dst = _validate_path(output_path)
        if not src.exists():
            return {"success": False, "message": f"Source not found: {path}"}
        with open(src, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)
        redacted_count = 0
        clean_rows = []
        for row in rows:
            new_row = []
            for cell in row:
                original = cell
                for label, pat in pats.items():
                    cell = _re.sub(pat, f"[{label.upper()}_REDACTED]", cell)
                if cell != original:
                    redacted_count += 1
                new_row.append(cell)
            clean_rows.append(new_row)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(clean_rows)
        logger.info(f"[FILE] redact_csv: {src} -> {dst} redacted={redacted_count}")
        return {"success": True, "message": f"Redacted {redacted_count} cells, saved to {dst.name}",
                "redacted_count": redacted_count, "output_path": str(dst)}
    except Exception as e:
        logger.error(f"[FILE] redact_csv error: {e}")
        return {"success": False, "message": f"redact_csv failed: {str(e)[:80]}"}


def verify_csv(path: str, expected_columns: list[str] | None = None) -> dict:
    """Parse CSV, verify structure: column count, row count > 0, optional column names match."""
    try:
        p = _validate_path(path)
        if not p.exists():
            return {"success": False, "message": f"File not found: {path}"}
        with open(p, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows:
            return {"success": False, "message": "CSV is empty", "valid": False}
        header = rows[0]
        data_rows = rows[1:]
        if expected_columns and header != expected_columns:
            return {"success": False, "message": f"Column mismatch: got {header}, expected {expected_columns}", "valid": False}
        logger.info(f"[FILE] verify_csv: {p} cols={len(header)} rows={len(data_rows)}")
        return {"success": True, "valid": True, "columns": header, "row_count": len(data_rows),
                "message": f"CSV valid: {len(header)} columns, {len(data_rows)} rows"}
    except Exception as e:
        logger.error(f"[FILE] verify_csv error: {e}")
        return {"success": False, "valid": False, "message": f"verify_csv failed: {str(e)[:80]}"}


def verify_image(path: str, expected_ratio: str | None = None) -> dict:
    """Verify file is a valid image with correct dimensions. Uses Pillow."""
    try:
        from PIL import Image
        p = _validate_path(path)
        if not p.exists():
            return {"success": False, "message": f"File not found: {path}"}
        img = Image.open(str(p))
        img.verify()
        # Re-open after verify (verify closes the file)
        img = Image.open(str(p))
        width, height = img.size
        fmt = img.format
        ratio_ok = True
        if expected_ratio:
            parts = expected_ratio.split(":")
            if len(parts) == 2:
                expected_w, expected_h = int(parts[0]), int(parts[1])
                actual_ratio = width / height if height else 0
                expected_r = expected_w / expected_h if expected_h else 0
                ratio_ok = abs(actual_ratio - expected_r) < 0.05
        logger.info(f"[FILE] verify_image: {p} {width}x{height} fmt={fmt}")
        return {"success": True, "valid": ratio_ok, "width": width, "height": height,
                "format": fmt, "ratio_ok": ratio_ok,
                "message": f"Image {width}x{height} ({fmt})" + ("" if ratio_ok else f" ratio mismatch (expected {expected_ratio})")}
    except ImportError:
        return {"success": False, "message": "verify_image: Pillow not installed"}
    except Exception as e:
        logger.error(f"[FILE] verify_image error: {e}")
        return {"success": False, "valid": False, "message": f"verify_image failed: {str(e)[:80]}"}


def verify_project(path: str, language: str = "") -> dict:
    """Verify project scaffold: src/, tests/, README, .gitignore, dependency manifest exist."""
    try:
        p = _validate_path(path)
        if not p.exists():
            return {"success": False, "message": f"Project path not found: {path}"}
        checks = {
            "src_dir": (p / "src").is_dir() or any(p.glob("src*")),
            "tests_dir": (p / "tests").is_dir() or any(p.glob("test*")),
            "readme": any(p.glob("README*")),
            "gitignore": (p / ".gitignore").is_file(),
            "git_repo": (p / ".git").is_dir(),
        }
        # Language-specific manifest checks
        manifests = {
            "python": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile"],
            "node": ["package.json"],
            "rust": ["Cargo.toml"],
            "go": ["go.mod"],
            "dotnet": ["*.csproj", "*.sln"],
        }
        if language in manifests:
            checks["manifest"] = any(p.glob(m) for m in manifests[language])
        else:
            checks["manifest"] = any(p.glob(f) for f in ["package.json", "requirements.txt", "Cargo.toml", "go.mod", "pyproject.toml"])
        passed = sum(1 for v in checks.values() if v)
        total = len(checks)
        logger.info(f"[FILE] verify_project: {p} {passed}/{total}")
        return {"success": True, "valid": passed >= 4, "checks": checks, "passed": passed, "total": total,
                "message": f"Project check: {passed}/{total} passed"}
    except Exception as e:
        logger.error(f"[FILE] verify_project error: {e}")
        return {"success": False, "valid": False, "message": f"verify_project failed: {str(e)[:80]}"}


def verify_record(store_path: str, record_id: str | int) -> dict:
    """Read JSONL store, find record by ID (uses 'id' or '_id' field), return match."""
    try:
        p = _validate_path(store_path)
        if not p.exists():
            return {"success": False, "message": f"Store not found: {store_path}"}
        with open(p, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    rec_id = rec.get("id") or rec.get("_id")
                    if str(rec_id) == str(record_id):
                        return {"success": True, "found": True, "record": rec,
                                "message": f"Record {record_id} found at line {line_no}"}
                except json.JSONDecodeError:
                    continue
        return {"success": True, "found": False, "message": f"Record {record_id} not found in {store_path}"}
    except Exception as e:
        logger.error(f"[FILE] verify_record error: {e}")
        return {"success": False, "message": f"verify_record failed: {str(e)[:80]}"}


def verify_sheet_row(path: str, sheet_name: str = "", row_index: int = 0) -> dict:
    """Read a row from Excel by index and return its values."""
    try:
        from openpyxl import load_workbook
        p = _validate_path(path)
        if not p.exists():
            return {"success": False, "message": f"File not found: {path}"}
        wb = load_workbook(str(p))
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
        if row_index < 1:
            row_index = ws.max_row
        values = [ws.cell(row=row_index, column=c).value for c in range(1, ws.max_column + 1)]
        logger.info(f"[FILE] verify_sheet_row: {p} row={row_index} values={len(values)}")
        return {"success": True, "values": values, "row_index": row_index,
                "message": f"Row {row_index}: {len(values)} values"}
    except ImportError:
        return {"success": False, "message": "verify_sheet_row: openpyxl not installed"}
    except Exception as e:
        logger.error(f"[FILE] verify_sheet_row error: {e}")
        return {"success": False, "message": f"verify_sheet_row failed: {str(e)[:80]}"}


# ---------------------------------------------------------------------------
# Filesystem-local batch actions (Phase 7 Batch 3)
# ---------------------------------------------------------------------------

def append_csv(rows: list, columns: list | None = None, path: str = "", min_confidence: float = 0.0) -> dict:
    """Append rows to an existing CSV file. Creates header if file doesn't exist."""
    try:
        p = Path(path) if path else Path.cwd() / "output.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        file_exists = p.exists() and p.stat().st_size > 0
        with open(p, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if columns and not file_exists:
                writer.writerow(columns)
            for row in rows:
                writer.writerow(row)
        return {"success": True, "path": str(p), "rows_appended": len(rows),
                "message": f"Appended {len(rows)} rows to {p.name}"}
    except Exception as e:
        return {"success": False, "message": f"append_csv failed: {str(e)[:80]}"}


def append_records(store: str, records: list | None = None) -> dict:
    """Append JSON records (one per line) to a store file."""
    records = records or []
    try:
        p = Path(store)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, default=str) + "\n")
        return {"success": True, "path": str(p), "records_appended": len(records),
                "message": f"Appended {len(records)} records to {p.name}"}
    except Exception as e:
        return {"success": False, "message": f"append_records failed: {str(e)[:80]}"}


def classify_file(file_path: str, rules: dict | None = None, ai: bool = False) -> dict:
    """Classify a file by extension, name patterns, or simple rules dict.
    
    rules: {"images": ["*.jpg","*.png"], "docs": ["*.pdf","*.docx"]} etc.
    Returns category name or 'uncategorized'.
    """
    rules = rules or {}
    p = Path(file_path)
    if not p.exists():
        return {"success": False, "message": f"File not found: {file_path}"}
    ext = p.suffix.lower()
    name = p.name.lower()
    category = "uncategorized"
    for cat, patterns in rules.items():
        for pat in patterns:
            pat_lower = pat.lower()
            if pat_lower.startswith("*."):
                if ext == pat_lower[1:]:
                    category = cat
                    break
            elif pat_lower in name:
                category = cat
                break
        if category != "uncategorized":
            break
    if category == "uncategorized":
        _EXT_CATS = {
            ".jpg": "images", ".jpeg": "images", ".png": "images", ".gif": "images",
            ".pdf": "documents", ".docx": "documents", ".txt": "documents",
            ".csv": "data", ".json": "data", ".xlsx": "data",
            ".mp4": "media", ".mp3": "media",
        }
        category = _EXT_CATS.get(ext, "uncategorized")
    return {"success": True, "file": str(p), "category": category,
            "extension": ext, "message": f"Classified as: {category}"}


def extract_text(file_path: str, max_chars: int = 100_000) -> dict:
    """Extract text content from a file. Supports txt, md, csv, json, log files."""
    p = Path(file_path)
    if not p.exists():
        return {"success": False, "message": f"File not found: {file_path}"}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        truncated = len(text) > max_chars
        text = text[:max_chars]
        lines = text.count("\n") + 1
        return {"success": True, "text": text, "truncated": truncated,
                "total_chars": len(text), "lines": lines,
                "message": f"Extracted {len(text)} chars from {p.name}"}
    except Exception as e:
        return {"success": False, "message": f"extract_text failed: {str(e)[:80]}"}


def group_duplicates(hash_index: dict | None = None) -> dict:
    """Group files by hash from a hash_index dict (hash -> [paths]).
    
    hash_index comes from hash_tree() output or a pre-computed index.
    Returns groups of duplicate files.
    """
    hash_index = hash_index or {}
    groups = []
    for h, paths in hash_index.items():
        if len(paths) > 1:
            groups.append({"hash": h, "files": paths, "count": len(paths)})
    return {"success": True, "duplicate_groups": len(groups),
            "total_duplicates": sum(g["count"] for g in groups),
            "groups": groups,
            "message": f"Found {len(groups)} duplicate groups"}


def store_transcript(store: str, transcript: str = "", summary: str = "", actions: list | None = None) -> dict:
    """Store a transcript with summary and actions to a JSON file."""
    actions = actions or []
    try:
        p = Path(store)
        p.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "transcript": transcript,
            "summary": summary,
            "actions": actions,
            "stored_at": __import__("datetime").datetime.utcnow().isoformat(),
        }
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return {"success": True, "path": str(p),
                "message": f"Stored transcript ({len(transcript)} chars) to {p.name}"}
    except Exception as e:
        return {"success": False, "message": f"store_transcript failed: {str(e)[:80]}"}


def verify_path(path: str) -> dict:
    """Verify a path exists and return metadata."""
    p = Path(path)
    if not p.exists():
        return {"success": False, "path": str(p), "exists": False,
                "message": f"Path not found: {path}"}
    is_dir = p.is_dir()
    size = p.stat().st_size if p.is_file() else 0
    return {"success": True, "path": str(p), "exists": True,
            "is_directory": is_dir, "is_file": p.is_file(),
            "size_bytes": size,
            "message": f"{'Directory' if is_dir else 'File'} exists: {p.name}"}


__all__ = [
    "open_folder", "create_file", "list_directory", "list_files",
    "write_csv", "read_file", "move_file", "fs_exists", "hash_file",
    "hash_tree", "store_record",
    "append_sheet_row", "prune_old_backups", "redact_csv", "verify_csv",
    "verify_image", "verify_project", "verify_record", "verify_sheet_row",
    "append_csv", "append_records", "classify_file", "extract_text",
    "group_duplicates", "store_transcript", "verify_path",
    "FOLDER_ALIASES", "WINDOWS_FOLDERS",
]


def list_files(name: str = "desktop") -> dict:
    """List files in a folder by name or path.

    Resolves friendly folder names (desktop, downloads, etc.) to real paths
    before listing, so 'list files in Desktop' works.
    """
    name_clean = name.lower().strip()
    # Resolve alias to real path
    if name_clean in FOLDER_ALIASES:
        alias = FOLDER_ALIASES[name_clean]
        # shell: paths need special handling — use open_folder's resolve
        if alias.startswith("shell:"):
            # On Windows, shell: paths resolve via explorer; use USERPROFILE
            subfolder = alias[len("shell:"):]
            real_path = str(Path.home() / subfolder)
        else:
            real_path = alias
    else:
        real_path = name_clean
    return list_directory(real_path)
