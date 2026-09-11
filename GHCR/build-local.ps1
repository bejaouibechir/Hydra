[CmdletBinding()]
param(
    [string]$Image = "hydra:local",
    [switch]$NoCache
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$dockerfile = Join-Path $PSScriptRoot "Dockerfile"

$arguments = @("build", "--file", $dockerfile, "--tag", $Image)
if ($NoCache) {
    $arguments += "--no-cache"
}
$arguments += $repoRoot

Write-Host "Building $Image"
& docker @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Docker build failed with exit code $LASTEXITCODE."
}

Write-Host "Image ready: $Image"
docker image inspect $Image --format "Size: {{.Size}} bytes | Created: {{.Created}}"
