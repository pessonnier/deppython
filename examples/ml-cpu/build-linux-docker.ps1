[CmdletBinding()]
param(
    [string]$Docker = "docker"
)

$ErrorActionPreference = "Stop"
$repository = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$output = Join-Path $repository "dist"
New-Item -ItemType Directory -Path $output -Force | Out-Null

foreach ($version in @("3.12", "3.14")) {
    $tag = $version.Replace(".", "")
    $image = "pydepot-ml-cpu:py$tag"
    & $Docker build `
        --build-arg "PYTHON_VERSION=$version" `
        --file (Join-Path $PSScriptRoot "Dockerfile") `
        --tag $image `
        $repository
    if ($LASTEXITCODE -ne 0) {
        throw "Échec du build Docker pour Python $version."
    }
    & $Docker run --rm `
        --mount "type=bind,source=$output,target=/out" `
        $image
    if ($LASTEXITCODE -ne 0) {
        throw "Échec de l'export Linux pour Python $version."
    }
}

Get-ChildItem -LiteralPath $output -Filter "ml-cpu-linux-*.pybundle" |
    Get-FileHash -Algorithm SHA256

