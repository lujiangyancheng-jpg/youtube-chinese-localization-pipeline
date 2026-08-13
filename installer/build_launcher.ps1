[CmdletBinding()]
param(
    [string]$OutputPath
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
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Path (Split-Path -Parent $OutputPath) -Force | Out-Null

$CompilerCandidates = @(
    (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
)
$Compiler = $CompilerCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $Compiler) {
    throw "The Windows .NET Framework C# compiler was not found. Install .NET Framework 4.8 or Windows developer tools."
}

& $Compiler /nologo /target:winexe /platform:x64 /optimize+ "/out:$OutputPath" `
    /reference:System.dll /reference:System.Windows.Forms.dll $SourcePath
if ($LASTEXITCODE -ne 0) {
    throw "Native GUI launcher compilation failed."
}
if (-not (Test-Path -LiteralPath $OutputPath -PathType Leaf)) {
    throw "Native GUI launcher output is missing: $OutputPath"
}
Write-Host "Native GUI launcher built: $OutputPath"
