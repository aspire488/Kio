<#
.SYNOPSIS
  Removes the KIO MCP server definitions from OpenCode's global config.
  Does NOT uninstall Node/npm/uv/git/OpenCode itself, and does not delete
  npx/uv package caches (use reset-mcps.ps1 for a full wipe).

.PARAMETER Server
  Optional. Remove a single server by name (filesystem, git, memory,
  sequential-thinking, context7, playwright). If omitted, removes all six.
#>

param(
    [string]$Server = ""
)

$ErrorActionPreference = "Stop"

$OcGlobalConfig = "$env:USERPROFILE\.config\opencode\opencode.json"
$BackupDir      = "$env:USERPROFILE\.kio-mcp-backups"
$allServers     = @("filesystem", "git", "memory", "sequential-thinking", "context7", "playwright")

if (-not (Test-Path $OcGlobalConfig)) {
    Write-Host "No global config found at $OcGlobalConfig — nothing to remove." -ForegroundColor Yellow
    exit 0
}

# Backup first — every destructive script in this package does this
if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir | Out-Null }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item $OcGlobalConfig "$BackupDir\opencode.$stamp.json"
Write-Host "Backed up config to $BackupDir\opencode.$stamp.json" -ForegroundColor Green

$json = Get-Content $OcGlobalConfig -Raw | ConvertFrom-Json

if ($Server -ne "") {
    if ($Server -notin $allServers) {
        Write-Host "Unknown server '$Server'. Valid names: $($allServers -join ', ')" -ForegroundColor Red
        exit 1
    }
    if ($json.mcp.PSObject.Properties.Name -contains $Server) {
        $json.mcp.PSObject.Properties.Remove($Server)
        Write-Host "Removed '$Server' from config." -ForegroundColor Green
    } else {
        Write-Host "'$Server' was not present in config." -ForegroundColor Yellow
    }
} else {
    foreach ($srv in $allServers) {
        if ($json.mcp.PSObject.Properties.Name -contains $srv) {
            $json.mcp.PSObject.Properties.Remove($srv)
        }
    }
    Write-Host "Removed all six KIO MCP server definitions." -ForegroundColor Green
}

$json | ConvertTo-Json -Depth 10 | Set-Content -Path $OcGlobalConfig -Encoding UTF8
Write-Host "Config written. Run 'opencode mcp list' to confirm." -ForegroundColor Cyan
