import os, sys, subprocess, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
worker = os.path.join(ROOT, "tests", "e2e_telegram", "_bot_worker.py")
flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
proc = subprocess.Popen(
    [sys.executable, worker],
    stdout=open(os.path.join(ROOT, "tests", "e2e_telegram", "bot_stdout.log"), "w"),
    stderr=open(os.path.join(ROOT, "tests", "e2e_telegram", "bot_stderr.log"), "w"),
    creationflags=flags,
)
with open(os.path.join(ROOT, "tests", "e2e_telegram", "bot.pid"), "w") as f:
    f.write(str(proc.pid))
print(f"Bot launched: PID={proc.pid}")
time.sleep(12)
alive = proc.poll() is None
print(f"Bot alive after 12s: {alive}")
if not alive:
    print(f"Exit code: {proc.returncode}")
    try:
        with open(os.path.join(ROOT, "tests", "e2e_telegram", "bot_stderr.log"), "r", encoding="utf-8") as f:
            for line in f.readlines()[-15:]:
                print(f"  ERR: {line.rstrip()}")
    except Exception:
        pass
else:
    print("Bot is running and polling Telegram")
