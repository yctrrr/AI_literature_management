param(
    [string]$TaskName = "AI Literature Management - Crawl and EndNote",
    [string]$ProjectRoot = "",
    [string]$PythonExe = "python",
    [string]$WeeklyDay = "Monday",
    [string]$At = "09:00"
)

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = $PSScriptRoot
}

$script = Join-Path $ProjectRoot "run_weekly.py"
$config = Join-Path $ProjectRoot "config.yaml"
$arguments = "`"$script`" --config `"$config`""

$action = New-ScheduledTaskAction -Execute $PythonExe -Argument $arguments -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $WeeklyDay -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force
Write-Host "Registered task: $TaskName"
