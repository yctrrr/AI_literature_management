param(
    [string]$TaskName = "AI Literature Management - Summary",
    [string]$ProjectRoot = "",
    [string]$PythonExe = "python",
    [string]$WeeklyDay = "Monday",
    [string]$At = "11:00"
)

$ErrorActionPreference = "Stop"
$implementation = Join-Path $PSScriptRoot "skills\weekly-literature-crawl\scripts\scheduler_summary.ps1"
if (-not (Test-Path -LiteralPath $implementation -PathType Leaf)) {
    throw "Scheduler implementation not found: $implementation"
}

& $implementation @PSBoundParameters
