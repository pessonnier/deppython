[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$OutputDirectory = "dist"
)

$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pydepot = Join-Path $repository "dist\pydepot.pyz"
$requirements = Join-Path $PSScriptRoot "requirements.txt"
$output = [IO.Path]::GetFullPath((Join-Path $repository $OutputDirectory))

if (-not (Test-Path -LiteralPath $pydepot -PathType Leaf)) {
    throw "Archive PyDepot introuvable: $pydepot"
}
New-Item -ItemType Directory -Path $output -Force | Out-Null

foreach ($version in @("3.12", "3.14")) {
    $tag = $version.Replace(".", "")
    $bundle = Join-Path $output "ml-cpu-windows-x86_64-py$tag.pybundle"
    & $Python $pydepot export `
        --requirements $requirements `
        --output $bundle `
        --python-version $version `
        --platform win_amd64 `
        --abi "cp$tag" `
        --extra-index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) {
        throw "Échec de l'export Windows pour Python $version."
    }
    & $Python $pydepot verify $bundle
    if ($LASTEXITCODE -ne 0) {
        throw "Échec de la vérification de $bundle."
    }
}

Get-ChildItem -LiteralPath $output -Filter "ml-cpu-windows-*.pybundle" |
    Get-FileHash -Algorithm SHA256

