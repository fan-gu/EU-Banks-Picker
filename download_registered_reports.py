"""Download verified official PDFs for every bank in report_registry.json."""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

BASE_DIR = Path(__file__).resolve().parent
TIMEOUT = 30


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    registry_path = BASE_DIR / "report_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    results = []

    for record in registry:
        ticker = record["ticker"]
        url = record.get("download_url")
        item = {"ticker": ticker, "bank_name": record["bank_name"], "url": url, "checked_at": datetime.now(timezone.utc).isoformat()}
        if not url:
            item["status"] = "pending_official_url"
            results.append(item)
            continue

        folder = BASE_DIR / "reports" / ticker
        folder.mkdir(parents=True, exist_ok=True)
        filename = record.get("filename") or f"{ticker}_report.pdf"
        destination = folder / filename
        try:
            response = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "EU-Banks-Picker/1.0"})
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
                raise ValueError(f"unexpected content type: {content_type or 'unknown'}")
            destination.write_bytes(response.content)
            item.update({"status": "downloaded", "path": str(destination), "sha256": sha256(destination), "bytes": destination.stat().st_size})
        except Exception as exc:  # keep processing the remaining universe
            item["status"] = "download_failed"
            item["error"] = str(exc)
        results.append(item)
        print(f"{ticker}: {item['status']}")

    output = BASE_DIR / "download_manifest.json"
    output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
