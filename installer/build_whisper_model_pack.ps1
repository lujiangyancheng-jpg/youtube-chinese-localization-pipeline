[CmdletBinding()]
param(
    [string]$Version = "0.6.5",
    [ValidateSet("Small", "Medium")]
    [string]$Model = "Small",
    [string]$SmallRevision = "536b0662742c02347bc0e980a01041f333bce120",
    [string]$SmallSha256 = "3E305921506D8872816023E4C273E75D2419FB89B24DA97B4FE7BCE14170D671",
    [string]$MediumRevision = "08e178d48790749d25932bbc082711ddcfdfbc4f",
    [string]$MediumSha256 = "9B45E1009DCC4AB601EFF815B61D80E60CE3FD8C74C1A14F4A282258286B51AE",
    [switch]$SkipInstaller,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$env:PYTHONUTF8 = "1"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $ProjectRoot "build\whisper-model-pack-$($Model.ToLowerInvariant())"
$StageRoot = Join-Path $BuildRoot "stage"
$DistRoot = Join-Path $ProjectRoot "dist"
$ModelName = $Model.ToLowerInvariant()
$ModelDirectory = "faster-whisper-$ModelName"
$Revision = if ($ModelName -eq "small") { $SmallRevision } else { $MediumRevision }
$ExpectedSha256 = if ($ModelName -eq "small") { $SmallSha256 } else { $MediumSha256 }
$ModelPackAppId = if ($ModelName -eq "small") {
    "1D590E67-81C8-4D04-9AFE-167A52D8D8B4"
} else {
    "5C1ED0E2-1E44-4B5C-8BBD-3CD26EA352F8"
}

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

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}
& $Python -c "import faster_whisper"
if ($LASTEXITCODE -ne 0) {
    throw "faster-whisper is required to build model packs. Create the project .venv first."
}

New-Item -ItemType Directory -Path $DistRoot -Force | Out-Null
Reset-GeneratedDirectory $StageRoot
$ModelsRoot = Join-Path $StageRoot "models"
$LicensesRoot = Join-Path $StageRoot "licenses"
New-Item -ItemType Directory -Path $ModelsRoot, $LicensesRoot -Force | Out-Null
$Destination = Join-Path $ModelsRoot $ModelDirectory

Write-Host "[1/4] Downloading the Whisper $Model model pack..."
& $Python -c "from faster_whisper.utils import download_model; download_model('$ModelName', output_dir=r'$Destination', revision='$Revision')"
if ($LASTEXITCODE -ne 0) { throw "Could not download Whisper $Model." }
$ModelFile = Join-Path $Destination "model.bin"
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $ModelFile).Hash -ne $ExpectedSha256) {
    throw "Whisper $Model model checksum mismatch."
}
Download-File "https://huggingface.co/Systran/faster-whisper-$ModelName/raw/main/README.md" (Join-Path $LicensesRoot "faster-whisper-$ModelName-README.md")
Download-File "https://raw.githubusercontent.com/openai/whisper/main/LICENSE" (Join-Path $LicensesRoot "Whisper-MIT.txt")

Write-Host "[2/4] Writing the model-pack manifest..."
[ordered]@{
    application = "YouTube Chinese Localizer"
    version = $Version
    model = $ModelName
    relative_path = "models/$ModelDirectory/model.bin"
    bytes = (Get-Item -LiteralPath $ModelFile).Length
    sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $ModelFile).Hash.ToLowerInvariant()
    license = "MIT"
} | ConvertTo-Json | Set-Content `
    -LiteralPath (Join-Path $StageRoot "model-pack-$ModelName.json") `
    -Encoding utf8

if (-not $SkipSmokeTest) {
    Write-Host "[3/4] Loading the model without network access..."
    & $Python -c "from faster_whisper import WhisperModel; WhisperModel(r'$Destination', device='cpu', compute_type='int8', local_files_only=True); print('Whisper $Model model pack smoke test: ok')"
    if ($LASTEXITCODE -ne 0) { throw "Whisper $Model model pack smoke test failed." }
} else {
    Write-Host "[3/4] Smoke test skipped."
}

if (-not $SkipInstaller) {
    Write-Host "[4/4] Building the Whisper $Model model-pack installer..."
    $Iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
    if (-not $Iscc) {
        $UserIscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
        if (Test-Path -LiteralPath $UserIscc) { $Iscc = $UserIscc }
    }
    if (-not $Iscc) {
        throw "Inno Setup 6 is required. Install it with: winget install JRSoftware.InnoSetup"
    }
    & $Iscc "/DStageDir=$StageRoot" "/DOutputDir=$DistRoot" "/DAppVersion=$Version" `
        "/DWhisperModel=$Model" "/DModelDirectory=$ModelDirectory" "/DModelPackAppId=$ModelPackAppId" `
        (Join-Path $PSScriptRoot "whisper-model-pack.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed to build the Whisper $Model model-pack installer." }
    $SetupFiles = Get-ChildItem -LiteralPath $DistRoot -File |
        Where-Object { $_.Name -like "YouTube-Chinese-Localizer-$Version-Whisper-$Model-Model-Setup*" } |
        Sort-Object Name
    $Checksums = foreach ($file in $SetupFiles) {
        "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant(), $file.Name
    }
    $Checksums | Set-Content `
        -LiteralPath (Join-Path $DistRoot "SHA256SUMS-$Version-whisper-$ModelName.txt") `
        -Encoding ascii
    $ReleaseFiles = Get-ChildItem -LiteralPath $DistRoot -File |
        Where-Object { $_.Name -like "YouTube-Chinese-Localizer-$Version-*-Setup*" } |
        Sort-Object Name
    $ReleaseChecksums = foreach ($file in $ReleaseFiles) {
        "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant(), $file.Name
    }
    $ReleaseChecksums | Set-Content -LiteralPath (Join-Path $DistRoot "SHA256SUMS.txt") -Encoding ascii
}

$StageBytes = (Get-ChildItem -LiteralPath $StageRoot -File -Recurse | Measure-Object Length -Sum).Sum
Write-Host ("Whisper {0} model pack ready: {1:N2} GiB" -f $Model, ($StageBytes / 1GB))
