[CmdletBinding()]
param(
    [string]$OutputPath,
    [string]$IconPath
)

$ErrorActionPreference = "Stop"

$ScriptRoot = $PSScriptRoot
$SourcePath = Join-Path $ScriptRoot "LocalizeStudioLauncher.cs"
if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
    throw "Launcher source is missing: $SourcePath"
}
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $ScriptRoot "Localize Studio.exe"
}
if ([string]::IsNullOrWhiteSpace($IconPath)) {
    $IconPath = Join-Path (Split-Path $ScriptRoot) "assets\branding\app-icon.ico"
}
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
$IconPath = [IO.Path]::GetFullPath($IconPath)
if (-not (Test-Path -LiteralPath $IconPath -PathType Leaf)) {
    throw "Launcher icon is missing: $IconPath"
}
New-Item -ItemType Directory -Path (Split-Path -Parent $OutputPath) -Force | Out-Null

$CompilerCandidates = @(
    (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
)
$Compiler = $CompilerCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $Compiler) {
    throw "The Windows .NET Framework C# compiler was not found. Install .NET Framework 4.8 or Windows developer tools."
}

& $Compiler /nologo /target:winexe /platform:x64 /optimize+ "/out:$OutputPath" "/win32icon:$IconPath" `
    /reference:System.dll /reference:System.Windows.Forms.dll $SourcePath
if ($LASTEXITCODE -ne 0) {
    throw "Native GUI launcher compilation failed."
}
if (-not (Test-Path -LiteralPath $OutputPath -PathType Leaf)) {
    throw "Native GUI launcher output is missing: $OutputPath"
}
Write-Host "Native GUI launcher built: $OutputPath"
