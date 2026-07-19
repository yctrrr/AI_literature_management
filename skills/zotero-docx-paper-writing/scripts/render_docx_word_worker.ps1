param([string]$Source, [string]$Pdf)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$zotero = @($word.AddIns) | Where-Object { $_.Name -eq 'Zotero.dotm' } | Select-Object -First 1
$wasInstalled = $null -ne $zotero -and $zotero.Installed
$document = $null
try {
    if ($wasInstalled) { $zotero.Installed = $false }
    $document = $word.Documents.Open($Source, $false, $true)
    $document.SaveAs2($Pdf, 17)
    $document.Close(0)
    $document = $null
} finally {
    $restoreError = $null
    if ($null -ne $document) {
        try { $document.Close(0) } catch {}
    }
    if ($wasInstalled) {
        try { $zotero.Installed = $true } catch { $restoreError = $_ }
    }
    $word.Quit()
    if ($null -ne $restoreError) { throw $restoreError }
}
