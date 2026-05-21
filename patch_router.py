with open(r'c:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\command_router.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Replace the search block
search_block = '''        # ── SEARCH ────────────────────────────────────────────────────────────
        if lower.startswith("search "):
            query = command[7:].strip()
            _log_route("route", intent="search")
            return execute_action("search_web", query)'''

new_search = '''        # ── SEARCH ────────────────────────────────────────────────────────────
        if lower.startswith("search "):
            query = command[7:].strip()
            for sep in [" in ", " on ", " using "]:
                if sep in query:
                    parts = query.rsplit(sep, 1)
                    target_app = parts[1].strip()
                    clean_query = parts[0].strip()
                    if target_app in ("chrome", "edge", "firefox", "brave"):
                        _log_route("route", intent="capability", app=target_app, cap="search")
                        return execute_action("execute_capability", f"{target_app}::search::{clean_query}")
            
            _log_route("route", intent="search")
            return execute_action("search_web", query)'''

code = code.replace(search_block, new_search)

# Replace the play block
play_block = '''        # ── PLAY (YouTube) ────────────────────────────────────────────────────
        if lower.startswith("play "):
            query = command[5:].strip()
            _log_route("route", intent="play_youtube")
            return execute_action("play_youtube", query)'''

new_play = '''        # ── PLAY (YouTube / Media) ─────────────────────────────────────────────
        if lower.startswith("play "):
            query = command[5:].strip()
            for sep in [" on ", " in ", " using "]:
                if sep in query:
                    parts = query.rsplit(sep, 1)
                    target_app = parts[1].strip()
                    clean_query = parts[0].strip()
                    if target_app in ("spotify", "youtube", "vlc", "capcut"):
                        _log_route("route", intent="capability", app=target_app, cap="play")
                        return execute_action("execute_capability", f"{target_app}::play::{clean_query}")
            
            _log_route("route", intent="play_youtube")
            return execute_action("play_youtube", query)'''

code = code.replace(play_block, new_play)

with open(r'c:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\command_router.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Router patched.")
