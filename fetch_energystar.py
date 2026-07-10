#!/usr/bin/env python3
"""
TrueWatt — ENERGY STAR data fetcher
Run this LOCALLY (not in a restricted sandbox). It needs open internet.

Pulls real ENERGY STAR certified room AC data from the EPA Socrata API,
derives steady-state watts from BTU / CEER, and writes a clean JSON the
calculator can load directly.

Usage:
    python fetch_energystar.py
    -> writes energystar_ac.json

Optional: get a free Socrata app token at https://data.energystar.gov and
set it below to lift the anonymous rate limit (not required for one pull).
"""
import json, urllib.request, urllib.parse, sys

APP_TOKEN = ""  # optional: paste a Socrata app token to raise rate limits

# EPA ENERGY STAR datasets (Socrata resource IDs). Add more categories here.
DATASETS = {
    "ac":      "5xn2-dv4h",   # Room Air Conditioners
    "fridge":  "p5st-his2",   # Refrigerators  (verify ID at data.energystar.gov)
    "dryer":   "t9u7-4j8e",   # Clothes Dryers (verify ID)
    "washer":  "bhcg-4ymj",   # Clothes Washers (verify ID)
    "dishwasher":"q8py-6w3f", # Dishwashers (verify ID)
}

BASE = "https://data.energystar.gov/resource/{rid}.json"

def fetch(rid, limit=2000):
    params = {"$limit": str(limit)}
    if APP_TOKEN:
        params["$$app_token"] = APP_TOKEN
    url = BASE.format(rid=rid) + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "truewatt/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def num(d, *keys):
    """First parseable numeric value among candidate field names."""
    for k in keys:
        if k in d and d[k] not in (None, "", "N/A"):
            try:
                return float(str(d[k]).replace(",", ""))
            except ValueError:
                continue
    return None

def normalize_ac(rows):
    out = []
    for d in rows:
        btu  = num(d, "cooling_capacity_btu_hour", "capacity_btu_h", "cooling_capacity")
        ceer = num(d, "ceer", "combined_energy_efficiency_ratio")
        brand= d.get("brand_name") or d.get("brand") or ""
        model= d.get("model_number") or d.get("model_name") or ""
        if not btu or not ceer:
            continue
        watts = round(btu / ceer)              # steady-state watts, the real derivation
        out.append({
            "n": f"{brand} {model}".strip(),
            "brand": brand,
            "btu": int(btu),
            "ceer": round(ceer, 1),
            "w": watts,
            "star": 1,                          # every row here is ENERGY STAR certified
            "p": None,                          # price: fill from retailer feed or manual
        })
    # de-dupe and sort most efficient (lowest watts per BTU) first
    seen, uniq = set(), []
    for m in sorted(out, key=lambda x: x["w"]/max(x["btu"],1)):
        key = (m["brand"], m["btu"], m["ceer"])
        if key in seen: continue
        seen.add(key); uniq.append(m)
    return uniq

def main():
    rid = DATASETS["ac"]
    print(f"Fetching room AC data from {rid} ...", file=sys.stderr)
    try:
        rows = fetch(rid)
    except Exception as e:
        print(f"FETCH FAILED: {e}", file=sys.stderr)
        print("If you see an allowlist/DNS error, run this on your own machine, "
              "not inside a restricted sandbox.", file=sys.stderr)
        sys.exit(1)
    print(f"  got {len(rows)} raw rows", file=sys.stderr)
    models = normalize_ac(rows)
    print(f"  kept {len(models)} usable models", file=sys.stderr)
    with open("energystar_ac.json", "w") as f:
        json.dump(models, f, indent=2)
    print("Wrote energystar_ac.json", file=sys.stderr)
    # show a peek
    for m in models[:8]:
        print(f"  {m['ceer']:>4} CEER  {m['btu']:>6} BTU  ~{m['w']:>4} W  {m['n']}", file=sys.stderr)

if __name__ == "__main__":
    main()
