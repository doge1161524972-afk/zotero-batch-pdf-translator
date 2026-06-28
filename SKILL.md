---
name: zotero-pdf2zh-bilingual
description: Batch translate PDFs from Zotero collections through a local zotero-pdf2zh/pdf2zh service, process one paper at a time to avoid batch failures, attach bilingual compare outputs back to Zotero Desktop, and verify or repair the bilingual layout so Chinese appears on the left and English on the right. Use when the user asks to translate Zotero folders/collections with pdf2zh, fdf2zh/pdf2zh bilingual compare, add translated PDFs as Zotero attachments, or fix Chinese-right/English-left compare PDFs.
---

# Zotero Pdf2zh Bilingual

## Overview

Use this skill for Zotero-backed pdf2zh batch work where reliability matters more than speed. The core rule is: translate and settle one PDF at a time, verify the output, then attach it, because putting many papers into pdf2zh at once can fail or produce partial results.

## Workflow

1. Check Zotero and pdf2zh readiness.
   - Use the Zotero skill/helper first if available to confirm `http://127.0.0.1:23119`.
   - Check the local pdf2zh service at `http://127.0.0.1:8890/health`.
   - Pass `--output-dir` when the local pdf2zh server writes translated files outside the current working directory.

2. Identify collection keys.
   - If the user points to visible Zotero folders but does not give keys, use the Zotero local API or SQLite only as needed to map folder names to collection keys.
   - Keep user-facing names in the report, but drive automation by stable Zotero collection keys.

3. Run one-by-one translation.
   - Prefer `scripts/zotero_pdf2zh_batch.py`.
   - It skips already translated outputs unless asked otherwise, calls pdf2zh once per source PDF, writes a manifest/report, and can fix compare PDFs so Chinese is left and English is right.
   - Use `--collection label=KEY` once per Zotero collection.

4. Attach outputs back to Zotero.
   - Zotero local API is reliable for reading children and verifying attachments, but file-attachment writes may not be available. Use `scripts/attach_outputs_to_zotero.ps1` to drive Zotero Desktop UI when direct API attachment is unavailable.
   - Run `-WhatIf` first, then attach in small limits such as `-Limit 1` or `-Limit 5`.
   - Keep Zotero visible and do not interact with it during UI automation.

5. Verify completion.
   - Re-run the Python script with `--verify-only` to count items, attachments, missing outputs, and compare layout.
   - Success requires zero missing translated attachments and zero compare PDFs where the right side has more Chinese than the left side.
   - Render or inspect at least one sample page visually when the user complained about layout.

## Commands

Translate two collections and create a manifest:

```powershell
$py = 'C:\path\to\python.exe'
$skill = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills\zotero-pdf2zh-bilingual' } else { Join-Path $HOME '.codex\skills\zotero-pdf2zh-bilingual' }
& $py (Join-Path $skill 'scripts\zotero_pdf2zh_batch.py') `
  --collection brain=ISTDU5JI `
  --collection review=ZWG4XSS6 `
  --report 'pdf2zh_zotero_batch_report.json'
```

Preview pending Zotero attachments:

```powershell
$script = [scriptblock]::Create((Get-Content -Raw (Join-Path $skill 'scripts\attach_outputs_to_zotero.ps1')))
& $script -Manifest 'C:\path\to\pdf2zh_zotero_batch_report.json' -WhatIf
```

Attach a few outputs:

```powershell
$script = [scriptblock]::Create((Get-Content -Raw (Join-Path $skill 'scripts\attach_outputs_to_zotero.ps1')))
& $script -Manifest 'C:\path\to\pdf2zh_zotero_batch_report.json' -Limit 5
```

Verify final state:

```powershell
& $py (Join-Path $skill 'scripts\zotero_pdf2zh_batch.py') `
  --collection brain=ISTDU5JI `
  --collection review=ZWG4XSS6 `
  --report 'pdf2zh_zotero_batch_report.json' `
  --verify-only
```

## Layout Contract

For bilingual compare PDFs, the preferred layout is:

- left side: Chinese translation
- right side: English original

If pdf2zh produces English-left/Chinese-right output, do not retranslate first. Use the script's side-fix logic to swap page halves in place after backing up the file. The script checks CJK character counts on both halves of the first pages before and after the swap.

## Notes

- Read `references/windows-zotero-pdf2zh.md` when Zotero UI automation, proxy bypass, or service paths are uncertain.
- Do not delete or replace original source PDFs.
- Back up any translated PDF before overwriting it in place.
- If a PDF tab is already open in Zotero, tell the user to close and reopen that PDF tab to refresh the displayed file.
