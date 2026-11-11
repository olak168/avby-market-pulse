<#
.SYNOPSIS
    Remove the daily dataset refresh task.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\unregister-schedule.ps1
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'AVBY-MarketPulse-Daily'
)

$ErrorActionPreference = 'Stop'

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host ("Removed task '{0}'." -f $TaskName)
} else {
    Write-Host ("Task '{0}' is not registered." -f $TaskName)
}
