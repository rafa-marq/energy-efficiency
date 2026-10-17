# Contributing

The goal is a global database of appliance energy use and electricity prices that
people can trust. That trust depends on a few hard rules.

## Data rules

1. **Every number comes from an official or primary source**: a government efficiency
   program, regulator or statistics agency. No blog posts, retailer copy or "typical" values.
2. **Missing stays missing.** If the source doesn't publish a value, write `null`.
   No placeholders, fallbacks or estimates. The one exception is a documented
   project-standard assumption (e.g. Brazil's tax rates): it goes in a separate,
   clearly named field next to the official value, never in place of it, and the
   dataset's `source.notes` says what was assumed.
3. **Derived values say how they were derived.** If you compute something (e.g. revenue /
   sales), describe the formula in the record's `price_basis` or `kwh_basis`.
4. **Keep records traceable.** Each record has `source_record_id`; each file has
   `source` (publisher, URL, license) and `fetched_at`.
5. **Compare within a country.** Test procedures differ (US DOE vs INMETRO vs EU), so
   `annual_kwh` from different countries is not directly comparable.
6. **Never commit API keys.** Read them from environment variables; document them in
   `.env.example` and the README.

## Adding a country

1. Create `sources/<cc>/` (ISO 3166-1 alpha-2, lowercase) with one module per upstream
   source. Use `sources.common.http.get_json` and `sources.common.dataset.write_dataset`.
   Fetchers should stay stdlib-only where possible.
2. Map products onto categories in `schema/categories.json`. If none fits, add a new
   category in the same PR.
3. Write output to `data/<cc>/products/<category>.json` and `data/<cc>/tariffs/<name>.json`.
4. Add tests in `tests/` using small, **real** sample responses saved in `tests/fixtures/`.
5. If a source renames or drops a field, the fetcher must fail loudly, not silently
   write empty data (see `check_fields` in `sources/us/energystar.py`).
6. Add the fetch command to `.github/workflows/refresh-data.yml`.
7. Run `uv run pytest -q` and `uv run python -m tools.validate`; add sanity bounds for
   your currency in `tools/validate.py`.
8. Update the coverage table in the README, including any known limits of the source.

Candidate sources we haven't evaluated yet: EU EPREL, Canada NRCan, Australia GEMS,
India BEE, UK. Open an issue before starting so efforts don't overlap.

## Pull requests

Keep data refreshes and code changes in separate PRs. In a data PR, mention anything
surprising in the diff (large count changes, removed records).
