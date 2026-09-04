"""Build auditable management-language signals from official bank PDFs.

This module intentionally keeps language and quantitative scores separate.
Signals are provisional until comparable history and an out-of-sample backtest
exist. The LLM is not used as an untraceable sentiment judge; every feature is
deterministic and every displayed observation retains its source page.
"""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re

from dotenv import load_dotenv
from pypdf import PdfReader

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = BASE_DIR / "reports"
DEFAULT_OUTPUT = BASE_DIR / "language_signals.json"
RULE_VERSION = "management-language-v1.0"

LEXICONS = {
    "positive": {
        "strong", "stronger", "robust", "resilient", "solid", "improved",
        "improving", "growth", "successful", "attractive", "outperform",
        "progress", "momentum", "confident", "confidence",
    },
    "negative": {
        "challenging", "headwind", "headwinds", "deterioration", "deteriorated",
        "pressure", "pressures", "adverse", "decline", "declined", "weak",
        "weaker", "downturn", "stress", "stressed",
    },
    "uncertainty": {
        "uncertain", "uncertainty", "volatile", "volatility", "potentially",
        "approximately", "depending", "subject", "risk", "risks",
    },
    "strong_modal": {
        "will", "must", "committed", "commit", "commits", "expect", "expects",
        "target", "targets",
    },
    "weak_modal": {
        "may", "might", "could", "would", "aim", "aims", "intend", "intends",
        "seek", "seeks", "consider", "expects approximately",
    },
    "caution_buffer": {
        "normalisation", "normalization", "prudent", "prudently", "one-off",
        "temporary", "temporarily", "selective", "disciplined", "resilient",
    },
    "confidence": {
        "momentum", "capital return", "share buyback", "buyback", "confident",
        "confidence", "strong", "robust", "solid",
    },
}

NARRATIVE_TERMS = re.compile(
    r"\b(?:outlook|guidance|expect|target|strategy|strategic|ambition|priority|"
    r"momentum|profitability|headwind|challenge|capital return|distribution|"
    r"dividend|buyback|management|we will|we aim|committed to|confident|"
    r"strong results|strong financial position|robust performance|"
    r"resilient performance)\b",
    flags=re.IGNORECASE,
)
EXCLUDED_CONTEXT = re.compile(
    r"\b(?:remuneration report|compensation report|accounting polic(?:y|ies)|"
    r"notes to the consolidated financial statements|auditor.?s report|"
    r"variable compensation|executive compensation|remuneration|"
    r"committed to compliance|applicable laws and regulations|"
    r"sustainable finance|sustainability|climate change|ESG risk|"
    r"described in the management report|glossary|table of contents)\b",
    flags=re.IGNORECASE,
)
GUIDANCE_TERMS = re.compile(
    r"\b(?:outlook|guidance|target|expect|forecast|ambition|objective|we will|"
    r"we aim|committed to)\b",
    flags=re.IGNORECASE,
)
ANNUAL_MANAGEMENT_SECTION = re.compile(
    r"\b(?:letter from|chief executive|ceo|management report|group performance|"
    r"financial performance|business review|strategic priorities|strategy|"
    r"outlook|targets and ambitions|financial objectives|results)\b",
    flags=re.IGNORECASE,
)
WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]*\b")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ").replace("\u00ad", "")
    return " ".join(text.split())


def split_sentences(text: str) -> list[str]:
    clean = clean_text(text)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", clean)
    # Investor presentations frequently use bullet fragments without terminal
    # punctuation. Preserve those management statements as auditable passages
    # instead of silently treating a slide as empty.
    bullet_blocks = re.split(r"\n\s*(?:[•▪◼�]|[-–—]\s+)", text)
    candidates = sentences + [clean_text(block) for block in bullet_blocks]
    unique = []
    seen = set()
    for sentence in candidates:
        if 40 <= len(sentence) <= 600 and sentence not in seen:
            seen.add(sentence)
            unique.append(sentence)
    return unique


def phrase_count(text: str, phrase: str) -> int:
    return len(re.findall(rf"\b{re.escape(phrase)}\b", text, flags=re.IGNORECASE))


def category_hits(text: str) -> dict[str, int]:
    return {
        category: sum(phrase_count(text, phrase) for phrase in phrases)
        for category, phrases in LEXICONS.items()
    }


def relevant_sentence(sentence: str) -> bool:
    if EXCLUDED_CONTEXT.search(sentence):
        return False
    # Requiring the narrative trigger in the same sentence prevents a single
    # word such as "performance" in a page heading from pulling an entire
    # accounting, regulatory or risk page into the language sample.
    return bool(NARRATIVE_TERMS.search(sentence))


