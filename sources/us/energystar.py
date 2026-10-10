"""US appliances from the EPA ENERGY STAR certified-products API (Socrata).

    uv run python -m sources.us.energystar            # all categories
    uv run python -m sources.us.energystar room_ac    # one category

Writes data/us/products/<category>.json. annual_kwh is the figure ENERGY STAR
publishes from the DOE test procedure; nothing is derived or estimated.

Optional: set SOCRATA_APP_TOKEN to raise the anonymous rate limit.
"""
import os
import sys

from sources.common.dataset import clean, num, write_dataset
from sources.common.http import get_json

BASE = "https://data.energystar.gov/resource/{rid}.json"
PAGE = 1000
KWH_BASIS = "US DOE test procedure, as published by ENERGY STAR"
LICENSE = "Public domain (US Government work)"

# category -> source dataset and field mapping. Field names verified against the
# live API; if ENERGY STAR renames a field, the fetcher fails loudly (see check_fields).
CATEGORIES = {
    "room_ac": {
        "rid": "5xn2-dv4h",
        "name": "ENERGY STAR Certified Room Air Conditioners",
        "kwh": "annual_energy_use_kwh_yr",
        "efficiency": ("combined_energy_efficiency_ratio_ceer", "CEER", "Btu/Wh"),
        "capacity": ("cooling_capacity_btu_hour", "Btu/h"),
        "attributes": ["type", "product_class", "variable_speed_compressor", "heating_mode",
                       "refrigerant_type", "percent_less_energy_use_than_us_federal_standard"],
    },
    "refrigerator": {
        "rid": "p5st-her9",
        "name": "ENERGY STAR Certified Residential Refrigerators",
        "kwh": "annual_energy_use_kwh_yr",
        "efficiency": None,
        "capacity": ("capacity_total_volume_ft3", "ft3"),
        "attributes": ["type", "product_class", "compact", "built_in", "ice_maker",
                       "us_federal_standard_kwh_yr", "percent_less_energy_use_than_us_federal_standard"],
    },
    "clothes_dryer": {
        "rid": "t9u7-4d2j",
        "name": "ENERGY STAR Certified Residential Clothes Dryers",
        "kwh": "estimated_annual_energy_use_kwh_yr",
        "efficiency": ("combined_energy_factor_cef", "CEF", "lb/kWh"),
        "capacity": ("drum_capacity_cu_ft", "ft3"),
        # type = Electric / Gas. For gas dryers annual_kwh excludes gas use.
        "attributes": ["type", "product_type", "vented_or_ventless"],
    },
    "clothes_washer": {
        "rid": "bghd-e2wd",
        "name": "ENERGY STAR Certified Residential Clothes Washers",
        "kwh": "annual_energy_use_kwh_year",
        "efficiency": ("integrated_modified_energy_factor_imef", "IMEF", "ft3/kWh/cycle"),
        "capacity": ("volume_cubic_feet", "ft3"),
        "attributes": ["load_configuration", "intended_market", "us_federal_standard_imef",
                       "annual_water_use_gallons_year"],
    },
    "dishwasher": {
        "rid": "q8py-6w3f",
        "name": "ENERGY STAR Certified Residential Dishwashers",
        "kwh": "annual_energy_use_kwh_year",
        "efficiency": None,
        "capacity": ("capacity_maximum_number_of_place_settings", "place settings"),
        "attributes": ["type", "us_federal_standard_kwh_year", "water_use_gallons_cycle"],
    },
}


def fetch_all(rid):
    token = os.environ.get("SOCRATA_APP_TOKEN")
    rows, offset = [], 0
    while True:
        params = {"$limit": PAGE, "$offset": offset, "$order": "pd_id"}
        if token:
            params["$$app_token"] = token
        page = get_json(BASE.format(rid=rid), params)
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        offset += PAGE


def check_fields(cat, cfg, rows):
    """Socrata omits null fields per row, so check the union across all rows."""
    seen = set().union(*(r.keys() for r in rows))
    needed = {"pd_id", "brand_name", cfg["kwh"]}
    if cfg["efficiency"]:
        needed.add(cfg["efficiency"][0])
    if cfg["capacity"]:
        needed.add(cfg["capacity"][0])
    missing = needed - seen
    if missing:
        raise RuntimeError(f"{cat}: source no longer has fields {sorted(missing)}; update CATEGORIES")


def normalize(cat, cfg, row):
    brand = clean(row.get("brand_name"))
    model = clean(row.get("model_number")) or clean(row.get("model_name"))
    if not brand or not model:
        return None
    eff = None
    if cfg["efficiency"]:
        field, metric, unit = cfg["efficiency"]
        v = num(row.get(field))
        if v is not None:
            eff = {"metric": metric, "value": v, "unit": unit}
    cap = None
    if cfg["capacity"]:
        field, unit = cfg["capacity"]
        v = num(row.get(field))
        if v is not None and v > 0:
            cap = {"value": v, "unit": unit}
    kwh = num(row.get(cfg["kwh"]))
    attrs = {}
    for a in cfg["attributes"]:
        raw = row.get(a)
        n = num(raw)
        attrs[a] = n if n is not None else clean(raw)
    return {
        "id": f"us-energystar-{row['pd_id']}",
        "country": "US",
        "category": cat,
        "brand": brand,
        "model": model,
        "annual_kwh": kwh if kwh and kwh > 0 else None,
        "kwh_basis": KWH_BASIS,
        "efficiency": eff,
        "capacity": cap,
        "attributes": attrs,
        "certifications": ["ENERGY STAR"],
        "source_record_id": str(row["pd_id"]),
    }


def run(cat):
    cfg = CATEGORIES[cat]
    print(f"{cat}: fetching {cfg['rid']} ...", file=sys.stderr)
    rows = fetch_all(cfg["rid"])
    check_fields(cat, cfg, rows)

    # The dataset covers the US and Canada; keep models certified for the US market.
    us_rows = [r for r in rows if "United States" in (r.get("markets") or "")]
    records, seen = [], set()
    for r in us_rows:
        rec = normalize(cat, cfg, r)
        if rec and rec["id"] not in seen:
            seen.add(rec["id"])
            records.append(rec)

    no_kwh = sum(1 for r in records if r["annual_kwh"] is None)
    print(f"  {len(rows)} rows, {len(rows) - len(us_rows)} not sold in US, "
          f"{len(records)} kept, {no_kwh} without annual kWh", file=sys.stderr)
    write_dataset(
        f"us/products/{cat}", "product",
        {"name": cfg["name"], "publisher": "US EPA ENERGY STAR",
         "url": f"https://data.energystar.gov/d/{cfg['rid']}", "license": LICENSE},
        records,
    )


def main(argv):
    cats = argv or list(CATEGORIES)
    unknown = [c for c in cats if c not in CATEGORIES]
    if unknown:
        sys.exit(f"unknown category {unknown}; choose from {list(CATEGORIES)}")
    for c in cats:
        run(c)


if __name__ == "__main__":
    main(sys.argv[1:])
