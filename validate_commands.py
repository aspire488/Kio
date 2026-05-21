import sys
sys.path.append('kio_final')
from mini_kio.core.runtime import dispatch_channel_input, bootstrap_runtime

def validate():
    runtime = bootstrap_runtime()
    
    commands = [
        "ping",
        "open notepad",
        "close notepad",
        "open chrome",
        "close chrome"
    ]
    
    for cmd in commands:
        print(f"\n--- Running: {cmd} ---")
        result = dispatch_channel_input(cmd)
        print("Result:", {k: v for k, v in result.items() if k in ('success', 'message', 'action', 'verification_status', 'failure_class', 'pid')})

if __name__ == "__main__":
    validate()
