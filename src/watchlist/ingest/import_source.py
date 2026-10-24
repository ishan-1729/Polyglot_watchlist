"""Import an approved saved snapshot, or an authored fixture, without networking."""

import argparse
from dataclasses import asdict, dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sqlite3
import stat

from watchlist.database import write_snapshot
from watchlist.entities import Provenance
from watchlist.ingest.fetch_source import DATASET, LICENSE_URL, MAX_EXPORT_BYTES, MAX_METADATA_BYTES
from watchlist.ingest.parse_opensanctions import PARSER_VERSION, ParsedEntity, parse_records


@dataclass(frozen=True)
class PreparedSnapshot:
    """Independently reconstructed snapshot from verified, retained input bytes."""

    provenance: Provenance
    records: list[ParsedEntity]
    receipt: dict
    selection: dict
    report: dict
    source_metadata: dict


def _read_saved_bytes(path: Path, limit: int, label: str) -> bytes:
    """Read one bounded regular file once and reject replacement during the read."""
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f'{label} must be an existing regular file')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(limit + 1)
        finished = os.fstat(stream.fileno())
    after = path.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    expected = tuple(getattr(before, field) for field in fields)
    if any(tuple(getattr(value, field) for field in fields) != expected for value in (opened, finished, after)):
        raise ValueError(f'{label} changed while being read')
    if len(raw) > limit:
        raise ValueError(f'{label} exceeds {limit} bytes')
    return raw


def _json_object(raw: bytes, label: str) -> dict:
    """Require unambiguous finite metadata, without executing provider content."""
    def unique(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'{label}: duplicate JSON key {key}')
            result[key] = value
        return result

    def nonfinite(value: str) -> None:
        raise ValueError(f'{label}: nonfinite JSON value {value}')

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError(f'{label}: nonfinite JSON value {value}')
        return parsed

    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite,
                           parse_float=finite_float)
    except RecursionError as exc:
        raise ValueError(f'{label}: JSON nesting limit exceeded') from exc
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object')
    return value


def _records_from_bytes(raw: bytes) -> list[dict]:
    """Apply the established JSON-lines reader rules to the already hashed buffer."""
    records: list[dict] = []
    for number, line in enumerate(io.StringIO(raw.decode('utf-8'), newline=None), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f'line {number}: invalid JSON') from exc
        except RecursionError as exc:
            raise ValueError(f'line {number}: JSON nesting limit exceeded') from exc
        if not isinstance(record, dict):
            raise ValueError(f'line {number}: record must be an object')
        records.append(record)
    return records


