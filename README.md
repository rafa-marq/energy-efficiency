# TrueWatt — real data setup

The calculator loads live data if these files sit next to `truecost-energy.html`.
Without them, it runs on labelled sample data. Both fetchers must run on a machine
with open internet (the build sandbox blocks these domains).

## 1. ENERGY STAR appliance specs  (free, no key for one pull)
    python fetch_energystar.py        # -> energystar_ac.json

Source: EPA ENERGY STAR Socrata API (data.energystar.gov, dataset 5xn2-dv4h for
room ACs). The script derives steady-state watts as BTU / CEER — the standard,
defensible conversion. Every row is ENERGY STAR certified.

What it does NOT include: retail price. Fill `p` from a retailer feed (Amazon
Product Advertising API, Best Buy API) or leave null — the UI keeps a price
stand-in and flags it. Verify the non-AC dataset IDs in the script before using.

## 2. Utility rates  (free key required)
    # get key: https://openei.org/services/api/signup/   (instant)
    # paste into fetch_rates.py
    python fetch_rates.py             # -> rates.json (starter set of utilities)
    python fetch_rates.py --zip 10001 # -> single ZIP lookup, prints JSON

Source: OpenEI URDB (NREL). Averages the residential energy-rate tiers into one
representative $/kWh. For the starter set, paste each utility's URDB page ID
(find at apps.openei.org/USURDB).

## 3. Drop files in place
Put `energystar_ac.json` and `rates.json` in the same folder as the HTML, or
wire them into your Next.js `public/` or an API route. The page fetches them on
load and replaces the sample data automatically; the disclaimer line turns green
when live data is detected.

## Honest data-coverage summary
| Field            | Source                | Status                         |
|------------------|-----------------------|--------------------------------|
| Efficiency/CEER  | ENERGY STAR API       | real, free, daily-updated      |
| Watts            | BTU / CEER            | derived, reliable              |
| ENERGY STAR flag | ENERGY STAR API       | real                           |
| Utility rate     | OpenEI URDB           | real, free (key), ~annual      |
| **Retail price** | retailer feed (TODO)  | **not in gov data — needs feed** |
