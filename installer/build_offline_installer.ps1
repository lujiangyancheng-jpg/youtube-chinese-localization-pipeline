[CmdletBinding()]
param(
    [string]$Version = "0.3.2",
    [string]$PythonVersion = "3.12.10",
    [string]$PythonArchiveSha256 = "4ACBED6DD1C744B0376E3B1CF57CE906F9DC9E95E68824584C8099A63025A3C3",
    [string]$WhisperModel = "medium",
    [string]$WhisperRevision = "08e178d48790749d25932bbc082711ddcfdfbc4f",
    [string]$OllamaVersion = "v0.32.5",
    [string]$NotoCjkRevision = "f8d157532fbfaeda587e826d4cd5b21a49186f7c",
    [string]$LxgwWenKaiRevision = "ed634e2291ff8adcffbab553d6c26cc95a0e4a0c",
    [string]$ArgosModelRoot = "$env:USERPROFILE\.youtube-chinese-localizer\models",
    [string]$OllamaModelRoot = "$env:USERPROFILE\.ollama\models",
    [switch]$SkipInstaller,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$env:PYTHONUTF8 = "1"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $ProjectRoot "build\offline-installer"
$StageRoot = Join-Path $BuildRoot "stage"
$CacheRoot = Join-Path $BuildRoot "download-cache"
$DistRoot = Join-Path $ProjectRoot "dist"

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

function Download-VerifiedFile([string]$Url, [string]$Destination, [string]$Sha256) {
    Download-File $Url $Destination
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash -ne $Sha256) {
        throw "Downloaded file checksum mismatch: $Destination"
    }
}

function Copy-RequiredDirectory([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        throw "Required directory is missing: $Source"
    }
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

New-Item -ItemType Directory -Path $CacheRoot, $DistRoot -Force | Out-Null
Reset-GeneratedDirectory $StageRoot

$AppRoot = Join-Path $StageRoot "app"
$RuntimeRoot = Join-Path $StageRoot "runtime"
$ModelsRoot = Join-Path $StageRoot "models"
$FontsRoot = Join-Path $StageRoot "fonts"
$LicenseRoot = Join-Path $StageRoot "licenses"
New-Item -ItemType Directory -Path $AppRoot, $RuntimeRoot, $ModelsRoot, $FontsRoot, $LicenseRoot -Force | Out-Null

Write-Host "[1/9] Staging application source..."
foreach ($file in @("main.py", "localizer_gui.pyw", "config.example.yaml", "LICENSE", "README.md")) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot $file) -Destination $AppRoot -Force
}
Copy-Item -LiteralPath (Join-Path $ProjectRoot "glossary.example.yaml") -Destination (Join-Path $AppRoot "glossary.yaml") -Force
Copy-RequiredDirectory (Join-Path $ProjectRoot "src") (Join-Path $AppRoot "src")
Copy-RequiredDirectory (Join-Path $ProjectRoot "docs") (Join-Path $AppRoot "docs")
Get-ChildItem -LiteralPath $AppRoot -Directory -Recurse -Filter "__pycache__" |
    ForEach-Object {
        Assert-ChildPath $_.FullName $StageRoot
        Remove-Item -LiteralPath $_.FullName -Recurse -Force
    }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Launch Localizer.cmd") -Destination $StageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "YouTube Localizer CLI.cmd") -Destination $StageRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "THIRD_PARTY_MODELS.md") -Destination $LicenseRoot

Write-Host "[2/9] Installing the embedded Python runtime and application dependencies..."
$PythonArchive = Join-Path $CacheRoot "python-$PythonVersion-embed-amd64.zip"
Download-File "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" $PythonArchive
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $PythonArchive).Hash -ne $PythonArchiveSha256) {
    throw "Embedded Python archive checksum mismatch."
}
$PythonRoot = Join-Path $RuntimeRoot "python"
New-Item -ItemType Directory -Path $PythonRoot -Force | Out-Null
Expand-Archive -LiteralPath $PythonArchive -DestinationPath $PythonRoot -Force
$PythonMinor = ($PythonVersion.Split('.')[0..1] -join '')
$PthFile = Join-Path $PythonRoot "python$PythonMinor._pth"
@(
    "python$PythonMinor.zip"
    "."
    "Lib\site-packages"
    "import site"
) | Set-Content -LiteralPath $PthFile -Encoding ascii
$GetPip = Join-Path $CacheRoot "get-pip.py"
Download-File "https://bootstrap.pypa.io/get-pip.py" $GetPip
$EmbeddedPython = Join-Path $PythonRoot "python.exe"
& $EmbeddedPython $GetPip --no-warn-script-location --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw "Could not bootstrap pip in the embedded Python runtime." }
Push-Location $ProjectRoot
try {
    & $EmbeddedPython -m pip install --disable-pip-version-check --no-cache-dir "hatchling>=1.26"
    if ($LASTEXITCODE -ne 0) { throw "Could not install the local build backend." }
    & $EmbeddedPython -m pip install --disable-pip-version-check --no-cache-dir --no-build-isolation ".[transcription,offline-translation]"
    if ($LASTEXITCODE -ne 0) { throw "Could not install application dependencies." }
} finally {
    Pop-Location
}

