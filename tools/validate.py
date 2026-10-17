"""Validate every file under data/ against the schemas, plus sanity checks.

    uv run python -m tools.validate

Exits non-zero on any problem, so CI can block bad data.
"""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schema"

# Plausibility bounds. A value outside these is almost certainly a parsing bug,
# not a real product, so we fail rather than publish it.
ANNUAL_KWH_BOUNDS = {
    "room_ac": (50, 5000),
    "refrigerator": (20, 2500),
    "clothes_dryer": (20, 2500),
    "clothes_washer": (10, 1500),
    "dishwasher": (50, 1000),
}
PRICE_PER_KWH_BOUNDS = {"USD": (0.02, 1.50), "BRL": (0.10, 5.00)}
COMPONENT_MAX = {"BRL/MWh": 10000, "BRL/kW": 1000}


def load(name):
    return json.loads((SCHEMA / name).read_text())


def main():
    dataset_v = Draft202012Validator(load("dataset.schema.json"))
    record_v = {
        "product": Draft202012Validator(load("product.schema.json")),
        "tariff": Draft202012Validator(load("tariff.schema.json")),
        "tariff_component": Draft202012Validator(load("tariff_component.schema.json")),
    }
    categories = load("categories.json")
    errors = []

    files = sorted((ROOT / "data").rglob("*.json"))
    for path in files:
        rel = path.relative_to(ROOT)
        doc = json.loads(path.read_text())
        for e in dataset_v.iter_errors(doc):
            errors.append(f"{rel}: {e.message}")
        if errors and errors[-1].startswith(str(rel)):
            continue
        if f"data/{doc['dataset']}.json" != str(rel):
            errors.append(f"{rel}: dataset field '{doc['dataset']}' does not match path")
        if doc["count"] != len(doc["records"]):
            errors.append(f"{rel}: count {doc['count']} != {len(doc['records'])} records")
        country = doc["dataset"].split("/")[0].upper()

        for r in doc["records"]:
            rid = r.get("id", "?")
            for e in record_v[doc["kind"]].iter_errors(r):
                errors.append(f"{rel} [{rid}]: {e.message}")
            if r.get("country") != country:
                errors.append(f"{rel} [{rid}]: country {r.get('country')} != {country}")
            if doc["kind"] == "product":
                cat = r.get("category")
                if cat not in categories:
                    errors.append(f"{rel} [{rid}]: unknown category {cat}")
                lo, hi = ANNUAL_KWH_BOUNDS.get(cat, (0, float("inf")))
                kwh = r.get("annual_kwh")
                if kwh is not None and not lo <= kwh <= hi:
                    errors.append(f"{rel} [{rid}]: annual_kwh {kwh} outside {lo}-{hi}")
            elif doc["kind"] == "tariff_component":
                hi = COMPONENT_MAX.get(r.get("unit"), float("inf"))
                t = r.get("total")
                if t is not None and t > hi:
                    errors.append(f"{rel} [{rid}]: total {t} {r.get('unit')} above {hi}")
            else:
                lo, hi = PRICE_PER_KWH_BOUNDS.get(r.get("currency"), (0, float("inf")))
                p = r.get("price_per_kwh")
                if p is not None and not lo <= p <= hi:
                    errors.append(f"{rel} [{rid}]: price_per_kwh {p} outside {lo}-{hi}")

    for e in errors[:200]:
        print(e, file=sys.stderr)
    if len(errors) > 200:
        print(f"... and {len(errors) - 200} more", file=sys.stderr)
    print(f"{len(files)} files checked, {len(errors)} problems", file=sys.stderr)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
