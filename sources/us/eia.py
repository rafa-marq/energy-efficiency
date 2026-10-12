"""US average residential electricity price per state, from the EIA Open Data API.

    uv run python -m sources.us.eia

Writes data/us/tariffs/eia_state_average.json: one record per state plus the
US total. Price = total residential revenue / total residential sales over the
latest 12 consecutive months EIA has published complete data for, which smooths
out summer/winter swings. A state with a gap falls back to an earlier window.

Set EIA_API_KEY (free: https://www.eia.gov/opendata/register.php). Without it the
public DEMO_KEY is used, which works but is heavily rate limited.
"""
import os
import sys
from collections import defaultdict

from sources.common.dataset import num, write_dataset
from sources.common.http import get_json

URL = "https://api.eia.gov/v2/electricity/retail-sales/data/"
MONTHS = 12
LOOKBACK = 24  # months searched for a complete 12-month window


def query(api_key, **extra):
    params = {
        "api_key": api_key,
        "frequency": "monthly",
        "data[]": ["revenue", "sales"],
        "facets[sectorid][]": "RES",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
    }
    params.update(extra)
    return get_json(URL, params)["response"]["data"]


def months_back(period, n):
    """'2026-07', 12 -> '2025-08' (the first month of a 12-month window)."""
    y, m = map(int, period.split("-"))
    idx = y * 12 + (m - 1) - (n - 1)
    return f"{idx // 12}-{idx % 12 + 1:02d}"


def latest_complete_window(by_period, latest):
    """Most recent run of MONTHS consecutive months with data -> (start, end, values)."""
    for back in range(LOOKBACK - MONTHS + 1):
        end = months_back(latest, back + 1)
        periods = [months_back(end, k + 1) for k in range(MONTHS)]
        if all(p in by_period for p in periods):
            return periods[-1], end, [by_period[p] for p in periods]
    return None


def main():
    api_key = os.environ.get("EIA_API_KEY") or "DEMO_KEY"
    if api_key == "DEMO_KEY":
        print("EIA_API_KEY not set; using rate-limited DEMO_KEY", file=sys.stderr)

    latest = query(api_key, **{"facets[stateid][]": "US", "length": 1})[0]["period"]
    rows = query(api_key, start=months_back(latest, LOOKBACK), end=latest, length=5000)

    by_state = defaultdict(dict)
    names = {}
    for r in rows:
        # Two-letter codes are states/DC; "US" is the national total. Longer codes
        # are census divisions, which we skip.
        if len(r["stateid"]) != 2:
            continue
        rev, sales = num(r.get("revenue")), num(r.get("sales"))
        if rev is not None and sales is not None and sales > 0:
            by_state[r["stateid"]][r["period"]] = (rev, sales)
        names[r["stateid"]] = r["stateDescription"]

    records = []
    for sid in names:
        window = latest_complete_window(by_state[sid], latest)
        if window is None:
            print(f"  skip {sid}: no complete {MONTHS}-month window in last {LOOKBACK}", file=sys.stderr)
            continue
        start, end, months = window
        if end != latest:
            print(f"  {sid}: gap in recent data, using {start}..{end}", file=sys.stderr)
        revenue = sum(rv for rv, _ in months)
        sales = sum(sl for _, sl in months)
        is_total = sid == "US"
        records.append({
            "id": f"us-eia-{sid}",
            "country": "US",
            "region": {"type": "country" if is_total else "state", "code": sid, "name": names[sid]},
            "utility": None,
            "currency": "USD",
            # million $ / million kWh = $/kWh
            "price_per_kwh": round(revenue / sales, 4),
            "price_basis": (f"Average residential price: sum of EIA residential revenue / sum of "
                            f"residential sales, {start} to {end}. An average across all residential "
                            f"customers as reported to EIA, not a specific tariff."),
            "taxes_included": None,
            "period": {"from": start, "to": end},
            "source_record_id": f"retail-sales/RES/{sid}/{start}..{end}",
        })

    print(f"  {len(records)} regions, latest month {latest}", file=sys.stderr)
    write_dataset(
        "us/tariffs/eia_state_average", "tariff",
        {"name": "EIA Electricity Retail Sales (Forms EIA-826, EIA-861, EIA-861M)",
         "publisher": "US Energy Information Administration",
         "url": "https://www.eia.gov/opendata/browser/electricity/retail-sales",
         "license": "Public domain (US Government work)",
         "notes": "EIA does not state whether revenue includes taxes, so taxes_included is null."},
        records,
    )


if __name__ == "__main__":
    main()
