[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Pdf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$sourcePath = (Resolve-Path -LiteralPath $Source -ErrorAction Stop).Path
$sourceName = [System.IO.Path]::GetFileName($sourcePath)
$ownerPath = Join-Path ([System.IO.Path]::GetDirectoryName($sourcePath)) ('~$' + $sourceName.Substring(2))
if (Test-Path -LiteralPath $ownerPath) {
    throw "Target DOCX is open in Word: $sourcePath"
}
$sourceStream = $null
try {
    $sourceStream = [System.IO.File]::Open($sourcePath, 'Open', 'Read', 'None')
} catch {
    throw "Target DOCX is locked: $sourcePath"
} finally {
    if ($null -ne $sourceStream) { $sourceStream.Dispose() }
}

$preexistingProcessIds = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object { [int]$_.Id })
$word = $null
$wordOwned = $false
$document = $null
$zotero = $null
$wasInstalled = $false
try {
    $word = New-Object -ComObject Word.Application
    $deadline = (Get-Date).AddSeconds(5)
    do {
        $newProcessIds = @(
            Get-Process WINWORD -ErrorAction SilentlyContinue |
                ForEach-Object { [int]$_.Id } |
                Where-Object { $preexistingProcessIds -notcontains $_ }
        )
        if ($newProcessIds.Count -eq 1) { break }
        Start-Sleep -Milliseconds 100
    } while ((Get-Date) -lt $deadline)
    if ($newProcessIds.Count -ne 1) {
        throw "Could not prove a single new Word process; found $($newProcessIds.Count). Existing Word windows were not touched."
    }

    $controlledProcess = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f [int]$newProcessIds[0])
    if ([string]$controlledProcess.CommandLine -notmatch '(/Automation\b|-Embedding\b)') {
        throw 'The new Word process is not identifiable as an automation instance. Existing Word windows were not touched.'
    }
    $wordOwned = $true
    if ($word.Documents.Count -ne 0) { throw 'The isolated Word instance is not empty.' }

    $word.Visible = $false
    $word.DisplayAlerts = 0
    $zotero = @($word.AddIns) | Where-Object { $_.Name -eq 'Zotero.dotm' } | Select-Object -First 1
    $wasInstalled = $null -ne $zotero -and [bool]$zotero.Installed
    if ($wasInstalled) {
        $zotero.Installed = $false
        if ($zotero.Installed) { throw 'Could not disable Zotero.dotm for isolated rendering.' }
    }

    $document = $word.Documents.Open($sourcePath, $false, $true)
    if (-not $document.ReadOnly) { throw 'Word did not open the source DOCX read-only.' }
    $document.SaveAs2($Pdf, 17)
    $document.Close(0)
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    $document = $null
    if (-not (Test-Path -LiteralPath $Pdf) -or (Get-Item -LiteralPath $Pdf).Length -eq 0) {
        throw "Word did not create a nonempty PDF: $Pdf"
    }
} finally {
    $restoreError = $null
    if ($null -ne $document -and $wordOwned) {
        try { $document.Close(0) } catch {}
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) } catch {}
    }
    if ($wasInstalled -and $wordOwned) {
        try {
            $zotero.Installed = $true
            if (-not $zotero.Installed) { throw 'Zotero.dotm was not restored.' }
        } catch { $restoreError = $_ }
    }
    if ($null -ne $word) {
        if ($wordOwned) { try { $word.Quit() } catch {} }
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) } catch {}
    }
    if ($null -ne $restoreError) { throw $restoreError }
}
