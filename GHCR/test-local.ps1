[CmdletBinding()]
param(
    [string]$Image = "hydra:local"
)

$ErrorActionPreference = "Stop"
$containerName = "hydra-smoke-$PID"

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed: docker $($Arguments -join ' ')"
    }
}

Write-Host "Checking the CLI"
Invoke-Docker run --rm $Image hdrctl --version
Invoke-Docker run --rm $Image hdrctl --help

try {
    Write-Host "Starting an isolated Hydra container"
    Invoke-Docker run --detach --rm --name $containerName $Image

    $ready = $false
    foreach ($attempt in 1..30) {
        $health = & docker inspect --format "{{.State.Health.Status}}" $containerName
        if ($health -eq "healthy") {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }

    if (-not $ready) {
        docker logs $containerName
        throw "Hydra did not become healthy within 30 seconds."
    }

    Write-Host "Checking the API response"
    Invoke-Docker exec $containerName python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:5678/api/health')); assert d['status']=='ok'; assert d['studio']=='bundled'; print(json.dumps(d, indent=2))"

    Write-Host "Checking the Studio entry page"
    Invoke-Docker exec $containerName python -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:5678/'); body=r.read().lower(); assert r.status==200 and b'<html' in body; print('Studio: HTTP 200')"

    Write-Host "Checking a complete CSV job"
    Invoke-Docker exec $containerName sh -c "hdrctl init /workspace/smoke-job --template csv && hdrctl validate /workspace/smoke-job && hdrctl run /workspace/smoke-job && test -f /workspace/smoke-job/data/output.csv"

    Write-Host "All local image smoke tests passed."
}
finally {
    & docker stop $containerName 2>$null | Out-Null
}