def prepare_snapshot(
    input_path: Path, metadata_path: Path, *, limit: int = 20,
    sample: bool = False, receipt_path: Path | None = None,
) -> PreparedSnapshot:
    """Verify supplied inputs and reconstruct the unchanged deterministic selection.

    Public imports require the acquisition receipt and its raw/metadata hashes.
    Sample mode uses an explicitly fictional metadata marker, never a public
    source masquerading as an authored fixture. Hashing and parsing use the same
    retained buffers, so a later file replacement cannot change the parsed rows.
    """
    if type(sample) is not bool:
        raise ValueError('sample must be an explicit boolean')
    raw_bytes = _read_saved_bytes(input_path, MAX_EXPORT_BYTES, 'source input')
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    metadata_bytes = _read_saved_bytes(metadata_path, MAX_METADATA_BYTES, 'metadata')
    metadata = _json_object(metadata_bytes, 'metadata')
    for key in ('last_change', 'version'):
        if metadata.get(key) is not None and not isinstance(metadata[key], str):
            raise ValueError(f'metadata {key} must be text or null')
    if sample:
        if metadata.get("synthetic") is not True or metadata.get("name") != "fictional-ftm-v1":
            raise ValueError("sample mode requires explicitly fictional fixture metadata")
        receipt = {
            "dataset": "fictional-ftm-v1", "provider": "Authored fictional fixture",
            "publisher": "Polyglot Watchlist learning project", "synthetic": True,
            "source_url": "local:tests/fixtures/opensanctions_synthetic.ftm.json",
            "download_url": "", "retrieved_at": "not applicable: authored offline fixture",
            "raw_sha256": raw_hash,
            "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
            "license": "authored-fictional-fixture", "license_url": "",
            "attribution": "Authored fictional examples; not OpenSanctions or UN records.",
        }
    else:
        if receipt_path is None:
            raise ValueError("public import requires a saved acquisition receipt")
        receipt = _json_object(_read_saved_bytes(receipt_path, MAX_METADATA_BYTES, 'acquisition receipt'),
                               'acquisition receipt')
        if (metadata.get("name") != DATASET or receipt.get("dataset") != DATASET
            or receipt.get("synthetic") is not False or receipt.get("license_url") != LICENSE_URL):
            raise ValueError("metadata or receipt does not describe the approved source")
        if receipt.get("raw_sha256") != raw_hash:
            raise ValueError("source checksum differs from acquisition receipt")
        if receipt.get("metadata_sha256") != hashlib.sha256(metadata_bytes).hexdigest():
            raise ValueError("metadata checksum differs from acquisition receipt")
        for key, size in (('bytes', len(raw_bytes)), ('metadata_bytes', len(metadata_bytes))):
            if key in receipt and (type(receipt[key]) is not int or receipt[key] != size):
                raise ValueError(f'acquisition receipt {key} differs from supplied input')
    for key in ('dataset', 'provider', 'publisher', 'source_url', 'download_url', 'retrieved_at', 'license_url'):
        if not isinstance(receipt.get(key), str) or (key not in ('download_url', 'license_url') and not receipt[key].strip()):
            raise ValueError(f'acquisition receipt {key} must be text')
    try:
        records, report = parse_records(_records_from_bytes(raw_bytes), synthetic=sample, limit=limit)
    except RecursionError as exc:
        raise ValueError('source JSON nesting limit exceeded while parsing records') from exc
    if not records:
        raise ValueError("no usable non-person targets; no database import performed")
    selection = {"limit": limit, "order": "provider_id_ascending", "non_person_only": True}
    fingerprint = json.dumps(
        [raw_hash, PARSER_VERSION, selection, sample, receipt["metadata_sha256"]],
        sort_keys=True,
    ).encode("utf-8")
    snapshot_id = hashlib.sha256(fingerprint).hexdigest()
    provenance = Provenance(
        snapshot_id=snapshot_id, dataset=receipt["dataset"], provider=receipt["provider"],
        publisher=receipt["publisher"], source_url=receipt["source_url"],
        download_url=receipt["download_url"], retrieved_at=receipt["retrieved_at"],
        source_updated_at=metadata.get("last_change"), export_version=metadata.get("version"),
        raw_sha256=raw_hash, license_url=receipt["license_url"],
    )
    report["stored_aliases"] = sum(len(record.aliases) for record in records)
    report["searchable_aliases"] = sum(len(record.entity.aliases) for record in records)
    return PreparedSnapshot(provenance, records, receipt, selection, report, metadata)


def import_snapshot(
    input_path: Path, metadata_path: Path, db_path: Path, *, limit: int = 20,
    sample: bool = False, receipt_path: Path | None = None,
) -> dict:
    """Import verified inputs; an identical repeat changes no database or exports."""
    prepared = prepare_snapshot(input_path, metadata_path, limit=limit, sample=sample, receipt_path=receipt_path)
    provenance, records = prepared.provenance, prepared.records
    receipt, selection, report = prepared.receipt, prepared.selection, prepared.report
    created = write_snapshot(
        db_path, provenance, records, receipt=receipt, selection=selection, report=report,
        source_metadata=prepared.source_metadata,
    )
    # The database stores the authoritative import report in the same transaction.
    # These local files are readable exports, reproducible from the saved inputs.
    if created and not sample:
        root = db_path.parent
        (root / "samples").mkdir(parents=True, exist_ok=True)
        (root / "manifests").mkdir(parents=True, exist_ok=True)
        selected_text = "\n".join(raw for record in records for raw in record.raw_records) + "\n"
        (root / "samples/un-organisations.ftm.json").write_text(selected_text, encoding="utf-8")
        (root / "manifests/ingestion-report.json").write_text(
            json.dumps({"provenance": asdict(provenance), "selection": selection, **report},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    return {
        "created": created, "snapshot_id": provenance.snapshot_id,
        "input_records": report["input_records"], "eligible_entities": report["eligible_entities"],
        "selected_entities": len(records), "stored_aliases": report["stored_aliases"],
        "searchable_aliases": report["searchable_aliases"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="store_true", help="Use authored fixtures from this checkout")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--receipt", type=Path, default=Path("data/manifests/source.json"))
    parser.add_argument("--organisations-only", action="store_true", help="Non-person targets only (always enforced)")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    if args.sample and (args.input or args.metadata):
        parser.error("--sample cannot be combined with external input or metadata")
    if args.sample:
        input_path = Path("tests/fixtures/opensanctions_synthetic.ftm.json")
        metadata_path = Path("tests/fixtures/opensanctions_synthetic.metadata.json")
    elif args.input is None or args.metadata is None:
        parser.error("public mode requires --input and --metadata")
    else:
        input_path, metadata_path = args.input, args.metadata
    try:
        result = import_snapshot(input_path, metadata_path, args.db, limit=args.limit,
                                 sample=args.sample, receipt_path=args.receipt)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
