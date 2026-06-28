param(
    [Parameter(Mandatory=$true)]
    [string]$Manifest,
    [int]$Limit = 0,
    [switch]$WhatIf,
    [string]$ZoteroBase = 'http://127.0.0.1:23119/api/users/0',
    [int]$AttachButtonX = 1552,
    [int]$AttachButtonY = 95,
    [int]$AttachFileMenuX = 1590,
    [int]$AttachFileMenuY = 193,
    [int]$FileNameBoxX = 1535,
    [int]$FileNameBoxY = 411
)

$ErrorActionPreference = 'Stop'

function Get-Children($ItemKey) {
    $encoded = [uri]::EscapeDataString($ItemKey)
    Invoke-RestMethod -Uri "$ZoteroBase/items/$encoded/children?format=json&include=data&limit=100" -TimeoutSec 30
}

function Test-Attached($ItemKey, $FileName) {
    $children = Get-Children $ItemKey
    foreach ($child in $children) {
        if ($child.data.filename -eq $FileName) {
            return $true
        }
    }
    return $false
}

function Normalize-ManifestRow($Row) {
    if (-not $Row.item_key -or -not $Row.output) {
        return $null
    }
    $output = [string]$Row.output
    if (-not (Test-Path -LiteralPath $output)) {
        return $null
    }
    $fileName = [IO.Path]::GetFileName($output)
    [pscustomobject]@{
        item_key = [string]$Row.item_key
        output = $output
        filename = $fileName
        title = [string]$Row.title
        attached = (Test-Attached ([string]$Row.item_key) $fileName)
    }
}

if (-not (Test-Path -LiteralPath $Manifest)) {
    throw "Manifest not found: $Manifest"
}

$rows = @(Get-Content -Raw -LiteralPath $Manifest | ConvertFrom-Json)
$pendingRows = @()
foreach ($row in $rows) {
    $normalized = Normalize-ManifestRow $row
    if ($null -ne $normalized -and -not $normalized.attached) {
        $pendingRows += $normalized
    }
}
if ($Limit -gt 0) {
    $pendingRows = @($pendingRows | Select-Object -First $Limit)
}

if ($WhatIf) {
    [pscustomobject]@{
        pending = $pendingRows.Count
        itemKeys = @($pendingRows | ForEach-Object { $_.item_key })
    } | ConvertTo-Json -Compress
    exit 0
}

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ZoteroAttachUi {
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint x, uint y, uint data, UIntPtr extraInfo);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
'@
Add-Type -AssemblyName System.Windows.Forms

function Click-At([int]$X, [int]$Y) {
    [ZoteroAttachUi]::SetCursorPos($X, $Y) | Out-Null
    [ZoteroAttachUi]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero)
    [ZoteroAttachUi]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)
}

$zotero = Get-Process zotero | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $zotero) {
    throw 'Zotero desktop window was not found.'
}

function Attach-One($Row) {
    [ZoteroAttachUi]::SetForegroundWindow([IntPtr]$zotero.MainWindowHandle) | Out-Null
    Start-Process ("zotero://select/library/items/$($Row.item_key)")
    Start-Sleep -Seconds 3

    Click-At $AttachButtonX $AttachButtonY
    Start-Sleep -Milliseconds 300
    Click-At $AttachFileMenuX $AttachFileMenuY
    Start-Sleep -Seconds 2
    Click-At $FileNameBoxX $FileNameBoxY
    Set-Clipboard -Value $Row.output
    [System.Windows.Forms.SendKeys]::SendWait('^v')
    Start-Sleep -Milliseconds 250
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
    Start-Sleep -Seconds 2

    foreach ($attempt in 0..15) {
        if (Test-Attached $Row.item_key $Row.filename) {
            Write-Output "ATTACHED $($Row.item_key) $($Row.filename)"
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Zotero API did not confirm attachment for $($Row.item_key)"
}

foreach ($row in $pendingRows) {
    Attach-One $row
}

[pscustomobject]@{ attached = $pendingRows.Count } | ConvertTo-Json -Compress
