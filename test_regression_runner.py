from mini_kio.core.command_router import handle_command
import json

cases=['open chrome and shutdown','open chrome and restart','open chrome and and','open and','search python and play interstellar theme','open vscode and open downloads folder','open kdenlive','What is string in python','What can you do','Who created you','random gibberish zzzxyz123']
for c in cases:
    print('CASE:',c)
    print(json.dumps(handle_command(c), indent=2))
