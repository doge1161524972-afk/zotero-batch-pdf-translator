# Zotero PDF2zh Bilingual Skill

A Codex skill for batch-translating PDFs from Zotero collections with a local
pdf2zh/zotero-pdf2zh service.

It is designed for the workflow where pdf2zh becomes unstable when too many
papers are submitted at once. The skill translates one paper at a time, records
a manifest, attaches the bilingual PDFs back to Zotero Desktop, and verifies the
preferred compare layout:

```text
Chinese translation | English original
```

## What It Does

- Reads PDFs from Zotero collections through the Zotero local API.
- Sends PDFs to a local pdf2zh service one by one.
- Reuses existing compare outputs when present.
- Writes a JSON manifest for audit and attachment automation.
- Checks whether bilingual compare PDFs are Chinese-left/English-right.
- Swaps page halves in place, with backups, when pdf2zh produces the opposite layout.
- Uses Zotero Desktop UI automation to attach outputs when the local API cannot create file attachments.
- Verifies missing outputs, missing Zotero attachments, and bad compare layouts.

## Requirements

- Windows for the included Zotero Desktop attachment automation script.
- Zotero Desktop with the local API enabled, usually at `http://127.0.0.1:23119`.
- A local pdf2zh or zotero-pdf2zh service, usually at `http://127.0.0.1:8890`.
- Python 3.10+ with `PyMuPDF` (`fitz`) available.
- PowerShell for `scripts/attach_outputs_to_zotero.ps1`.

The scripts default to the author's local pdf2zh paths in examples, but all
service URLs, output folders, and manifests are configurable by command-line
arguments.

## Installation

Clone the repository directly into your Codex skills folder:

```powershell
$skills = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills' } else { Join-Path $HOME '.codex\skills' }
git clone https://github.com/YOUR-USER/zotero-pdf2zh-bilingual-skill.git (Join-Path $skills 'zotero-pdf2zh-bilingual')
```

If you download the repo as a ZIP, extract it so the final folder contains
`SKILL.md` at its root:

```text
.../skills/zotero-pdf2zh-bilingual/SKILL.md
```

## Usage

Translate Zotero collections:

```powershell
$py = 'C:\path\to\python.exe'
$skill = Join-Path $env:CODEX_HOME 'skills\zotero-pdf2zh-bilingual'
& $py (Join-Path $skill 'scripts\zotero_pdf2zh_batch.py') `
  --collection review=ZWG4XSS6 `
  --pdf2zh-base 'http://127.0.0.1:8890' `
  --output-dir 'D:\CodexApps\zotero-pdf2zh\server\translated' `
  --report '.\pdf2zh_zotero_batch_report.json'
```

Preview pending Zotero attachments:

```powershell
$script = [scriptblock]::Create((Get-Content -Raw (Join-Path $skill 'scripts\attach_outputs_to_zotero.ps1')))
& $script -Manifest '.\pdf2zh_zotero_batch_report.json' -WhatIf
```

Attach outputs in small batches:

```powershell
& $script -Manifest '.\pdf2zh_zotero_batch_report.json' -Limit 5
```

Verify final state:

```powershell
& $py (Join-Path $skill 'scripts\zotero_pdf2zh_batch.py') `
  --collection review=ZWG4XSS6 `
  --report '.\pdf2zh_zotero_batch_report.json' `
  --verify-only
```

## Safety Notes

- The source PDFs in Zotero are not modified.
- Translated compare PDFs are backed up before in-place side swapping.
- Zotero UI automation depends on screen coordinates; run `-WhatIf` first and keep Zotero visible.
- If Zotero is already showing an old PDF tab, close and reopen that tab after replacement.
- Do not commit translated papers, manifests containing private library titles, or Zotero storage paths.

## Repository Layout

```text
SKILL.md
agents/openai.yaml
scripts/zotero_pdf2zh_batch.py
scripts/attach_outputs_to_zotero.ps1
references/windows-zotero-pdf2zh.md
tests/test_side_swap.py
```

## Development

Install the Python dependency:

```powershell
python -m pip install pymupdf
```

Run the side-swap unit test:

```powershell
python -m unittest discover -s tests
```

Validate the skill with your local Codex skill validator if available:

```powershell
python path\to\quick_validate.py .
```

## License

MIT
