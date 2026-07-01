import importlib.util
import tempfile
import unittest
from pathlib import Path

import fitz


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "zotero_pdf2zh_batch.py"
spec = importlib.util.spec_from_file_location("zotero_pdf2zh_batch", SCRIPT)
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


def make_two_column_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=400, height=200)
    page.draw_rect(fitz.Rect(0, 0, 200, 200), color=(1, 0, 0), fill=(1, 0, 0))
    page.draw_rect(fitz.Rect(200, 0, 400, 200), color=(0, 1, 0), fill=(0, 1, 0))
    doc.save(path)
    doc.close()


def make_alternating_dual_pdf(path: Path) -> None:
    doc = fitz.open()
    english = doc.new_page(width=400, height=200)
    english.insert_text((36, 80), "This is an English original page with many Latin words.", fontsize=12)
    chinese = doc.new_page(width=400, height=200)
    chinese.insert_text((36, 80), "这是中文译文页面，包含很多中文字符，用于检测交替页。", fontsize=12)
    doc.save(path)
    doc.close()


class SideSwapTest(unittest.TestCase):
    def test_swap_moves_right_half_to_left_side(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = Path(temp_dir) / "source.pdf"
            out = Path(temp_dir) / "swapped.pdf"
            make_two_column_pdf(src)

            batch.swap_compare_pdf_sides(src, out)

            with fitz.open(out) as doc:
                pix = doc[0].get_pixmap()
            left_pixel = pix.pixel(50, 100)
            right_pixel = pix.pixel(350, 100)
            self.assertGreater(left_pixel[1], left_pixel[0])
            self.assertGreater(right_pixel[0], right_pixel[1])

    def test_detects_alternating_page_dual(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original = Path(temp_dir) / "original.pdf"
            src = Path(temp_dir) / "alternating.pdf"
            make_two_column_pdf(original)
            make_alternating_dual_pdf(src)

            self.assertTrue(batch.is_probably_alternating_page_dual(src, source_path=original))

    def test_scanned_failure_detection(self):
        self.assertTrue(batch.scanned_failure("Babeldoc translation error: Scanned PDF detected."))
        self.assertFalse(batch.scanned_failure("ordinary timeout"))

    def test_zotero_key_validation_rejects_cloud_invalid_keys(self):
        self.assertTrue(batch.is_valid_zotero_key("AIV5GKIM"))
        self.assertFalse(batch.is_valid_zotero_key("IA0QWB2N"))
        self.assertFalse(batch.is_valid_zotero_key("FFT15MT8"))
        self.assertFalse(batch.is_valid_zotero_key("MU9B9AOE"))


if __name__ == "__main__":
    unittest.main()
