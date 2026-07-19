param(
    [string]$TaskName = "AI Literature Management - Summary",
    [string]$ProjectRoot = "",
    [string]$PythonExe = "python",
    [string]$WeeklyDay = "Monday",
    [string]$At = "11:00"
)

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = $PSScriptRoot
}

$script = Join-Path $ProjectRoot "run_summary.py"
$config = Join-Path $ProjectRoot "config.yaml"
$arguments = "`"$script`" --config `"$config`""

$action = New-ScheduledTaskAction -Execute $PythonExe -Argument $arguments -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $WeeklyDay -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force
Write-Host "Registered task: $TaskName"
