[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$OpenCodeVersion = "1.18.26",
    [ValidateSet("x64", "x64-baseline", "arm64")]
    [string]$OpenCodeVariant = "x64",
    [string]$OutputDirectory = "dist"
)

$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pydepot = Join-Path $repository "dist\pydepot.pyz"
$requirements = Join-Path $PSScriptRoot "requirements.txt"
$outputRoot = [IO.Path]::GetFullPath((Join-Path $repository $OutputDirectory))
$bundle = Join-Path $outputRoot "opencode-speckit-linux-$OpenCodeVariant-py312.pybundle"
$assetName = "opencode-linux-$OpenCodeVariant.tar.gz"
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) (
    "pydepot-opencode-" + [Guid]::NewGuid().ToString("N")
)

if (-not (Test-Path -LiteralPath $pydepot -PathType Leaf)) {
    throw "Archive PyDepot introuvable: $pydepot"
}

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
New-Item -ItemType Directory -Path $temporaryRoot | Out-Null

try {
    $headers = @{
        Accept = "application/vnd.github+json"
        "User-Agent" = "PyDepot-OpenCode-example"
        "X-GitHub-Api-Version" = "2022-11-28"
    }
    $releaseUri = (
        "https://api.github.com/repos/anomalyco/opencode/releases/tags/v" +
        $OpenCodeVersion
    )
    Write-Host "Consultation de la release OpenCode v$OpenCodeVersion..."
    $release = Invoke-RestMethod -Uri $releaseUri -Headers $headers
    $asset = @($release.assets | Where-Object { $_.name -eq $assetName })
    if ($asset.Count -ne 1) {
        throw "Asset OpenCode introuvable ou ambigu: $assetName"
    }

    $archive = Join-Path $temporaryRoot $assetName
    Write-Host "Téléchargement de $assetName..."
    Invoke-WebRequest -Uri $asset[0].browser_download_url -OutFile $archive -Headers $headers

    if ($asset[0].digest -match '^sha256:([0-9a-f]{64})$') {
        $expectedHash = $Matches[1]
        $actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) {
            throw "Empreinte OpenCode invalide: attendue $expectedHash, obtenue $actualHash"
        }
        Write-Host "Empreinte OpenCode vérifiée: $actualHash"
    }

    $extracted = Join-Path $temporaryRoot "extracted"
    New-Item -ItemType Directory -Path $extracted | Out-Null
    & tar.exe -xzf $archive -C $extracted
    if ($LASTEXITCODE -ne 0) {
        throw "Échec de l'extraction de $assetName avec tar.exe."
    }
    $candidates = @(Get-ChildItem -LiteralPath $extracted -Recurse -File |
        Where-Object { $_.Name -eq "opencode" })
    if ($candidates.Count -ne 1) {
        throw "L'archive doit contenir exactement un exécutable nommé opencode."
    }

    & $Python $pydepot export `
        --requirements $requirements `
        --output $bundle `
        --python-version 3.12 `
        --platform manylinux_2_17_x86_64 `
        --abi cp312 `
        --allow-cross-platform `
        --include-executable ($candidates[0].FullName + "=opencode")
    if ($LASTEXITCODE -ne 0) {
        throw "Échec de l'export du bundle OpenCode + Spec Kit."
    }

    & $Python $pydepot verify $bundle
    if ($LASTEXITCODE -ne 0) {
        throw "Échec de la vérification du bundle $bundle."
    }

    Get-Item -LiteralPath $bundle | Select-Object FullName, Length
    Get-FileHash -LiteralPath $bundle -Algorithm SHA256
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
