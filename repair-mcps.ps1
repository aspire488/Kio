<#
.SYNOPSIS
  Attempts automatic fixes for the most common KIO MCP stack failures:
  execution policy, missing uv, stale npx cache, missing Chromium binary,
  and malformed global config (restored from latest backup).
#>

$ErrorActionPreference = "Continue"

$KioRoot        = $PSScriptRoot
$OcGlobalConfig = "$env:USERPROFILE\.config\opencode\opencode.json"
$BackupDir      = "$env:USERPROFILE\.kio-mcp-backups"

Write-Host "== KIO MCP Stack Repair ==" -ForegroundColor Cyan

# 1. Execution policy
$policy = Get-ExecutionPolicy -Scope CurrentUser
if ($policy -eq "Restricted") {
    Write-Host "Fixing execution policy (was Restricted)..." -ForegroundColor Yellow
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
}

# 2. uv/uvx missing
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv missing - reinstalling..." -ForegroundColor Yellow
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    Write-Host "Restart PowerShell after this completes, then re-run repair." -ForegroundColor Yellow
}

# 3. Config JSON malformed -> restore latest backup
$configOk = $true
if (Test-Path $OcGlobalConfig) {
    try {
        Get-Content $OcGlobalConfig -Raw | ConvertFrom-Json | Out-Null
    } catch {
        $configOk = $false
    }
} else {
    $configOk = $false
}

if (-not $configOk) {
    Write-Host "Global config missing or malformed." -ForegroundColor Yellow
    if (Test-Path $BackupDir) {
        $latest = Get-ChildItem $BackupDir -Filter "opencode.*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($latest) {
            Copy-Item $latest.FullName $OcGlobalConfig -Force
            Write-Host "Restored from latest backup: $($latest.Name)" -ForegroundColor Green
        } else {
            Write-Host "No backup found. Run install-mcps.ps1 to regenerate config from scratch." -ForegroundColor Red
        }
    } else {
        Write-Host "No backup directory found. Run install-mcps.ps1 to regenerate config from scratch." -ForegroundColor Red
    }
}

# 4. Clear npx cache for the six packages (fixes "stuck on old broken version" issues)
Write-Host "`nClearing npm exec cache for the MCP packages..." -ForegroundColor Cyan
npm cache clean --force 2>$null

# 5. Re-verify Playwright Chromium binary
Write-Host "Re-checking Playwright Chromium install..." -ForegroundColor Cyan
cmd /c "npx -y playwright install chromium"

# 6. Re-warm the rest (pre-download packages without starting servers)
$npxPkgs = @(
    "@modelcontextprotocol/server-filesystem",
    "@modelcontextprotocol/server-memory",
    "@modelcontextprotocol/server-sequential-thinking",
    "@upstash/context7-mcp"
)
foreach ($pkg in $npxPkgs) {
    Write-Host "  - npm pack --dry-run $pkg" -ForegroundColor DarkGray
    cmd /c "npm pack --dry-run $pkg >nul 2>&1"
}
if (Get-Command uvx -ErrorAction SilentlyContinue) {
    cmd /c "uvx mcp-server-git --help >nul 2>&1"
}

Write-Host "`nRepair pass complete. Run verify-mcps.ps1 to confirm." -ForegroundColor Cyan
