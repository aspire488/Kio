<#
.SYNOPSIS
  Updates all six MCP servers to latest, keeping Playwright's MCP version
  and Chromium binary version in sync (they must match).
#>

$ErrorActionPreference = "Continue"
$KioRoot = $PSScriptRoot

Write-Host "== KIO MCP Stack Update ==" -ForegroundColor Cyan

Write-Host "`nUpdating npx-cached packages..." -ForegroundColor Cyan
cmd /c "npm cache clean --force"
$npxPkgs = @(
    "@modelcontextprotocol/server-filesystem",
    "@modelcontextprotocol/server-memory",
    "@modelcontextprotocol/server-sequential-thinking",
    "@upstash/context7-mcp"
)
foreach ($pkg in $npxPkgs) {
    Write-Host "  - npm pack --dry-run $pkg@latest" -ForegroundColor DarkGray
    cmd /c "npm pack --dry-run $pkg@latest >nul 2>&1"
}

Write-Host "`nUpdating Playwright MCP + matching Chromium build (must move together)..." -ForegroundColor Cyan
cmd /c "npm pack --dry-run @playwright/mcp@latest >nul 2>&1"
cmd /c "npx -y playwright install chromium"

Write-Host "`nUpdating Git MCP server (uv tool)..." -ForegroundColor Cyan
if (Get-Command uv -ErrorAction SilentlyContinue) {
    cmd /c "uv cache clean mcp-server-git >nul 2>&1"
    cmd /c "uvx mcp-server-git --help >nul 2>&1"
} else {
    Write-Host "uv not found - skipping. Run repair-mcps.ps1 first." -ForegroundColor Red
}

Write-Host "`nUpdate complete. Run verify-mcps.ps1, then re-run the functional test prompts (Phase 6) - a version bump is the most common cause of a previously-working server silently breaking." -ForegroundColor Cyan
