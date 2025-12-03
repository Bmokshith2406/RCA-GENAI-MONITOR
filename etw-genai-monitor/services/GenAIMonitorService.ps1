param(
    [string]$InstallDir = "C:\opt\etw-genai-monitor"
)

$PythonExe = Join-Path $InstallDir ".venv\Scripts\python.exe"
$Script    = Join-Path $InstallDir "api\server.py"

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument $Script
$Trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "EtwGenAiKernelMonitor" -Action $Action -Trigger $Trigger -RunLevel Highest -Force

Write-Output "Registered scheduled task 'EtwGenAiKernelMonitor'."

