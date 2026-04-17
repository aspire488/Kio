# Mini-KIO — Lightweight Personal AI Assistant

API-powered personal assistant. Runs under 100MB RAM. No local AI models.

```
User → Telegram → Intent Router → AI (Groq) / Automation → Response
```

---

## Setup (5 minutes)

### 1. Get API Keys

| Key | Where to get it | Required? |
|-----|----------------|-----------|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) → API Keys | ✅ Yes |
| `TELEGRAM_TOKEN` | Message [@BotFather](https://t.me/BotFather) → `/newbot` | ✅ Yes |
| `ALLOWED_USER_IDS` | Message [@userinfobot](https://t.me/userinfobot) | ✅ Yes |
| `CLAUDE_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | Optional |
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com/apikey) | Optional |

### 2. Clone and Install

```bash
git clone <your-repo> mini_kio
cd mini_kio

# Create virtual environment (keeps RAM clean)
python3 -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
nano .env    # or use any text editor
```

Fill in your keys:
```env
GROQ_API_KEY=gsk_xxxxxxxxxxxx
TELEGRAM_TOKEN=1234567890:AAxxxxxxxxxxxx
ALLOWED_USER_IDS=987654321
```

### 4. Run

```bash
python main.py
```

You'll see:
```
==================================================
  Mini-KIO — Lightweight Personal AI Assistant
==================================================
10:23:01 [INFO] main: Initializing database...
10:23:01 [INFO] main: Database ready.
10:23:01 [INFO] main: Starting Telegram interface...
🤖 Mini-KIO is running. Press Ctrl+C to stop.
```

Open Telegram → find your bot → `/start`

---

## Commands

| What you type | What happens |
|---------------|-------------|
| `open youtube` | Opens YouTube in browser |
| `open vscode` | Launches VS Code |
| `take screenshot` | Saves screenshot to ~/Pictures |
| `save idea Build a portfolio` | Stores idea in SQLite |
| `list ideas` | Shows all saved ideas |
| `delete idea #3` | Deletes idea #3 |
| `add task Review PR` | Adds task |
| `list tasks` | Shows pending tasks |
| `complete task #1` | Marks task done |
| `remember that db = mini_kio_memory.db` | Saves key-value |
| `what is db` | Retrieves value |
| `generate code for a REST API in Flask` | Groq generates code |
| `system info` | Shows RAM/OS stats |
| Anything else | AI chat via Groq |

---

## RAM Profile

| State | Expected RAM |
|-------|-------------|
| Idle (bot polling) | ~45–60 MB |
| Active AI response | ~70–95 MB |
| Peak (code gen) | ~90–110 MB |

Stays well under your 120 MB target.

---

## Run on Boot (Linux — systemd)

```bash
# Create service file
sudo nano /etc/systemd/system/mini-kio.service
```

```ini
[Unit]
Description=Mini-KIO Personal Assistant
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/mini_kio
ExecStart=/path/to/mini_kio/venv/bin/python main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable mini-kio
sudo systemctl start mini-kio
sudo systemctl status mini-kio
```

---

## File Structure

```
mini_kio/
├── main.py          # Entry point
├── config.py        # Environment variables
├── ai.py            # Groq/Claude/Gemini API calls
├── router.py        # Intent detection + routing
├── automation.py    # Safe whitelisted system actions
├── memory.py        # SQLite: ideas, tasks, key-value
├── telegram_bot.py  # Telegram interface + auth
├── voice.py         # Placeholder for future voice
├── requirements.txt
├── .env.example
└── .env             # Your secrets (never commit this)
```

---

## Adding New Commands

**1. Add to `automation.py`** — new whitelisted action:
```python
def open_spotify() -> dict:
    webbrowser.open("https://open.spotify.com")
    return _ok("✅ Opened Spotify")
```

**2. Add to `ALLOWED_URLS` or `ALLOWED_APPS`** in `automation.py`

**3. Add pattern to `router.py`**:
```python
(r"\bopen\s+spotify\b", "open_website"),
```

**4. Add handler in `route()` in `router.py`** if needed.

That's it. No framework changes, no class hierarchy changes.

---

## Troubleshooting

**`TELEGRAM_TOKEN not set`** → Check your `.env` file exists and has the token.

**`All AI providers failed`** → Verify `GROQ_API_KEY` at console.groq.com → API Keys.

**Screenshot fails** → Install: `sudo apt install gnome-screenshot` or `sudo apt install scrot`

**VS Code won't open** → Make sure `code` is in PATH: `which code`

**Bot doesn't respond** → Check you're using your actual Telegram user ID (not username). Message @userinfobot.
