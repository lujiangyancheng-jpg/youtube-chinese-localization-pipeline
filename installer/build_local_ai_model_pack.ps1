[CmdletBinding()]
param(
    [string]$Version = "0.6.9",
    [string]$OllamaVersion = "v0.32.5",
    [string]$OllamaModelRoot = "$env:USERPROFILE\.ollama\models",
    [string]$QwenModelBlobSha256 = "3E4CB14174460404E7A233E531675303B2FBF7749C02F91864FE311AB6344E4F",
    [string]$CertificateThumbprint = "",
    [switch]$SkipInstaller,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $ProjectRoot "build\local-ai-model-pack"
$StageRoot = Join-Path $BuildRoot "stage"
$CacheRoot = Join-Path $BuildRoot "download-cache"
$DistRoot = Join-Path $ProjectRoot "dist"
$ManifestRelativePath = "manifests\registry.ollama.ai\library\qwen3\4b"
$ModelPackAppId = "98E9F02E-2C63-4B29-A62A-23CBBEEFB562"

function Assert-ChildPath([string]$Path, [string]$Parent) {
    $resolvedPath = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $resolvedParent = [IO.Path]::GetFullPath($Parent).TrimEnd('\')
    if (-not $resolvedPath.StartsWith("$resolvedParent\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing generated-file operation outside $resolvedParent`: $resolvedPath"
    }
}

function Reset-GeneratedDirectory([string]$Path) {
    Assert-ChildPath $Path $ProjectRoot
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

function Download-File([string]$Url, [string]$Destination) {
    if (Test-Path -LiteralPath $Destination) {
        return
    }
    New-Item -ItemType Directory -Path (Split-Path $Destination) -Force | Out-Null
    $partial = "$Destination.partial"
    & curl.exe --fail --location --retry 5 --retry-delay 2 --output $partial $Url
    if ($LASTEXITCODE -ne 0) {
        throw "Download failed: $Url"
    }
    Move-Item -LiteralPath $partial -Destination $Destination
}

function Copy-RequiredFile([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "Required file is missing: $Source"
    }
    New-Item -ItemType Directory -Path (Split-Path $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Copy-RequiredOllamaModel([string]$SourceRoot, [string]$DestinationRoot) {
    $manifestSource = Join-Path $SourceRoot $ManifestRelativePath
    if (-not (Test-Path -LiteralPath $manifestSource -PathType Leaf)) {
        throw "The local Qwen3:4b manifest is missing: $manifestSource. Run 'ollama pull qwen3:4b' first."
    }
    $manifestText = Get-Content -LiteralPath $manifestSource -Raw
    $digests = [regex]::Matches($manifestText, '"digest"\s*:\s*"sha256:([a-f0-9]{64})"') |
        ForEach-Object { $_.Groups[1].Value.ToLowerInvariant() } |
        Select-Object -Unique
    $requiredModelDigest = $QwenModelBlobSha256.ToLowerInvariant()
    if ($digests -notcontains $requiredModelDigest) {
        throw "The local qwen3:4b manifest does not reference the pinned Qwen model blob."
    }
    foreach ($digest in $digests) {
        Copy-RequiredFile (Join-Path $SourceRoot "blobs\sha256-$digest") `
            (Join-Path $DestinationRoot "blobs\sha256-$digest")
    }
    Copy-RequiredFile $manifestSource (Join-Path $DestinationRoot $ManifestRelativePath)
    return $digests
}

New-Item -ItemType Directory -Path $DistRoot, $CacheRoot -Force | Out-Null
Reset-GeneratedDirectory $StageRoot
$ModelsRoot = Join-Path $StageRoot "models"
$RuntimeRoot = Join-Path $StageRoot "runtime"
$LicensesRoot = Join-Path $StageRoot "licenses"
$OllamaModelsDestination = Join-Path $ModelsRoot "ollama"
New-Item -ItemType Directory -Path $ModelsRoot, $RuntimeRoot, $LicensesRoot -Force | Out-Null

Write-Host "[1/4] Copying only the Qwen3:4b model files required by Ollama..."
$modelDigests = Copy-RequiredOllamaModel $OllamaModelRoot $OllamaModelsDestination
$qwenBlob = Join-Path $OllamaModelsDestination "blobs\sha256-$($QwenModelBlobSha256.ToLowerInvariant())"
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $qwenBlob).Hash -ne $QwenModelBlobSha256) {
    throw "Qwen3:4b model checksum mismatch."
}
$licenseDigest = $modelDigests | Where-Object { $_ -eq "d18a5cc71b84bc4af394a31116bd3932b42241de70c77d2b76d69a314ec8aa12" } | Select-Object -First 1
if (-not $licenseDigest) { throw "Could not locate the Qwen Apache-2.0 license blob in the Qwen manifest." }
Copy-RequiredFile (Join-Path $OllamaModelsDestination "blobs\sha256-$licenseDigest") `
    (Join-Path $LicensesRoot "Qwen3-Apache-2.0.txt")

Write-Host "[2/4] Downloading the standalone Ollama runtime..."
$OllamaRelease = Invoke-RestMethod -Uri "https://api.github.com/repos/ollama/ollama/releases/tags/$OllamaVersion"
$OllamaAsset = $OllamaRelease.assets | Where-Object { $_.name -eq "ollama-windows-amd64.zip" } | Select-Object -First 1
$ChecksumAsset = $OllamaRelease.assets | Where-Object { $_.name -eq "sha256sum.txt" } | Select-Object -First 1
if (-not $OllamaAsset -or -not $ChecksumAsset) { throw "The Ollama release is missing Windows assets." }
$OllamaArchive = Join-Path $CacheRoot "$($OllamaRelease.tag_name)-ollama-windows-amd64.zip"
$OllamaChecksums = Join-Path $CacheRoot "$($OllamaRelease.tag_name)-sha256sum.txt"
Download-File $OllamaAsset.browser_download_url $OllamaArchive
Download-File $ChecksumAsset.browser_download_url $OllamaChecksums
$ChecksumLine = Get-Content -LiteralPath $OllamaChecksums | Where-Object { $_ -match "ollama-windows-amd64\.zip" } | Select-Object -First 1
if (-not $ChecksumLine) { throw "Ollama checksum entry is missing." }
$ExpectedChecksum = ($ChecksumLine -split '\s+')[0].ToUpperInvariant()
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $OllamaArchive).Hash -ne $ExpectedChecksum) {
    throw "Ollama archive checksum mismatch."
}
$OllamaRuntimeRoot = Join-Path $RuntimeRoot "ollama"
New-Item -ItemType Directory -Path $OllamaRuntimeRoot -Force | Out-Null
Expand-Archive -LiteralPath $OllamaArchive -DestinationPath $OllamaRuntimeRoot -Force
Download-File "https://raw.githubusercontent.com/ollama/ollama/main/LICENSE" (Join-Path $LicensesRoot "Ollama-MIT.txt")

Write-Host "[3/4] Writing the local AI model-pack manifest..."
[ordered]@{
    application = "YouTube Chinese Localizer"
    version = $Version
    models = @("qwen3:4b")
    model_blob_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $qwenBlob).Hash.ToLowerInvariant()
    ollama_version = $OllamaRelease.tag_name
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $StageRoot "model-pack-local-ai.json") -Encoding utf8

if (-not $SkipSmokeTest) {
    Write-Host "[4/4] Checking the standalone Ollama runtime..."
    & (Join-Path $OllamaRuntimeRoot "ollama.exe") --version
    if ($LASTEXITCODE -ne 0) { throw "The staged Ollama runtime smoke test failed." }
} else {
    Write-Host "[4/4] Smoke test skipped."
}

if (-not $SkipInstaller) {
    $Iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
    if (-not $Iscc) {
        $UserIscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
        if (Test-Path -LiteralPath $UserIscc) { $Iscc = $UserIscc }
    }
    if (-not $Iscc) { throw "Inno Setup 6 is required. Install it with: winget install JRSoftware.InnoSetup" }
    & $Iscc "/DStageDir=$StageRoot" "/DOutputDir=$DistRoot" "/DAppVersion=$Version" "/DModelPackAppId=$ModelPackAppId" `
        (Join-Path $PSScriptRoot "local-ai-model-pack.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed to build the Local AI model-pack installer." }
    $SetupFiles = Get-ChildItem -LiteralPath $DistRoot -File |
        Where-Object { $_.Name -like "YouTube-Chinese-Localizer-$Version-Local-AI-Model-Setup*" } |
        Sort-Object Name
    if ($CertificateThumbprint) {
        & (Join-Path $PSScriptRoot "sign_release.ps1") -CertificateThumbprint $CertificateThumbprint `
            -ArtifactPath @($SetupFiles | Where-Object { $_.Extension -eq ".exe" } | ForEach-Object FullName)
    }
    $Checksums = foreach ($file in $SetupFiles) {
        "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant(), $file.Name
    }
    $Checksums | Set-Content -LiteralPath (Join-Path $DistRoot "SHA256SUMS-$Version-local-ai.txt") -Encoding ascii
    $ReleaseFiles = Get-ChildItem -LiteralPath $DistRoot -File |
        Where-Object { $_.Name -like "YouTube-Chinese-Localizer-$Version-*-Setup*" } |
        Sort-Object Name
    $ReleaseChecksums = foreach ($file in $ReleaseFiles) {
        "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant(), $file.Name
    }
    $ReleaseChecksums | Set-Content -LiteralPath (Join-Path $DistRoot "SHA256SUMS.txt") -Encoding ascii
}

$StageBytes = (Get-ChildItem -LiteralPath $StageRoot -File -Recurse | Measure-Object Length -Sum).Sum
Write-Host ("Local AI model pack ready: {0:N2} GiB" -f ($StageBytes / 1GB))
