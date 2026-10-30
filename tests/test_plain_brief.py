"""Regression tests for the one-page plain-language brief."""
import unittest
from pathlib import Path

from src.make_plain_brief import build_html

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


class TestPlainBrief(unittest.TestCase):
    def test_html_explains_why_useful_and_limits(self):
        page = build_html()
        for phrase in [
            "Why this project can be useful",
            "How the loop works",
            "What the synthetic test found",
            "What it does not do",
            "Computer-generated lab only",
            "Not the best baseline",
            "Real campaign missing",
            "No real-world trial-reduction claim",
        ]:
            self.assertIn(phrase, page)
        self.assertNotIn("<script", page.lower())

    def test_html_translates_jargon(self):
        page = build_html()
        self.assertIn("how much protein is broken into small peptides", page)
        self.assertIn("one-setting-at-a-time", page)
        self.assertIn("cheat sheet", page)

    def test_exports_are_nonempty_when_present(self):
        pdf = REPORTS / "plain_language_brief.pdf"
        png = REPORTS / "plain_language_brief.png"
        if pdf.exists():
            data = pdf.read_bytes()
            self.assertTrue(data.startswith(b"%PDF"))
            self.assertGreater(len(data), 20_000)
        if png.exists():
            self.assertGreater(png.stat().st_size, 20_000)


if __name__ == "__main__":
    unittest.main()
