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

API_KEY = "PASTE_YOUR_OPENEI_KEY"   # <-- required
BASE = "https://api.openei.org/utility_rates"

# Starter set: utility "label" pages in URDB for the defaults already in the UI.
# (Look these up once at apps.openei.org/USURDB and paste the page IDs.)
STARTER = {
    "US average":        None,          # synthetic fallback, set manually to 0.17
    "Con Edison (NY)":   "RATE_PAGE_ID_CONED",
    "PG&E (CA)":         "RATE_PAGE_ID_PGE",
    "ComEd (IL)":        "RATE_PAGE_ID_COMED",
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

def by_zip(z):
    data = get_json({
        "version": "latest", "format": "json", "api_key": API_KEY,
        "sector": "Residential", "detail": "full",
        "address": z, "limit": 5, "orderby": "is_default", "direction": "desc",
    })
    items = data.get("items", [])
    if not items:
        print("No rates found for that ZIP.", file=sys.stderr); return
    best = items[0]
    rate = avg_energy_rate(best)
    print(json.dumps({
        "zip": z,
        "utility": best.get("utility"),
        "rate_name": best.get("name"),
        "avg_kwh_usd": rate,
        "source_url": best.get("uri"),
    }, indent=2))

def starter_set():
    out = []
    for name, page in STARTER.items():
        if not page:
            out.append({"name": name, "rate": 0.17, "note": "national average (manual)"})
            continue
        data = get_json({
            "version": "latest", "format": "json", "api_key": API_KEY,
            "detail": "full", "getpage": page, "limit": 1,
        })
        items = data.get("items", [])
        if items:
            out.append({"name": name, "rate": avg_energy_rate(items[0]),
                        "utility": items[0].get("utility")})
    with open("rates.json", "w") as f:
        json.dump(out, f, indent=2)
    print("Wrote rates.json", file=sys.stderr)
    print(json.dumps(out, indent=2), file=sys.stderr)

if __name__ == "__main__":
    if API_KEY == "PASTE_YOUR_OPENEI_KEY":
        print("Set API_KEY first (free at openei.org/services/api/signup).", file=sys.stderr)
        sys.exit(1)
    if len(sys.argv) >= 3 and sys.argv[1] == "--zip":
        by_zip(sys.argv[2])
    else:
        starter_set()
