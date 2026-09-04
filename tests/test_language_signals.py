"""Unit tests for deterministic management-language signal rules."""

from pathlib import Path
import sys
import unittest

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.language_signals import category_hits, quadrant, score_features


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


if __name__ == "__main__":
    unittest.main()
