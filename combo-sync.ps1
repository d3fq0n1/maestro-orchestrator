
# combo-sync.ps1 - Pull + Smart Git sync for d3fq0n1 (defcon)

# Set working directory
Set-Location "C:\Users\blake\Downloads"

# Set Git identity
git config user.name "d3fq0n1"
git config user.email "blake.pirateking@gmail.com"

# Pull latest changes first
Write-Host "`n🔄 Pulling latest changes from origin/main..."
git pull origin main

# Check for changes to commit
$gitStatus = git status --porcelain
if ($gitStatus) {
    Write-Host "`nChanges detected:"
    git status

    $commitMsg = Read-Host "`nEnter commit message"
    if (-not $commitMsg) {
        Write-Host "Aborting: no commit message entered."
        exit
    }

    git add .
    git commit -m "$commitMsg"
    git push origin main
    Write-Host "`n✅ Sync complete."
} else {
    Write-Host "`nNo changes to commit. ✅ Working directory clean."
}
