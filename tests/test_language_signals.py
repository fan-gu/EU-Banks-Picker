"""Unit tests for deterministic management-language signal rules."""

from pathlib import Path
import json
import sys
import unittest

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.language_signals import category_hits, quadrant, score_features, split_sentences


class LanguageSignalTests(unittest.TestCase):
    def test_financial_language_categories_are_separate(self):
        hits = category_hits(
            "We will deliver strong capital return, although the outlook may remain challenging."
        )
        self.assertGreater(hits["positive"], 0)
        self.assertGreater(hits["negative"], 0)
        self.assertGreater(hits["strong_modal"], 0)
        self.assertGreater(hits["weak_modal"], 0)

    def test_more_certain_language_scores_higher(self):
        confident = {
            "positive": 8, "negative": 1, "uncertainty": 1,
            "strong_modal": 8, "weak_modal": 1, "caution_buffer": 1,
            "confidence": 6,
        }
        cautious = {
            "positive": 2, "negative": 5, "uncertainty": 8,
            "strong_modal": 1, "weak_modal": 8, "caution_buffer": 6,
            "confidence": 1,
        }
        self.assertGreater(
            score_features(confident, 1000)["language_score"],
            score_features(cautious, 1000)["language_score"],
        )

    def test_quadrants_preserve_two_axes(self):
        self.assertEqual(quadrant(70, 70), "Confirmed strength")
        self.assertEqual(quadrant(30, 70), "Potential turnaround")
        self.assertEqual(quadrant(70, 30), "Early warning")
        self.assertEqual(quadrant(30, 30), "High-risk screen")

    def test_bullet_fragments_are_preserved_as_passages(self):
        passages = split_sentences(
            "Q2 highlights\n"
            "- We remain confident and will deliver our capital target\n"
            "- The outlook may remain challenging because uncertainty is high"
        )
        self.assertTrue(any("remain confident" in item for item in passages))
        self.assertTrue(any("may remain challenging" in item for item in passages))


class LanguageCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = Path(__file__).resolve().parent.parent
        cls.sources = json.loads(
            (base_dir / "language_report_sources.json").read_text(encoding="utf-8")
        )["sources"]
        cls.manifest = json.loads(
            (base_dir / "language_download_manifest.json").read_text(encoding="utf-8")
        )
        cls.archive = json.loads(
            (base_dir / "language_signals.json").read_text(encoding="utf-8")
        )

    def test_curated_source_and_download_coverage_is_23_banks(self):
        self.assertEqual(len(self.sources), 23)
        self.assertEqual(len({row["ticker"] for row in self.sources}), 23)
        self.assertEqual(len(self.manifest), 23)
        self.assertTrue(all(row["status"] == "downloaded" for row in self.manifest))

    def test_signal_archive_has_auditable_provisional_coverage(self):
        self.assertEqual(self.archive["coverage"]["provisional_banks"], 23)
        self.assertEqual(self.archive["coverage"]["insufficient_banks"], 0)
        self.assertEqual(len(self.archive["documents"]), 23)
        self.assertTrue(
            all(len(row["evidence"]) >= 3 for row in self.archive["documents"])
        )
        self.assertTrue(
            all(row["publication_eligible"] is False for row in self.archive["signals"])
        )


if __name__ == "__main__":
    unittest.main()
