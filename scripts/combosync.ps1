
# combo-sync.ps1 - Pull + Smart Git sync for d3fq0n1 (defcon)
# Clean version with no emojis or formatting symbols

# Set working directory
Set-Location "C:\Users\blake\Downloads\git\maestro-orchestrator"

# Set Git identity
git config user.name "d3fq0n1"
git config user.email "blake.pirateking@gmail.com"

# Pull latest changes first
Write-Host ""
Write-Host "Pulling latest changes from origin/main..."
git pull origin main

# Check for changes to commit
$gitStatus = git status --porcelain
if ($gitStatus) {
    Write-Host ""
    Write-Host "Changes detected:"
    git status

    $commitMsg = Read-Host "Enter commit message"
    if (-not $commitMsg) {
        Write-Host "Aborting: no commit message entered."
        exit
    }

    git add .
    git commit -m "$commitMsg"
    git push origin main
    Write-Host ""
    Write-Host "Sync complete."
} else {
    Write-Host ""
    Write-Host "No changes to commit. Working directory clean."
}
