"""
Pytest auto-guard: sets KIO_TEST_MODE=1 and installs operational
monkeypatches before any test runs to intercept all webbrowser.open,
subprocess.Popen/run, and os.startfile calls.
"""

import os

os.environ["KIO_TEST_MODE"] = "1"

from mini_kio.core._operational_monkeypatch import install_monkeypatches

install_monkeypatches()
