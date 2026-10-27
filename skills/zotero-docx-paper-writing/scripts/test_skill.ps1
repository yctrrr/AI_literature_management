[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $env:TEMP ("zotero-docx-paper-writing-test-{0}" -f (Get-Date -Format 'yyyyMMdd-HHmmss')))
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

if (Test-Path -LiteralPath $OutputDirectory) { throw "Test directory already exists: $OutputDirectory" }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null

$skillRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$auditScript = Join-Path $skillRoot 'scripts\audit_docx_scope.ps1'
$backupScript = Join-Path $skillRoot 'scripts\backup_docx.ps1'
$refreshGuardScript = Join-Path $skillRoot 'scripts\invoke_zotero_refresh_guarded.ps1'

$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($refreshGuardScript, [ref]$null, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) {
    throw ('Guarded refresh script has parse errors: ' + (($parseErrors | ForEach-Object { $_.Message }) -join '; '))
}
$refreshGuardSource = Get-Content -LiteralPath $refreshGuardScript -Raw
$guardRequirements = [ordered]@{
    NamedMutex = 'Mutex\(\$false, ''Global\\Codex\.Zotero\.WordIntegration\.Guard\.v1''\)'
    AllowsUnrelatedWord = 'preexistingWordProcessIds'
    ChecksTargetLock = 'Get-TargetDocumentLockState'
    VerifiesControlledProcess = 'newWordProcessIds\.Count -ne 1'
    RejectsNonAutomationProcess = 'controlledWordCommandLine -notmatch'
    QuitsOnlyOwnedWord = 'if \(\$wordOwned\) \{ try \{ \$word\.Quit\(\)'
    RejectsReadOnlyTarget = '\$document\.ReadOnly'
    RequiresZotero = 'Get-Process zotero'
    DetectsZoteroDialogs = 'MozillaDialogClass'
    DetectsKnownBusyWarning = '\\u6587\\u5B57\\u5904\\u7406\\u5668'
    InvokesRefreshOnce = '\$word\.Run\(''ZoteroRefresh''\)'
    MinimumSettlingPeriod = '\[ValidateRange\(5, 300\)\]'
    StableFingerprint = 'consecutiveStable -ge \$StableSamples'
    RequiresDialogsToClose = 'currentDialogs\.Count -gt 0'
    FailedCloseWithoutSave = '\$document\.Close\(0\)'
    SaveAfterSettling = '\$document\.Save\(\)'
}
if ($refreshGuardSource -match 'Close all Word instances') {
    throw 'Guarded refresh must not require unrelated Word documents to close.'
}
foreach ($requirement in $guardRequirements.GetEnumerator()) {
    $matches = [regex]::Matches($refreshGuardSource, $requirement.Value)
    if ($matches.Count -eq 0) { throw "Guarded refresh requirement missing: $($requirement.Key)" }
    if ($requirement.Key -eq 'InvokesRefreshOnce' -and $matches.Count -ne 1) {
        throw "ZoteroRefresh must be invoked exactly once; found $($matches.Count)."
    }
}

function Add-ZipText($Archive, [string]$Name, [string]$Text) {
    $entry = $Archive.CreateEntry($Name)
    $writer = New-Object System.IO.StreamWriter($entry.Open(), (New-Object System.Text.UTF8Encoding($false)))
    try { $writer.Write($Text) } finally { $writer.Dispose() }
}

