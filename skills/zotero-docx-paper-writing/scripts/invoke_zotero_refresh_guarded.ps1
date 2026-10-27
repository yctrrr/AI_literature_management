[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Path,

    [ValidateRange(5, 300)]
    [int]$MinimumSettlingSeconds = 5,

    [ValidateRange(2, 20)]
    [int]$StableSamples = 3,

    [ValidateRange(250, 5000)]
    [int]$PollMilliseconds = 1000,

    [ValidateRange(10, 600)]
    [int]$MaximumWaitSeconds = 60,

    [string]$ReportPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class ZoteroDialogInspector {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")]
    private static extern bool EnumChildWindows(IntPtr parent, EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr hWnd, StringBuilder text, int maxCount);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);

    private static string ReadText(IntPtr hWnd) {
        StringBuilder text = new StringBuilder(2048);
        GetWindowText(hWnd, text, text.Capacity);
        return text.ToString();
    }

    public static long[] FindMozillaDialogs() {
        List<long> dialogs = new List<long>();
        EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
            StringBuilder className = new StringBuilder(256);
            GetClassName(hWnd, className, className.Capacity);
            if (!String.Equals(className.ToString(), "MozillaDialogClass", StringComparison.Ordinal)) return true;

            dialogs.Add(hWnd.ToInt64());
            return true;
        }, IntPtr.Zero);
        return dialogs.ToArray();
    }
}
'@

function Get-ZoteroDialogs {
    $dialogs = @()
    foreach ($rawHandle in @([ZoteroDialogInspector]::FindMozillaDialogs())) {
        $handle = [IntPtr]$rawHandle
        $automationText = @()
        try {
            $element = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
            if ($null -ne $element) {
                $elements = $element.FindAll(
                    [System.Windows.Automation.TreeScope]::Subtree,
                    [System.Windows.Automation.Condition]::TrueCondition
                )
                foreach ($child in $elements) {
                    $name = [string]$child.Current.Name
                    if (-not [string]::IsNullOrWhiteSpace($name)) { $automationText += $name.Trim() }
                }
            }
        } catch {}
        $dialogs += [pscustomobject]@{
            Handle = ('0x{0:X}' -f $rawHandle)
            Text = @(($automationText | Sort-Object -Unique))
        }
    }
    return $dialogs
}

function Test-ZoteroIntegrationWarning($Dialogs) {
    $text = @($Dialogs | ForEach-Object { $_.Text }) -join ' | '
    return $text -match '(\u6587\u5B57\u5904\u7406\u5668\u96C6\u6210\u547D\u4EE4\u5DF2\u5728\u8FD0\u884C|word processor integration command is already running|integration command is already running|\u9519\u8BEF|\berror\b)'
}

function Get-DocumentFieldState($Document) {
    $parts = New-Object 'System.Collections.Generic.List[string]'
    $fieldCount = 0
    $zoteroFieldCount = 0

    foreach ($storyType in @($Document.StoryRanges | ForEach-Object { $_.StoryType } | Sort-Object -Unique)) {
        $range = $Document.StoryRanges.Item($storyType)
        while ($null -ne $range) {
            foreach ($field in @($range.Fields)) {
                $fieldCount++
                $code = [string]$field.Code.Text
                $result = [string]$field.Result.Text
                if ($code -match 'ADDIN\s+ZOTERO_(ITEM|BIBL)') { $zoteroFieldCount++ }
                $parts.Add(('{0}:{1}:{2}' -f $storyType, $code, $result))
            }
            $range = $range.NextStoryRange
        }
    }

    $bytes = [System.Text.Encoding]::UTF8.GetBytes(($parts -join "`n"))
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $fingerprint = ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '')
    } finally {
        $sha.Dispose()
    }

    return [pscustomobject]@{
        FieldCount = $fieldCount
        ZoteroFieldCount = $zoteroFieldCount
        Fingerprint = $fingerprint
    }
}

function Set-Failure([string]$Code, [int]$ExitCode, [string]$Message) {
    $script:failureCode = $Code
    $script:resultExitCode = $ExitCode
    throw $Message
}

