[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Before,

    [Parameter(Mandatory = $true)]
    [string]$After,

    [string[]]$AllowedAnchor = @(),

    [string[]]$AllowedSection = @(),

    [ValidateRange(1, 20)]
    [int]$MaxAnchorBlockParagraphs = 1,

    [ValidateRange(10000, 25000000)]
    [int]$MaxLcsCells = 4000000,

    [switch]$AllowCitationChanges,

    [switch]$AllowCitationFieldCountChanges,

    [switch]$AllowBibliographyChanges,

    [string[]]$AllowedPartPattern = @(),

    [string]$ReportPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$wordNamespace = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

function Normalize-Text([string]$Text) {
    if ($null -eq $Text) { return '' }
    return (($Text -replace '[\s\u00A0]+', ' ').Trim())
}

function Get-StableXml($Node) {
    $clone = $Node.CloneNode($true)
    if ($clone.LocalName -eq 'pPr') {
        foreach ($paragraphMarkProperties in @($clone.SelectNodes('./*[local-name()="rPr"]'))) {
            [void]$paragraphMarkProperties.ParentNode.RemoveChild($paragraphMarkProperties)
        }
    }
    $attributes = @($clone.SelectNodes('.//@*'))
    foreach ($attribute in $attributes) {
        if ($attribute.LocalName -match '^(rsid.*|paraId|textId)$') {
            [void]$attribute.OwnerElement.RemoveAttributeNode($attribute)
        }
    }
    return $clone.OuterXml
}

function Get-StableStructureXml($Node) {
    $clone = $Node.CloneNode($true)
    foreach ($textNode in @($clone.SelectNodes('.//*[local-name()="t" or local-name()="delText" or local-name()="instrText"]'))) {
        $textNode.InnerText = ''
    }
    foreach ($propertyNode in @($clone.SelectNodes('.//*[local-name()="pPr" or local-name()="rPr" or local-name()="tcPr" or local-name()="trPr" or local-name()="tblPr"]'))) {
        [void]$propertyNode.ParentNode.RemoveChild($propertyNode)
    }
    foreach ($attribute in @($clone.SelectNodes('.//@*'))) {
        if ($attribute.LocalName -match '^(rsid.*|paraId|textId)$') {
            [void]$attribute.OwnerElement.RemoveAttributeNode($attribute)
        }
    }
    return $clone.OuterXml
}

function Test-RecordEqual($Left, $Right) {
    return $Left.Text -ceq $Right.Text `
        -and $Left.FormatSignature -ceq $Right.FormatSignature `
        -and $Left.StructuralSignature -ceq $Right.StructuralSignature `
        -and $Left.FieldSignature -ceq $Right.FieldSignature `
        -and $Left.FieldStructureSignature -ceq $Right.FieldStructureSignature `
        -and $Left.FieldBoundaryValid -eq $Right.FieldBoundaryValid
}

function Get-Sha256Hex([byte[]]$Bytes) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '')
    } finally {
        $sha.Dispose()
    }
}

function Get-DocxPartSignatures([string]$DocumentPath) {
    $resolved = (Resolve-Path -LiteralPath $DocumentPath -ErrorAction Stop).Path
    $signatures = @{}
    $archive = [System.IO.Compression.ZipFile]::OpenRead($resolved)
    try {
        foreach ($entry in $archive.Entries) {
            if (-not $entry.Name) { continue }
            $memory = New-Object System.IO.MemoryStream
            $stream = $entry.Open()
            try { $stream.CopyTo($memory) } finally { $stream.Dispose() }
            $bytes = $memory.ToArray()
            $memory.Dispose()

            if ($entry.FullName -like '*.xml' -or $entry.FullName -like '*.rels') {
                try {
                    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
                    [xml]$partXml = $text
                    foreach ($attribute in @($partXml.SelectNodes('//@*'))) {
                        if ($attribute.LocalName -match '^(rsid.*|paraId|textId)$') {
                            [void]$attribute.OwnerElement.RemoveAttributeNode($attribute)
                        }
                    }
                    if ($entry.FullName -eq 'docProps/core.xml') {
                        foreach ($node in @($partXml.SelectNodes('//*'))) {
                            if ($node.LocalName -in @('modified', 'lastModifiedBy', 'revision')) {
                                [void]$node.ParentNode.RemoveChild($node)
                            }
                        }
                    }
                    if ($entry.FullName -eq 'docProps/app.xml') {
                        foreach ($node in @($partXml.SelectNodes('//*'))) {
                            if ($node.LocalName -in @('TotalTime', 'Pages', 'Words', 'Characters', 'Lines', 'Paragraphs', 'CharactersWithSpaces')) {
                                [void]$node.ParentNode.RemoveChild($node)
                            }
                        }
                    }
                    if ($entry.FullName -eq 'word/settings.xml') {
                        foreach ($node in @($partXml.SelectNodes('//*[local-name()="rsids"]'))) {
                            [void]$node.ParentNode.RemoveChild($node)
                        }
                    }
                    if ($entry.FullName -like 'word/footer*.xml') {
                        foreach ($node in @($partXml.SelectNodes('//*[local-name()="sdtEndPr" and not(@*) and not(node())]'))) {
                            [void]$node.ParentNode.RemoveChild($node)
                        }
                    }
                    if ($entry.FullName -eq 'word/document.xml') {
                        foreach ($paragraphNode in @($partXml.SelectNodes('//*[local-name()="p"]'))) {
                            [void]$paragraphNode.ParentNode.RemoveChild($paragraphNode)
                        }
                        foreach ($textNode in @($partXml.SelectNodes('//*[local-name()="t" or local-name()="delText" or local-name()="instrText"]'))) {
                            $textNode.InnerText = ''
                        }
                        $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes($partXml.OuterXml)
                        $signatures['word/document.xml#body-structure'] = Get-Sha256Hex $bytes
                        continue
                    }
                    $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes($partXml.OuterXml)
                } catch {
                    # Preserve the original bytes when an XML-like part cannot be parsed.
                }
            }
            $signatures[$entry.FullName] = Get-Sha256Hex $bytes
        }
    } finally {
        $archive.Dispose()
    }
    return $signatures
}

function Get-DocxParagraphs([string]$DocumentPath) {
    $resolved = (Resolve-Path -LiteralPath $DocumentPath -ErrorAction Stop).Path
    if ([System.IO.Path]::GetExtension($resolved) -ne '.docx') {
        throw "Not a DOCX file: $DocumentPath"
    }

    $archive = [System.IO.Compression.ZipFile]::OpenRead($resolved)
    try {
        $entry = $archive.GetEntry('word/document.xml')
        if ($null -eq $entry) { throw "Missing word/document.xml: $resolved" }
        $reader = New-Object System.IO.StreamReader($entry.Open())
        try { [xml]$xml = $reader.ReadToEnd() } finally { $reader.Dispose() }
        $stylesEntry = $archive.GetEntry('word/styles.xml')
        $stylesXml = $null
        if ($null -ne $stylesEntry) {
            $stylesReader = New-Object System.IO.StreamReader($stylesEntry.Open())
            try { [xml]$stylesXml = $stylesReader.ReadToEnd() } finally { $stylesReader.Dispose() }
        }
    } finally {
        $archive.Dispose()
    }

    $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
    $ns.AddNamespace('w', $wordNamespace)
    $nodes = $xml.SelectNodes('//w:body//w:p', $ns)
    $styleLevels = @{}
    if ($null -ne $stylesXml) {
        $styleNs = New-Object System.Xml.XmlNamespaceManager($stylesXml.NameTable)
        $styleNs.AddNamespace('w', $wordNamespace)
        $styleInfo = @{}
        foreach ($styleNode in $stylesXml.SelectNodes('//w:style', $styleNs)) {
            $styleId = $styleNode.GetAttribute('styleId', $wordNamespace)
            if (-not $styleId) { continue }
            $outlineNode = $styleNode.SelectSingleNode('./w:pPr/w:outlineLvl', $styleNs)
            $basedOnNode = $styleNode.SelectSingleNode('./w:basedOn', $styleNs)
            $outline = if ($null -ne $outlineNode) { [int]$outlineNode.GetAttribute('val', $wordNamespace) + 1 } else { 0 }
            $basedOn = if ($null -ne $basedOnNode) { $basedOnNode.GetAttribute('val', $wordNamespace) } else { '' }
            $styleInfo[$styleId] = @{ Outline = $outline; BasedOn = $basedOn }
            if ($outline -gt 0 -and $outline -le 9) { $styleLevels[$styleId] = $outline }
        }
        for ($pass = 0; $pass -lt $styleInfo.Count; $pass++) {
            foreach ($styleId in $styleInfo.Keys) {
                if ($styleLevels.ContainsKey($styleId)) { continue }
                $base = $styleInfo[$styleId].BasedOn
                if ($base -and $styleLevels.ContainsKey($base)) { $styleLevels[$styleId] = $styleLevels[$base] }
            }
        }
    }
    $records = @()
    $index = 0
    $fieldStack = New-Object System.Collections.Stack

    foreach ($paragraph in $nodes) {
        $index++
        $full = New-Object System.Text.StringBuilder
        $prose = New-Object System.Text.StringBuilder
        $hasCitation = $false
        $hasBibliography = $false
        $citationFieldCount = 0
        $bibliographyFieldCount = 0
        $fieldCodes = @()
        $fieldStructures = @()
        $fieldBoundaryValid = $true
        foreach ($context in $fieldStack) {
            if ($context.Phase -ne 'result' -or -not $context.IsZotero) { continue }
            $fieldCodes += 'CONTINUATION:' + (Normalize-Text $context.Code)
            $fieldStructures += 'CONTINUATION:' + $context.Type
            if ($context.Code -match 'ZOTERO_ITEM') { $hasCitation = $true; $citationFieldCount = 1 }
            if ($context.Code -match 'ZOTERO_BIBL') { $hasBibliography = $true; $bibliographyFieldCount = 1 }
        }

        foreach ($node in $paragraph.SelectNodes('.//*', $ns)) {
            if ($node.NamespaceURI -ne $wordNamespace) { continue }
            switch ($node.LocalName) {
                'fldChar' {
                    $kind = $node.GetAttribute('fldCharType', $wordNamespace)
                    if ($kind -eq 'begin') {
                        $fieldStack.Push(@{ Phase = 'code'; Code = ''; IsZotero = $false; Type = 'FIELD' })
                        $fieldStructures += 'BEGIN'
                    } elseif ($kind -eq 'separate' -and $fieldStack.Count -gt 0) {
                        $context = $fieldStack.Peek()
                        $context.Phase = 'result'
                        $context.IsZotero = $context.Code -match 'ADDIN\s+ZOTERO_'
                        if ($context.Code -match 'ZOTERO_ITEM') { $context.Type = 'ZOTERO_ITEM' }
                        elseif ($context.Code -match 'ZOTERO_BIBL') { $context.Type = 'ZOTERO_BIBL' }
                        $fieldCodes += Normalize-Text $context.Code
                        $fieldStructures += 'SEPARATE:' + $context.Type
                        if ($context.Code -match 'ZOTERO_ITEM') { $hasCitation = $true; $citationFieldCount++ }
                        if ($context.Code -match 'ZOTERO_BIBL') { $hasBibliography = $true; $bibliographyFieldCount++ }
                    } elseif ($kind -eq 'end' -and $fieldStack.Count -gt 0) {
                        $fieldStructures += 'END:' + $fieldStack.Peek().Type
                        [void]$fieldStack.Pop()
                    } elseif ($kind -eq 'end') {
                        $fieldStructures += 'UNMATCHED_END'
                        $fieldBoundaryValid = $false
                    } elseif ($kind -eq 'separate') {
                        $fieldStructures += 'UNMATCHED_SEPARATE'
                        $fieldBoundaryValid = $false
                    }
                }
                'instrText' {
                    if ($fieldStack.Count -gt 0) {
                        $fieldStack.Peek().Code += $node.InnerText
                    }
                }
                't' {
                    [void]$full.Append($node.InnerText)
                    $insideZoteroResult = $false
                    foreach ($context in $fieldStack) {
                        if ($context.Phase -eq 'result' -and $context.IsZotero) {
                            $insideZoteroResult = $true
                            if ($context.Code -match 'ZOTERO_ITEM') { $hasCitation = $true; if ($citationFieldCount -eq 0) { $citationFieldCount = 1 } }
                            if ($context.Code -match 'ZOTERO_BIBL') { $hasBibliography = $true; if ($bibliographyFieldCount -eq 0) { $bibliographyFieldCount = 1 } }
                            break
                        }
                    }
                    if (-not $insideZoteroResult) { [void]$prose.Append($node.InnerText) }
                }
                'tab' {
                    [void]$full.Append("`t")
                    [void]$prose.Append("`t")
                }
                'br' {
                    [void]$full.Append("`n")
                    [void]$prose.Append("`n")
                }
            }
        }

        $styleNode = $paragraph.SelectSingleNode('./w:pPr/w:pStyle', $ns)
        $style = if ($null -ne $styleNode) { $styleNode.GetAttribute('val', $wordNamespace) } else { '' }
        $headingLevel = 0
        $directOutline = $paragraph.SelectSingleNode('./w:pPr/w:outlineLvl', $ns)
        if ($null -ne $directOutline) { $headingLevel = [int]$directOutline.GetAttribute('val', $wordNamespace) + 1 }
        elseif ($styleLevels.ContainsKey($style)) { $headingLevel = $styleLevels[$style] }
        elseif ($style -match '^Heading\s*([1-9])$') { $headingLevel = [int]$matches[1] }
        elseif ($style -eq 'Heading-Main') { $headingLevel = 1 }
        if ($headingLevel -gt 9) { $headingLevel = 0 }

        $formatParts = @()
        $formatSetParts = @()
        $formatNodes = $paragraph.SelectNodes(
            './w:pPr | .//w:rPr[not(parent::w:pPr)] | ancestor::w:tc[1]/w:tcPr | ancestor::w:tr[1]/w:trPr | ancestor::w:tbl[1]/w:tblPr | .//w:drawing | .//w:pict',
            $ns
        )
        foreach ($formatNode in $formatNodes) {
            $stableFormat = Get-StableXml $formatNode
            $formatParts += $stableFormat
            $formatSetParts += $stableFormat
        }
        $structureParts = @()
        $structureNodes = $paragraph.SelectNodes(
            './/w:bookmarkStart | .//w:bookmarkEnd | .//w:sdtPr | .//w:ins | .//w:del | .//w:hyperlink | ancestor::w:tbl[1]/w:tblGrid',
            $ns
        )
        foreach ($structureNode in $structureNodes) {
            $structureParts += Get-StableStructureXml $structureNode
        }

        $records += [pscustomobject]@{
            Index = $index
            Text = Normalize-Text $full.ToString()
            ProseText = Normalize-Text $prose.ToString()
            Style = $style
            HeadingLevel = $headingLevel
            FormatSignature = ($formatParts -join '')
            FormatSetSignature = (@($formatSetParts | Sort-Object -Unique) -join '')
            StructuralSignature = ($structureParts -join '')
            FieldSignature = ($fieldCodes -join "`n")
            FieldStructureSignature = ($fieldStructures -join "`n")
            FieldBoundaryValid = $fieldBoundaryValid
            CitationFieldCount = $citationFieldCount
            BibliographyFieldCount = $bibliographyFieldCount
            HasCitation = $hasCitation
            HasBibliography = $hasBibliography
        }
    }
    if ($fieldStack.Count -gt 0 -and $records.Count -gt 0) {
        $records[-1].FieldSignature += "`nUNTERMINATED_FIELD_STACK:$($fieldStack.Count)"
        $records[-1].FieldStructureSignature += "`nUNTERMINATED_FIELD_STACK:$($fieldStack.Count)"
        $records[-1].FieldBoundaryValid = $false
    }
    return $records
}

