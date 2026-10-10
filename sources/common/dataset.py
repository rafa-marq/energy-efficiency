"""Writing dataset files and parsing source values, shared by all country fetchers."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def num(value):
    """Parse a numeric source value; None if absent or not a number. Never guesses."""
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s == "" or s.upper() in ("N/A", "NA", "NONE"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def clean(value):
    """Strip a source string; None for empty / placeholder values."""
    if value is None:
        return None
    s = str(value).strip()
    return None if s == "" or s.upper() in ("N/A", "NA") else s


def write_dataset(dataset, kind, source, records):
    """Write data/<dataset>.json with a provenance envelope. Records are sorted by id
    so re-running a fetcher produces a minimal diff."""
    records = sorted(records, key=lambda r: r["id"])
    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{dataset}: duplicate record ids")
    out = {
        "dataset": dataset,
        "kind": kind,
        "source": source,
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "count": len(records),
        "records": records,
    }
    path = DATA_DIR / f"{dataset}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"  wrote {path.relative_to(DATA_DIR.parent)} ({len(records)} records)", file=sys.stderr)
    return path
