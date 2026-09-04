"""Extract metric-relevant PDF tables with page-level visual evidence.

The output is deliberately an evidence archive, not an automatic source of
ranking inputs. Every extracted table remains ``pending_human_review`` until a
reviewer confirms the metric definition, scope, unit and reporting period.
"""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re

from dotenv import load_dotenv
from pypdf import PdfReader

try:
    import pdfplumber
except ImportError as exc:  # pragma: no cover - dependency error is actionable
    raise RuntimeError("Install PDF dependencies with: pip install pdfplumber pypdfium2") from exc

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = BASE_DIR / "reports"
DEFAULT_OUTPUT_PATH = BASE_DIR / "table_evidence_index.json"
DEFAULT_IMAGE_DIR = BASE_DIR / "evidence" / "table_images"

# These patterns identify candidate pages and tables. They do not extract a
# financial value on their own; a reviewer must still validate the evidence.
METRIC_PATTERNS = {
    "cet1_ratio": r"\b(?:CET\s*1|common equity tier\s*1)\b",
    "total_capital_ratio": r"\btotal capital ratio\b",
    "leverage_ratio": r"\bleverage ratio\b",
    "lcr": r"\b(?:LCR|liquidity coverage ratio)\b",
    "nsfr": r"\b(?:NSFR|net stable funding ratio)\b",
    "npl_ratio": r"\b(?:NPL|non[- ]performing loans?|non[- ]performing exposures?)\b",
    "npl_coverage": r"\b(?:NPL|non[- ]performing).{0,35}\bcoverage\b",
    "cost_of_risk": r"\bcost of risk\b",
    "net_interest_margin": r"\b(?:NIM|net interest margin)\b",
    "cost_income_ratio": r"\bcost[- ]to[- ]income(?: ratio)?\b",
    "roe": r"\b(?:ROE|return on equity)\b",
    "rote": r"\b(?:RoTE|return on tangible equity)\b",
    "loan_deposit_ratio": r"\b(?:loan[- ]to[- ]deposit|loans[- ]to[- ]deposits)\b",
    "stage_3_ratio": r"\bstage\s*3(?: ratio)?\b",
    "price_to_book": r"\b(?:price[- ]to[- ]book|P\s*/\s*B)\b",
    "book_value_per_share": r"\b(?:tangible )?book value per share\b",
    "earnings_per_share": r"\b(?:earnings per share|EPS)\b",
    "dividend_per_share": r"\b(?:dividend per share|DPS)\b",
    "payout_ratio": r"\bpayout ratio\b",
}
COMPILED_PATTERNS = {
    name: re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    for name, pattern in METRIC_PATTERNS.items()
}
EXCLUDED_CONTEXT = re.compile(
    r"\b(?:remuneration|variable compensation|compensation awarded|executive compensation)\b",
    flags=re.IGNORECASE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_cell(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\x00", " ").split())


def clean_grid(rows: list[list]) -> list[list[str]]:
    cleaned = [[clean_cell(cell) for cell in row] for row in rows if row]
    cleaned = [row for row in cleaned if any(row)]
    if not cleaned:
        return []
    width = max(len(row) for row in cleaned)
    return [row + [""] * (width - len(row)) for row in cleaned]


def unique_headers(first_row: list[str]) -> list[str]:
    seen = {}
    headers = []
    for index, value in enumerate(first_row, start=1):
        base = value or f"column_{index}"
        seen[base] = seen.get(base, 0) + 1
        headers.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return headers


def structured_rows(grid: list[list[str]]) -> tuple[list[str], list[dict]]:
    if not grid:
        return [], []
    headers = unique_headers(grid[0])
    return headers, [dict(zip(headers, row)) for row in grid[1:]]


def is_structured_table(grid: list[list[str]], bbox, page) -> bool:
    """Reject chart/slide regions that PDF line detection mistakes for tables."""
    if len(grid) < 3 or max(len(row) for row in grid) < 2:
        return False
    populated_cells = [cell for row in grid for cell in row if cell]
    if len(populated_cells) < 4 or max(map(len, populated_cells)) > 500:
        return False
    x0, top, x1, bottom = bbox
    coverage = ((x1 - x0) * (bottom - top)) / (page.width * page.height)
    if coverage > 0.92 and len(grid) <= 3:
        return False
    return True


def matched_metrics(text: str) -> list[str]:
    return [name for name, pattern in COMPILED_PATTERNS.items() if pattern.search(text)]


def excerpt_for_metrics(page_text: str, metrics: list[str], radius: int = 220) -> str:
    for metric in metrics:
        match = COMPILED_PATTERNS[metric].search(page_text)
        if match:
            start = max(0, match.start() - radius)
            end = min(len(page_text), match.end() + radius)
            return " ".join(page_text[start:end].split())
    return " ".join(page_text[: radius * 2].split())


def load_manifest() -> dict[str, dict]:
    path = BASE_DIR / "download_manifest.json"
    if not path.exists():
        return {}
    return {row["ticker"]: row for row in json.loads(path.read_text(encoding="utf-8"))}


def render_table_evidence(page, bbox, destination: Path, resolution: int = 144) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    x0, top, x1, bottom = bbox
    margin = 8
    crop = (
        max(0, x0 - margin),
        max(0, top - margin),
        min(page.width, x1 + margin),
        min(page.height, bottom + margin),
    )
    page.crop(crop).to_image(resolution=resolution, antialias=True).save(destination)


def extract_document(path: Path, image_root: Path, render_images: bool = True) -> dict:
    ticker = path.parent.name
    manifest = load_manifest().get(ticker, {})
    fast_reader = PdfReader(str(path))
    print(f"Processing {ticker}: {path.name} ({len(fast_reader.pages)} pages)", flush=True)
    document_record = {
        "ticker": ticker,
        "bank_name": manifest.get("bank_name"),
        "document": path.name,
        "source_url": manifest.get("url"),
        "sha256": sha256(path),
        "page_count": len(fast_reader.pages),
        "candidate_page_count": 0,
        "scanned_or_image_only_pages": 0,
        "rejected_layout_regions": 0,
        "table_count": 0,
        "tables": [],
    }

    with pdfplumber.open(str(path)) as pdf:
        for page_number, fast_page in enumerate(fast_reader.pages, start=1):
            # pypdf is materially faster for the initial keyword screen. The
            # layout-aware parser is invoked only for candidate pages.
            page_text = fast_page.extract_text() or ""
            if not page_text.strip():
                document_record["scanned_or_image_only_pages"] += 1
                continue
            if not matched_metrics(page_text):
                continue
            document_record["candidate_page_count"] += 1
            page = pdf.pages[page_number - 1]
            try:
                found_tables = page.find_tables()
            except Exception as exc:  # malformed pages should not abort a batch
                document_record.setdefault("warnings", []).append(
                    {"page": page_number, "message": f"table detection failed: {exc}"}
                )
                continue

            for table_number, table in enumerate(found_tables, start=1):
                grid = clean_grid(table.extract() or [])
                if not is_structured_table(grid, table.bbox, page):
                    document_record["rejected_layout_regions"] += 1
                    continue
                table_text = " ".join(cell for row in grid for cell in row if cell)
                table_metrics = matched_metrics(table_text)
                if not table_metrics:
                    continue
                # EPS is also a common label inside executive-pay scorecards.
                # Those tables are governance evidence, not bank valuation data.
                if table_metrics == ["earnings_per_share"] and EXCLUDED_CONTEXT.search(table_text):
                    document_record["rejected_layout_regions"] += 1
                    continue

                evidence_seed = f"{document_record['sha256']}:{page_number}:{table_number}:{table.bbox}"
                evidence_id = hashlib.sha1(evidence_seed.encode("utf-8")).hexdigest()[:16]
                relative_image = (
                    Path("evidence")
                    / "table_images"
                    / ticker
                    / f"{path.stem}_p{page_number:04d}_t{table_number:02d}.png"
                )
                image_path = image_root / ticker / relative_image.name
                render_error = None
                if render_images and not image_path.exists():
                    try:
                        render_table_evidence(page, table.bbox, image_path)
                    except Exception as exc:
                        render_error = str(exc)

                headers, records = structured_rows(grid)
                record = {
                    "evidence_id": evidence_id,
                    "ticker": ticker,
                    "bank_name": manifest.get("bank_name"),
                    "document": path.name,
                    "source_url": manifest.get("url"),
                    "page": page_number,
                    "table_number": table_number,
                    "bbox": [round(float(value), 2) for value in table.bbox],
                    "matched_metrics": table_metrics,
                    "headers": headers,
                    "rows": records,
                    "raw_grid": grid,
                    "page_excerpt": excerpt_for_metrics(page_text, table_metrics),
                    "evidence_image": (
                        image_path.relative_to(BASE_DIR).as_posix()
                        if render_images and not render_error and image_path.is_relative_to(BASE_DIR)
                        else str(image_path) if render_images and not render_error else None
                    ),
                    "extraction_method": "pdfplumber_table",
                    "confidence": "candidate",
                    "validation_status": "pending_human_review",
                }
                if render_error:
                    record["render_warning"] = render_error
                document_record["tables"].append(record)

    document_record["table_count"] = len(document_record["tables"])
    print(
        f"Completed {ticker}: {document_record['candidate_page_count']} candidate page(s), "
        f"{document_record['table_count']} retained table(s)",
        flush=True,
    )
    return document_record


def ingest_directory(
    reports_dir: Path,
    output_path: Path,
    image_root: Path,
    ticker_filter: set[str] | None = None,
    render_images: bool = True,
) -> dict:
    paths = sorted(reports_dir.rglob("*.pdf"))
    if ticker_filter:
        paths = [path for path in paths if path.parent.name.upper() in ticker_filter]
    documents = [extract_document(path, image_root, render_images) for path in paths]
    archive = {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "purpose": "Candidate table evidence; not approved ranking inputs",
        "source_count": len(documents),
        "table_count": sum(document["table_count"] for document in documents),
        "documents": documents,
    }
    output_path.write_text(json.dumps(archive, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"Ingested {archive['source_count']} PDF(s); found "
        f"{archive['table_count']} metric-relevant table(s)."
    )
    print(f"Evidence index: {output_path}")
    if render_images:
        print(f"Evidence images: {image_root}")
    return archive


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--image-dir", type=Path, default=DEFAULT_IMAGE_DIR)
    parser.add_argument(
        "--ticker",
        action="append",
        help="Process only this ticker. Repeat the option for multiple banks.",
    )
    parser.add_argument("--no-images", action="store_true", help="Skip evidence PNG rendering.")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    ingest_directory(
        arguments.reports_dir.resolve(),
        arguments.output.resolve(),
        arguments.image_dir.resolve(),
        {ticker.upper() for ticker in arguments.ticker} if arguments.ticker else None,
        render_images=not arguments.no_images,
    )
