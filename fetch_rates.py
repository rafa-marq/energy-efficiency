#!/usr/bin/env python3
"""
TrueWatt — utility rate fetcher (OpenEI URDB)
Run LOCALLY; needs open internet and a free OpenEI API key.
Get a key (instant, free): https://openei.org/services/api/signup/

Two modes:
  A) --zip 10001        -> look up the default residential rate for that ZIP's utility
  B) (no args)          -> pull a starter set of major utilities into rates.json

The URDB 'flatdemand'/energy structure can be complex (tiers, TOU). For a
shopping calculator you want ONE representative $/kWh, so we compute a simple
average of the energy-rate tiers from the utility's default residential rate.
"""
import json, sys, urllib.request, urllib.parse

API_KEY = "Lyuxedg7iw03C4RggcUIx8cnoQ8U5M2sMt34tYyV"
BASE = "https://api.openei.org/utility_rates"

# Starter set: a representative ZIP per utility. ZIP lookup works with just the
# API key (no URDB page IDs to hunt down) and returns each utility's default
# residential rate. Edit these ZIPs to match the utilities you want to feature.
US_AVERAGE = 0.17          # national average $/kWh, used as a labelled fallback
STARTER = {
    "Con Edison (NY)":   "10001",
    "PG&E (CA)":         "94103",
    "ComEd (IL)":        "60601",
}

def get_json(params):
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "truewatt/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def avg_energy_rate(rate):
    """Average $/kWh across the energy rate tiers of a URDB rate record."""
    structure = rate.get("energyratestructure") or []
    vals = []
    for period in structure:
        for tier in period:
            r = tier.get("rate")
            if isinstance(r, (int, float)) and r > 0:
                vals.append(r)
    if not vals:
        return None
    return round(sum(vals) / len(vals), 4)

def rate_for_zip(z):
    """(utility_name, avg $/kWh, source_uri) for the default residential rate at a ZIP."""
    data = get_json({
        "version": "latest", "format": "json", "api_key": API_KEY,
        "sector": "Residential", "detail": "full",
        "address": z, "limit": 5, "orderby": "is_default", "direction": "desc",
    })
    items = data.get("items", [])
    if not items:
        return None
    best = items[0]
    return best.get("utility"), avg_energy_rate(best), best.get("uri")

def write_rates(rows):
    """Write rates.json in the shape the calculator loads: [{name, rate}, ...]."""
    with open("rates.json", "w") as f:
        json.dump(rows, f, indent=2)
    print("Wrote rates.json", file=sys.stderr)
    print(json.dumps(rows, indent=2), file=sys.stderr)

def by_zip(z):
    r = rate_for_zip(z)
    if not r or r[1] is None:
        print("No usable rate found for that ZIP.", file=sys.stderr); return
    util, rate, uri = r
    write_rates([
        {"name": "US average", "rate": US_AVERAGE},
        {"name": f"{util} (ZIP {z})", "rate": rate, "source_url": uri},
    ])

def starter_set():
    rows = [{"name": "US average", "rate": US_AVERAGE, "note": "national average (manual)"}]
    for name, z in STARTER.items():
        r = rate_for_zip(z)
        if r and r[1] is not None:
            rows.append({"name": name, "rate": r[1], "utility": r[0]})
        else:
            print(f"  ! no rate returned for {name} (ZIP {z}) — skipped", file=sys.stderr)
    write_rates(rows)

if __name__ == "__main__":
    if API_KEY == "PASTE_YOUR_OPENEI_KEY":
        print("Set API_KEY first (free at openei.org/services/api/signup).", file=sys.stderr)
        sys.exit(1)
    if len(sys.argv) >= 3 and sys.argv[1] == "--zip":
        by_zip(sys.argv[2])
    else:
        starter_set()
