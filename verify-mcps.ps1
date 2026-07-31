<#
.SYNOPSIS
  Verifies the KIO MCP stack: prerequisites, config validity, and OpenCode's
  own view of server status. Does not run functional in-session test prompts
  (those are manual - see Phase 6 of KIO_MCP_SETUP.md).
#>

$OcGlobalConfig = "$env:USERPROFILE\.config\opencode\opencode.json"
$expectedServers = @("filesystem", "git", "memory", "sequential-thinking", "context7", "playwright")

$fail = 0

function Check($label, [bool]$ok, $detail = "") {
    if ($ok) {
        Write-Host "[OK]   $label" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $label $detail" -ForegroundColor Red
        $script:fail++
    }
}

Write-Host "== KIO MCP Stack Verification ==" -ForegroundColor Cyan

Check "node on PATH"    ((Get-Command node -ErrorAction SilentlyContinue) -ne $null)
Check "npm on PATH"     ((Get-Command npm  -ErrorAction SilentlyContinue) -ne $null)
Check "npx on PATH"     ((Get-Command npx  -ErrorAction SilentlyContinue) -ne $null)
Check "git on PATH"     ((Get-Command git  -ErrorAction SilentlyContinue) -ne $null)
Check "uv on PATH"      ((Get-Command uv   -ErrorAction SilentlyContinue) -ne $null)
Check "uvx on PATH"     ((Get-Command uvx  -ErrorAction SilentlyContinue) -ne $null)
Check "opencode on PATH" ((Get-Command opencode -ErrorAction SilentlyContinue) -ne $null)

$policy = Get-ExecutionPolicy -Scope CurrentUser
Check "ExecutionPolicy (CurrentUser) allows local scripts" ($policy -in @("RemoteSigned", "Unrestricted", "Bypass")) "(current: $policy)"

Check "Global config exists" (Test-Path $OcGlobalConfig) "($OcGlobalConfig)"

if (Test-Path $OcGlobalConfig) {
    try {
        $json = Get-Content $OcGlobalConfig -Raw | ConvertFrom-Json
        Check "Global config is valid JSON" $true
        $mcpKeys = $json.mcp.PSObject.Properties.Name
        foreach ($srv in $expectedServers) {
            Check "  -> '$srv' defined in config" ($mcpKeys -contains $srv)
        }
        foreach ($srv in $expectedServers) {
            if ($mcpKeys -contains $srv) {
                $enabled = $json.mcp.$srv.enabled
                Check "  -> '$srv' enabled=true" ($enabled -eq $true)
            }
        }
    } catch {
        Check "Global config is valid JSON" $false "($_)"
    }
}

$contextKey = [System.Environment]::GetEnvironmentVariable("CONTEXT7_API_KEY", "User")
Check "CONTEXT7_API_KEY set (optional)" ($null -ne $contextKey) "(not fatal - Context7 works without it at lower limits)"

Write-Host "`n-- OpenCode's own view --" -ForegroundColor Cyan
try {
    opencode mcp list
} catch {
    Write-Host "Could not run 'opencode mcp list' - is opencode on PATH and this config loaded?" -ForegroundColor Red
    $fail++
}

Write-Host "`n== Summary ==" -ForegroundColor Cyan
if ($fail -eq 0) {
    Write-Host "All automated checks passed. Now run the manual functional test prompts (Phase 6 of the setup guide) inside an actual OpenCode session - this script cannot do that part for you." -ForegroundColor Green
} else {
    Write-Host "$fail check(s) failed. Run repair-mcps.ps1, or see Phase 7 (Troubleshooting) in KIO_MCP_SETUP.md." -ForegroundColor Red
}
