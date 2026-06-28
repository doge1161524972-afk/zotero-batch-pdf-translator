# Windows Zotero Pdf2zh Notes

Use these notes when the main workflow fails or the environment is unclear.

## Local endpoints

- Zotero local API: `http://127.0.0.1:23119/api/users/0`
- Zotero connector probe: `http://127.0.0.1:23119/connector/ping`
- pdf2zh service: `http://127.0.0.1:8890`
- pdf2zh health: `http://127.0.0.1:8890/health`

Set loopback proxy bypass before local HTTP calls:

```powershell
$env:NO_PROXY = '127.0.0.1,localhost'
$env:no_proxy = '127.0.0.1,localhost'
```

## Example paths from one Windows setup

- pdf2zh server root: `D:\CodexApps\zotero-pdf2zh\server`
- pdf2zh Python: `D:\CodexApps\zotero-pdf2zh\server\zotero-pdf2zh-next-venv\Scripts\python.exe`
- translated output directory: `D:\CodexApps\zotero-pdf2zh\server\translated`

Treat versions and paths as examples only. Prefer passing `--output-dir`, `--pdf2zh-base`, and the Python executable that belongs to the user's own pdf2zh installation.

## Attachment strategy

The local Zotero API is useful for reading item children and verifying attached filenames. Do not assume it can create file attachments. When attachment creation is unavailable, drive Zotero Desktop UI with `scripts/attach_outputs_to_zotero.ps1`.

The UI script depends on the Zotero window layout. If clicks miss:

1. Bring Zotero to the foreground.
2. Keep it maximized or in the same position.
3. Adjust `-AttachButtonX`, `-AttachButtonY`, `-AttachFileMenuX`, `-AttachFileMenuY`, `-FileNameBoxX`, and `-FileNameBoxY`.
4. Run `-WhatIf` first, then small `-Limit` batches.

Run the PowerShell script in the current interactive host with `[scriptblock]::Create(...)`; launching a child PowerShell process can prevent `SendKeys` from reaching the file picker.

## Layout strategy

pdf2zh compare outputs may be English-left/Chinese-right even when the user expects Chinese-left/English-right. Before retranslation, inspect CJK counts by half-page. If Chinese is stronger on the right, swap the left and right halves of each page and verify again.

If the user still sees the old layout in Zotero after replacement, ask them to close the open PDF tab and reopen it. Zotero can display a cached open file.
