$ErrorActionPreference = "Stop"
$transcriptFile = Join-Path $PSScriptRoot "telegram_transcript.log"

# Remove old transcript
Remove-Item -Force $transcriptFile -ErrorAction SilentlyContinue

# Start the bot with logging redirected
Write-Host "Starting KIO Telegram Bot..."
Write-Host "Transcript will be written to: $transcriptFile"
Write-Host ""
Write-Host "IMPORTANT: Now send messages to the KIO bot on Telegram."
Write-Host "The bot's responses will be captured here."
Write-Host "Press Ctrl+C to stop the bot when done."
Write-Host ""

# Set environment to ensure logging is visible
$env:PYTHONUNBUFFERED = "1"

# Run the bot - it will log everything to console which we capture
python -u "$PSScriptRoot\kio_bot.py" *>&1 | Tee-Object -FilePath $transcriptFile
