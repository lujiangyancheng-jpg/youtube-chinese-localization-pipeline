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
$Python = Join-Path $Root "runtime\python\python.exe"
$Ollama = Join-Path $Root "runtime\ollama\ollama.exe"
$Models = Join-Path $Root "models"
foreach ($required in @($Python, $Ollama, (Join-Path $Models "faster-whisper-medium\model.bin"))) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Offline installation is incomplete: $required"
    }
}

$env:YOUTUBE_LOCALIZER_HOME = $Root
$env:YOUTUBE_LOCALIZER_MODELS = $Models
$env:FFMPEG_PATH = Join-Path $Root "runtime\ffmpeg\bin\ffmpeg.exe"
$env:FFPROBE_PATH = Join-Path $Root "runtime\ffmpeg\bin\ffprobe.exe"
$env:OLLAMA_PATH = $Ollama

& $Python -c "from pathlib import Path; from youtube_localizer.resources import resolve_whisper_model; from youtube_localizer.translation.offline import validate_offline_model; p,local=resolve_whisper_model('medium'); assert local; assert validate_offline_model(Path(r'$Models')/'translate-en_zh-1_9'); assert validate_offline_model(Path(r'$Models')/'translate-zh_en-1_9', source_code='zh', target_code='en'); from faster_whisper import WhisperModel; WhisperModel(p, device='cpu', compute_type='int8', local_files_only=True); print('installed offline models: ok')"
if ($LASTEXITCODE -ne 0) { throw "Installed model loading failed." }

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
