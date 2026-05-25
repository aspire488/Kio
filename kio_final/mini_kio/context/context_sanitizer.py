import re
import base64
from typing import Tuple, List, Optional


class ContextSanitizer:
    """
    Sanitizes untrusted context data to prevent injection and authority bypass.
    Strictly deterministic. No semantic reasoning.
    """

    RESTRICTED_PATTERNS = [
        r";", r"&", r"\|", r">", r"<", r"\$\(", r"eval\(", r"exec\(",
        r"sudo\s", r"cmd\.exe", r"powershell\.exe", r"powershell\s",
        r"bash\s", r"sh\s",
        r"rm\s+-rf", r"format\s+[a-z]:", r"del\s+/s",
        r"\{\s*\"intent_type\"\s*:",
        r"import\s+os", r"import\s+subprocess", r"import\s+shutil",
        r"subprocess\.", r"os\.system", r"shell=True",
    ]

    MAX_ENTRY_SIZE = 2048

    # Patterns for import sanitization (rejected entirely, not truncated)
    IMPORT_REJECT_PATTERNS = [
        r"cmd\.exe",
        r"powershell",
        r"eval\s*\(",
        r"exec\s*\(",
        r"subprocess",
        r"os\.system",
        r"shell\s*=",
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"ignore\s+(all\s+)?prior\s+instructions",
        r"you\s+are\s+(now\s+)?a\s+free\s+ai",
        r"your\s+new\s+instruction",
        r"disregard\s+(all\s+)?(prior|previous)",
        r"```\s*\w*\s*\n",
    ]

    # Prompt injection phrases (case-insensitive)
    IMPORT_REJECT_PHRASES = [
        "ignore previous instructions",
        "ignore all previous instructions",
        "you are now a free ai",
        "your new instruction is",
        "disregard all previous",
        "system prompt override",
    ]

    def sanitize(self, text: str) -> Tuple[bool, str, List[str]]:
        """
        Validates and cleanses context text.
        Returns: (is_safe, sanitized_text, errors)
        """
        errors = []

        if len(text) > self.MAX_ENTRY_SIZE:
            errors.append(f"Context entry oversized ({len(text)} > {self.MAX_ENTRY_SIZE})")
            return False, "", errors

        for pattern in self.RESTRICTED_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                errors.append(f"Restricted pattern detected: {pattern}")
                return False, "", errors

        sanitized = "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t")

        return True, sanitized.strip(), []

    def sanitize_history(self, history_entries: List[str]) -> List[str]:
        """Bulk sanitization for imported histories."""
        sanitized_list = []
        for entry in history_entries:
            is_safe, text, _ = self.sanitize(entry)
            if is_safe:
                sanitized_list.append(text)
        return sanitized_list

    def sanitize_import(self, text: str, max_length: int = 4096) -> Tuple[bool, str, List[str]]:
        """
        Hardened sanitization for imported memory entries.
        Rejects malicious patterns entirely.
        Truncates oversized SAFE text.
        """
        errors = []

        # 1. Reject empty
        if not text or not text.strip():
            errors.append("Empty text rejected")
            return False, "", errors

        # 2. Check for prompt injection phrases
        text_lower = text.lower()
        for phrase in self.IMPORT_REJECT_PHRASES:
            if phrase in text_lower:
                errors.append(f"Prompt injection phrase detected: {phrase}")
                return False, "", errors

        # 3. Reject malicious patterns
        for pattern in self.IMPORT_REJECT_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                errors.append(f"Restricted pattern detected in import: {pattern}")
                return False, "", errors

        # 4. Reject base64 blobs (80+ chars requiring at least one digit or symbol)
        b64_chunk = re.search(r"(?=[A-Za-z0-9+/=]{81,})[A-Za-z0-9+/=]*[0-9+/][A-Za-z0-9+/=]*", text)
        if b64_chunk:
            errors.append("Base64 blob rejected")
            return False, "", errors

        # 5. Reject markdown code blocks (``` ... ```)
        if re.search(r"```", text):
            errors.append("Markdown code block rejected")
            return False, "", errors

        # 6. Size enforcement: truncate oversized SAFE text
        if len(text) > max_length:
            text = text[:max_length]

        # 7. Clean non-printable characters
        sanitized = "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t")

        return True, sanitized.strip(), []