def evidence_priority(record: dict) -> tuple[int, int, int]:
    hits = record["hits"]
    divergence_terms = hits["negative"] + hits["uncertainty"] + hits["weak_modal"]
    guidance = 1 if record["is_guidance"] else 0
    total = sum(hits.values())
    return guidance, divergence_terms, total


def score_features(counts: dict[str, int], word_count: int) -> dict:
    positive = counts["positive"]
    negative = counts["negative"]
    strong = counts["strong_modal"]
    weak = counts["weak_modal"]
    uncertainty = counts["uncertainty"]
    caution = counts["caution_buffer"]
    confidence = counts["confidence"]

    tone_balance = (positive - negative) / max(positive + negative, 1)
    commitment_balance = (strong - weak) / max(strong + weak, 1)
    uncertainty_rate = 1000 * uncertainty / max(word_count, 1)
    caution_rate = 1000 * caution / max(word_count, 1)
    confidence_rate = 1000 * confidence / max(word_count, 1)

    # Transparent bounded heuristic for the MVP. It is not publication-eligible
    # until its coefficients and thresholds pass a pre-registered backtest.
    raw_score = (
        50
        + 20 * tone_balance
        + 12 * commitment_balance
        + min(confidence_rate, 8)
        - min(uncertainty_rate * 1.5, 12)
        - min(caution_rate, 8)
    )
    language_score = round(max(0, min(100, raw_score)), 1)
    return {
        "language_score": language_score,
        "tone_balance": round(tone_balance, 4),
        "commitment_balance": round(commitment_balance, 4),
        "uncertainty_per_1000_words": round(uncertainty_rate, 2),
        "caution_per_1000_words": round(caution_rate, 2),
        "confidence_per_1000_words": round(confidence_rate, 2),
    }


def infer_document_metadata(path: Path) -> tuple[str, str]:
    name = path.stem.lower()
    year_match = re.search(r"20\d{2}", name)
    year = year_match.group(0) if year_match else "unknown"
    if "annual" in name:
        return "annual_report", f"FY{year}"
    if "h1" in name or "half" in name:
        return "half_year_results", f"H1 {year}"
    if "q1" in name or "q2" in name or "q3" in name or "q4" in name:
        quarter = re.search(r"q[1-4]", name).group(0).upper()
        return "quarterly_results", f"{quarter} {year}"
    return "unclassified", year


def page_is_eligible(page_text: str, document_type: str) -> bool:
    if document_type == "annual_report":
        # Annual reports contain hundreds of pages of mandatory risk,
        # accounting and Pillar 3 language. Only management-facing sections
        # are admitted to the language sample in v1.
        return bool(ANNUAL_MANAGEMENT_SECTION.search(page_text[:700]))
    return document_type in {"half_year_results", "quarterly_results"}


def analyze_pdf(path: Path, source: dict) -> dict:
    ticker = source["ticker"]
    inferred_type, inferred_period = infer_document_metadata(path)
    document_type = source.get("document_type", inferred_type)
    period = source.get("period", inferred_period)
    evidence = []
    counts = {category: 0 for category in LEXICONS}
    word_count = 0
    page_count = 0

    reader = PdfReader(str(path))
    print(f"Analyzing {ticker}: {path.name} ({len(reader.pages)} pages)", flush=True)
    for page_number, page in enumerate(reader.pages, start=1):
        page_count += 1
        page_text = clean_text(page.extract_text() or "")
        if not page_text or not page_is_eligible(page_text, document_type):
            continue
        for sentence in split_sentences(page_text):
            if not relevant_sentence(sentence):
                continue
            hits = category_hits(sentence)
            words = WORD_RE.findall(sentence)
            if not words:
                continue
            word_count += len(words)
            for category, value in hits.items():
                counts[category] += value
            if any(hits.values()) or GUIDANCE_TERMS.search(sentence):
                evidence.append(
                    {
                        "page": page_number,
                        "sentence": sentence[:500],
                        "is_guidance": bool(GUIDANCE_TERMS.search(sentence)),
                        "hits": hits,
                        "review_status": "pending_human_review",
                    }
                )

    features = score_features(counts, word_count)
    evidence.sort(key=evidence_priority, reverse=True)
    selected_evidence = evidence[:8]
    minimum_coverage = word_count >= 150 and len(selected_evidence) >= 3
    record = {
        "ticker": ticker,
        "bank_name": source.get("bank_name"),
        "document": path.name,
        "document_type": document_type,
        "period": period,
        "publication_date": None,
        "source_url": source.get("download_url"),
        "official_page": source.get("official_page"),
        "document_sha256": sha256(path),
        "page_count": page_count,
        "analyzed_word_count": word_count,
        "feature_counts": counts,
        "features": features,
        "evidence": selected_evidence,
        "status": "provisional_single_period" if minimum_coverage else "insufficient",
        "history_periods": 1,
        "language_drift_score": None,
        "backtest_status": "not_run",
        "publication_eligible": False,
        "comparability_warning": (
            "Single-period and mixed document genres; do not interpret as a trading signal."
        ),
    }
    print(
        f"Completed {ticker}: {word_count:,} narrative words, "
        f"status={record['status']}",
        flush=True,
    )
    return record


