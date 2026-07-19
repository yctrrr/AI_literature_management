[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string[]]$Path,

    [string]$OutputDirectory,

    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$Label = 'before_edit'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$resolvedFiles = @()
foreach ($item in $Path) {
    $resolved = Resolve-Path -LiteralPath $item -ErrorAction Stop
    $file = Get-Item -LiteralPath $resolved.Path -ErrorAction Stop
    if ($file.PSIsContainer -or $file.Extension -ne '.docx') {
        throw "Not a DOCX file: $item"
    }
    $resolvedFiles += $file
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
if (-not $OutputDirectory) {
    $parent = $resolvedFiles[0].DirectoryName
    $OutputDirectory = Join-Path $parent ("backup_{0}_{1}" -f $Label, $timestamp)
}

$backupRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $backupRoot) {
    throw "Backup directory already exists: $backupRoot"
}
New-Item -ItemType Directory -Path $backupRoot | Out-Null

$manifestFiles = @()
$usedNames = @{}
foreach ($file in $resolvedFiles) {
    $destinationName = $file.Name
    if ($usedNames.ContainsKey($destinationName.ToLowerInvariant())) {
        $destinationName = "{0}_{1}{2}" -f $file.BaseName, ($usedNames.Count + 1), $file.Extension
    }
    $usedNames[$destinationName.ToLowerInvariant()] = $true
    $destination = Join-Path $backupRoot $destinationName

    $sourceHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    Copy-Item -LiteralPath $file.FullName -Destination $destination
    $backupHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
    if ($sourceHash -ne $backupHash) {
        throw "Hash mismatch after backup: $($file.FullName)"
    }

    $manifestFiles += [ordered]@{
        source = $file.FullName
        backup = $destination
        bytes = $file.Length
        sha256 = $sourceHash
    }
}

$manifest = [ordered]@{
    createdAt = (Get-Date).ToString('o')
    label = $Label
    backupDirectory = $backupRoot
    files = $manifestFiles
}
$manifestPath = Join-Path $backupRoot 'backup-manifest.json'
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

[pscustomobject]@{
    BackupDirectory = $backupRoot
    Manifest = $manifestPath
    FileCount = $manifestFiles.Count
    Verified = $true
}
