param(
    [string]$TaskName = "AI Literature Management - Crawl and EndNote",
    [string]$ProjectRoot = "",
    [string]$PythonExe = "python",
    [string]$WeeklyDay = "Monday",
    [string]$At = "09:00"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    if (-not [string]::IsNullOrWhiteSpace($env:AI_LITERATURE_PROJECT_ROOT)) {
        $ProjectRoot = $env:AI_LITERATURE_PROJECT_ROOT
    }
    else {
        $skillRoot = Split-Path $PSScriptRoot -Parent
        $skillsRoot = Split-Path $skillRoot -Parent
        $ProjectRoot = Split-Path $skillsRoot -Parent
    }
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$script = Join-Path $ProjectRoot "run_weekly.py"
$config = Join-Path $ProjectRoot "config.yaml"
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) {
    throw "Weekly crawler entry point not found: $script"
}
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
    throw "Initialized configuration not found: $config"
}

$arguments = "`"$script`" --config `"$config`" --no-summarize"
$action = New-ScheduledTaskAction -Execute $PythonExe -Argument $arguments -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $WeeklyDay -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force
Write-Host "Registered task: $TaskName"
