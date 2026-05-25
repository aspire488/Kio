"""
export_parser.py — Deterministic import utilities for external memory.

Provider-agnostic. No network. No provider-specific schemas.
stdlib only.
"""

import json
import os
from typing import List, Dict, Any, Optional
from .context_models import ImportEntry


def load_import(path: str) -> Optional[Dict[str, Any]]:
    """
    Load a JSON file and return raw data.
    Returns None if file is missing, unreadable, or not valid JSON.
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, UnicodeDecodeError):
        return None


def extract_entries(raw_data: Any) -> List[Dict[str, Any]]:
    """
    Extract candidate entries from generic JSON data.
    Accepts:
      - list of dicts (direct entry list)
      - dict with 'entries' key (wrapped format)
    Returns empty list for any other structure.
    """
    if isinstance(raw_data, list):
        return raw_data

    if isinstance(raw_data, dict):
        entries = raw_data.get("entries")
        if isinstance(entries, list):
            return entries

    return []


def normalize_entries(entries: List[Dict[str, Any]]) -> List[ImportEntry]:
    """
    Normalize a list of raw entry dicts to ImportEntry objects.
    Fields: timestamp (int), role (str), text (str), source (str).

    Missing or invalid fields use safe defaults:
      - timestamp: 0
      - role: "user"
      - text: ""
      - source: "external_memory"
    """
    result: List[ImportEntry] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue

        timestamp = entry.get("timestamp", 0)
        if not isinstance(timestamp, int):
            try:
                timestamp = int(timestamp)
            except (ValueError, TypeError):
                timestamp = 0

        role = entry.get("role", "user")
        if not isinstance(role, str):
            role = "user"

        text = entry.get("text", "")
        if not isinstance(text, str):
            text = str(text) if text is not None else ""

        source = entry.get("source", "external_memory")
        if not isinstance(source, str):
            source = "external_memory"

        result.append(ImportEntry(
            timestamp=timestamp,
            role=role,
            text=text,
            source=source,
        ))

    return result
