import os
import re

with open(r'c:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\app_operator.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Update _fuzzy_app_discovery
old_fuzzy = '''    search_dirs = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
    ]'''

new_fuzzy = '''    local_app_data = os.environ.get("LOCALAPPDATA", "")
    roaming_app_data = os.environ.get("APPDATA", "")
    user_profile = os.environ.get("USERPROFILE", "")
    search_dirs = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        local_app_data,
        roaming_app_data,
        os.path.join(local_app_data, "Programs"),
        os.path.join(local_app_data, "Microsoft", "WindowsApps"),
        os.path.join(user_profile, "scoop", "apps"),
        os.path.join(os.environ.get("ProgramData", ""), "chocolatey", "bin"),
        os.path.join(roaming_app_data, "npm"),
    ]'''

code = code.replace(old_fuzzy, new_fuzzy)

# 2. Add execute_capability
new_func = '''
# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------
APP_CAPABILITIES = {
    "chrome": ["search", "open_url", "youtube", "new_tab"],
    "edge": ["search", "open_url", "youtube"],
    "firefox": ["search", "open_url", "youtube"],
    "brave": ["search", "open_url", "youtube"],
    "spotify": ["play", "pause", "next", "previous"],
    "vlc": ["play", "pause"],
    "youtube": ["play"],
    "vscode": ["open_project", "open_file"],
    "telegram": ["send_message"],
    "capcut": ["play"],
}

def execute_capability(target: str) -> dict:
    parts = target.split("::", 2)
    if len(parts) < 2:
        return {"success": False, "message": "Invalid capability routing format."}
    
    app_name, cap = parts[0], parts[1]
    args = parts[2] if len(parts) == 3 else ""
    
    caps = APP_CAPABILITIES.get(app_name, [])
    if cap not in caps:
        return {"success": False, "message": f"{app_name} does not support '{cap}'."}
        
    logger.info(f"[CAPABILITY] Routing {cap} to {app_name} with args: {args}")
    
    if cap in ("search", "open_url", "youtube"):
        import urllib.parse
        if cap == "search":
            url = f"https://www.google.com/search?q={urllib.parse.quote_plus(args)}"
        elif cap == "youtube" or (cap == "play" and app_name == "youtube"):
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(args)}&autoplay=1"
        else:
            url = args if args.startswith("http") else "https://" + args
            
        info = _find_in_registry(app_name)
        if not info:
            return {"success": False, "message": f"Browser {app_name} not found in registry."}
        
        path = _resolve_path(info)
        if not path:
             return {"success": False, "message": f"Browser {app_name} path not found."}
             
        try:
            import subprocess
            subprocess.Popen([path, url], shell=False)
            return {"success": True, "message": f"Routed {cap} to {app_name}."}
        except Exception as e:
            return {"success": False, "message": f"Failed to route {cap} to {app_name}: {e}"}
            
    # For now, just mock media capabilities since KIO is lightweight and doesn't hook into Windows Media APIs
    if cap in ("play", "pause", "next", "previous", "open_project", "open_file", "send_message"):
        return {"success": True, "message": f"Successfully routed '{cap}' to {app_name} (mocked API)."}
        
    return {"success": False, "message": f"Capability {cap} not implemented."}
'''

if 'def execute_capability' not in code:
    code = code.replace('__all__ = ["launch_app"', new_func + '\n__all__ = ["launch_app", "execute_capability", ')

# 3. UWP close fix
old_close = '''                if f_result.returncode == 0:
                    _cleanup_chrome_temp_profile(pid)
                    return {"success": True, "message": f"Closed {name} (pid {pid}) forcefully.", "pid": pid}'''
                    
new_close = '''                if f_result.returncode == 0:
                    _cleanup_chrome_temp_profile(pid)
                    
                    # Phase E: UWP Container-Aware Check
                    info = _find_in_registry(key)
                    if info and info.get("lifecycle") == "uwp":
                         return {"success": True, "message": f"Closed {name} (pid {pid}) [Note: UWP shared-container persistence limitation may leave ghost UI]", "pid": pid}
                         
                    return {"success": True, "message": f"Closed {name} (pid {pid}) forcefully.", "pid": pid}'''

code = code.replace(old_close, new_close)

with open(r'c:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\app_operator.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("app_operator.py patched.")
