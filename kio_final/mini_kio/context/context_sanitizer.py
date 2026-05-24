import re
from typing import Tuple, List, Optional

class ContextSanitizer:
    """
    Sanitizes untrusted context data to prevent injection and authority bypass.
    Strictly deterministic. No semantic reasoning.
    """

    # Patterns that look like execution attempts or shell fragments
    RESTRICTED_PATTERNS = [
        r";", r"&", r"\|", r">", r"<", r"\$\(", r"eval\(", r"sudo\s",
        r"cmd\.exe", r"powershell\.exe", r"bash\s", r"sh\s",
        r"rm\s+-rf", r"format\s+[a-z]:", r"del\s+/s",
        r"\{\s*\"intent_type\"\s*:", # Block raw intent JSON in context to prevent hijacking
        r"import\s+os", r"import\s+subprocess", r"import\s+shutil"
    ]

    MAX_ENTRY_SIZE = 2048 # Bounded entry size

    def sanitize(self, text: str) -> Tuple[bool, str, List[str]]:
        """
        Validates and cleanses context text.
        Returns: (is_safe, sanitized_text, errors)
        """
        errors = []
        
        # 1. Size Check
        if len(text) > self.MAX_ENTRY_SIZE:
            errors.append(f"Context entry oversized ({len(text)} > {self.MAX_ENTRY_SIZE})")
            return False, "", errors

        # 2. Executable/Injection Pattern Check
        for pattern in self.RESTRICTED_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                errors.append(f"Restricted pattern detected: {pattern}")
                return False, "", errors

        # 3. Basic cleaning (remove non-printable or suspicious control chars)
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