function New-FixtureDocx(
    [string]$Path,
    [string]$Intro,
    [string]$Methods,
    [string]$CitationResult,
    [string]$BibliographyResult,
    [bool]$IncludeCitationField = $true,
    [string]$Title = 'Fixture',
    [string]$MethodsHeading = 'Methods',
    [bool]$BoldMethods = $false,
    [bool]$BoldCitationResult = $false,
    [bool]$OmitBibliographyEnd = $false,
    [string]$BibliographyPrefix = '',
    [string]$SectionXml = '<w:sectPr/>',
    [string]$ZoteroPref = 'pref-a',
    [int]$AppPages = 1,
    [string]$AppCompany = 'Fixture Company',
    [string]$SettingsRsid = '00112233',
    [int]$SettingsZoom = 100,
    [bool]$FooterSdtEndPr = $false,
    [string]$FooterText = '1'
) {
    $citationResultRun = if ($BoldCitationResult) { '<w:r><w:rPr><w:b/></w:rPr><w:t>' + $CitationResult + '</w:t></w:r>' } else { '<w:r><w:t>' + $CitationResult + '</w:t></w:r>' }
    $citation = if ($IncludeCitationField) {
        '<w:r><w:fldChar w:fldCharType="begin"/><w:instrText> ADDIN ZOTERO_ITEM CSL_CITATION {}</w:instrText><w:fldChar w:fldCharType="separate"/></w:r>' +
        $citationResultRun + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    } else {
        '<w:r><w:t>' + $CitationResult + '</w:t></w:r>'
    }
    $bibliographyEnd = if ($OmitBibliographyEnd) { '' } else { '<w:r><w:fldChar w:fldCharType="end"/></w:r>' }
    $bibliographyPrefixRun = if ($BibliographyPrefix) { '<w:r><w:t>' + $BibliographyPrefix + '</w:t></w:r>' } else { '' }
    $methodsRun = if ($BoldMethods) { '<w:r><w:rPr><w:b/></w:rPr><w:t>' + $Methods + '</w:t></w:r>' } else { '<w:r><w:t>' + $Methods + '</w:t></w:r>' }
    $document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' +
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Introduction</w:t></w:r></w:p>' +
        '<w:p><w:r><w:t>' + $Intro + '</w:t></w:r>' + $citation + '</w:p>' +
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>' + $MethodsHeading + '</w:t></w:r></w:p>' +
        '<w:p>' + $methodsRun + '</w:p>' +
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>References</w:t></w:r></w:p>' +
        '<w:p>' + $bibliographyPrefixRun + '<w:r><w:fldChar w:fldCharType="begin"/><w:instrText> ADDIN ZOTERO_BIBL {}</w:instrText><w:fldChar w:fldCharType="separate"/></w:r>' +
        '<w:r><w:t>' + $BibliographyResult + '</w:t></w:r>' + $bibliographyEnd + '</w:p>' +
        $SectionXml + '</w:body></w:document>'
    $contentTypes = '<?xml version="1.0" encoding="UTF-8"?>' +
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
        '<Default Extension="xml" ContentType="application/xml"/>' +
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>' +
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>' +
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>' +
        '<Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/>' +
        '</Types>'
    $rootRels = '<?xml version="1.0" encoding="UTF-8"?>' +
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>' +
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>' +
        '</Relationships>'
    $styles = '<?xml version="1.0" encoding="UTF-8"?>' +
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' +
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style></w:styles>'
    $core = '<?xml version="1.0" encoding="UTF-8"?>' +
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>' + $Title + '</dc:title></cp:coreProperties>'
    $custom = '<?xml version="1.0" encoding="UTF-8"?>' +
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">' +
        '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="ZOTERO_PREF_1"><vt:lpwstr>' + $ZoteroPref + '</vt:lpwstr></property></Properties>'
    $app = '<?xml version="1.0" encoding="UTF-8"?>' +
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">' +
        '<TotalTime>10</TotalTime><Pages>' + $AppPages + '</Pages><Words>20</Words><Characters>100</Characters>' +
        '<Lines>4</Lines><Paragraphs>6</Paragraphs><CharactersWithSpaces>120</CharactersWithSpaces>' +
        '<Company>' + $AppCompany + '</Company></Properties>'
    $settings = '<?xml version="1.0" encoding="UTF-8"?>' +
        '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' +
        '<w:zoom w:percent="' + $SettingsZoom + '"/><w:rsids><w:rsidRoot w:val="' + $SettingsRsid + '"/>' +
        '<w:rsid w:val="' + $SettingsRsid + '"/></w:rsids></w:settings>'
    $sdtEndPr = if ($FooterSdtEndPr) { '<w:sdtEndPr/>' } else { '' }
    $footer = '<?xml version="1.0" encoding="UTF-8"?>' +
        '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:sdt><w:sdtPr><w:id w:val="1"/></w:sdtPr>' +
        $sdtEndPr + '<w:sdtContent><w:p><w:r><w:t>' + $FooterText + '</w:t></w:r></w:p></w:sdtContent></w:sdt></w:ftr>'

    $fileStream = [System.IO.File]::Open($Path, [System.IO.FileMode]::CreateNew)
    $archive = New-Object System.IO.Compression.ZipArchive($fileStream, [System.IO.Compression.ZipArchiveMode]::Create, $false)
    try {
        Add-ZipText $archive '[Content_Types].xml' $contentTypes
        Add-ZipText $archive '_rels/.rels' $rootRels
        Add-ZipText $archive 'word/document.xml' $document
        Add-ZipText $archive 'word/styles.xml' $styles
        Add-ZipText $archive 'docProps/core.xml' $core
        Add-ZipText $archive 'docProps/custom.xml' $custom
        Add-ZipText $archive 'docProps/app.xml' $app
        Add-ZipText $archive 'word/settings.xml' $settings
        Add-ZipText $archive 'word/footer1.xml' $footer
    } finally {
        $archive.Dispose()
        $fileStream.Dispose()
    }
}

