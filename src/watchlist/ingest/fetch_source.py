"""Explicit network command for the approved OpenSanctions UN-only export."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DATASET = "un_sc_sanctions"
BASE_URL = f"https://data.opensanctions.org/datasets/latest/{DATASET}"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc/4.0/"
MAX_EXPORT_BYTES = 10 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024


def read_bounded(url: str, limit: int) -> bytes:
    """Read an HTTPS response within a hard byte cap, including unknown lengths."""
    request = Request(url, headers={"User-Agent": "PolyglotWatchlistResearch/0.2"})
    with urlopen(request, timeout=30) as response:
        final_url = urlparse(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != "data.opensanctions.org":
            raise ValueError("unexpected download destination")
        length = response.headers.get("Content-Length")
        if length is not None and int(length) > limit:
            raise ValueError("download exceeds approved byte limit")
        chunks: list[bytes] = []
        received = 0
        while chunk := response.read(min(65536, limit - received + 1)):
            received += len(chunk)
            if received > limit:
                raise ValueError("download exceeds approved byte limit")
            chunks.append(chunk)
    return b"".join(chunks)


def fetch_snapshot(output_root: Path, max_bytes: int = MAX_EXPORT_BYTES) -> dict:
    """Fetch once, verify metadata checksum when supplied, and save a receipt.

    Refuse existing outputs: a new acquisition must not silently overwrite the
    frozen bytes used in a previous experiment. No data is fetched on import.
    """
    if not 0 < max_bytes <= MAX_EXPORT_BYTES:
        raise ValueError("max_bytes must be between 1 and 10485760")
    raw_dir = output_root / "raw" / DATASET
    export_path = raw_dir / "entities.ftm.json"
    metadata_path = raw_dir / "index.json"
    receipt_path = output_root / "manifests" / "source.json"
    if any(path.exists() for path in (export_path, metadata_path, receipt_path)):
        raise ValueError("snapshot outputs already exist; reuse the saved snapshot")
    metadata_bytes = read_bounded(f"{BASE_URL}/index.json", MAX_METADATA_BYTES)
    metadata = json.loads(metadata_bytes)
    if not isinstance(metadata, dict) or metadata.get("name") != DATASET:
        raise ValueError("metadata does not identify the approved UN dataset")
    export_bytes = read_bounded(f"{BASE_URL}/entities.ftm.json", max_bytes)
    resources = metadata.get("resources", [])
    resource = next(
        (item for item in resources if item.get("name") == "entities.ftm.json"), {}
    )
    expected_sha1 = resource.get("checksum")
    if expected_sha1 and hashlib.sha1(export_bytes).hexdigest() != expected_sha1:
        raise ValueError("export does not match metadata checksum; snapshot changed")
    receipt = {
        "dataset": DATASET,
        "provider": "OpenSanctions",
        "publisher": "United Nations Security Council",
        "source_url": f"https://www.opensanctions.org/datasets/{DATASET}/",
        "download_url": f"{BASE_URL}/entities.ftm.json",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "raw_sha256": hashlib.sha256(export_bytes).hexdigest(),
        "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "bytes": len(export_bytes),
        "metadata_bytes": len(metadata_bytes),
        "license": "CC-BY-NC-4.0",
        "license_url": LICENSE_URL,
        "synthetic": False,
        "attribution": (
            "OpenSanctions, UN Security Council Consolidated Sanctions; "
            "upstream publisher: United Nations Security Council. "
            "CC BY-NC 4.0. Filtered and converted for non-commercial research. "
            "No endorsement; data supplied without warranties."
        ),
    }
    raw_dir.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_bytes(export_bytes)
    metadata_path.write_bytes(metadata_bytes)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=[DATASET], default=DATASET)
    parser.add_argument("--max-bytes", type=int, default=MAX_EXPORT_BYTES)
    parser.add_argument("--output-root", type=Path, default=Path("data"))
    args = parser.parse_args()
    try:
        receipt = fetch_snapshot(args.output_root, args.max_bytes)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
