import json

def _get_target_and_clean_query(query: str, seps: list[str]) -> tuple[str, str]:
    for sep in seps:
        if sep in query:
            parts = query.rsplit(sep, 1)
            target_app = parts[1].strip().lower()
            clean_query = parts[0].strip()
            if target_app in ("chrome", "edge", "firefox", "brave", "spotify", "youtube", "vlc", "vscode", "telegram"):
                return target_app, clean_query
    return "", query