def load_language_manifest() -> list[dict]:
    path = BASE_DIR / "language_download_manifest.json"
    if not path.exists():
        raise FileNotFoundError(
            "language_download_manifest.json is missing; run "
            "download_language_reports.py first."
        )
    return [
        record
        for record in json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") == "downloaded"
    ]


def load_universe() -> list[dict]:
    path = BASE_DIR / "bank_master.json"
    return json.loads(path.read_text(encoding="utf-8"))["constituents"]


def load_numeric_scores() -> dict[str, float]:
    path = BASE_DIR / "full_universe_scores.json"
    return {
        record["ticker"]: record["score"]
        for record in json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") == "ranked"
    }


def quadrant(numeric_score: float, language_score: float) -> str:
    if numeric_score >= 50 and language_score >= 50:
        return "Confirmed strength"
    if numeric_score < 50 <= language_score:
        return "Potential turnaround"
    if numeric_score >= 50 > language_score:
        return "Early warning"
    return "High-risk screen"


def build_archive(reports_dir: Path, output_path: Path) -> dict:
    manifest = load_language_manifest()
    numeric_scores = load_numeric_scores()
    analyzed = {}
    for source in manifest:
        path = Path(source["path"])
        if not path.is_absolute():
            path = reports_dir / source["ticker"] / path.name
        if not path.exists():
            print(f"Skipping missing curated report: {path}", flush=True)
            continue
        analyzed[source["ticker"]] = analyze_pdf(path, source)
    signals = []
    for bank in load_universe():
        ticker = bank["ticker"]
        numeric_score = numeric_scores.get(ticker)
        language = analyzed.get(ticker)
        if not language or language["status"] == "insufficient":
            signals.append(
                {
                    "ticker": ticker,
                    "bank_name": bank["bank_name"],
                    "numeric_score": numeric_score,
                    "language_score": None,
                    "language_drift_score": None,
                    "divergence": None,
                    "quadrant": None,
                    "status": "insufficient_language_data",
                    "alerts": [],
                    "publication_eligible": False,
                }
            )
            continue
        language_score = language["features"]["language_score"]
        divergence = round(numeric_score - language_score, 1) if numeric_score is not None else None
        alerts = []
        if divergence is not None and abs(divergence) >= 20:
            alerts.append(
                {
                    "type": "numeric_language_divergence",
                    "severity": "research_review",
                    "message": f"Numeric-language gap reached {divergence:+.1f} points.",
                    "review_status": "pending_human_review",
                }
            )
        signals.append(
            {
                "ticker": ticker,
                "bank_name": bank["bank_name"],
                "numeric_score": numeric_score,
                "language_score": language_score,
                "language_drift_score": None,
                "divergence": divergence,
                "quadrant": quadrant(numeric_score, language_score),
                "status": "provisional_single_period",
                "alerts": alerts,
                "publication_eligible": False,
            }
        )

    archive = {
        "schema_version": "1.0",
        "rule_version": RULE_VERSION,
        "generated_at": utc_now(),
        "methodology": {
            "axes_are_independent": True,
            "language_model": "deterministic_financial_lexicon",
            "minimum_history_for_preliminary_trend": 4,
            "minimum_history_for_drift_alerts": 8,
            "publication_gate": "backtest_and_human_review_required",
            "labels_are_research_screens_not_investment_recommendations": True,
        },
        "coverage": {
            "universe_banks": len(signals),
            "provisional_banks": sum(s["status"] == "provisional_single_period" for s in signals),
            "insufficient_banks": sum(s["status"] == "insufficient_language_data" for s in signals),
        },
        "documents": list(analyzed.values()),
        "signals": signals,
    }
    output_path.write_text(json.dumps(archive, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"Wrote {output_path}: {archive['coverage']['provisional_banks']} provisional, "
        f"{archive['coverage']['insufficient_banks']} insufficient."
    )
    return archive


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    build_archive(arguments.reports_dir.resolve(), arguments.output.resolve())
