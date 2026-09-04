"""Download the curated management-language report set with PDF validation."""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCES = BASE_DIR / "language_report_sources.json"
DEFAULT_REPORTS = BASE_DIR / "reports"
DEFAULT_MANIFEST = BASE_DIR / "language_download_manifest.json"
MAX_BYTES = 30 * 1024 * 1024
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def portable_path(path: Path) -> str:
    """Store paths relative to the repository when possible."""
    try:
        return path.resolve().relative_to(BASE_DIR).as_posix()
    except ValueError:
        return str(path.resolve())


def download(source: dict, reports_dir: Path, timeout: int) -> dict:
    target_dir = reports_dir / source["ticker"]
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source["filename"]
    result = {**source, "checked_at": datetime.now(timezone.utc).isoformat()}
    try:
        if target.exists():
            content = target.read_bytes()
            if content.lstrip().startswith(b"%PDF") and len(content) <= MAX_BYTES:
                result.update(
                    status="downloaded",
                    path=portable_path(target),
                    final_url=source["download_url"],
                    bytes=len(content),
                    sha256=sha256_bytes(content),
                    cache_hit=True,
                )
                print(f"{source['ticker']}: downloaded (cached)", flush=True)
                return result
        response = requests.get(
            source["download_url"],
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": BROWSER_USER_AGENT,
                "Referer": source["official_page"],
            },
            verify=source.get("verify_ssl", True),
        )
        response.raise_for_status()
        content = response.content
        if len(content) > MAX_BYTES:
            raise ValueError(f"file exceeds {MAX_BYTES // 1024 // 1024} MB limit")
        if not content.lstrip().startswith(b"%PDF"):
            kind = response.headers.get("content-type", "unknown")
            raise ValueError(f"response is not a PDF (content-type={kind})")
        target.write_bytes(content)
        result.update(
            status="downloaded",
            path=portable_path(target),
            final_url=response.url,
            bytes=len(content),
            sha256=sha256_bytes(content),
        )
    except Exception as exc:  # keep the batch running and make failure auditable
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    print(f"{source['ticker']}: {result['status']}", flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    payload = json.loads(args.sources.read_text(encoding="utf-8"))
    records = []
    for source in payload["sources"]:
        records.append(download(source, args.reports_dir, args.timeout))
        # Checkpoint after every bank so a network interruption never discards
        # the audit trail for the reports already processed.
        args.manifest.write_text(
            json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    succeeded = sum(record["status"] == "downloaded" for record in records)
    print(f"Wrote {args.manifest}: {succeeded}/{len(records)} downloaded.")


if __name__ == "__main__":
    main()