Write-Host "[3/9] Downloading the multilingual Whisper $WhisperModel model..."
$WhisperDestination = Join-Path $ModelsRoot "faster-whisper-$WhisperModel"
& $EmbeddedPython -c "from faster_whisper.utils import download_model; download_model('$WhisperModel', output_dir=r'$WhisperDestination', revision='$WhisperRevision')"
if ($LASTEXITCODE -ne 0) { throw "Could not download the faster-whisper model." }
Download-File "https://huggingface.co/Systran/faster-whisper-$WhisperModel/raw/main/README.md" (Join-Path $LicenseRoot "faster-whisper-$WhisperModel-README.md")
Download-File "https://raw.githubusercontent.com/openai/whisper/main/LICENSE" (Join-Path $LicenseRoot "Whisper-MIT.txt")

Write-Host "[4/9] Copying both Argos translation models..."
foreach ($name in @("translate-en_zh-1_9", "translate-zh_en-1_9")) {
    $source = Join-Path $ArgosModelRoot $name
    Copy-RequiredDirectory $source (Join-Path $ModelsRoot $name)
    Copy-Item -LiteralPath (Join-Path $source "README.md") -Destination (Join-Path $LicenseRoot "$name-README.md") -Force
}
Download-File "https://creativecommons.org/licenses/by/4.0/legalcode.txt" (Join-Path $LicenseRoot "CC-BY-4.0.txt")

Write-Host "[5/9] Downloading three bundled subtitle fonts..."
$FontCacheRoot = Join-Path $CacheRoot "fonts"
New-Item -ItemType Directory -Path $FontCacheRoot -Force | Out-Null
$FontAssets = @(
    @{
        Name = "NotoSansCJKsc-Regular.otf"
        Url = "https://raw.githubusercontent.com/notofonts/noto-cjk/$NotoCjkRevision/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"
        Sha256 = "2C76254F6FC379FDDFCE0A7E84FB5385BB135D3E399294F6EEB6680D0365B74B"
    },
    @{
        Name = "NotoSerifCJKsc-Regular.otf"
        Url = "https://raw.githubusercontent.com/notofonts/noto-cjk/$NotoCjkRevision/Serif/OTF/SimplifiedChinese/NotoSerifCJKsc-Regular.otf"
        Sha256 = "2A2EAE2628DF83556C54018C41E20FA532C1B862C5256AE8B3F23FEB918D12CA"
    },
    @{
        Name = "LXGWWenKai-Regular.ttf"
        Url = "https://raw.githubusercontent.com/lxgw/LxgwWenKai/$LxgwWenKaiRevision/fonts/TTF/LXGWWenKai-Regular.ttf"
        Sha256 = "39AD71264B588165B469E35E6AFB162A378DACD1F95348160240BA9038AC3009"
    }
)
foreach ($font in $FontAssets) {
    $cachedFont = Join-Path $FontCacheRoot $font.Name
    Download-VerifiedFile $font.Url $cachedFont $font.Sha256
    Copy-Item -LiteralPath $cachedFont -Destination (Join-Path $FontsRoot $font.Name) -Force
}
Download-File "https://raw.githubusercontent.com/notofonts/noto-cjk/$NotoCjkRevision/Sans/LICENSE" (Join-Path $LicenseRoot "Noto-Sans-CJK-SC-OFL-1.1.txt")
Download-File "https://raw.githubusercontent.com/notofonts/noto-cjk/$NotoCjkRevision/Serif/LICENSE" (Join-Path $LicenseRoot "Noto-Serif-CJK-SC-OFL-1.1.txt")
Download-File "https://raw.githubusercontent.com/lxgw/LxgwWenKai/$LxgwWenKaiRevision/OFL.txt" (Join-Path $LicenseRoot "LXGW-WenKai-OFL-1.1.txt")

Write-Host "[6/9] Copying Qwen3:4b and downloading the standalone Ollama runtime..."
Copy-RequiredDirectory $OllamaModelRoot (Join-Path $ModelsRoot "ollama")
$QwenLicenseBlob = Get-ChildItem -LiteralPath (Join-Path $OllamaModelRoot "blobs") -File |
    Where-Object { $_.Length -gt 10000 -and $_.Length -lt 13000 } |
    Select-Object -First 1
