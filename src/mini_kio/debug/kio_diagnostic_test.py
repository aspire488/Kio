"""KIO Automation Diagnostic Test - Run full test sequence."""

import sys

sys.path.insert(0, "..")

from core.task_engine import run_task_queue


commands = [
    "open chrome",
    "open chrome and search laliga table",
    "open chrome and search IPL points table",
    "open calculator",
    "open notepad and type hello world then close notepad",
    "open whatsapp and send Thankss to ADITYA(Mallia)🤓",
    "open claude",
]


if __name__ == "__main__":
    print("=" * 60)
    print("KIO AUTOMATION DIAGNOSTIC TEST")
    print("=" * 60)
    print()

    result = run_task_queue(commands)

    print()
    print("=" * 60)
    print("KIO AUTOMATION DIAGNOSTIC COMPLETE")
    print("=" * 60)
    print(f"Total commands executed: {result['total']}")
    print(f"Failures: {result['failed']}")

    with open("debug/kio_diagnostic_log.txt", "w") as f:
        f.write("KIO AUTOMATION DIAGNOSTIC LOG\n")
        f.write("=" * 40 + "\n\n")
        for r in result["results"]:
            status = "OK" if r.get("success") else "FAIL"
            f.write(f"{status}: {r['command']}\n")
            if r.get("error"):
                f.write(f"  Error: {r['error']}\n")

    print()
    if result["failed"] > 0:
        print(f"Check debug/kio_diagnostic_log.txt for failures")
