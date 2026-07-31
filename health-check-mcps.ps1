<#
.SYNOPSIS
  Combined health check + version audit for the KIO MCP stack.
  Run this weekly or whenever something feels "off" - it's read-only,
  makes no changes.
#>

Write-Host "== KIO MCP Stack Health Check + Version Audit ==" -ForegroundColor Cyan

Write-Host "`n-- Core tool versions --" -ForegroundColor Cyan
Write-Host "node:      $(node -v 2>$null)"
Write-Host "npm:       $(npm -v 2>$null)"
Write-Host "npx:       $(npx -v 2>$null)"
Write-Host "git:       $(git --version 2>$null)"
Write-Host "uv:        $(uv --version 2>$null)"
Write-Host "opencode:  $(opencode --version 2>$null)"

Write-Host "`n-- Cached MCP package versions (from npm cache metadata) --" -ForegroundColor Cyan
$npxPackages = @(
    "@modelcontextprotocol/server-filesystem",
    "@modelcontextprotocol/server-memory",
    "@modelcontextprotocol/server-sequential-thinking",
    "@upstash/context7-mcp",
    "@playwright/mcp"
)
foreach ($pkg in $npxPackages) {
    $latest = npm view $pkg version 2>$null
    Write-Host "$pkg -> latest on registry: $latest"
}

Write-Host "`n-- Git MCP server (PyPI) --" -ForegroundColor Cyan
try {
    $pypiInfo = Invoke-RestMethod -Uri "https://pypi.org/pypi/mcp-server-git/json" -ErrorAction Stop
    Write-Host "mcp-server-git -> latest on PyPI: $($pypiInfo.info.version)"
} catch {
    Write-Host "Could not reach PyPI to check mcp-server-git version (network/firewall?)" -ForegroundColor Yellow
}

Write-Host "`n-- Disk usage of MCP-related caches --" -ForegroundColor Cyan
$npmCache = "$env:APPDATA\npm-cache"
$playwrightCache = "$env:USERPROFILE\AppData\Local\ms-playwright"
foreach ($dir in @($npmCache, $playwrightCache)) {
    if (Test-Path $dir) {
        $size = (Get-ChildItem $dir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
        Write-Host ("{0}: {1:N1} MB" -f $dir, $size)
    } else {
        Write-Host "$dir : not present"
    }
}

Write-Host "`n-- OneDrive sync status reminder --" -ForegroundColor Cyan
Write-Host "If the KIO repo is still inside OneDrive Desktop sync, confirm the sync icon shows fully synced before trusting any 'file not found' error as real."

Write-Host "`n-- Config presence --" -ForegroundColor Cyan
$OcGlobalConfig = "$env:USERPROFILE\.config\opencode\opencode.json"
if (Test-Path $OcGlobalConfig) {
    Write-Host "Global config present: $OcGlobalConfig" -ForegroundColor Green
    Write-Host "Last modified: $((Get-Item $OcGlobalConfig).LastWriteTime)"
} else {
    Write-Host "Global config MISSING: $OcGlobalConfig" -ForegroundColor Red
}

Write-Host "`nHealth check complete. This script made no changes." -ForegroundColor Cyan
