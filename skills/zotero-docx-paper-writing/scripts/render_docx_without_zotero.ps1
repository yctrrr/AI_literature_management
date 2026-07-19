[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Path,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (Get-Process WINWORD -ErrorAction SilentlyContinue) {
    throw 'Close all Word windows before isolated rendering. The script refuses to attach to an existing Word session.'
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
$worker = Join-Path $PSScriptRoot 'render_docx_word_worker.ps1'
$results = @()

foreach ($requestedPath in $Path) {
    $source = (Resolve-Path -LiteralPath $requestedPath -ErrorAction Stop).Path
    if ([System.IO.Path]::GetExtension($source) -ne '.docx') {
        throw "Not a DOCX file: $source"
    }

    $beforeHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    $pdf = Join-Path $outputRoot ([System.IO.Path]::GetFileNameWithoutExtension($source) + '.rendered.pdf')
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $worker -Source $source -Pdf $pdf
    if ($LASTEXITCODE -ne 0) { throw "Isolated Word rendering failed for: $source" }

    $afterHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    if ($afterHash -ne $beforeHash) { throw "Rendering changed the source DOCX: $source" }
    $results += [pscustomobject]@{
        Source = $source
        Pdf = $pdf
        PdfBytes = (Get-Item -LiteralPath $pdf).Length
        SourceSha256 = $afterHash
    }
}

$results