if (-not $QwenLicenseBlob) { throw "Could not locate the Qwen Apache-2.0 license blob." }
Copy-Item -LiteralPath $QwenLicenseBlob.FullName -Destination (Join-Path $LicenseRoot "Qwen3-Apache-2.0.txt") -Force

$OllamaRelease = Invoke-RestMethod -Uri "https://api.github.com/repos/ollama/ollama/releases/tags/$OllamaVersion"
$OllamaAsset = $OllamaRelease.assets | Where-Object { $_.name -eq "ollama-windows-amd64.zip" } | Select-Object -First 1
$ChecksumAsset = $OllamaRelease.assets | Where-Object { $_.name -eq "sha256sum.txt" } | Select-Object -First 1
if (-not $OllamaAsset -or -not $ChecksumAsset) { throw "The latest Ollama release is missing Windows assets." }
$OllamaArchive = Join-Path $CacheRoot "$($OllamaRelease.tag_name)-ollama-windows-amd64.zip"
$OllamaChecksums = Join-Path $CacheRoot "$($OllamaRelease.tag_name)-sha256sum.txt"
Download-File $OllamaAsset.browser_download_url $OllamaArchive
Download-File $ChecksumAsset.browser_download_url $OllamaChecksums
$ChecksumLine = Get-Content -LiteralPath $OllamaChecksums | Where-Object { $_ -match "ollama-windows-amd64\.zip" } | Select-Object -First 1
if (-not $ChecksumLine) { throw "Ollama checksum entry is missing." }
$ExpectedChecksum = ($ChecksumLine -split '\s+')[0].ToUpperInvariant()
$ActualChecksum = (Get-FileHash -Algorithm SHA256 -LiteralPath $OllamaArchive).Hash
if ($ActualChecksum -ne $ExpectedChecksum) { throw "Ollama archive checksum mismatch." }
$OllamaRoot = Join-Path $RuntimeRoot "ollama"
New-Item -ItemType Directory -Path $OllamaRoot -Force | Out-Null
Expand-Archive -LiteralPath $OllamaArchive -DestinationPath $OllamaRoot -Force
Download-File "https://raw.githubusercontent.com/ollama/ollama/main/LICENSE" (Join-Path $LicenseRoot "Ollama-MIT.txt")

Write-Host "[7/9] Copying FFmpeg and its redistribution notices..."
$FfmpegExe = (Get-Command ffmpeg -ErrorAction Stop).Source
$FfprobeExe = (Get-Command ffprobe -ErrorAction Stop).Source
$FfmpegBin = Join-Path $RuntimeRoot "ffmpeg\bin"
New-Item -ItemType Directory -Path $FfmpegBin -Force | Out-Null
Copy-Item -LiteralPath $FfmpegExe, $FfprobeExe -Destination $FfmpegBin -Force
$FfmpegDistributionRoot = Split-Path (Split-Path $FfmpegExe)
Copy-Item -LiteralPath (Join-Path $FfmpegDistributionRoot "LICENSE") -Destination (Join-Path $LicenseRoot "FFmpeg-GPLv3.txt") -Force
Copy-Item -LiteralPath (Join-Path $FfmpegDistributionRoot "README.txt") -Destination (Join-Path $LicenseRoot "FFmpeg-build-README.txt") -Force
if (Test-Path -LiteralPath (Join-Path $FfmpegDistributionRoot "doc")) {
    Copy-RequiredDirectory (Join-Path $FfmpegDistributionRoot "doc") (Join-Path $LicenseRoot "FFmpeg-doc")
}