function Get-AllowedSectionIndexes($Records, [string[]]$Names) {
    $allowed = New-Object 'System.Collections.Generic.HashSet[int]'
    if ($Names.Count -eq 0) { return ,$allowed }
    foreach ($name in $Names) {
        if ([string]::IsNullOrWhiteSpace($name)) { throw 'AllowedSection values cannot be empty.' }
        $matches = @($Records | Where-Object {
            $_.HeadingLevel -gt 0 -and [string]::Equals($_.Text, (Normalize-Text $name), [System.StringComparison]::OrdinalIgnoreCase)
        })
        if ($matches.Count -gt 1) { throw "Ambiguous section heading: $name" }
        if ($matches.Count -eq 0) { continue }
        $record = $matches[0]
        $i = $record.Index - 1
        $level = $record.HeadingLevel
        for ($j = $i; $j -lt $Records.Count; $j++) {
            if ($j -gt $i -and $Records[$j].HeadingLevel -gt 0 -and $Records[$j].HeadingLevel -le $level) { break }
            [void]$allowed.Add($Records[$j].Index)
        }
    }
    return ,$allowed
}

function Get-DiffOperations($OldRecords, $NewRecords) {
    $n = $OldRecords.Count
    $m = $NewRecords.Count
    if (($n + 1) * ($m + 1) -gt $MaxLcsCells) {
        throw "Document comparison exceeds MaxLcsCells=$MaxLcsCells. Audit smaller authorized sections or raise the limit explicitly."
    }
    $dp = New-Object 'int[,]' ($n + 1), ($m + 1)
    for ($i = $n - 1; $i -ge 0; $i--) {
        for ($j = $m - 1; $j -ge 0; $j--) {
            $nextI = $i + 1
            $nextJ = $j + 1
            if (Test-RecordEqual $OldRecords[$i] $NewRecords[$j]) {
                $dp[$i, $j] = $dp[$nextI, $nextJ] + 1
            } else {
                $down = $dp[$nextI, $j]
                $right = $dp[$i, $nextJ]
                $dp[$i, $j] = [Math]::Max($down, $right)
            }
        }
    }

    $operations = @()
    $i = 0
    $j = 0
    while ($i -lt $n -or $j -lt $m) {
        $nextI = $i + 1
        $nextJ = $j + 1
        if ($i -lt $n -and $j -lt $m -and (Test-RecordEqual $OldRecords[$i] $NewRecords[$j])) {
            $operations += [pscustomobject]@{ Kind = 'equal'; Old = $OldRecords[$i]; New = $NewRecords[$j] }
            $i++; $j++
        } elseif ($i -lt $n -and ($j -ge $m -or $dp[$nextI, $j] -ge $dp[$i, $nextJ])) {
            $operations += [pscustomobject]@{ Kind = 'delete'; Old = $OldRecords[$i]; New = $null }
            $i++
        } else {
            $operations += [pscustomobject]@{ Kind = 'insert'; Old = $null; New = $NewRecords[$j] }
            $j++
        }
    }
    return $operations
}

