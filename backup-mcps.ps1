<#
.SYNOPSIS
  Backup/restore/export/import for the KIO MCP global config.

.PARAMETER Action
  One of: Backup, Restore, Export, Import, List

.PARAMETER Path
  For Restore: specific backup file to restore (defaults to latest).
  For Export/Import: target/source file path (defaults to Desktop).
#>

param(
    [ValidateSet("Backup", "Restore", "Export", "Import", "List")]
    [string]$Action = "Backup",
    [string]$Path = ""
)

$OcGlobalConfig = "$env:USERPROFILE\.config\opencode\opencode.json"
$BackupDir      = "$env:USERPROFILE\.kio-mcp-backups"

if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir | Out-Null }

switch ($Action) {

    "Backup" {
        if (-not (Test-Path $OcGlobalConfig)) {
            Write-Host "No config found at $OcGlobalConfig — nothing to back up." -ForegroundColor Yellow
            exit 0
        }
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $dest = "$BackupDir\opencode.$stamp.json"
        Copy-Item $OcGlobalConfig $dest
        Write-Host "Backed up to $dest" -ForegroundColor Green
    }

    "Restore" {
        if ($Path -eq "") {
            $target = Get-ChildItem $BackupDir -Filter "opencode.*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if (-not $target) {
                Write-Host "No backups found in $BackupDir" -ForegroundColor Red
                exit 1
            }
            $Path = $target.FullName
        }
        if (-not (Test-Path $Path)) {
            Write-Host "Backup file not found: $Path" -ForegroundColor Red
            exit 1
        }
        # Validate before restoring
        try {
            Get-Content $Path -Raw | ConvertFrom-Json | Out-Null
        } catch {
            Write-Host "Backup file is not valid JSON, refusing to restore: $Path" -ForegroundColor Red
            exit 1
        }
        Copy-Item $Path $OcGlobalConfig -Force
        Write-Host "Restored $Path -> $OcGlobalConfig" -ForegroundColor Green
    }

    "Export" {
        if ($Path -eq "") { $Path = "$env:USERPROFILE\Desktop\kio-mcp-config-export.json" }
        if (-not (Test-Path $OcGlobalConfig)) {
            Write-Host "No config found to export." -ForegroundColor Red
            exit 1
        }
        Copy-Item $OcGlobalConfig $Path -Force
        Write-Host "Exported to $Path" -ForegroundColor Green
        Write-Host "NOTE: CONTEXT7_API_KEY is stored as an env var reference, not a literal value, so this export is safe to share/move between machines — just re-set the env var on the target machine." -ForegroundColor Yellow
    }

    "Import" {
        if ($Path -eq "") {
            Write-Host "Specify -Path to the config file to import." -ForegroundColor Red
            exit 1
        }
        if (-not (Test-Path $Path)) {
            Write-Host "File not found: $Path" -ForegroundColor Red
            exit 1
        }
        try {
            Get-Content $Path -Raw | ConvertFrom-Json | Out-Null
        } catch {
            Write-Host "Import file is not valid JSON, aborting." -ForegroundColor Red
            exit 1
        }
        # Backup current before overwriting
        if (Test-Path $OcGlobalConfig) {
            $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
            Copy-Item $OcGlobalConfig "$BackupDir\opencode.$stamp.pre-import.json"
        }
        $OcGlobalDir = Split-Path -Parent $OcGlobalConfig
        if (-not (Test-Path $OcGlobalDir)) { New-Item -ItemType Directory -Path $OcGlobalDir -Force | Out-Null }
        Copy-Item $Path $OcGlobalConfig -Force
        Write-Host "Imported $Path -> $OcGlobalConfig (previous config backed up first)" -ForegroundColor Green
    }

    "List" {
        Get-ChildItem $BackupDir -Filter "opencode.*.json" | Sort-Object LastWriteTime -Descending |
            Format-Table Name, LastWriteTime, Length -AutoSize
    }
}
