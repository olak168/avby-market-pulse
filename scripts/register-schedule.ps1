<#
.SYNOPSIS
    Register the daily 13:00 dataset refresh in Windows Task Scheduler.

.DESCRIPTION
    Creates (or replaces) the task "AVBY-MarketPulse-Daily" for the current user.
    The task runs while the user is logged on and starts as soon as possible if the
    machine was asleep at 13:00. Overlapping runs are ignored by the task and by a
    mutex inside update-dashboard.ps1.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register-schedule.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register-schedule.ps1 -Time 09:30 -Pages 80
#>
[CmdletBinding()]
param(
    [string]$Time = '13:00',
    [int]$Pages = 50
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$UpdateScript = Join-Path $PSScriptRoot 'update-dashboard.ps1'
$TaskName = 'AVBY-MarketPulse-Daily'

if (-not (Test-Path -LiteralPath $UpdateScript)) {
    throw "Cannot find $UpdateScript"
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -Pages {1}' -f $UpdateScript, $Pages) `
    -WorkingDirectory $ProjectRoot

$trigger = New-ScheduledTaskTrigger -Daily -At $Time

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'Refresh the AV.BY Market Pulse dataset from cars.av.by every day at 13:00.' `
    -Force | Out-Null

Write-Host ("Registered task '{0}' for {1} at {2}." -f $TaskName, $currentUser, $Time)
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State | Format-Table -AutoSize
