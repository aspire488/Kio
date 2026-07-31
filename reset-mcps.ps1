<#
.SYNOPSIS
  Full wipe: removes config, clears npx/npm and uv caches for these packages,
  removes the cached Playwright Chromium binary, then re-runs install-mcps.ps1
  from a clean state. Use when repair-mcps.ps1 doesn't fix a persistent issue.

.NOTES
  This is the "nuclear option" — everything is rebuilt from scratch. Your
  KIO repo itself is never touched; only OpenCode/MCP-related caches and config.
#>

$ErrorActionPreference = "Continue"

$OcGlobalConfig = "$env:USERPROFILE\.config\opencode\opencode.json"
$BackupDir      = "$env:USERPROFILE\.kio-mcp-backups"
$ScriptDir      = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "== KIO MCP Stack Reset (full wipe) ==" -ForegroundColor Red
Write-Host "This will remove your global OpenCode MCP config (backed up first) and clear npm/uv/Playwright caches." -ForegroundColor Yellow
$confirm = Read-Host "Type YES to continue"
if ($confirm -ne "YES") {
    Write-Host "Aborted." -ForegroundColor Yellow
    exit 0
}

if (Test-Path $OcGlobalConfig) {
    if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir | Out-Null }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Copy-Item $OcGlobalConfig "$BackupDir\opencode.$stamp.pre-reset.json"
    Write-Host "Backed up config to $BackupDir\opencode.$stamp.pre-reset.json" -ForegroundColor Green
    Remove-Item $OcGlobalConfig -Force
}

Write-Host "`nClearing npm cache..." -ForegroundColor Cyan
npm cache clean --force

Write-Host "Clearing uv cache..." -ForegroundColor Cyan
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv cache clean
}

Write-Host "Removing cached Playwright Chromium binary..." -ForegroundColor Cyan
$playwrightCache = "$env:USERPROFILE\AppData\Local\ms-playwright"
if (Test-Path $playwrightCache) {
    Remove-Item $playwrightCache -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "`nRebuilding from scratch via install-mcps.ps1..." -ForegroundColor Cyan
& "$ScriptDir\install-mcps.ps1"

Write-Host "`nReset complete." -ForegroundColor Green