function Invoke-Audit([string]$Name, [string]$Before, [string]$After, [string[]]$Arguments, [int]$ExpectedExit) {
    $report = Join-Path $OutputDirectory ($Name + '.json')
    $command = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $auditScript, '-Before', $Before, '-After', $After, '-ReportPath', $report) + $Arguments
    & powershell.exe @command | Out-Null
    $actual = $LASTEXITCODE
    if ($actual -ne $ExpectedExit) { throw "$Name returned $actual; expected $ExpectedExit" }
    return [pscustomobject]@{ Test = $Name; Exit = $actual; Passed = $true }
}

$before = Join-Path $OutputDirectory 'before.docx'
$allowed = Join-Path $OutputDirectory 'allowed.docx'
$unauthorized = Join-Path $OutputDirectory 'unauthorized.docx'
$zoteroOnly = Join-Path $OutputDirectory 'zotero-only.docx'
$fieldCorrupt = Join-Path $OutputDirectory 'field-corrupt.docx'
$metadataChanged = Join-Path $OutputDirectory 'metadata-changed.docx'
$adjacentChanged = Join-Path $OutputDirectory 'adjacent-changed.docx'
$formatChanged = Join-Path $OutputDirectory 'format-changed.docx'
$malformedField = Join-Path $OutputDirectory 'malformed-field.docx'
$bodyStructureChanged = Join-Path $OutputDirectory 'body-structure-changed.docx'
$citationFormatChanged = Join-Path $OutputDirectory 'citation-format-changed.docx'
$bibliographyProseChanged = Join-Path $OutputDirectory 'bibliography-prose-changed.docx'
$zoteroPrefChanged = Join-Path $OutputDirectory 'zotero-pref-changed.docx'
$volatileWordStateChanged = Join-Path $OutputDirectory 'volatile-word-state-changed.docx'
$appPropertyChanged = Join-Path $OutputDirectory 'app-property-changed.docx'
$settingsPropertyChanged = Join-Path $OutputDirectory 'settings-property-changed.docx'
$footerContentChanged = Join-Path $OutputDirectory 'footer-content-changed.docx'

New-FixtureDocx $before 'Aggregate welfare gains require evidence.' 'Methods remain unchanged.' '7' '7. Existing reference.'
New-FixtureDocx $allowed 'Firm-level implementation requires evidence.' 'Methods remain unchanged.' '7' '7. Existing reference.'
New-FixtureDocx $unauthorized 'Aggregate welfare gains require evidence.' 'Methods changed outside scope.' '7' '7. Existing reference.'
New-FixtureDocx $zoteroOnly 'Aggregate welfare gains require evidence.' 'Methods remain unchanged.' '9' '9. Updated reference.'
New-FixtureDocx $fieldCorrupt 'Aggregate welfare gains require evidence.' 'Methods remain unchanged.' '7' '7. Existing reference.' $false
New-FixtureDocx $metadataChanged 'Aggregate welfare gains require evidence.' 'Methods remain unchanged.' '7' '7. Existing reference.' $true 'Changed metadata'
New-FixtureDocx -Path $adjacentChanged -Intro 'Firm-level implementation requires evidence.' -Methods 'Protected adjacent paragraph changed.' -CitationResult '7' -BibliographyResult '7. Existing reference.' -MethodsHeading 'Changed Methods'
New-FixtureDocx -Path $formatChanged -Intro 'Aggregate welfare gains require evidence.' -Methods 'Methods remain unchanged.' -CitationResult '7' -BibliographyResult '7. Existing reference.' -BoldMethods $true
New-FixtureDocx -Path $malformedField -Intro 'Aggregate welfare gains require evidence.' -Methods 'Methods remain unchanged.' -CitationResult '7' -BibliographyResult '7. Existing reference.' -OmitBibliographyEnd $true
New-FixtureDocx -Path $bodyStructureChanged -Intro 'Aggregate welfare gains require evidence.' -Methods 'Methods remain unchanged.' -CitationResult '7' -BibliographyResult '7. Existing reference.' -SectionXml '<w:sectPr><w:pgSz w:w="15840" w:h="12240" w:orient="landscape"/></w:sectPr>'
New-FixtureDocx -Path $citationFormatChanged -Intro 'Aggregate welfare gains require evidence.' -Methods 'Methods remain unchanged.' -CitationResult '9' -BibliographyResult '7. Existing reference.' -BoldCitationResult $true
New-FixtureDocx -Path $bibliographyProseChanged -Intro 'Aggregate welfare gains require evidence.' -Methods 'Methods remain unchanged.' -CitationResult '7' -BibliographyResult '9. Updated reference.' -BibliographyPrefix 'Unrelated prose.'
New-FixtureDocx -Path $zoteroPrefChanged -Intro 'Aggregate welfare gains require evidence.' -Methods 'Methods remain unchanged.' -CitationResult '7' -BibliographyResult '7. Existing reference.' -ZoteroPref 'pref-b'
New-FixtureDocx -Path $volatileWordStateChanged -Intro 'Aggregate welfare gains require evidence.' -Methods 'Methods remain unchanged.' -CitationResult '7' -BibliographyResult '7. Existing reference.' -AppPages 2 -SettingsRsid '44556677' -FooterSdtEndPr $true
New-FixtureDocx -Path $appPropertyChanged -Intro 'Aggregate welfare gains require evidence.' -Methods 'Methods remain unchanged.' -CitationResult '7' -BibliographyResult '7. Existing reference.' -AppCompany 'Changed Company'
New-FixtureDocx -Path $settingsPropertyChanged -Intro 'Aggregate welfare gains require evidence.' -Methods 'Methods remain unchanged.' -CitationResult '7' -BibliographyResult '7. Existing reference.' -SettingsZoom 90
New-FixtureDocx -Path $footerContentChanged -Intro 'Aggregate welfare gains require evidence.' -Methods 'Methods remain unchanged.' -CitationResult '7' -BibliographyResult '7. Existing reference.' -FooterText '2'

