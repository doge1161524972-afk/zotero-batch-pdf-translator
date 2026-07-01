import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

import fitz


DEFAULT_ZOTERO_BASE = "http://127.0.0.1:23119/api/users/0"
DEFAULT_PDF2ZH_BASE = "http://127.0.0.1:8890"
DEFAULT_OUTPUT_DIR = Path(os.environ.get("PDF2ZH_OUTPUT_DIR", "translated"))
DEFAULT_BACKUP_ROOT = Path("tmp/pdf2zh_side_swap_backups")


def api_json(url, data=None, timeout=30):
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def parse_collection(value):
    if "=" in value:
        label, key = value.split("=", 1)
        return label.strip(), key.strip()
    return value.strip(), value.strip()


def get_collection_items(zotero_base, collection_key):
    url = f"{zotero_base}/collections/{collection_key}/items/top?format=json&include=data&limit=100"
    return api_json(url)


def get_children(zotero_base, item_key):
    quoted = urllib.parse.quote(item_key)
    url = f"{zotero_base}/items/{quoted}/children?format=json&include=data&limit=100"
    return api_json(url)


def get_file_path(zotero_base, attachment_key):
    quoted = urllib.parse.quote(attachment_key)
    url = f"{zotero_base}/items/{quoted}/file/view/url"
    with urllib.request.urlopen(url, timeout=15) as response:
        file_url = response.read().decode("utf-8", errors="replace").strip()
    parsed = urllib.parse.urlparse(file_url)
    return Path(urllib.parse.unquote(parsed.path.lstrip("/")))


def is_translated_output(filename):
    lowered = filename.lower()
    markers = [
        ".compare.pdf",
        "_compare.pdf",
        "tb_compare.pdf",
        "lr_dual.pdf",
        "tb_dual.pdf",
        ".dual.pdf",
        "-dual.pdf",
        ".mono.pdf",
        "-mono.pdf",
        ".zh-cn.",
        "no_watermark",
        "crop-compare",
    ]
    return any(marker in lowered for marker in markers)


def pdf_attachment_candidates(item, children):
    candidates = []
    data = item.get("data", {})
    if data.get("itemType") == "attachment" and data.get("contentType") == "application/pdf":
        candidates.append(item)
    candidates.extend(
        child for child in children
        if child.get("data", {}).get("contentType") == "application/pdf"
    )
    originals = []
    translated = []
    for candidate in candidates:
        data = candidate.get("data", {})
        filename = data.get("filename") or data.get("title") or ""
        if is_translated_output(filename):
            translated.append(candidate)
        else:
            originals.append(candidate)
    return originals or translated


def compare_candidates(pdf_path, output_dir):
    stem = pdf_path.stem
    return [
        output_dir / f"{stem}.compare.pdf",
        output_dir / f"{stem}.no_watermark.zh-CN.compare.pdf",
        output_dir / f"{stem}.zh-CN.compare.pdf",
        output_dir / f"{stem}.no_watermark.zh-CN.LR_compare.pdf",
        output_dir / f"{stem}.zh-CN.LR_compare.pdf",
        output_dir / f"{stem}.no_watermark.zh-CN.TB_compare.pdf",
        output_dir / f"{stem}.no_watermark.zh-CN.dual.pdf",
        output_dir / f"{stem}.zh-CN.dual.pdf",
        output_dir / f"{stem}.no_watermark.zh-CN.LR_dual.pdf",
        output_dir / f"{stem}.zh-CN.LR_dual.pdf",
    ]


def existing_compare(pdf_path, output_dir):
    for candidate in compare_candidates(pdf_path, output_dir):
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    matches = list(output_dir.glob(f"{pdf_path.stem}*compare*.pdf"))
    if not matches:
        matches = list(output_dir.glob(f"{pdf_path.stem}*dual*.pdf"))
    return matches[0] if matches else None


def translate_one(pdf2zh_base, pdf_path, args):
    encoded = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
    payload = {
        "fileName": pdf_path.name,
        "fileContent": "data:application/pdf;base64," + encoded,
        "engine": args.engine,
        "next_service": args.next_service,
        "sourceLang": args.source_lang,
        "targetLang": args.target_lang,
        "noWatermark": args.no_watermark,
        "noMono": args.no_mono,
        "noDual": False,
        "compare": True,
        "dualMode": args.dual_mode,
        "qps": args.qps,
        "poolSize": args.pool_size,
        "disableGlossary": args.disable_glossary,
    }
    return api_json(f"{pdf2zh_base}/translate", payload, timeout=args.translate_timeout)


def scanned_failure(text):
    return "scanned pdf detected" in (text or "").lower()


