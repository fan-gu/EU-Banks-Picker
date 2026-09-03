"""Production-oriented PDF ingestion with page-level provenance.

Text and tables are extracted when available. Images are catalogued for a
future OCR/vision stage rather than being mistaken for extracted facts.
"""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

from dotenv import load_dotenv
from pypdf import PdfReader

try:
    import pdfplumber
except ImportError:  # pragma: no cover - optional dependency
    pdfplumber = None

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_pdf(path: Path) -> dict:
    reader = PdfReader(str(path))
    pages = []
    with_plumber = pdfplumber is not None
    plumber_pdf = pdfplumber.open(str(path)) if with_plumber else None
    try:
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            tables = []
            if plumber_pdf is not None:
                tables = plumber_pdf.pages[number - 1].extract_tables() or []
            pages.append(
                {
                    "page": number,
                    "text": text,
                    "tables": tables,
                    "has_text": bool(text.strip()),
                    "table_count": len(tables),
                    "image_analysis": "not_run",
                }
            )
    finally:
        if plumber_pdf is not None:
            plumber_pdf.close()

    return {
        "document": path.name,
        "source_path": str(path),
        "sha256": sha256(path),
        "page_count": len(pages),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "extractor": {"pypdf": True, "pdfplumber": with_plumber, "ocr": False},
        "pages": pages,
    }


def ingest_directory(reports_dir: Path, output_path: Path) -> None:
    records = [extract_pdf(path) for path in sorted(reports_dir.rglob("*.pdf"))]
    output_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Ingested {len(records)} PDF(s) into {output_path}")


if __name__ == "__main__":
    ingest_directory(BASE_DIR / "reports", BASE_DIR / "production_pdf_archive.json")
