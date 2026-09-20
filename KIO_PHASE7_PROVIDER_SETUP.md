# KIO Phase 7 Provider Setup Guide

## Credentials Required for External Providers

### Google Calendar + Drive (B)
1. Go to https://console.cloud.google.com
2. Create project "KIO" or select existing
3. Enable APIs: Google Calendar API, Google Drive API
4. Create OAuth 2.0 Desktop credentials
5. Download credentials.json to `~/.kio/credentials/google_credentials.json`
6. Set env vars:
   ```
   GOOGLE_OAUTH_CLIENT_ID=<from credentials.json>
   GOOGLE_OAUTH_CLIENT_SECRET=<from credentials.json>
   ```

### YouTube Data API (C)
1. Same Google Cloud project as above
2. Enable YouTube Data API v3
3. Create OAuth 2.0 credentials (Desktop or TV/Limited Input)
4. Set env vars:
   ```
   YOUTUBE_CLIENT_ID=<from credentials.json>
   YOUTUBE_CLIENT_SECRET=<from credentials.json>
   ```

### Notion (D)
1. Go to https://www.notion.so/my-integrations
2. Create new integration "KIO"
3. Copy Internal Integration Token
4. Set env var:
   ```
   NOTION_API_KEY=<integration_token>
   ```

### Todoist (D)
1. Go to https://todoist.com/app/settings/integrations/developer
2. Create new integration
3. Copy API token
4. Set env var:
   ```
   TODOIST_API_TOKEN=<api_token>
   ```

## Already Configured Providers (No Action Needed)

| Provider | Status | Env Var |
|----------|--------|---------|
| Telegram Bot | ✅ Active | TELEGRAM_TOKEN |
| GitHub API | ✅ Active | GITHUB_TOKEN |
| Gemini (Google AI) | ✅ Active | GEMINI_API_KEY |
| Groq | ✅ Active | GROQ_API_KEY |
| OpenRouter | ✅ Active | OPENROUTER_API_KEY |
| Tavily Search | ✅ Active | TAVILY_API_KEY |
| Exa Search | ✅ Active | EXA_API_KEY |
| HuggingFace | ✅ Active | HF_TOKEN |
| Edge TTS | ✅ Active | (no key needed) |
| FFmpeg | ✅ Active | (no key needed) |
| Playwright | ✅ Active | (browser-based) |

## Adding Credentials

After creating credentials, add them to `C:\Users\joelj\OneDrive\Desktop\Kio\kio_fixed_v3\kio_final\.env`:

```bash
# Google Calendar/Drive
GOOGLE_OAUTH_CLIENT_ID=your_client_id
GOOGLE_OAUTH_CLIENT_SECRET=your_client_secret

# YouTube
YOUTUBE_CLIENT_ID=your_client_id
YOUTUBE_CLIENT_SECRET=your_client_secret

# Notion
NOTION_API_KEY=your_integration_token

# Todoist
TODOIST_API_TOKEN=your_api_token
```
