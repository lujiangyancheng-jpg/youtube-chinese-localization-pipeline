[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [int]$OllamaPort = 11436,
    [switch]$SkipInference
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$Root = (Resolve-Path -LiteralPath $InstallRoot).Path
$ManifestPath = Join-Path $Root "offline-assets.json"
$TierPath = Join-Path $Root "package-tier.txt"
$PackageTier = if (Test-Path -LiteralPath $TierPath) {
    (Get-Content -LiteralPath $TierPath -Raw -Encoding ascii).Trim().ToLowerInvariant()
} else {
    "complete"
}
if ($PackageTier -notin @("standard", "complete")) {
    throw "Offline installation has an unknown package tier: $PackageTier"
}
$IsCompletePackage = $PackageTier -eq "complete"
$Python = Join-Path $Root "runtime\python\python.exe"
$Ollama = Join-Path $Root "runtime\ollama\ollama.exe"
$Models = Join-Path $Root "models"
$Fonts = Join-Path $Root "fonts"
$RequiredFiles = @(
    $Python
    $ManifestPath
    (Join-Path $Root "runtime-dependencies.lock")
    (Join-Path $Root "app\main.py")
    (Join-Path $Root "runtime\ffmpeg\bin\ffmpeg.exe")
    (Join-Path $Root "runtime\ffmpeg-nvenc-compat\bin\ffmpeg.exe")
    (Join-Path $Root "runtime\python\_tkinter.pyd")
    (Join-Path $Root "runtime\python\tcl86t.dll")
    (Join-Path $Root "runtime\python\tk86t.dll")
    (Join-Path $Root "runtime\python\zlib1.dll")
    (Join-Path $Root "runtime\python\Lib\tkinter\__init__.py")
    (Join-Path $Root "runtime\python\tcl\tk8.6\tk.tcl")
    (Join-Path $Models "faster-whisper-small\model.bin")
    (Join-Path $Fonts "NotoSansCJKsc-Regular.otf")
    (Join-Path $Fonts "NotoSerifCJKsc-Regular.otf")
    (Join-Path $Fonts "LXGWWenKai-Regular.ttf")
)
if ($IsCompletePackage) {
    $RequiredFiles += @(
        $Ollama
        (Join-Path $Models "faster-whisper-medium\model.bin")
    )
}
foreach ($required in $RequiredFiles) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Offline installation is incomplete: $required"
    }
}

