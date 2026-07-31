<#
.SYNOPSIS
  Installs and configures the 6-server KIO MCP stack (Filesystem, Git, Memory,
  Sequential Thinking, Context7, Playwright) into OpenCode's global config.

.NOTES
  Idempotent: safe to re-run. Backs up any existing global config first.
#>

$ErrorActionPreference = "Stop"

$KioRoot        = $PSScriptRoot
$OcGlobalDir    = "$env:USERPROFILE\.config\opencode"
$OcGlobalConfig = "$OcGlobalDir\opencode.json"
$BackupDir      = "$env:USERPROFILE\.kio-mcp-backups"

Write-Host "== KIO MCP Stack Installer ==" -ForegroundColor Cyan

# --- Phase 1: prerequisite checks ---
function Test-Command($name) {
    $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

$missing = @()
foreach ($cmd in @("node", "npm", "npx", "git", "opencode")) {
    if (-not (Test-Command $cmd)) { $missing += $cmd }
}
if ($missing.Count -gt 0) {
    Write-Host "Missing required commands: $($missing -join ', ')" -ForegroundColor Red
    Write-Host "Install these first, then re-run this script." -ForegroundColor Red
    exit 1
}

if (-not (Test-Command "uv")) {
    Write-Host "uv not found — installing (required for the Git MCP server)..." -ForegroundColor Yellow
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    Write-Host "uv installed. Close and reopen PowerShell, then re-run this script." -ForegroundColor Yellow
    exit 0
}

if (-not (Test-Path $KioRoot)) {
    Write-Host "KIO root not found at $KioRoot — check the path or edit `$KioRoot at the top of this script." -ForegroundColor Red
    exit 1
}

# --- Backup existing global config if present ---
if (Test-Path $OcGlobalConfig) {
    if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir | Out-Null }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Copy-Item $OcGlobalConfig "$BackupDir\opencode.$stamp.json"
    Write-Host "Backed up existing global config to $BackupDir\opencode.$stamp.json" -ForegroundColor Green
}

if (-not (Test-Path $OcGlobalDir)) {
    New-Item -ItemType Directory -Path $OcGlobalDir -Force | Out-Null
}

# --- Warm the npx/uvx caches so failures surface here, not inside OpenCode ---
Write-Host "`nPre-downloading packages to local caches..." -ForegroundColor Cyan
$npxPkgs = @(
    "@modelcontextprotocol/server-filesystem",
    "@modelcontextprotocol/server-memory",
    "@modelcontextprotocol/server-sequential-thinking",
    "@upstash/context7-mcp",
    "@playwright/mcp@latest"
)
foreach ($pkg in $npxPkgs) {
    Write-Host "  - npm pack --dry-run $pkg" -ForegroundColor DarkGray
    cmd /c "npm pack --dry-run $pkg >nul 2>&1"
}
Write-Host "  - uvx mcp-server-git --help" -ForegroundColor DarkGray
cmd /c "uvx mcp-server-git --help >nul 2>&1"

Write-Host "Pre-downloading Playwright Chromium (required for browser automation)..." -ForegroundColor Cyan
cmd /c "npx -y playwright install chromium"

# --- Write global config ---
$escapedKioRoot = $KioRoot -replace '\\', '\\\\'

$config = @"
{
  "`$schema": "https://opencode.ai/config.json",
  "mcp": {
    "filesystem": {
      "type": "local",
      "command": ["cmd", "/c", "npx", "-y", "@modelcontextprotocol/server-filesystem", "$escapedKioRoot"],
      "enabled": true
    },
    "git": {
      "type": "local",
      "command": ["uvx", "--with", "mcp<2.0.0", "mcp-server-git", "--repository", "$escapedKioRoot"],
      "enabled": true
    },
    "memory": {
      "type": "local",
      "command": ["cmd", "/c", "npx", "-y", "@modelcontextprotocol/server-memory"],
      "enabled": true
    },
    "sequential-thinking": {
      "type": "local",
      "command": ["cmd", "/c", "npx", "-y", "@modelcontextprotocol/server-sequential-thinking"],
      "enabled": true
    },
    "context7": {
      "type": "local",
      "command": ["cmd", "/c", "npx", "-y", "@upstash/context7-mcp"],
      "environment": {
        "CONTEXT7_API_KEY": "{env:CONTEXT7_API_KEY}"
      },
      "enabled": true
    },
    "playwright": {
      "type": "local",
      "command": ["cmd", "/c", "npx", "-y", "@playwright/mcp@latest"],
      "enabled": true
    }
  }
}
"@

Set-Content -Path $OcGlobalConfig -Value $config -Encoding UTF8
Write-Host "`nWrote global config: $OcGlobalConfig" -ForegroundColor Green

# --- Validate JSON ---
try {
    Get-Content $OcGlobalConfig -Raw | ConvertFrom-Json | Out-Null
    Write-Host "Config JSON is valid." -ForegroundColor Green
} catch {
    Write-Host "Config JSON failed to parse: $_" -ForegroundColor Red
    exit 1
}

# --- Ensure CONTEXT7_API_KEY reminder ---
$existingKey = [System.Environment]::GetEnvironmentVariable("CONTEXT7_API_KEY", "User")
if (-not $existingKey) {
    Write-Host "`nCONTEXT7_API_KEY is not set. Context7 will still work at low rate limits without it." -ForegroundColor Yellow
    Write-Host "Get a free key at context7.com/dashboard, then run:" -ForegroundColor Yellow
    Write-Host '  [System.Environment]::SetEnvironmentVariable("CONTEXT7_API_KEY", "YOUR_KEY", "User")' -ForegroundColor Yellow
}

Write-Host "`nInstall complete. Run verify-mcps.ps1 next." -ForegroundColor Cyan
