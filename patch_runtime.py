with open(r'c:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\runtime.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Update register_tracked_process
old_reg = '''        entry = {
            "pid": pid,
            "name": name,
            "target": target,
            "launched_at": time.monotonic(),
            "status": "active",
        }'''

new_reg = '''        import psutil
        try:
            p = psutil.Process(pid)
            create_time = p.create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            create_time = 0.0

        entry = {
            "pid": pid,
            "name": name,
            "target": target,
            "launched_at": time.monotonic(),
            "create_time": create_time,
            "status": "active",
        }'''

code = code.replace(old_reg, new_reg)

# 2. Update prune_tracked_processes
old_prune = '''            if is_windows:
                try:
                    # tasklist FI "PID eq ..." is lightweight
                    r = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                        capture_output=True,
                        text=True,
                        timeout=1,
                    )
                    if str(pid) in r.stdout:
                        alive = True
                    else:
                        emit_runtime_trace("DEBUG_runtime_prune_dead_tasklist", pid=pid, name=entry["name"], stdout=r.stdout[:100])
                except Exception as e:
                    # Best effort: assume alive if check fails
                    emit_runtime_trace("DEBUG_runtime_prune_error", pid=pid, error=str(e))
                    alive = True'''

new_prune = '''            if is_windows:
                try:
                    import psutil
                    try:
                        p = psutil.Process(pid)
                        if p.is_running():
                            # Phase A: Prevent PID reuse corruption
                            if entry.get("create_time", 0.0) > 0.0:
                                current_create_time = p.create_time()
                                if abs(current_create_time - entry["create_time"]) > 1.0:
                                    emit_runtime_trace("DEBUG_runtime_prune_pid_reused", pid=pid, name=entry["name"])
                                    alive = False
                                else:
                                    alive = True
                            else:
                                alive = True
                        else:
                            alive = False
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        alive = False
                except Exception as e:
                    emit_runtime_trace("DEBUG_runtime_prune_error", pid=pid, error=str(e))
                    alive = True'''

code = code.replace(old_prune, new_prune)

with open(r'c:\Users\HP\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\mini_kio\core\runtime.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("runtime.py patched.")