def translate_one_ocr_cli(pdf_path, args):
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    exe = Path(args.pdf2zh_next_exe)
    service = args.next_service or "deepseek"
    command = [
        str(exe),
        str(pdf_path),
        f"--{service}",
        "--qps", str(args.qps),
        "--output", str(output_dir),
        "--lang-in", args.source_lang,
        "--lang-out", args.target_lang,
        "--watermark-output-mode", "no_watermark",
        "--pool-max-workers", str(args.pool_size),
        "--skip-scanned-detection",
        "--auto-enable-ocr-workaround",
    ]
    if args.config_file:
        command.extend(["--config-file", args.config_file])
    if args.no_mono:
        command.append("--no-mono")
    log_path = Path(args.report).with_suffix(f".{pdf_path.stem}.ocr_retry.log")
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        result = subprocess.run(
            command,
            cwd=str(output_dir),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=args.translate_timeout,
        )
    output = existing_compare(pdf_path, output_dir)
    if result.returncode == 0 and output:
        return {"status": "translated_ocr_retry", "output": str(output), "ocr_retry_log": str(log_path)}
    tail = ""
    if log_path.exists():
        tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:])
    return {
        "status": "error",
        "error": f"OCR retry failed with exit {result.returncode}: {tail}",
        "ocr_retry_log": str(log_path),
    }


def wait_for_file_task(pdf2zh_base, file_name, max_seconds):
    start = time.time()
    while time.time() - start < max_seconds:
        tasks = api_json(f"{pdf2zh_base}/api/tasks").get("tasks", [])
        active = [
            task for task in tasks
            if task.get("active") and task.get("fileName") == file_name
        ]
        if not active:
            return
        task = active[0]
        print(
            f"    progress={task.get('progress')} status={task.get('status')} "
            f"message={task.get('message')}",
            flush=True,
        )
        time.sleep(15)
    raise TimeoutError("pdf2zh task did not finish before timeout")


def count_text(text):
    return {
        "cjk": sum("\u4e00" <= ch <= "\u9fff" for ch in text),
        "latin": sum(ch.isascii() and ch.isalpha() for ch in text),
    }


def score_pdf_sides(path, max_pages=3):
    with fitz.open(path) as doc:
        left = []
        right = []
        for page in list(doc)[:max_pages]:
            half = page.rect.width / 2
            for block in page.get_text("blocks"):
                if block[0] < half:
                    left.append(block[4])
                else:
                    right.append(block[4])
    return {"left": count_text("".join(left)), "right": count_text("".join(right))}


def should_swap(side_scores):
    return side_scores["right"]["cjk"] > side_scores["left"]["cjk"]