function Get-WordOwnerFilePath([string]$DocumentPath) {
    $directory = [System.IO.Path]::GetDirectoryName($DocumentPath)
    $name = [System.IO.Path]::GetFileName($DocumentPath)
    $ownerName = if ($name.Length -gt 2) { '~$' + $name.Substring(2) } else { '~$' + $name }
    return [System.IO.Path]::Combine($directory, $ownerName)
}

function Get-TargetDocumentLockState([string]$DocumentPath) {
    $ownerPath = Get-WordOwnerFilePath $DocumentPath
    if (Test-Path -LiteralPath $ownerPath) {
        return [pscustomobject]@{
            Available = $false
            Reason = 'word_owner_file'
            OwnerFile = $ownerPath
            Error = $null
        }
    }

    $lastError = $null
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $stream = $null
        try {
            $stream = [System.IO.File]::Open(
                $DocumentPath,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::ReadWrite,
                [System.IO.FileShare]::None
            )
            return [pscustomobject]@{
                Available = $true
                Reason = 'exclusive_access_confirmed'
                OwnerFile = $ownerPath
                Error = $null
            }
        } catch {
            $lastError = $_.Exception.Message
            if ($attempt -lt 3) { Start-Sleep -Milliseconds 200 }
        } finally {
            if ($null -ne $stream) { $stream.Dispose() }
        }
    }
    return [pscustomobject]@{
        Available = $false
        Reason = 'exclusive_access_denied'
        OwnerFile = $ownerPath
        Error = $lastError
    }
}

$startedAt = Get-Date
$resolvedPath = $null
$initialHash = $null
$finalHash = $null
$initialState = $null
$finalState = $null
$samples = @()
$warningDialogs = @()
$observedDialogs = @()
$failureCode = $null
$failureMessage = $null
$resultExitCode = 5
$saved = $false
$refreshInvocations = 0
$mutexAcquired = $false
$mutex = $null
$word = $null
$document = $null
$wordOwned = $false
$preexistingWordProcessIds = @()
$newWordProcessIds = @()
$controlledWordProcessId = $null
$controlledWordCommandLine = $null
$targetLockState = $null

