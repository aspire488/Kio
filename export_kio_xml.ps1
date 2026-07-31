$OutputDir = "kio_xml_chunks"
$ChunkSizeMB = 20
$ChunkSize = $ChunkSizeMB * 1MB

$ExcludeDirs = @(
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode"
)

if (Test-Path $OutputDir) {
    Remove-Item $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Path $OutputDir | Out-Null

$chunk = 1
$currentSize = 0
$currentFile = Join-Path $OutputDir ("KIO_PART_{0:D3}.xml" -f $chunk)

function Start-Chunk($path) {
@"
<?xml version="1.0" encoding="UTF-8"?>
<repository>
"@ | Set-Content $path -Encoding UTF8
}

function End-Chunk($path) {
"</repository>" | Add-Content $path -Encoding UTF8
}

Start-Chunk $currentFile

Get-ChildItem . -Recurse -File | Where-Object {

    foreach ($d in $ExcludeDirs) {
        if ($_.FullName -match "\\$([regex]::Escape($d))\\") {
            return $false
        }
    }

    return $true

} | Sort-Object FullName | ForEach-Object {

    $relative = Resolve-Path -Relative $_.FullName

    try {
        $content = Get-Content $_.FullName -Raw -Encoding UTF8
    }
    catch {
        $content = "[Binary or unreadable]"
    }

    $xml = @"

<file path="$relative" size="$($_.Length)" modified="$($_.LastWriteTimeUtc.ToString("o"))">
<![CDATA[
$content
]]>
</file>

"@

    $bytes = [Text.Encoding]::UTF8.GetByteCount($xml)

    if (($currentSize + $bytes) -gt $ChunkSize) {

        End-Chunk $currentFile

        $chunk++
        $currentFile = Join-Path $OutputDir ("KIO_PART_{0:D3}.xml" -f $chunk)

        Start-Chunk $currentFile
        $currentSize = 0
    }

    Add-Content $currentFile $xml -Encoding UTF8
    $currentSize += $bytes
}

End-Chunk $currentFile

Write-Host ""
Write-Host "Done!"
Write-Host "Output folder: $OutputDir"
Write-Host "Chunks created:"
Get-ChildItem $OutputDir
