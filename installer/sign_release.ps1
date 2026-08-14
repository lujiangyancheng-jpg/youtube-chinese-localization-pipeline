[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CertificateThumbprint,
    [Parameter(Mandatory = $true)]
    [string[]]$ArtifactPath,
    [string]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

function Find-SignTool {
    $roots = @(
        (Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"),
        (Join-Path $env:ProgramFiles "Windows Kits\10\bin")
    ) | Where-Object { Test-Path -LiteralPath $_ -PathType Container }
    $candidates = foreach ($root in $roots) {
        Get-ChildItem -LiteralPath $root -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' }
    }
    return $candidates | Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}

$normalizedThumbprint = ($CertificateThumbprint -replace '\s', '').ToUpperInvariant()
$certificate = Get-ChildItem "Cert:\CurrentUser\My" |
    Where-Object { $_.Thumbprint -eq $normalizedThumbprint } |
    Select-Object -First 1
if (-not $certificate -or -not $certificate.HasPrivateKey) {
    throw "A usable code-signing certificate was not found in Cert:\CurrentUser\My for thumbprint $normalizedThumbprint."
}
$signTool = Find-SignTool
if (-not $signTool) {
    throw "signtool.exe was not found. Install the Windows SDK Signing Tools component."
}

foreach ($rawPath in $ArtifactPath) {
    $artifact = (Resolve-Path -LiteralPath $rawPath -ErrorAction Stop).Path
    if ([IO.Path]::GetExtension($artifact) -notin @(".exe", ".msi")) {
        throw "Only Windows executable installer artifacts may be signed: $artifact"
    }
    & $signTool sign /sha1 $normalizedThumbprint /fd SHA256 /tr $TimestampServer /td SHA256 /v $artifact
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode signing failed: $artifact"
    }
    $signature = Get-AuthenticodeSignature -FilePath $artifact
    if ($signature.Status -ne "Valid") {
        throw "Authenticode verification failed for ${artifact}: $($signature.Status) $($signature.StatusMessage)"
    }
    Write-Host "Authenticode signature verified: $artifact"
}