try {
    $resolvedPath = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    $file = Get-Item -LiteralPath $resolvedPath -ErrorAction Stop
    if ($file.PSIsContainer -or $file.Extension -ine '.docx') {
        Set-Failure 'invalid_document' 2 "Not a DOCX file: $resolvedPath"
    }
    if ($MaximumWaitSeconds -le $MinimumSettlingSeconds) {
        Set-Failure 'invalid_timing' 2 'MaximumWaitSeconds must exceed MinimumSettlingSeconds.'
    }

    $mutex = New-Object System.Threading.Mutex($false, 'Global\Codex.Zotero.WordIntegration.Guard.v1')
    try {
        $mutexAcquired = $mutex.WaitOne(0, $false)
    } catch [System.Threading.AbandonedMutexException] {
        $mutexAcquired = $true
    }
    if (-not $mutexAcquired) {
        Set-Failure 'integration_command_already_guarded' 3 'Another guarded Zotero Word command is already running.'
    }

    $targetLockState = Get-TargetDocumentLockState $resolvedPath
    if (-not $targetLockState.Available) {
        Set-Failure 'target_document_open_or_locked' 2 ('Close only the target document before guarded Zotero refresh. Lock reason: ' + $targetLockState.Reason)
    }
    if (-not (Get-Process zotero -ErrorAction SilentlyContinue)) {
        Set-Failure 'zotero_not_running' 2 'Start Zotero before guarded Zotero refresh.'
    }
    $warningDialogs = @(Get-ZoteroDialogs)
    if ($warningDialogs.Count -gt 0) {
        $observedDialogs = $warningDialogs
        Set-Failure 'preexisting_zotero_dialog' 2 'Close the existing Zotero dialog before refresh.'
    }

    $initialHash = (Get-FileHash -LiteralPath $resolvedPath -Algorithm SHA256).Hash
    $preexistingWordProcessIds = @(
        Get-Process WINWORD -ErrorAction SilentlyContinue |
            ForEach-Object { [int]$_.Id }
    )
    $word = New-Object -ComObject Word.Application

    $processDeadline = (Get-Date).AddSeconds(5)
    do {
        $currentWordProcessIds = @(
            Get-Process WINWORD -ErrorAction SilentlyContinue |
                ForEach-Object { [int]$_.Id }
        )
        $newWordProcessIds = @(
            $currentWordProcessIds |
                Where-Object { $preexistingWordProcessIds -notcontains $_ }
        )
        if ($newWordProcessIds.Count -eq 1) { break }
        Start-Sleep -Milliseconds 100
    } while ((Get-Date) -lt $processDeadline)

    if ($newWordProcessIds.Count -ne 1) {
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) } catch {}
        $word = $null
        Set-Failure 'word_process_identity_unavailable' 2 ("Expected exactly one new controlled Word process, found {0}; existing Word documents were left unchanged." -f $newWordProcessIds.Count)
    }
    $controlledWordProcessId = [int]$newWordProcessIds[0]
    $controlledWordProcess = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $controlledWordProcessId)
    $controlledWordCommandLine = [string]$controlledWordProcess.CommandLine
    if ($controlledWordCommandLine -notmatch '(/Automation\b|-Embedding\b)') {
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) } catch {}
        $word = $null
        Set-Failure 'word_instance_not_isolated' 2 'The new Word process was not identifiable as an automation instance. Existing Word documents were left unchanged; no refresh was attempted.'
    }
    $wordOwned = $true
    $word.Visible = $false
    $word.DisplayAlerts = 0
    if ($word.Documents.Count -ne 0) {
        Set-Failure 'unexpected_open_document' 2 'The controlled Word instance was not empty.'
    }

    $document = $word.Documents.Open($resolvedPath, $false, $false)
    if ([bool]$document.ReadOnly) {
        Set-Failure 'target_document_read_only' 2 'The target document opened read-only, indicating a lock or access conflict. No refresh was attempted.'
    }
    $openedPath = [System.IO.Path]::GetFullPath([string]$document.FullName)
    $targetPath = [System.IO.Path]::GetFullPath($resolvedPath)
    $pathMatches = [string]::Equals($openedPath, $targetPath, [System.StringComparison]::OrdinalIgnoreCase)
    if ($word.Documents.Count -ne 1 -or -not $pathMatches) {
        Set-Failure 'document_isolation_failed' 2 ("Guarded refresh requires exactly one target document. Count={0}; opened={1}; target={2}" -f $word.Documents.Count, $openedPath, $targetPath)
    }
    $initialState = Get-DocumentFieldState $document

    # Word.Run returns before Zotero necessarily finishes its asynchronous work.
    $refreshInvocations++
    $word.Run('ZoteroRefresh')

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $lastFingerprint = $null
    $consecutiveStable = 0
    while ($stopwatch.Elapsed.TotalSeconds -lt $MaximumWaitSeconds) {
        Start-Sleep -Milliseconds $PollMilliseconds
        $currentDialogs = @(Get-ZoteroDialogs)
        if ($currentDialogs.Count -gt 0) { $observedDialogs = $currentDialogs }
        if (Test-ZoteroIntegrationWarning $currentDialogs) {
            $warningDialogs = $currentDialogs
            $dialogText = @($currentDialogs | ForEach-Object { $_.Text }) -join ' || '
            Set-Failure 'zotero_integration_dialog' 4 ('Zotero displayed an integration warning: ' + $dialogText)
        }

        try {
            $state = Get-DocumentFieldState $document
        } catch {
            $samples += [pscustomobject]@{
                ElapsedSeconds = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 3)
                Readable = $false
                Error = $_.Exception.Message
            }
            continue
        }
        $samples += [pscustomobject]@{
            ElapsedSeconds = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 3)
            Readable = $true
            FieldCount = $state.FieldCount
            ZoteroFieldCount = $state.ZoteroFieldCount
            Fingerprint = $state.Fingerprint
        }

        if ($stopwatch.Elapsed.TotalSeconds -lt $MinimumSettlingSeconds -or $currentDialogs.Count -gt 0) {
            $lastFingerprint = $null
            $consecutiveStable = 0
            continue
        }
        if ($state.Fingerprint -ceq $lastFingerprint) {
            $consecutiveStable++
        } else {
            $lastFingerprint = $state.Fingerprint
            $consecutiveStable = 1
        }
        if ($consecutiveStable -ge $StableSamples) {
            $finalState = $state
            break
        }
    }
    $stopwatch.Stop()

    if ($null -eq $finalState) {
        Set-Failure 'refresh_settling_timeout' 5 'Zotero refresh did not reach a stable readable field state before timeout.'
    }
    $currentDialogs = @(Get-ZoteroDialogs)
    if ($currentDialogs.Count -gt 0) {
        $warningDialogs = $currentDialogs
        $observedDialogs = $currentDialogs
        Set-Failure 'zotero_dialog_still_open' 4 'A Zotero dialog remained open after field settling.'
    }

    $document.Save()
    $saved = $true
    $document.Close(0)
    try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) } catch {}
    $document = $null
    $word.Quit()
    try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) } catch {}
    $word = $null
    $finalHash = (Get-FileHash -LiteralPath $resolvedPath -Algorithm SHA256).Hash
    $resultExitCode = 0
} catch {
    $failureMessage = $_.Exception.Message
    if (-not $failureCode) { $failureCode = 'unexpected_error' }
} finally {
    if ($null -ne $document) {
        try { $document.Close(0) } catch {}
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) } catch {}
    }
    if ($null -ne $word) {
        if ($wordOwned) { try { $word.Quit() } catch {} }
        try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) } catch {}
    }
    if ($mutexAcquired -and $null -ne $mutex) {
        try { $mutex.ReleaseMutex() } catch {}
    }
    if ($null -ne $mutex) { $mutex.Dispose() }
}

