---
name: zotero-batch-pdf-translator
description: Batch translate PDFs from Zotero collections through a local zotero-pdf2zh/pdf2zh service, process one paper at a time to avoid batch failures, attach bilingual compare outputs back to Zotero Desktop, enforce the layout contract that Chinese is on the left and English is on the right, and retry old/scanned PDFs through OCR workaround before declaring them failed. Use when the user asks to batch translate Zotero folders/collections with pdf2zh, fdf2zh/pdf2zh bilingual compare, add translated PDFs as Zotero attachments, fix Chinese-right/English-left compare PDFs, prevent alternating-page dual PDFs from being attached, or translate old scanned literature PDFs.
---

# Zotero Batch PDF Translator

## Overview

Use this skill for Zotero-backed pdf2zh batch work where reliability matters more than speed. The core rule is: translate and settle one PDF at a time, verify the output, then attach it, because putting many papers into pdf2zh at once can fail or produce partial results.

Hard layout rule: deliver and attach only left-right bilingual PDFs with Chinese on the left and English on the right. Alternating-page dual PDFs, where one page is English and the next page is Chinese, are only temporary intermediates and must be converted or regenerated before attaching to Zotero.

Hard OCR rule: old or scanned literature PDFs must get an OCR-workaround attempt before being marked failed. If pdf2zh/Babeldoc reports `Scanned PDF detected`, or an old PDF produces no output after scan detection, rerun through pdf2zh-next with scan detection skipped and OCR workaround enabled.

Hard sync rule: translated attachments must have Zotero-server-valid item keys before the run is called complete. Zotero item keys are 8 characters drawn from `23456789ABCDEFGHIJKLMNPQRSTUVWXYZ`; keys containing `0`, `1`, or `O` can exist locally after a buggy attachment path but will fail Zotero sync with HTTP 400.

## Workflow

1. Check Zotero and pdf2zh readiness.
   - Use the Zotero skill/helper first if available to confirm `http://127.0.0.1:23119`.
   - Check the local pdf2zh service at `http://127.0.0.1:8890/health`.
   - Treat `127.0.0.1` as the installer's own computer. If their Zotero or pdf2zh ports differ, pass `--zotero-base` and `--pdf2zh-base`.
   - Pass `--output-dir` when the local pdf2zh server writes translated files outside the current working directory.

2. Identify collection keys.
   - If the user points to visible Zotero folders but does not give keys, use the Zotero local API or SQLite only as needed to map folder names to collection keys.
   - Keep user-facing names in the report, but drive automation by stable Zotero collection keys.

3. Run one-by-one translation.
   - Prefer `scripts/zotero_pdf2zh_batch.py`.
   - It skips already translated outputs unless asked otherwise, calls pdf2zh once per source PDF, writes a manifest/report, and can fix compare PDFs so Chinese is left and English is right.
   - Do not pass `--use-alternating-pages-dual` for final deliverables. If direct `pdf2zh_next` CLI is used as a fallback, omit that flag and prefer a left-right compare/dual output. If the only successful output is alternating-page dual, convert it into a left-Chinese/right-English PDF before attachment.
   - For old/scanned PDFs, do not stop at the first `Scanned PDF detected` failure. Retry with `--skip-scanned-detection --auto-enable-ocr-workaround` before reporting failure. This retry may produce rougher text, but it is the expected path for older scanned journal PDFs.
   - Use `--collection label=KEY` once per Zotero collection.

4. Attach outputs back to Zotero.
   - Zotero local API is reliable for reading children and verifying attachments, but file-attachment writes may not be available. Use `scripts/attach_outputs_to_zotero.ps1` to drive Zotero Desktop UI when direct API attachment is unavailable.
   - Run `-WhatIf` first, then attach in small limits such as `-Limit 1` or `-Limit 5`.
   - Keep Zotero visible and do not interact with it during UI automation.

5. Verify completion.
   - Re-run the Python script with `--verify-only` to count items, attachments, missing outputs, and compare layout.
   - Success requires zero missing translated attachments, zero invalid Zotero attachment keys, zero title/file mismatches, zero alternating-page dual attachments, and zero compare PDFs where the right side has more Chinese than the left side.
   - Render or inspect at least one sample page visually when the user complained about layout.

## Commands

Translate two collections and create a manifest:

```powershell
$py = 'C:\path\to\python.exe'
$skill = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills\zotero-batch-pdf-translator' } else { Join-Path $HOME '.codex\skills\zotero-batch-pdf-translator' }
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

For bilingual compare PDFs, the required layout is:

- left side: Chinese translation
- right side: English original

Never attach an alternating-page dual PDF as the final Zotero translation. A file is alternating-page dual when page 1 is mostly English and page 2 is mostly Chinese, or when the page count is about twice the original page count. If this appears, either regenerate as left-right compare/dual or rebuild the PDF by pairing each English/Chinese page into one page with Chinese on the left and English on the right.

If pdf2zh produces English-left/Chinese-right output, do not retranslate first. Use the script's side-fix logic to swap page halves in place after backing up the file. The script checks CJK character counts on both halves of the first pages before and after the swap.

Before attaching outputs to Zotero, verify each translated attachment title or filename maps to the parent Zotero item title. The final report must include title/file matching status, Zotero key validity, and layout verification status.

## OCR Contract

When a source PDF is old, scanned, or triggers `Scanned PDF detected`, run an OCR-workaround retry before declaring the item failed. The retry command shape for direct `pdf2zh_next` fallback is:

```powershell
pdf2zh_next.exe <source.pdf> --<service> --output <output-dir> --lang-in en --lang-out zh-CN --config-file <config.toml> --watermark-output-mode no_watermark --no-mono --skip-scanned-detection --auto-enable-ocr-workaround
```

Do not attach OCR-workaround output until it also passes the layout contract: left Chinese, right English, not alternating pages. Label/report these rows as OCR-retried so the user knows quality may be rougher than normal text PDFs.

## Notes

- Read `references/windows-zotero-pdf2zh.md` when Zotero UI automation, proxy bypass, or service paths are uncertain.
- Do not delete or replace original source PDFs.
- Back up any translated PDF before overwriting it in place.
- If a PDF tab is already open in Zotero, tell the user to close and reopen that PDF tab to refresh the displayed file.
