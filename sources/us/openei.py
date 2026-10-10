"""Current default residential tariff for a US ZIP code, from the OpenEI Utility Rate
Database (URDB, maintained by NREL).

    uv run python -m sources.us.openei 10001

Prints one tariff record as JSON. This is an on-demand lookup, not a bulk dataset:
URDB has thousands of utilities and its data quality varies (e.g. a ZIP can map to
the wrong pricing zone), so treat results as a starting point and check source_url.

price_per_kwh is only set when the energy charge is flat. Tiered, seasonal and
time-of-use tariffs have no single per-kWh price without assuming a usage profile,
so they get price_per_kwh = null and a `structure` summary instead.

Requires OPENEI_API_KEY (free: https://openei.org/services/api/signup/).
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

from sources.common.http import get_json

URL = "https://api.openei.org/utility_rates"


def current_default_rate(zip_code, api_key):
    items = get_json(URL, {
        "version": "latest", "format": "json", "api_key": api_key,
        "sector": "Residential", "detail": "full", "approved": "true",
        "address": zip_code, "orderby": "startdate", "direction": "desc", "limit": 100,
    }).get("items", [])
    now = time.time()
    current = [i for i in items if not i.get("enddate") or i["enddate"] > now]
    defaults = [i for i in current if i.get("is_default")]
    return (defaults or [None])[0], len(current)


def summarize(rate):
    """Shape of a URDB energy charge. Effective $/kWh per tier is rate + adj."""
    periods = rate.get("energyratestructure") or []
    tier_prices = [[(t.get("rate") or 0) + (t.get("adj") or 0) for t in p] for p in periods]
    flat_prices = sorted({round(x, 5) for p in tier_prices for x in p if x > 0})

    kinds = []
    if any(len(p) > 1 for p in periods):
        kinds.append("tiered")
    weekday = rate.get("energyweekdayschedule") or []
    weekend = rate.get("energyweekendschedule") or []
    if len({tuple(m) for m in weekday + weekend}) > 1:
        kinds.append("seasonal")
    if any(len(set(m)) > 1 for m in weekday + weekend):
        kinds.append("time_of_use")
    if not kinds:
        kinds.append("flat")

    fixed = rate.get("fixedchargefirstmeter")
    if fixed is not None and rate.get("fixedchargeunits") != "$/month":
        fixed = None  # only report monthly fixed charges; other units aren't comparable
    return {
        "type": kinds,
        "fixed_monthly": fixed,
        "energy_rate_min": flat_prices[0] if flat_prices else None,
        "energy_rate_max": flat_prices[-1] if flat_prices else None,
    }


def to_record(zip_code, rate):
    s = summarize(rate)
    single = s["energy_rate_min"] is not None and s["energy_rate_min"] == s["energy_rate_max"]
    fixed_note = (f" Excludes a fixed charge of ${s['fixed_monthly']}/month."
                  if s["fixed_monthly"] else "")
    if single:
        basis = "Flat energy charge from URDB (rate + adjustments)." + fixed_note
    else:
        basis = (f"{'/'.join(s['type'])} tariff: energy charges range "
                 f"${s['energy_rate_min']}-${s['energy_rate_max']}/kWh (rate + adjustments); "
                 f"no single per-kWh price without a usage profile." + fixed_note)
    end = rate.get("enddate")
    return {
        "id": f"us-urdb-{rate['label']}",
        "country": "US",
        "region": {"type": "postal_code", "code": zip_code, "name": zip_code},
        "utility": {"id": f"eia:{rate.get('eiaid')}", "name": rate.get("utility")},
        "currency": "USD",
        "price_per_kwh": s["energy_rate_min"] if single else None,
        "price_basis": f"{rate.get('name')}. {basis} Source: {rate.get('uri')}",
        "taxes_included": None,
        "period": {
            "from": datetime.fromtimestamp(rate["startdate"], timezone.utc).date().isoformat(),
            "to": datetime.fromtimestamp(end, timezone.utc).date().isoformat() if end else None,
        },
        "source_record_id": rate["label"],
        "structure": s,
    }


def main(argv):
    if len(argv) != 1:
        sys.exit("usage: python -m sources.us.openei <ZIP>")
    api_key = os.environ.get("OPENEI_API_KEY")
    if not api_key:
        sys.exit("Set OPENEI_API_KEY first (free at openei.org/services/api/signup).")
    rate, n_current = current_default_rate(argv[0], api_key)
    if rate is None:
        sys.exit(f"No current default residential rate in URDB for {argv[0]} "
                 f"({n_current} current non-default rates found).")
    print(json.dumps(to_record(argv[0], rate), indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