function Test-OfflineAssetManifest([string]$RootPath, [string]$Path) {
    try {
        $manifest = Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json
    } catch {
        throw "Offline asset manifest cannot be read: $($_.Exception.Message)"
    }
    if ($manifest.application -ne "YouTube Chinese Localizer" -or -not $manifest.version) {
        throw "Offline asset manifest has an unexpected application identity."
    }
    $assets = @($manifest.assets)
    $minimumAssetCount = if ($IsCompletePackage) { 9 } else { 7 }
    if ($assets.Count -lt $minimumAssetCount) {
        throw "Offline asset manifest is incomplete."
    }
    $resolvedRoot = [IO.Path]::GetFullPath($RootPath).TrimEnd('\')
    foreach ($asset in $assets) {
        $relative = [string]$asset.relative_path
        if ([string]::IsNullOrWhiteSpace($relative) -or [IO.Path]::IsPathRooted($relative)) {
            throw "Offline asset manifest has an unsafe path: $relative"
        }
        $candidate = [IO.Path]::GetFullPath((Join-Path $resolvedRoot ($relative -replace '/', '\')))
        if (-not $candidate.StartsWith("$resolvedRoot\", [StringComparison]::OrdinalIgnoreCase)) {
            throw "Offline asset manifest points outside the installation: $relative"
        }
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "Bundled asset is missing: $relative"
        }
        $item = Get-Item -LiteralPath $candidate
        if ($item.Length -ne [int64]$asset.bytes) {
            throw "Bundled asset size mismatch: $relative"
        }
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant()
        if ($actual -ne ([string]$asset.sha256).ToLowerInvariant()) {
            throw "Bundled asset checksum mismatch: $relative"
        }
    }
    return $manifest
}

$Manifest = Test-OfflineAssetManifest $Root $ManifestPath
Write-Host "offline asset manifest: ok ($(@($Manifest.assets).Count) verified assets)"

$env:YOUTUBE_LOCALIZER_HOME = $Root
$env:YOUTUBE_LOCALIZER_MODELS = $Models
$env:YOUTUBE_LOCALIZER_FONTS = $Fonts
$env:FFMPEG_PATH = Join-Path $Root "runtime\ffmpeg\bin\ffmpeg.exe"
$env:FFPROBE_PATH = Join-Path $Root "runtime\ffmpeg\bin\ffprobe.exe"
if ($IsCompletePackage) { $env:OLLAMA_PATH = $Ollama } else { Remove-Item Env:OLLAMA_PATH -ErrorAction SilentlyContinue }
$env:YOUTUBE_LOCALIZER_EXPECTED_VERSION = [string]$Manifest.version

& $Python -c "import tkinter as tk; from youtube_localizer.gui import LocalizerWindow; root=tk.Tk(); root.attributes('-alpha', 0.0); window=LocalizerWindow(root); root.update(); assert root.title().startswith('Localize Studio'); assert (root.winfo_width(), root.winfo_height()) == (980, 720); assert window.empty_state.winfo_ismapped(); assert not window.settings_panel.winfo_ismapped(); root.destroy(); print('installed desktop interface: ok')"
if ($LASTEXITCODE -ne 0) { throw "Installed desktop interface loading failed." }

if ($IsCompletePackage) {
    & $Python -c "import os; from pathlib import Path; from youtube_localizer import __version__; from youtube_localizer.resources import bundled_fonts_directory, resolve_whisper_model; from youtube_localizer.translation.offline import validate_offline_model; from faster_whisper import WhisperModel; models=Path(os.environ['YOUTUBE_LOCALIZER_MODELS']); fonts=Path(os.environ['YOUTUBE_LOCALIZER_FONTS']).resolve(); assert __version__ == os.environ['YOUTUBE_LOCALIZER_EXPECTED_VERSION']; refs=[resolve_whisper_model(name) for name in ('medium', 'small')]; assert all(local for _,local in refs); assert bundled_fonts_directory() == fonts; assert validate_offline_model(models/'translate-en_zh-1_9'); assert validate_offline_model(models/'translate-zh_en-1_9', source_code='zh', target_code='en'); [WhisperModel(reference, device='cpu', compute_type='int8', local_files_only=True) for reference,_ in refs]; print('installed complete offline models and fonts: ok')"
} else {
    & $Python -c "import os; from pathlib import Path; from youtube_localizer import __version__; from youtube_localizer.resources import bundled_fonts_directory, resolve_whisper_model; from youtube_localizer.translation.offline import validate_offline_model; from faster_whisper import WhisperModel; models=Path(os.environ['YOUTUBE_LOCALIZER_MODELS']); fonts=Path(os.environ['YOUTUBE_LOCALIZER_FONTS']).resolve(); assert __version__ == os.environ['YOUTUBE_LOCALIZER_EXPECTED_VERSION']; reference, local=resolve_whisper_model('small'); assert local; assert bundled_fonts_directory() == fonts; assert validate_offline_model(models/'translate-en_zh-1_9'); assert validate_offline_model(models/'translate-zh_en-1_9', source_code='zh', target_code='en'); WhisperModel(reference, device='cpu', compute_type='int8', local_files_only=True); print('installed standard offline models and fonts: ok')"
}
if ($LASTEXITCODE -ne 0) { throw "Installed model loading failed." }

& $Python (Join-Path $Root "app\main.py") --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Installed command-line interface loading failed." }

if (-not $IsCompletePackage) {
    Write-Host "Standard package verification complete; local AI paragraph inference is intentionally not bundled."
    return
}

if ($SkipInference) {
    return
}

$PreviousOllamaModels = $env:OLLAMA_MODELS
$PreviousOllamaHost = $env:OLLAMA_HOST
$env:OLLAMA_MODELS = Join-Path $Models "ollama"
$env:OLLAMA_HOST = "127.0.0.1:$OllamaPort"
$LogRoot = Join-Path $Root "smoke-test-logs"
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
$Service = $null
try {
    $Service = Start-Process -FilePath $Ollama -ArgumentList "serve" -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogRoot "ollama.stdout.log") `
        -RedirectStandardError (Join-Path $LogRoot "ollama.stderr.log")
    $Ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $Tags = Invoke-RestMethod -Uri "http://127.0.0.1:$OllamaPort/api/tags" -TimeoutSec 2
            $Ready = $true
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $Ready) { throw "Bundled Ollama did not start." }
    $Names = @($Tags.models | ForEach-Object { $_.name })
    if ($Names -notcontains "qwen3:4b") {
        throw "Bundled qwen3:4b is not listed: $($Names -join ', ')"
    }
    $Body = @{
        model = "qwen3:4b"
        messages = @(
            @{
                role = "system"
                content = "Translate the user text to Simplified Chinese. Return only the JSON field."
            }
            @{
                role = "user"
                content = "Offline package works."
            }
        )
        stream = $false
        think = $false
        format = @{
            type = "object"
            properties = @{ translation = @{ type = "string"; minLength = 1 } }
            required = @("translation")
            additionalProperties = $false
        }
        keep_alive = 0
        options = @{ temperature = 0 }
    } | ConvertTo-Json -Depth 6
    $Reply = Invoke-RestMethod -Method Post `
        -Uri "http://127.0.0.1:$OllamaPort/api/chat" `
        -ContentType "application/json; charset=utf-8" `
        -Body $Body `
        -TimeoutSec 180
    $Translated = ($Reply.message.content | ConvertFrom-Json).translation
    if (-not $Translated) { throw "Bundled Qwen returned no translation." }
    [PSCustomObject]@{
        models = $Names
        translation = $Translated
        service_pid = $Service.Id
    } | ConvertTo-Json -Depth 4
} finally {
    if ($Service -and -not $Service.HasExited) {
        Stop-Process -Id $Service.Id -Force
        $Service.WaitForExit(5000)
    }
    $env:OLLAMA_MODELS = $PreviousOllamaModels
    $env:OLLAMA_HOST = $PreviousOllamaHost
}
