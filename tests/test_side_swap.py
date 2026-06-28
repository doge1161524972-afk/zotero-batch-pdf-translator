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


if __name__ == "__main__":
    unittest.main()