Write-Host "[8/9] Writing a checksummed offline asset manifest..."
$ManifestAssets = @(
    @{ name = "faster-whisper-$WhisperModel"; path = "models/faster-whisper-$WhisperModel/model.bin"; license = "MIT" },
    @{ name = "argos-en-zh-1.9"; path = "models/translate-en_zh-1_9/model/model.bin"; license = "CC-BY-4.0" },
    @{ name = "argos-zh-en-1.9"; path = "models/translate-zh_en-1_9/model/model.bin"; license = "CC-BY-4.0" },
    @{ name = "qwen3-4b-q4_k_m"; path = "models/ollama/blobs/sha256-3e4cb14174460404e7a233e531675303b2fbf7749c02f91864fe311ab6344e4f"; license = "Apache-2.0" }
    @{ name = "noto-sans-cjk-sc-regular"; path = "fonts/NotoSansCJKsc-Regular.otf"; license = "OFL-1.1" }
    @{ name = "noto-serif-cjk-sc-regular"; path = "fonts/NotoSerifCJKsc-Regular.otf"; license = "OFL-1.1" }
    @{ name = "lxgw-wenkai-regular"; path = "fonts/LXGWWenKai-Regular.ttf"; license = "OFL-1.1" }
)
$Manifest = foreach ($asset in $ManifestAssets) {
    $assetPath = Join-Path $StageRoot ($asset.path.Replace('/', '\'))
    if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) { throw "Manifest asset is missing: $assetPath" }
    $item = Get-Item -LiteralPath $assetPath
    [ordered]@{
        name = $asset.name
        relative_path = $asset.path
        bytes = $item.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $assetPath).Hash.ToLowerInvariant()
        license = $asset.license
    }
}
[ordered]@{
    application = "YouTube Chinese Localizer"
    version = $Version
    generated_utc = [DateTime]::UtcNow.ToString("o")
    assets = $Manifest
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $StageRoot "offline-assets.json") -Encoding utf8

if (-not $SkipSmokeTest) {
    Write-Host "[9/9] Smoke-testing the staged application with network-free model resolution..."
    $previousHome = $env:YOUTUBE_LOCALIZER_HOME
    $previousModels = $env:YOUTUBE_LOCALIZER_MODELS
    $previousFonts = $env:YOUTUBE_LOCALIZER_FONTS
    $previousFfmpeg = $env:FFMPEG_PATH
    $previousFfprobe = $env:FFPROBE_PATH
    try {
        $env:YOUTUBE_LOCALIZER_HOME = $StageRoot
        $env:YOUTUBE_LOCALIZER_MODELS = $ModelsRoot
        $env:YOUTUBE_LOCALIZER_FONTS = $FontsRoot
        $env:FFMPEG_PATH = Join-Path $FfmpegBin "ffmpeg.exe"
        $env:FFPROBE_PATH = Join-Path $FfmpegBin "ffprobe.exe"
        & $EmbeddedPython -c "from youtube_localizer.resources import resolve_whisper_model, bundled_fonts_directory, bundled_ollama_models, ollama_executable; p,local=resolve_whisper_model('$WhisperModel'); assert local; assert bundled_fonts_directory(); assert bundled_ollama_models(); assert ollama_executable(); from faster_whisper import WhisperModel; WhisperModel(p, device='cpu', compute_type='int8', local_files_only=True); print('offline runtime smoke test: ok')"
        if ($LASTEXITCODE -ne 0) { throw "Staged offline runtime smoke test failed." }
        & $EmbeddedPython (Join-Path $AppRoot "main.py") --help | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Staged CLI smoke test failed." }
    } finally {
        $env:YOUTUBE_LOCALIZER_HOME = $previousHome
        $env:YOUTUBE_LOCALIZER_MODELS = $previousModels
        $env:YOUTUBE_LOCALIZER_FONTS = $previousFonts
        $env:FFMPEG_PATH = $previousFfmpeg
        $env:FFPROBE_PATH = $previousFfprobe
    }
} else {
    Write-Host "[9/9] Smoke test skipped."
}

if (-not $SkipInstaller) {
    $Iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
    if (-not $Iscc) {
        $DefaultIscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
        if (Test-Path -LiteralPath $DefaultIscc) { $Iscc = $DefaultIscc }
    }
    if (-not $Iscc) {
        $UserIscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
        if (Test-Path -LiteralPath $UserIscc) { $Iscc = $UserIscc }
    }
    if (-not $Iscc) {
        throw "Inno Setup 6 is required. Install it with: winget install JRSoftware.InnoSetup"
    }
    & $Iscc "/DStageDir=$StageRoot" "/DOutputDir=$DistRoot" "/DAppVersion=$Version" (Join-Path $PSScriptRoot "offline-installer.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed to build the installer." }
    $SetupFiles = Get-ChildItem -LiteralPath $DistRoot -File |
        Where-Object { $_.Name -like "YouTube-Chinese-Localizer-$Version-Offline-Setup*" } |
        Sort-Object Name
    $Checksums = foreach ($file in $SetupFiles) {
        "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant(), $file.Name
    }
    $Checksums | Set-Content -LiteralPath (Join-Path $DistRoot "SHA256SUMS.txt") -Encoding ascii
}

$StageBytes = (Get-ChildItem -LiteralPath $StageRoot -File -Recurse | Measure-Object Length -Sum).Sum
Write-Host ("Offline stage ready: {0} ({1:N2} GiB)" -f $StageRoot, ($StageBytes / 1GB))
if (-not $SkipInstaller) {
    Write-Host "Installer output: $DistRoot"
}
