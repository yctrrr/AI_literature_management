param(
    [string]$TaskName = "AI Literature Management - Crawl and EndNote",
    [string]$ProjectRoot = "",
    [string]$PythonExe = "python",
    [string]$WeeklyDay = "Monday",
    [string]$At = "09:00"
)

$ErrorActionPreference = "Stop"
$implementation = Join-Path $PSScriptRoot "skills\weekly-literature-crawl\scripts\scheduler_crawl_endnote.ps1"
if (-not (Test-Path -LiteralPath $implementation -PathType Leaf)) {
    throw "Scheduler implementation not found: $implementation"
}

& $implementation @PSBoundParameters
