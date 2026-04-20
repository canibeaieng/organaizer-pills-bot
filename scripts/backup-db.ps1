# Backup medications.db from Docker volume on VM to local PC
# Runs daily via Windows Task Scheduler

$VM_HOST     = "root@2.26.61.97"
$BACKUP_DIR  = "$env:USERPROFILE\Documents\Backups\organaizer-pills-bot"
$KEEP_COPIES = 2

# Ensure backup directory exists
if (-not (Test-Path $BACKUP_DIR)) {
    New-Item -ItemType Directory -Path $BACKUP_DIR -Force | Out-Null
}

$date      = Get-Date -Format "yyyy-MM-dd_HH-mm"
$localFile = "$BACKUP_DIR\medications_$date.db"
$logFile   = "$BACKUP_DIR\backup.log"

function Write-Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Add-Content -Path $logFile -Value $line
    Write-Host $line
}

Write-Log "Starting backup..."

# Copy DB from running container to /tmp on VM
ssh -o BatchMode=yes -o ConnectTimeout=10 $VM_HOST `
    "docker cp organizer-bot:/app/data/medications.db /tmp/med_backup.db"

if ($LASTEXITCODE -ne 0) {
    Write-Log "ERROR: Failed to copy DB from container. SSH exit code: $LASTEXITCODE"
    exit 1
}

# Download the file via SCP
scp -o BatchMode=yes -o ConnectTimeout=10 "${VM_HOST}:/tmp/med_backup.db" $localFile

if ($LASTEXITCODE -ne 0) {
    Write-Log "ERROR: SCP download failed. Exit code: $LASTEXITCODE"
    exit 1
}

# Cleanup temp file on VM
ssh -o BatchMode=yes $VM_HOST "rm -f /tmp/med_backup.db" | Out-Null

# Keep only the most recent backup files
Get-ChildItem -Path $BACKUP_DIR -Filter "medications_*.db" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $KEEP_COPIES |
    Remove-Item -Force

$sizeMB = [math]::Round((Get-Item $localFile).Length / 1MB, 3)
Write-Log "Backup saved: $localFile ($sizeMB MB)"
Write-Log "Done."