$backupDirectory = Join-Path $OutputDirectory 'backup'
& $backupScript -Path @($before, $allowed) -OutputDirectory $backupDirectory -Label test | Out-Null
$manifest = Get-Content -Raw (Join-Path $backupDirectory 'backup-manifest.json') | ConvertFrom-Json
foreach ($item in $manifest.files) {
    if ((Get-FileHash -LiteralPath $item.backup -Algorithm SHA256).Hash -ne $item.sha256) {
        throw 'Backup hash verification failed.'
    }
}

$results = @()
$results += Invoke-Audit 'allowed-anchor' $before $allowed @('-AllowedAnchor', 'Aggregate welfare gains') 0
$results += Invoke-Audit 'unauthorized-prose' $before $unauthorized @('-AllowedAnchor', 'Aggregate welfare gains') 2
$results += Invoke-Audit 'citation-and-bibliography' $before $zoteroOnly @('-AllowCitationChanges', '-AllowBibliographyChanges') 0
$results += Invoke-Audit 'flattened-field' $before $fieldCorrupt @('-AllowedAnchor', 'Aggregate welfare gains', '-AllowCitationChanges') 2
$results += Invoke-Audit 'adjacent-change' $before $adjacentChanged @('-AllowedAnchor', 'Aggregate welfare gains', '-MaxAnchorBlockParagraphs', '3') 2
$results += Invoke-Audit 'format-change' $before $formatChanged @('-AllowedAnchor', 'Aggregate welfare gains') 2
$results += Invoke-Audit 'malformed-field' $before $malformedField @('-AllowBibliographyChanges') 2
$results += Invoke-Audit 'malformed-field-anchor' $before $malformedField @('-AllowedAnchor', '7. Existing reference.') 2
$results += Invoke-Audit 'malformed-field-section' $before $malformedField @('-AllowedSection', 'References') 2
$results += Invoke-Audit 'body-structure' $before $bodyStructureChanged @() 2
$results += Invoke-Audit 'citation-format' $before $citationFormatChanged @('-AllowCitationChanges') 2
$results += Invoke-Audit 'bibliography-prose' $before $bibliographyProseChanged @('-AllowBibliographyChanges') 2
$results += Invoke-Audit 'zotero-pref' $before $zoteroPrefChanged @('-AllowCitationChanges', '-AllowBibliographyChanges') 2
$results += Invoke-Audit 'metadata-blocked' $before $metadataChanged @() 2
$results += Invoke-Audit 'metadata-allowed' $before $metadataChanged @('-AllowedPartPattern', 'docProps/core.xml') 0
$results += Invoke-Audit 'volatile-word-state' $before $volatileWordStateChanged @() 0
$results += Invoke-Audit 'app-property' $before $appPropertyChanged @() 2
$results += Invoke-Audit 'settings-property' $before $settingsPropertyChanged @() 2
$results += Invoke-Audit 'footer-content' $before $footerContentChanged @() 2

[pscustomobject]@{
    Passed = $true
    TestCount = $results.Count
    BackupFilesVerified = $manifest.files.Count
    RefreshGuardChecks = $guardRequirements.Count
    OutputDirectory = $OutputDirectory
}
exit 0