def is_probably_alternating_page_dual(path, source_path=None):
    try:
        with fitz.open(path) as translated:
            translated_pages = translated.page_count
            if translated_pages < 2 or translated_pages % 2:
                return False
            if source_path:
                try:
                    with fitz.open(source_path) as source:
                        if translated_pages == source.page_count * 2:
                            return True
                except Exception:
                    pass
            first = count_text(translated[0].get_text())
            second = count_text(translated[1].get_text())
    except Exception:
        return False
    first_is_english = first["latin"] > max(first["cjk"] * 2, 80)
    second_is_chinese = second["cjk"] > max(second["latin"] // 3, 80)
    first_is_chinese = first["cjk"] > max(first["latin"] // 3, 80)
    second_is_english = second["latin"] > max(second["cjk"] * 2, 80)
    return (first_is_english and second_is_chinese) or (first_is_chinese and second_is_english)


def swap_compare_pdf_sides(src_path, out_path):
    src_path = Path(src_path)
    out_path = Path(out_path)
    with fitz.open(src_path) as src_doc, fitz.open() as out_doc:
        for page in src_doc:
            width = page.rect.width
            height = page.rect.height
            half = width / 2
            new_page = out_doc.new_page(width=width, height=height)
            new_page.show_pdf_page(
                fitz.Rect(0, 0, half, height),
                src_doc,
                page.number,
                clip=fitz.Rect(half, 0, width, height),
            )
            new_page.show_pdf_page(
                fitz.Rect(half, 0, width, height),
                src_doc,
                page.number,
                clip=fitz.Rect(0, 0, half, height),
            )
        out_doc.save(out_path, garbage=4, deflate=True)


def backup_path_for(path, backup_dir):
    digest = hashlib.sha1(str(path).encode("utf-8", errors="replace")).hexdigest()[:10]
    safe_name = re.sub(r'[<>:"/\\\\|?*]+', "_", path.name)
    return backup_dir / f"{digest}_{safe_name}"


def ensure_chinese_left(path, backup_root):
    if is_probably_alternating_page_dual(path):
        raise RuntimeError(
            "alternating-page dual PDF detected; rebuild or regenerate as left-Chinese/right-English before attaching"
        )
    before = score_pdf_sides(path)
    if not should_swap(before):
        return {"status": "already_left", "before": before, "after": before}

    backup_dir = backup_root / time.strftime("%Y%m%d-%H%M%S")
    backup = backup_path_for(path, backup_dir)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", dir=str(path.parent)) as temp:
        temp_path = Path(temp.name)
    try:
        swap_compare_pdf_sides(path, temp_path)
        after = score_pdf_sides(temp_path)
        if after["left"]["cjk"] <= after["right"]["cjk"]:
            raise RuntimeError(f"side check failed after swap for {path}")
        os.replace(temp_path, path)
        return {"status": "swapped", "backup": str(backup), "before": before, "after": after}
    finally:
        if temp_path.exists():
            temp_path.unlink()


def child_has_filename(children, filename):
    return any((child.get("data", {}).get("filename") or "") == filename for child in children)


def child_with_filename(children, filename):
    for child in children:
        data = child.get("data", {})
        if (data.get("filename") or "") == filename:
            return child
    return None


def title_words(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def title_matches_item(row, child):
    child_data = child.get("data", {}) if child else {}
    parent_title = row.get("title") or ""
    child_title = child_data.get("title") or ""
    filename = child_data.get("filename") or ""
    item_key = row.get("item_key") or ""
    parent_head = " ".join(title_words(parent_title)[:5])
    child_words = " ".join(title_words(child_title))
    return (
        bool(parent_head and parent_head in child_words)
        or bool(item_key and filename.startswith(f"zotero_{item_key}_"))
    )


def save_report(path, rows):
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def build_item_rows(args):
    rows = []
    collections = [parse_collection(value) for value in args.collection]
    for collection_name, collection_key in collections:
        items = get_collection_items(args.zotero_base, collection_key)
        for index, item in enumerate(items, 1):
            data = item.get("data", {})
            item_key = data.get("key") or item.get("key")
            title = data.get("title") or item_key
            children = get_children(args.zotero_base, item_key)
            originals = pdf_attachment_candidates(item, children)
            row = {
                "collection": collection_name,
                "collection_key": collection_key,
                "index": index,
                "title": title,
                "item_key": item_key,
            }
            if not originals:
                row["status"] = "no_pdf"
                rows.append(row)
                continue
            attachment = originals[0]
            attachment_key = attachment.get("data", {}).get("key") or attachment.get("key")
            source_path = get_file_path(args.zotero_base, attachment_key)
            row.update({"source_attachment_key": attachment_key, "source_pdf": str(source_path)})
            rows.append(row)
    return rows


def verify_rows(args, rows):
    output_dir = Path(args.output_dir)
    bad_layout = []
    missing_outputs = []
    missing_attachments = []
    title_mismatches = []
    verified = []
    for row in rows:
        if not row.get("source_pdf"):
            missing_outputs.append(row)
            continue
        output = Path(row.get("output") or "")
        if not output.exists():
            output = existing_compare(Path(row["source_pdf"]), output_dir)
        if not output or not output.exists():
            missing_outputs.append(row)
            continue
        if is_probably_alternating_page_dual(output, row.get("source_pdf")):
            bad_layout.append({**row, "output": str(output), "layout_error": "alternating_page_dual"})
            continue
        scores = score_pdf_sides(output)
        if should_swap(scores):
            bad_layout.append({**row, "output": str(output), "side_scores": scores})
        children = get_children(args.zotero_base, row["item_key"])
        child = child_with_filename(children, output.name)
        if not child:
            missing_attachments.append({**row, "output": str(output)})
        elif not title_matches_item(row, child):
            title_mismatches.append({
                **row,
                "output": str(output),
                "attachment_title": child.get("data", {}).get("title") or "",
                "attachment_filename": child.get("data", {}).get("filename") or "",
            })
        verified.append({**row, "output": str(output), "side_scores": scores})
    return {
        "items": len(rows),
        "verified_outputs": len(verified),
        "missing_outputs": len(missing_outputs),
        "missing_attachments": len(missing_attachments),
        "title_mismatches": len(title_mismatches),
        "bad_layout": len(bad_layout),
        "missing_output_examples": missing_outputs[:5],
        "missing_attachment_examples": missing_attachments[:5],
        "title_mismatch_examples": title_mismatches[:5],
        "bad_layout_examples": bad_layout[:5],
    }


def run_translation(args):
    health = api_json(f"{args.pdf2zh_base}/health")
    print(f"pdf2zh: {health}", flush=True)
    output_dir = Path(args.output_dir)
    backup_root = Path(args.backup_root)
    report_path = Path(args.report)
    rows = build_item_rows(args)
    report = []

    for row in rows:
        title = row["title"]
        if row.get("status") == "no_pdf":
            print(f"{row['index']:02d}. SKIP no PDF: {title}", flush=True)
            report.append(row)
            save_report(report_path, report)
            continue
        source_path = Path(row["source_pdf"])
        if not source_path.exists():
            row["status"] = "missing_file"
            print(f"{row['index']:02d}. SKIP missing file: {title} -> {source_path}", flush=True)
            report.append(row)
            save_report(report_path, report)
            continue

        output = existing_compare(source_path, output_dir)
        if output and args.skip_existing:
            row.update({"status": "existing", "output": str(output)})
            print(f"{row['index']:02d}. DONE existing: {title} -> {output.name}", flush=True)
        else:
            print(f"{row['index']:02d}. START {title}", flush=True)
            request_error = ""
            try:
                response = translate_one(args.pdf2zh_base, source_path, args)
                print(f"    response={response}", flush=True)
                output = existing_compare(source_path, output_dir)
                if output:
                    row.update({"status": "translated", "output": str(output)})
                    print(f"    OK -> {output.name}", flush=True)
                else:
                    row["status"] = "no_output"
                    print("    FAIL no compare output found", flush=True)
            except Exception as exc:
                request_error = str(exc)
                print(f"    REQUEST ERROR {type(exc).__name__}: {exc}", flush=True)
                try:
                    wait_for_file_task(args.pdf2zh_base, source_path.name, args.translate_timeout)
                    output = existing_compare(source_path, output_dir)
                    if output:
                        row.update({"status": "translated_after_request_error", "output": str(output)})
                        print(f"    OK after request error -> {output.name}", flush=True)
                    else:
                        row.update({"status": "error", "error": str(exc)})
                except Exception as wait_exc:
                    row.update({"status": "error", "error": f"{exc}; settlement: {wait_exc}"})

            if (
                args.ocr_retry
                and row.get("status") in {"no_output", "error"}
                and (row.get("status") == "no_output" or scanned_failure(request_error) or scanned_failure(row.get("error", "")))
            ):
                print("    OCR retry for scanned/old PDF", flush=True)
                try:
                    retry = translate_one_ocr_cli(source_path, args)
                    row.update(retry)
                    if row.get("output"):
                        print(f"    OCR OK -> {Path(row['output']).name}", flush=True)
                    else:
                        print("    OCR failed", flush=True)
                except Exception as retry_exc:
                    row.update({
                        "status": "error",
                        "error": f"{row.get('error', '')}; OCR retry: {type(retry_exc).__name__}: {retry_exc}",
                    })

        if args.ensure_chinese_left and row.get("output"):
            try:
                fix = ensure_chinese_left(Path(row["output"]), backup_root)
            except Exception as exc:
                fix = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
                row["status"] = "bad_layout"
            row["layout_fix"] = fix
            print(f"    layout={fix['status']}", flush=True)
        report.append(row)
        save_report(report_path, report)

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", action="append", required=True, help="collection key or label=key")
    parser.add_argument("--zotero-base", default=DEFAULT_ZOTERO_BASE)
    parser.add_argument("--pdf2zh-base", default=DEFAULT_PDF2ZH_BASE)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--report", default="pdf2zh_zotero_batch_report.json")
    parser.add_argument("--backup-root", default=str(DEFAULT_BACKUP_ROOT))
    parser.add_argument("--engine", default="pdf2zh_next")
    parser.add_argument("--next-service", default="siliconflowfree")
    parser.add_argument("--pdf2zh-next-exe", default=os.environ.get("PDF2ZH_NEXT_EXE", "pdf2zh_next"))
    parser.add_argument("--config-file", default=os.environ.get("PDF2ZH_CONFIG_FILE", ""))
    parser.add_argument("--source-lang", default="en")
    parser.add_argument("--target-lang", default="zh-CN")
    parser.add_argument("--dual-mode", default="LR")
    parser.add_argument("--qps", type=int, default=8)
    parser.add_argument("--pool-size", type=int, default=80)
    parser.add_argument("--translate-timeout", type=int, default=7200)
    parser.add_argument("--no-watermark", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--no-mono", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--disable-glossary", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--skip-existing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--ensure-chinese-left", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--ocr-retry", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

    if args.verify_only:
        report_path = Path(args.report)
        if report_path.exists():
            rows = json.loads(report_path.read_text(encoding="utf-8"))
        else:
            rows = build_item_rows(args)
        summary = verify_rows(args, rows)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        raise SystemExit(
            1 if summary["missing_outputs"]
            or summary["missing_attachments"]
            or summary["title_mismatches"]
            or summary["bad_layout"]
            else 0
        )

    report = run_translation(args)
    if args.json:
        print(json.dumps({"report": str(Path(args.report).resolve()), "rows": report}, ensure_ascii=False, indent=2))
    else:
        print(f"Report: {Path(args.report).resolve()}")


if __name__ == "__main__":
    main()