function Test-AllRecordsAnchored($Records, [string[]]$Anchors) {
    if ($Records.Count -eq 0 -or $Anchors.Count -eq 0) { return $false }
    foreach ($record in $Records) {
        $recordMatched = $false
        foreach ($anchor in $Anchors) {
            if ([string]::IsNullOrWhiteSpace($anchor)) { throw 'AllowedAnchor values cannot be empty.' }
            if ($record.Text.IndexOf($anchor, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
                $recordMatched = $true
                break
            }
        }
        if (-not $recordMatched) { return $false }
    }
    return $true
}

$oldRecords = @(Get-DocxParagraphs $Before)
$newRecords = @(Get-DocxParagraphs $After)
$oldParts = Get-DocxPartSignatures $Before
$newParts = Get-DocxPartSignatures $After
$changedParts = @()
$unauthorizedParts = @()
$partNames = @(($oldParts.Keys + $newParts.Keys) | Sort-Object -Unique)
foreach ($partName in $partNames) {
    $oldSignature = if ($oldParts.ContainsKey($partName)) { $oldParts[$partName] } else { $null }
    $newSignature = if ($newParts.ContainsKey($partName)) { $newParts[$partName] } else { $null }
    if ($oldSignature -ceq $newSignature) { continue }
    $changedParts += $partName
    $partAllowed = $false
    foreach ($pattern in $AllowedPartPattern) {
        if ($partName -like $pattern) { $partAllowed = $true; break }
    }
    if (-not $partAllowed) { $unauthorizedParts += $partName }
}
$oldSectionIndexes = Get-AllowedSectionIndexes $oldRecords $AllowedSection
$newSectionIndexes = Get-AllowedSectionIndexes $newRecords $AllowedSection
$operations = @(Get-DiffOperations $oldRecords $newRecords)

$blocks = @()
$current = @()
foreach ($operation in $operations) {
    if ($operation.Kind -eq 'equal') {
        if ($current.Count -gt 0) { $blocks += ,@($current); $current = @() }
    } else {
        $current += $operation
    }
}
if ($current.Count -gt 0) { $blocks += ,@($current) }

$blockReports = @()
$blockNumber = 0
foreach ($block in $blocks) {
    $blockNumber++
    $oldChanged = @($block | Where-Object { $null -ne $_.Old } | ForEach-Object { $_.Old })
    $newChanged = @($block | Where-Object { $null -ne $_.New } | ForEach-Object { $_.New })
    $allChanged = @($oldChanged + $newChanged)

    $allOldRecordsAnchored = Test-AllRecordsAnchored $oldChanged $AllowedAnchor
    $anchorBounded = $allOldRecordsAnchored `
        -and $oldChanged.Count -le $MaxAnchorBlockParagraphs `
        -and $newChanged.Count -le $MaxAnchorBlockParagraphs

    $oldCitationFields = ($oldChanged | Measure-Object -Property CitationFieldCount -Sum).Sum
    $newCitationFields = ($newChanged | Measure-Object -Property CitationFieldCount -Sum).Sum
    $oldBibliographyFields = ($oldChanged | Measure-Object -Property BibliographyFieldCount -Sum).Sum
    $newBibliographyFields = ($newChanged | Measure-Object -Property BibliographyFieldCount -Sum).Sum
    $zoteroFieldCountsPreserved = $oldCitationFields -eq $newCitationFields `
        -and $oldBibliographyFields -eq $newBibliographyFields
    $fieldBoundariesValid = @($allChanged | Where-Object { -not $_.FieldBoundaryValid }).Count -eq 0
    $fieldStructuresPreserved = (($oldChanged | ForEach-Object { $_.FieldStructureSignature }) -join "`n") -ceq (($newChanged | ForEach-Object { $_.FieldStructureSignature }) -join "`n")
    $scopeFieldIntegrity = $fieldBoundariesValid `
        -and (($zoteroFieldCountsPreserved -and $fieldStructuresPreserved) -or $AllowCitationFieldCountChanges)
    if (-not $scopeFieldIntegrity) {
        $anchorBounded = $false
    }

    # Zotero refresh can split runs and update adjacent citation fields while an
    # anchored paragraph is replaced by multiple paragraphs. Pair unchanged
    # prose records first, validate them as citation-only changes, then apply the
    # anchor gate only to the unpaired replacement records.
    $pairedOldIndexes = New-Object 'System.Collections.Generic.HashSet[int]'
    $pairedNewIndexes = New-Object 'System.Collections.Generic.HashSet[int]'
    $citationPairCount = 0
    foreach ($oldRecord in $oldChanged) {
        $newRecord = $newChanged | Where-Object {
            -not $pairedNewIndexes.Contains($_.Index) -and $_.ProseText -ceq $oldRecord.ProseText
        } | Select-Object -First 1
        if ($null -eq $newRecord) { continue }
        $pairIsCitationOnly = $oldRecord.CitationFieldCount -gt 0 `
            -and $oldRecord.CitationFieldCount -eq $newRecord.CitationFieldCount `
            -and $oldRecord.BibliographyFieldCount -eq $newRecord.BibliographyFieldCount `
            -and $oldRecord.FormatSetSignature -ceq $newRecord.FormatSetSignature `
            -and $oldRecord.StructuralSignature -ceq $newRecord.StructuralSignature `
            -and $oldRecord.FieldStructureSignature -ceq $newRecord.FieldStructureSignature `
            -and $oldRecord.FieldBoundaryValid `
            -and $newRecord.FieldBoundaryValid
        if (-not $pairIsCitationOnly) { continue }
        [void]$pairedOldIndexes.Add($oldRecord.Index)
        [void]$pairedNewIndexes.Add($newRecord.Index)
        $citationPairCount++
    }
    $anchorOldChanged = @($oldChanged | Where-Object { -not $pairedOldIndexes.Contains($_.Index) })
    $anchorNewChanged = @($newChanged | Where-Object { -not $pairedNewIndexes.Contains($_.Index) })
    $anchorPlusCitations = $AllowCitationChanges `
        -and $citationPairCount -gt 0 `
        -and (Test-AllRecordsAnchored $anchorOldChanged $AllowedAnchor) `
        -and $anchorOldChanged.Count -le $MaxAnchorBlockParagraphs `
        -and $anchorNewChanged.Count -le $MaxAnchorBlockParagraphs
    if ($anchorPlusCitations) {
        $anchorOldCitationFields = ($anchorOldChanged | Measure-Object -Property CitationFieldCount -Sum).Sum
        $anchorNewCitationFields = ($anchorNewChanged | Measure-Object -Property CitationFieldCount -Sum).Sum
        $anchorOldBibliographyFields = ($anchorOldChanged | Measure-Object -Property BibliographyFieldCount -Sum).Sum
        $anchorNewBibliographyFields = ($anchorNewChanged | Measure-Object -Property BibliographyFieldCount -Sum).Sum
        $anchorFieldCountsPreserved = $anchorOldCitationFields -eq $anchorNewCitationFields `
            -and $anchorOldBibliographyFields -eq $anchorNewBibliographyFields
        $anchorBoundariesValid = @($anchorOldChanged + $anchorNewChanged | Where-Object { -not $_.FieldBoundaryValid }).Count -eq 0
        if (-not $anchorBoundariesValid -or (-not $anchorFieldCountsPreserved -and -not $AllowCitationFieldCountChanges)) {
            $anchorPlusCitations = $false
        }
    }

    $sectionAllowed = $allChanged.Count -gt 0
    foreach ($record in $oldChanged) {
        if (-not $oldSectionIndexes.Contains($record.Index)) { $sectionAllowed = $false; break }
    }
    if ($sectionAllowed) {
        foreach ($record in $newChanged) {
            if (-not $newSectionIndexes.Contains($record.Index)) { $sectionAllowed = $false; break }
        }
    }
    if (-not $scopeFieldIntegrity) {
        $sectionAllowed = $false
    }

    $citationOnly = $AllowCitationChanges -and $oldChanged.Count -gt 0 -and $oldChanged.Count -eq $newChanged.Count
    if ($citationOnly) {
        for ($pairIndex = 0; $pairIndex -lt $oldChanged.Count; $pairIndex++) {
            $oldRecord = $oldChanged[$pairIndex]
            $newRecord = $newChanged[$pairIndex]
            if ($oldRecord.ProseText -cne $newRecord.ProseText `
                -or $oldRecord.CitationFieldCount -le 0 `
                -or $oldRecord.CitationFieldCount -ne $newRecord.CitationFieldCount `
                -or $oldRecord.BibliographyFieldCount -ne $newRecord.BibliographyFieldCount `
                -or $oldRecord.FormatSignature -cne $newRecord.FormatSignature `
                -or $oldRecord.StructuralSignature -cne $newRecord.StructuralSignature `
                -or $oldRecord.FieldStructureSignature -cne $newRecord.FieldStructureSignature `
                -or -not $oldRecord.FieldBoundaryValid `
                -or -not $newRecord.FieldBoundaryValid) {
                $citationOnly = $false
                break
            }
        }
    }

    $bibliographyOnly = $AllowBibliographyChanges -and $allChanged.Count -gt 0
    if ($bibliographyOnly) {
        foreach ($record in $allChanged) {
            if (-not $record.HasBibliography -or $record.ProseText -ne '' -or -not $record.FieldBoundaryValid) {
                $bibliographyOnly = $false
                break
            }
        }
        if ($bibliographyOnly) {
            $oldFormats = @(($oldChanged | ForEach-Object { $_.FormatSignature }) | Sort-Object -Unique)
            $newFormats = @(($newChanged | ForEach-Object { $_.FormatSignature }) | Sort-Object -Unique)
            $oldStructures = @(($oldChanged | ForEach-Object { $_.StructuralSignature }) | Sort-Object -Unique)
            $newStructures = @(($newChanged | ForEach-Object { $_.StructuralSignature }) | Sort-Object -Unique)
            if (($oldFormats -join "`n") -cne ($newFormats -join "`n") `
                -or ($oldStructures -join "`n") -cne ($newStructures -join "`n")) {
                $bibliographyOnly = $false
            }
        }
    }

    $authorized = $anchorBounded -or $anchorPlusCitations -or $sectionAllowed -or $citationOnly -or $bibliographyOnly
    $reason = if ($anchorBounded) { 'allowed-anchor' }
              elseif ($anchorPlusCitations) { 'allowed-anchor-plus-citations' }
              elseif ($sectionAllowed) { 'allowed-section' }
              elseif ($citationOnly) { 'citation-only' }
              elseif ($bibliographyOnly) { 'bibliography-only' }
              else { 'unauthorized' }

    $blockReports += [ordered]@{
        block = $blockNumber
        authorized = $authorized
        reason = $reason
        oldIndexes = @($oldChanged | ForEach-Object { $_.Index })
        newIndexes = @($newChanged | ForEach-Object { $_.Index })
        oldText = @($oldChanged | ForEach-Object { $_.Text })
        newText = @($newChanged | ForEach-Object { $_.Text })
        formatChanged = (($oldChanged | ForEach-Object { $_.FormatSignature }) -join "`n") -cne (($newChanged | ForEach-Object { $_.FormatSignature }) -join "`n")
        fieldChanged = (($oldChanged | ForEach-Object { $_.FieldSignature }) -join "`n") -cne (($newChanged | ForEach-Object { $_.FieldSignature }) -join "`n")
        structureChanged = (($oldChanged | ForEach-Object { $_.StructuralSignature }) -join "`n") -cne (($newChanged | ForEach-Object { $_.StructuralSignature }) -join "`n")
    }
}

$unauthorized = @($blockReports | Where-Object { -not $_.authorized })
$report = [ordered]@{
    before = (Resolve-Path -LiteralPath $Before).Path
    after = (Resolve-Path -LiteralPath $After).Path
    oldParagraphCount = $oldRecords.Count
    newParagraphCount = $newRecords.Count
    changedBlockCount = $blockReports.Count
    unauthorizedBlockCount = $unauthorized.Count
    changedPackageParts = $changedParts
    unauthorizedPackageParts = $unauthorizedParts
    passed = ($unauthorized.Count -eq 0 -and $unauthorizedParts.Count -eq 0)
    blocks = $blockReports
}

$json = $report | ConvertTo-Json -Depth 8
if (-not $ReportPath) {
    $afterFile = Get-Item -LiteralPath (Resolve-Path -LiteralPath $After).Path
    $ReportPath = Join-Path $afterFile.DirectoryName ($afterFile.BaseName + '.scope-audit.json')
}
$reportDirectory = Split-Path -Parent ([System.IO.Path]::GetFullPath($ReportPath))
if ($reportDirectory -and -not (Test-Path -LiteralPath $reportDirectory)) {
    New-Item -ItemType Directory -Path $reportDirectory | Out-Null
}
$json | Set-Content -LiteralPath $ReportPath -Encoding UTF8

[pscustomobject]@{
    Passed = $report.passed
    ChangedBlocks = $report.changedBlockCount
    UnauthorizedBlocks = $report.unauthorizedBlockCount
    UnauthorizedParts = $report.unauthorizedPackageParts.Count
    ReportPath = $ReportPath
}

if ($unauthorized.Count -gt 0 -or $unauthorizedParts.Count -gt 0) { exit 2 }
