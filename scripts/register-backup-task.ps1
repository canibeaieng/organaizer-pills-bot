$scriptPath = "C:\Users\Egor\Documents\Codex\organaizer\scripts\backup-db.ps1"

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -Daily -At "12:00"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

$task = Register-ScheduledTask `
    -TaskName "OrganizerPillsBot-DBBackup" `
    -Description "Daily backup of medications.db from VM to local PC" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Force

if ($task) {
    Write-Host "SUCCESS: Task registered"
    $info = Get-ScheduledTaskInfo -TaskName "OrganizerPillsBot-DBBackup"
    Write-Host "Next run: $($info.NextRunTime)"
} else {
    Write-Host "FAILED to register task"
}
