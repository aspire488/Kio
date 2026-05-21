def _refine_pid_windows(
    initial_pid: int,
    proc_name: str,
    prior_pids: set[int] | None = None,
    launch_start: float | None = None,
    uwp_packages: list[str] | None = None,
    lifecycle: str = "standard",
) -> int | None:
    """Surgical PID refinement: Capture the 'real' PID if the initial one is a transient launcher."""
    if not _IS_WINDOWS:
        return initial_pid

    prior_pids = prior_pids or set()
    if launch_start is None:
        launch_start = time.time()

    uwp_packages = uwp_packages or []

    try:
        import psutil
        
        target_names = {proc_name.lower()}
        for u in uwp_packages:
            target_names.add(u.lower())
        
        normalized_targets = {t if t.endswith(".exe") else t + ".exe" for t in target_names}

        # Helper exclusion logic
        def _is_valid_root(proc: psutil.Process) -> bool:
            try:
                cmdline = proc.cmdline()
                name = proc.name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False

            # Reject common helper/launcher wrappers if they are not explicitly what we launched
            if name in ("conhost.exe", "cmd.exe", "powershell.exe", "update.exe", "launcher.exe", "bash.exe", "wsl.exe"):
                if lifecycle != "launcher":
                    return False

            if len(cmdline) <= 1:
                return True

            for arg in cmdline[1:]:
                # Common Electron / Browser / Chromium helpers
                arg_lower = arg.lower()
                if any(x in arg_lower for x in (
                    "--type=renderer", 
                    "--type=gpu-process", 
                    "--type=utility", 
                    "--type=crashpad-handler", 
                    "--type=broker"
                )):
                    return False
                
            if lifecycle == "browser":
                for arg in cmdline[1:]:
                    if arg.lower().startswith("--type="):
                        return arg.lower() == "--type=browser"
                        
            return True

        # Packaged app detection
        is_packaged_broker = False
        try:
            initial_proc = psutil.Process(initial_pid)
            if initial_proc.is_running():
                iname = initial_proc.name().lower()
                if iname in ("applicationframehost.exe", "shellexperiencehost.exe"):
                    is_packaged_broker = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # UWP Refinement
        if lifecycle == "uwp" or is_packaged_broker:
            deadline = launch_start + 3.0
            
            def _find_latest_uwp_process(exclude_pids: set[int]) -> psutil.Process | None:
                newest_proc = None
                newest_time = 0.0
                for proc in psutil.process_iter(['pid', 'name', 'create_time']):
                    try:
                        pid = proc.info['pid']
                        name = proc.info['name']
                        if pid in exclude_pids:
                            continue
                        if not name or name.lower() not in normalized_targets:
                            continue
                        if not proc.is_running():
                            continue
                        if not _is_valid_root(proc):
                            continue
                            
                        ctime = proc.info['create_time']
                        if ctime > newest_time:
                            newest_time = ctime
                            newest_proc = proc
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                return newest_proc

            while time.time() < deadline:
                newest_proc = _find_latest_uwp_process(prior_pids)
                if newest_proc is not None:
                    logger.info(f"[APP] PID refined for {proc_name} (UWP): {initial_pid} -> {newest_proc.pid}")
                    return newest_proc.pid
                time.sleep(0.1)
                
            logger.info(f"[APP] UWP PID refinement timeout for {proc_name}")
            return None

        # Singleton reuse detection
        if lifecycle == "singleton":
            def _find_latest_singleton() -> psutil.Process | None:
                newest_proc = None
                newest_time = 0.0
                for proc in psutil.process_iter(['pid', 'name', 'create_time']):
                    try:
                        pid = proc.info['pid']
                        name = proc.info['name']
                        if not name or name.lower() not in normalized_targets:
                            continue
                        if not proc.is_running():
                            continue
                        if not _is_valid_root(proc):
                            continue
                        ctime = proc.info['create_time']
                        if ctime > newest_time:
                            newest_time = ctime
                            newest_proc = proc
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                return newest_proc

            deadline = launch_start + 3.0
            while time.time() < deadline:
                new_proc = _find_latest_singleton()
                # If we found a process and it's NOT in prior_pids, it's new
                if new_proc and new_proc.pid not in prior_pids:
                    logger.info(f"[APP] PID refined for {proc_name} (new singleton instance): {initial_pid} -> {new_proc.pid}")
                    return new_proc.pid
                time.sleep(0.1)
            
            # If we timeout and no NEW process, fallback to existing
            existing = _find_latest_singleton()
            if existing and existing.pid in prior_pids:
                logger.info(f"[APP] Singleton reuse detected for {proc_name}: {existing.pid}")
                return existing.pid
            
            logger.info(f"[APP] Singleton PID refinement failed for {proc_name}")
            return None

        # Standard / Browser / Electron refinement (Tree lineage and creation time)
        target_name = proc_name.lower()
        if not target_name.endswith(".exe"):
            target_name += ".exe"

        def _find_recent_target_child(parent_proc: psutil.Process) -> psutil.Process | None:
            newest_proc = None
            newest_time = 0.0
            now = time.time()
            for child in parent_proc.children(recursive=True):
                try:
                    if child.is_running() and child.name().lower() == target_name and _is_valid_root(child):
                        create_time = child.create_time()
                        if (now - create_time) < 5.0 and create_time > newest_time:
                            newest_time = create_time
                            newest_proc = child
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return newest_proc

        def _find_root_ancestor(proc: psutil.Process) -> psutil.Process | None:
            for ancestor in proc.parents():
                try:
                    if ancestor.name().lower() == target_name and _is_valid_root(ancestor):
                        return ancestor
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return None

        def _find_latest_matching_process(exclude_pids: set[int], allow_stale: bool = False) -> psutil.Process | None:
            root_proc = None
            root_time = 0.0
            now = time.time()
            for proc in psutil.process_iter(['pid', 'name', 'create_time']):
                try:
                    pid = proc.info['pid']
                    name = proc.info['name']
                    create_time = proc.info['create_time']
                    if pid in exclude_pids:
                        continue
                    if not name or name.lower() != target_name:
                        continue
                    if not proc.is_running():
                        continue
                    if not allow_stale and (create_time < launch_start - 2.0 or create_time > now + 2.0):
                        continue
                    if _is_valid_root(proc):
                        if create_time > root_time:
                            root_time = create_time
                            root_proc = proc
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return root_proc

        try:
            p = psutil.Process(initial_pid)
            if p.is_running():
                if _is_valid_root(p):
                    return initial_pid

                parent_root = _find_root_ancestor(p)
                if parent_root is not None:
                    logger.info(
                        f"[APP] PID refined for {proc_name} via ancestor root: {initial_pid} -> {parent_root.pid}"
                    )
                    return parent_root.pid

                child_proc = _find_recent_target_child(p)
                if child_proc is not None:
                    logger.info(
                        f"[APP] PID refined for {proc_name} via child: {initial_pid} -> {child_proc.pid}"
                    )
                    return child_proc.pid

                if p.name().lower() == target_name:
                    newest_proc = _find_latest_matching_process({initial_pid} | prior_pids)
                    if newest_proc is not None:
                        logger.info(
                            f"[APP] PID refined for {proc_name}: {initial_pid} -> {newest_proc.pid}"
                        )
                        return newest_proc.pid
                    return initial_pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        newest_proc = _find_latest_matching_process(prior_pids)
        if newest_proc is not None:
            logger.info(f"[APP] PID refined for {proc_name}: {initial_pid} -> {newest_proc.pid}")
            return newest_proc.pid

        # Launcher-detach refinement: If no new process found, maybe it re-used a singleton?
        # Standard/Electron apps sometimes behave as singletons.
        fallback_proc = _find_latest_matching_process(set(), allow_stale=True)
        if fallback_proc is not None:
            logger.info(
                f"[APP] PID fallback refined for {proc_name}: {initial_pid} -> {fallback_proc.pid}"
            )
            return fallback_proc.pid
    except Exception as exc:
        logger.debug(f"[APP] PID refinement skipped: {exc}")

    return initial_pid