if ($resolvedPath -and (Test-Path -LiteralPath $resolvedPath)) {
    if (-not $finalHash) { $finalHash = (Get-FileHash -LiteralPath $resolvedPath -Algorithm SHA256).Hash }
    if (-not $saved -and $initialHash -and $finalHash -ne $initialHash) {
        $failureCode = 'source_changed_after_failed_refresh'
        $failureMessage = 'The source file changed despite failure; preserve the baseline backup and stop automation.'
        $resultExitCode = 5
    }
}

$report = [ordered]@{
    success = ($resultExitCode -eq 0)
    status = if ($resultExitCode -eq 0) { 'refreshed_and_saved' } else { 'failed_without_save' }
    failureCode = $failureCode
    message = $failureMessage
    document = $resolvedPath
    startedAt = $startedAt.ToString('o')
    completedAt = (Get-Date).ToString('o')
    refreshInvocations = $refreshInvocations
    saved = $saved
    initialSha256 = $initialHash
    finalSha256 = $finalHash
    initialFieldState = $initialState
    finalFieldState = $finalState
    warningDialogs = $warningDialogs
    observedZoteroDialogs = $observedDialogs
    wordIsolation = [ordered]@{
        targetLockState = $targetLockState
        preexistingProcessIds = $preexistingWordProcessIds
        newProcessIds = $newWordProcessIds
        controlledProcessId = $controlledWordProcessId
        controlledProcessCommandLine = $controlledWordCommandLine
        controlledProcessOwned = $wordOwned
    }
    settling = [ordered]@{
        minimumSeconds = $MinimumSettlingSeconds
        maximumSeconds = $MaximumWaitSeconds
        pollMilliseconds = $PollMilliseconds
        requiredStableSamples = $StableSamples
        samples = $samples
    }
}
$json = $report | ConvertTo-Json -Depth 8
if ($ReportPath) {
    $reportFullPath = [System.IO.Path]::GetFullPath($ReportPath)
    $reportDirectory = Split-Path -Parent $reportFullPath
    if ($reportDirectory -and -not (Test-Path -LiteralPath $reportDirectory)) {
        New-Item -ItemType Directory -Path $reportDirectory | Out-Null
    }
    $json | Set-Content -LiteralPath $reportFullPath -Encoding UTF8
}
$json
exit $resultExitCode
