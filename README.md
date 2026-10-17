# TrueWatt data

An open, source-traceable database of **appliance energy use** and **electricity
prices**, country by country, so anyone can compute what an appliance really costs
to own: purchase price + a lifetime of electricity.

Every number comes from an official source and records where it came from. Missing
values are `null`, never estimated. See [CONTRIBUTING.md](CONTRIBUTING.md) for the rules
and how to add a country.

## Coverage

| Country | Data | Source | Records |
|---|---|---|---|
| 🇺🇸 US | Room ACs, refrigerators, dryers, washers, dishwashers (annual kWh from DOE test procedures) | EPA ENERGY STAR API | ~6,700 models |
| 🇺🇸 US | Average residential price per state, trailing 12 months | EIA Open Data API | 50 states + DC + US |
| 🇺🇸 US | Utility tariff by ZIP (on-demand lookup, not stored) | OpenEI URDB | — |
| 🇧🇷 BR | Full tariff tables in force today: group A (A1–A4, AS; Azul, Verde) demand and energy charges by time slot, group B (B1–B4; Convencional, Branca, pre-paid) by subclass | ANEEL open data | 10,800 lines, 103 utilities |
| 🇧🇷 BR | Residential price per utility (B1 conventional), for the calculator | ANEEL open data | 103 utilities |
| 🇧🇷 BR | Planned: appliances (INMETRO/PBE) | | |

ENERGY STAR only lists certified (efficient) models, so the US product data does not
include the least efficient models on the market.

## Layout

```
schema/        JSON Schemas for datasets, products, tariffs; shared category list
sources/<cc>/  one fetcher per upstream source, per country (stdlib only)
data/<cc>/     generated JSON: products/<category>.json, tariffs/<name>.json
tools/         validate.py: schema + sanity checks over data/
tests/         parser tests against real sample responses
```

Each data file is an envelope (`dataset`, `kind`, `source`, `fetched_at`, `count`)
around a sorted `records` array, so refreshes produce small, reviewable diffs.

## Running

Requires [uv](https://docs.astral.sh/uv/).

```sh
cp .env.example .env            # fill in keys (see below)
set -a; source .env; set +a

uv run python -m sources.us.energystar     # -> data/us/products/*.json
uv run python -m sources.us.eia            # -> data/us/tariffs/eia_state_average.json
uv run python -m sources.us.openei 10001   # prints the current default tariff for a ZIP
uv run python -m sources.br.aneel          # -> data/br/tariffs/aneel_{components,residential}.json (no key)

uv run pytest -q
uv run python -m tools.validate
```

| Variable | Needed for | Get one |
|---|---|---|
| `EIA_API_KEY` | `sources.us.eia` (falls back to the rate-limited `DEMO_KEY`) | https://www.eia.gov/opendata/register.php |
| `OPENEI_API_KEY` | `sources.us.openei` | https://openei.org/services/api/signup/ |
| `SOCRATA_APP_TOKEN` | optional, raises ENERGY STAR rate limits | https://data.energystar.gov |

A weekly GitHub Action re-fetches everything and opens a PR with the diff.

## Known limits

- **Tariffs by utility are messy.** URDB can map a ZIP to the wrong zone or utility,
  and some "default" rates are delivery-only. Tiered/seasonal/TOU tariffs have no single
  $/kWh, so the lookup returns `price_per_kwh: null` plus a range and fixed charge.
  The EIA state average is the reliable default.
- **EIA doesn't say whether its revenue figures include taxes**, so `taxes_included` is `null`.
- **ANEEL tariffs exclude taxes and surcharges** (ICMS, PIS/COFINS, public lighting fee,
  tariff flags); `taxes_included` is `false`. Each record also carries a with-taxes figure
  using **project-standard assumptions: ICMS 18%, PIS/COFINS 3.65%**, applied the Brazilian
  way (on the gross amount): `tariff / (1 - 0.18 - 0.0365)`. Real ICMS varies by state and
  consumption band, so treat it as an estimate. The official value is never altered. The dataset doesn't
  say which state a utility serves, so `region` is `null`.
- **Gas dryers:** `annual_kwh` covers electricity only, not gas.
- **No retail prices yet.** Government datasets don't include them.

## Licenses

Code: see LICENSE (to be chosen). Data keeps its upstream terms, recorded in each
file's `source.license`. US federal data (ENERGY STAR, EIA) is public domain. ANEEL data is under the ODbL, which requires attribution and share-alike for
derived databases.

The prototype calculator UI is in `truecost-energy.html`; it still uses sample data and
will be rewired to `data/` later.
