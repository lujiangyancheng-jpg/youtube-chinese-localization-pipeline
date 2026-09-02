[CmdletBinding()]
param(
    [string]$Version = "0.7.0",
    [string]$RuntimeVersion = "20250915",
    [string]$RuntimeArchiveSha256 = "7425BE94B94E4C8F37A1E433AC0E0100C43790E2C37418F4B65D8235ADFBDC87",
    [string]$CertificateThumbprint = "",
    [switch]$SkipInstaller,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $ProjectRoot "build\super-resolution-pack"
$StageRoot = Join-Path $BuildRoot "stage"
$CacheRoot = Join-Path $BuildRoot "download-cache"
$ExtractRoot = Join-Path $BuildRoot "expanded"
$DistRoot = Join-Path $ProjectRoot "dist"
$RuntimeRoot = Join-Path $StageRoot "runtime\super-resolution"
$LicenseRoot = Join-Path $StageRoot "licenses"
$ArchiveName = "waifu2x-ncnn-vulkan-$RuntimeVersion-windows.zip"
$Archive = Join-Path $CacheRoot $ArchiveName
$ArchiveUrl = "https://github.com/nihui/waifu2x-ncnn-vulkan/releases/download/$RuntimeVersion/$ArchiveName"

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

function Download-VerifiedFile([string]$Url, [string]$Destination, [string]$Sha256) {
    New-Item -ItemType Directory -Path (Split-Path $Destination) -Force | Out-Null
    if (-not (Test-Path -LiteralPath $Destination)) {
        $partial = "$Destination.partial"
        & curl.exe --fail --location --retry 5 --retry-delay 2 --output $partial $Url
        if ($LASTEXITCODE -ne 0) { throw "Download failed: $Url" }
        Move-Item -LiteralPath $partial -Destination $Destination
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash -ne $Sha256) {
        throw "Downloaded file checksum mismatch: $Destination"
    }
}

New-Item -ItemType Directory -Path $CacheRoot, $DistRoot -Force | Out-Null
Reset-GeneratedDirectory $StageRoot
Reset-GeneratedDirectory $ExtractRoot
New-Item -ItemType Directory -Path $RuntimeRoot, $LicenseRoot -Force | Out-Null

Write-Host "[1/4] Downloading the pinned NCNN/Vulkan AI upscaler..."
Download-VerifiedFile $ArchiveUrl $Archive $RuntimeArchiveSha256
Expand-Archive -LiteralPath $Archive -DestinationPath $ExtractRoot -Force
$Executable = Get-ChildItem -LiteralPath $ExtractRoot -Recurse -Filter "waifu2x-ncnn-vulkan.exe" |
    Select-Object -First 1
if (-not $Executable) { throw "The AI upscaler archive is missing its executable." }
$SourceRoot = $Executable.Directory.FullName
foreach ($file in @("waifu2x-ncnn-vulkan.exe", "vcomp140.dll")) {
    $source = Join-Path $SourceRoot $file
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing runtime file: $file" }
    Copy-Item -LiteralPath $source -Destination $RuntimeRoot -Force
}
foreach ($directory in @("models-upconv_7_photo", "models-cunet")) {
    $source = Join-Path $SourceRoot $directory
    if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "Missing model set: $directory" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $RuntimeRoot $directory) -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $SourceRoot "LICENSE") `
    -Destination (Join-Path $LicenseRoot "waifu2x-ncnn-vulkan-MIT.txt") -Force
Copy-Item -LiteralPath (Join-Path $SourceRoot "README.md") `
    -Destination (Join-Path $LicenseRoot "waifu2x-ncnn-vulkan-README.md") -Force

Write-Host "[2/4] Writing the component manifest..."
[ordered]@{
    application = "YouTube Chinese Localizer"
    version = $Version
    component = "ai-super-resolution"
    runtime = "waifu2x-ncnn-vulkan"
    upstream_version = $RuntimeVersion
    archive_sha256 = $RuntimeArchiveSha256.ToLowerInvariant()
    executable_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $RuntimeRoot "waifu2x-ncnn-vulkan.exe")).Hash.ToLowerInvariant()
    modes = @("general-photo", "animation")
    license = "MIT"
} | ConvertTo-Json | Set-Content `
    -LiteralPath (Join-Path $StageRoot "super-resolution-pack.json") -Encoding utf8

if (-not $SkipSmokeTest) {
    Write-Host "[3/4] Probing AI inference with safe Vulkan fallback..."
    $Ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source
    $ProbeInput = Join-Path $BuildRoot "probe-input.png"
    & $Ffmpeg -hide_banner -loglevel error -y -f lavfi -i "testsrc2=size=64x64:rate=1" -frames:v 1 $ProbeInput
    if ($LASTEXITCODE -ne 0) { throw "Could not create the AI upscaler smoke-test frame." }
    $ProbeOutput = Join-Path $BuildRoot "probe-output.png"
    $Succeeded = $false
    foreach ($GpuId in @(0, 1, -1)) {
        if (Test-Path -LiteralPath $ProbeOutput) { Remove-Item -LiteralPath $ProbeOutput -Force }
        & (Join-Path $RuntimeRoot "waifu2x-ncnn-vulkan.exe") `
            -i $ProbeInput -o $ProbeOutput -n 1 -s 2 `
            -m (Join-Path $RuntimeRoot "models-upconv_7_photo") -g $GpuId -t 128
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $ProbeOutput -PathType Leaf)) {
            Write-Host "AI upscaler smoke test: ok on device $GpuId"
            $Succeeded = $true
            break
        }
    }
    if (-not $Succeeded) { throw "AI upscaler failed its GPU and CPU smoke-test paths." }
} else {
    Write-Host "[3/4] Smoke test skipped."
}

if (-not $SkipInstaller) {
    Write-Host "[4/4] Building the optional AI super-resolution installer..."
    $Iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
    if (-not $Iscc) {
        $UserIscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
        if (Test-Path -LiteralPath $UserIscc) { $Iscc = $UserIscc }
    }
    if (-not $Iscc) { throw "Inno Setup 6 is required." }
    & $Iscc "/DStageDir=$StageRoot" "/DOutputDir=$DistRoot" "/DAppVersion=$Version" `
        (Join-Path $PSScriptRoot "super-resolution-pack.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed to build the AI enhancement pack." }
    $Setup = Join-Path $DistRoot "YouTube-Chinese-Localizer-$Version-AI-Super-Resolution-Setup.exe"
    if ($CertificateThumbprint) {
        & (Join-Path $PSScriptRoot "sign_release.ps1") `
            -CertificateThumbprint $CertificateThumbprint -ArtifactPath @($Setup)
    }
    "{0}  {1}" -f `
        (Get-FileHash -Algorithm SHA256 -LiteralPath $Setup).Hash.ToLowerInvariant(), `
        (Split-Path $Setup -Leaf) |
        Set-Content -LiteralPath (Join-Path $DistRoot "SHA256SUMS-$Version-super-resolution.txt") -Encoding ascii
} else {
    Write-Host "[4/4] Installer build skipped."
}

$StageBytes = (Get-ChildItem -LiteralPath $StageRoot -File -Recurse | Measure-Object Length -Sum).Sum
Write-Host ("AI super-resolution pack ready: {0:N2} MiB" -f ($StageBytes / 1MB))
