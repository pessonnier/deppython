[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$PythonVersion = "3.14",
    [string]$OpenCodeVersion = "1.18.34",
    [string]$SpecKitVersion = "1.1.0",
    [string]$SpecKitSourceSha256 = "e39dc9db2155ab2c987a9ee892428222a44fa263bee5025d4bcceb223f3c078c",
    [string]$SpecKitWheelSha256 = "f6bd760911940f0bcd263bc25ee078e3f4157f7d387cf58b881847364ab90b66",
    [ValidateSet("x64", "x64-baseline", "arm64")]
    [string]$OpenCodeVariant = "x64",
    [string]$OutputDirectory = "dist"
)

$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pydepot = Join-Path $repository "dist\pydepot.pyz"
$requirements = Join-Path $PSScriptRoot "requirements.txt"
$outputRoot = [IO.Path]::GetFullPath((Join-Path $repository $OutputDirectory))
$pythonTag = $PythonVersion.Replace(".", "")
$bundle = Join-Path $outputRoot (
    "opencode-speckit-graphify-linux-$OpenCodeVariant-py$pythonTag.pybundle"
)
$assetName = "opencode-linux-$OpenCodeVariant.tar.gz"
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) (
    "pydepot-opencode-speckit-graphify-" + [Guid]::NewGuid().ToString("N")
)

if (-not (Test-Path -LiteralPath $pydepot -PathType Leaf)) {
    throw "Archive PyDepot introuvable: $pydepot"
}
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    throw "Fichier requirements introuvable: $requirements"
}

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
New-Item -ItemType Directory -Path $temporaryRoot | Out-Null

