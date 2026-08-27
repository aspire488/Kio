Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final"
WshShell.Run """C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\.venv\Scripts\python.exe"" -u kio_bot.py", 0, False