try {
    $headers = @{
        Accept = "application/vnd.github+json"
        "User-Agent" = "PyDepot-offline-deployment"
        "X-GitHub-Api-Version" = "2022-11-28"
    }

    $openCodeReleaseUri = (
        "https://api.github.com/repos/anomalyco/opencode/releases/tags/v" +
        $OpenCodeVersion
    )
    Write-Host "Consultation de la release OpenCode v$OpenCodeVersion..."
    $openCodeRelease = Invoke-RestMethod -Uri $openCodeReleaseUri -Headers $headers
    $asset = @($openCodeRelease.assets | Where-Object { $_.name -eq $assetName })
    if ($asset.Count -ne 1) {
        throw "Asset OpenCode introuvable ou ambigu: $assetName"
    }

    $openCodeArchive = Join-Path $temporaryRoot $assetName
    Write-Host "Téléchargement de $assetName..."
    Invoke-WebRequest `
        -Uri $asset[0].browser_download_url `
        -OutFile $openCodeArchive `
        -Headers $headers

    if ($asset[0].digest -notmatch '^sha256:([0-9a-f]{64})$') {
        throw "La release OpenCode ne publie pas d'empreinte SHA-256 pour $assetName."
    }
    $expectedOpenCodeHash = $Matches[1]
    $actualOpenCodeHash = (
        Get-FileHash -LiteralPath $openCodeArchive -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($actualOpenCodeHash -ne $expectedOpenCodeHash) {
        throw (
            "Empreinte OpenCode invalide: attendue $expectedOpenCodeHash, " +
            "obtenue $actualOpenCodeHash"
        )
    }
    Write-Host "Empreinte OpenCode vérifiée: $actualOpenCodeHash"

    $openCodeExtracted = Join-Path $temporaryRoot "opencode"
    New-Item -ItemType Directory -Path $openCodeExtracted | Out-Null
    & tar.exe -xzf $openCodeArchive -C $openCodeExtracted
    if ($LASTEXITCODE -ne 0) {
        throw "Échec de l'extraction de $assetName avec tar.exe."
    }
    $openCodeCandidates = @(
        Get-ChildItem -LiteralPath $openCodeExtracted -Recurse -File |
            Where-Object { $_.Name -eq "opencode" }
    )
    if ($openCodeCandidates.Count -ne 1) {
        throw "L'archive doit contenir exactement un exécutable nommé opencode."
    }

    $specKitReleaseUri = (
        "https://api.github.com/repos/github/spec-kit/releases/tags/v" +
        $SpecKitVersion
    )
    Write-Host "Consultation de la release Spec Kit v$SpecKitVersion..."
    $specKitRelease = Invoke-RestMethod -Uri $specKitReleaseUri -Headers $headers
    if ($specKitRelease.tag_name -ne "v$SpecKitVersion" -or $specKitRelease.prerelease) {
        throw "La release stable Spec Kit v$SpecKitVersion est introuvable."
    }

    $specKitArchive = Join-Path $temporaryRoot "spec-kit-v$SpecKitVersion.tar.gz"
    $specKitArchiveUri = (
        "https://github.com/github/spec-kit/archive/refs/tags/v" +
        $SpecKitVersion + ".tar.gz"
    )
    Write-Host "Téléchargement des sources Spec Kit v$SpecKitVersion..."
    Invoke-WebRequest -Uri $specKitArchiveUri -OutFile $specKitArchive -Headers $headers
    $specKitSourceHash = (
        Get-FileHash -LiteralPath $specKitArchive -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($specKitSourceHash -ne $SpecKitSourceSha256.ToLowerInvariant()) {
        throw (
            "Empreinte des sources Spec Kit invalide: attendue $SpecKitSourceSha256, " +
            "obtenue $specKitSourceHash"
        )
    }
    Write-Host "Empreinte des sources Spec Kit: $specKitSourceHash"

    $specKitExtracted = Join-Path $temporaryRoot "spec-kit"
    New-Item -ItemType Directory -Path $specKitExtracted | Out-Null
    & tar.exe -xzf $specKitArchive -C $specKitExtracted
    if ($LASTEXITCODE -ne 0) {
        throw "Échec de l'extraction des sources Spec Kit avec tar.exe."
    }
    $specKitProjects = @(
        Get-ChildItem -LiteralPath $specKitExtracted -Recurse -File -Filter "pyproject.toml" |
            Where-Object {
                (Get-Content -LiteralPath $_.FullName -Raw) -match (
                    '(?m)^name\s*=\s*["'']specify-cli["'']\s*$'
                )
            }
    )
    if ($specKitProjects.Count -ne 1) {
        throw "La source Spec Kit doit contenir exactement un projet specify-cli."
    }

    $wheelDirectory = Join-Path $temporaryRoot "wheels"
    New-Item -ItemType Directory -Path $wheelDirectory | Out-Null
    Write-Host "Construction du wheel Spec Kit v$SpecKitVersion..."
    & $Python -m pip wheel `
        $specKitProjects[0].Directory.FullName `
        --no-deps `
        --wheel-dir $wheelDirectory `
        --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        throw "Échec de la construction du wheel Spec Kit."
    }
    $specKitWheels = @(Get-ChildItem -LiteralPath $wheelDirectory -File -Filter "*.whl")
    if ($specKitWheels.Count -ne 1) {
        throw "La construction Spec Kit doit produire exactement un wheel."
    }
    $specKitWheelHash = (
        Get-FileHash -LiteralPath $specKitWheels[0].FullName -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($specKitWheelHash -ne $SpecKitWheelSha256.ToLowerInvariant()) {
        throw (
            "Empreinte du wheel Spec Kit invalide: attendue $SpecKitWheelSha256, " +
            "obtenue $specKitWheelHash"
        )
    }
    Write-Host "Empreinte du wheel Spec Kit: $specKitWheelHash"

    $exportArguments = @(
        $pydepot,
        "export",
        $specKitWheels[0].FullName,
        "--requirements", $requirements,
        "--output", $bundle,
        "--python-version", $PythonVersion,
        "--platform", "manylinux_2_28_x86_64",
        "--platform", "manylinux_2_17_x86_64",
        "--platform", "manylinux2014_x86_64",
        "--platform", "manylinux_2_5_x86_64",
        "--platform", "manylinux1_x86_64",
        "--abi", "cp$pythonTag",
        "--abi", "abi3",
        "--abi", "none",
        "--allow-cross-platform",
        "--include-executable", ($openCodeCandidates[0].FullName + "=opencode")
    )
    & $Python @exportArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Échec de l'export du bundle OpenCode + Spec Kit + Graphify."
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
