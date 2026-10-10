import json
from pathlib import Path

from jsonschema import Draft202012Validator

from sources.us import eia, energystar, openei

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
PRODUCT = Draft202012Validator(json.loads((ROOT / "schema/product.schema.json").read_text()))
TARIFF = Draft202012Validator(json.loads((ROOT / "schema/tariff.schema.json").read_text()))


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def test_energystar_room_ac_maps_official_fields():
    cat = "room_ac"
    rows = fixture("energystar_room_ac.json")
    energystar.check_fields(cat, energystar.CATEGORIES[cat], rows)
    for row in rows:
        rec = energystar.normalize(cat, energystar.CATEGORIES[cat], row)
        assert not list(PRODUCT.iter_errors(rec))
        assert rec["annual_kwh"] == float(row["annual_energy_use_kwh_yr"])
        assert rec["efficiency"] == {"metric": "CEER", "value": float(row["combined_energy_efficiency_ratio_ceer"]), "unit": "Btu/Wh"}
        assert rec["capacity"]["value"] == float(row["cooling_capacity_btu_hour"])
        assert rec["source_record_id"] == row["pd_id"]


def test_energystar_dryer_keeps_fuel_type():
    cat = "clothes_dryer"
    for row in fixture("energystar_clothes_dryer.json"):
        rec = energystar.normalize(cat, energystar.CATEGORIES[cat], row)
        assert not list(PRODUCT.iter_errors(rec))
        assert rec["attributes"]["type"] == row["type"]


def test_energystar_missing_value_stays_null():
    cat = "room_ac"
    row = dict(fixture("energystar_room_ac.json")[0])
    del row["annual_energy_use_kwh_yr"]
    rec = energystar.normalize(cat, energystar.CATEGORIES[cat], row)
    assert rec["annual_kwh"] is None


def test_energystar_renamed_field_fails_loudly():
    rows = [{k: v for k, v in r.items() if k != "annual_energy_use_kwh_yr"}
            for r in fixture("energystar_room_ac.json")]
    try:
        energystar.check_fields("room_ac", energystar.CATEGORIES["room_ac"], rows)
    except RuntimeError as e:
        assert "annual_energy_use_kwh_yr" in str(e)
    else:
        raise AssertionError("expected RuntimeError")


def test_eia_months_back():
    assert eia.months_back("2026-07", 12) == "2025-08"
    assert eia.months_back("2026-01", 2) == "2025-12"
    assert eia.months_back("2026-07", 1) == "2026-07"


def test_eia_window_skips_gap():
    months = {eia.months_back("2026-07", k): (1.0, 10.0) for k in range(1, 25)}
    del months["2026-05"]
    start, end, values = eia.latest_complete_window(months, "2026-07")
    assert (start, end, len(values)) == ("2025-05", "2026-04", 12)


def test_eia_window_none_when_too_sparse():
    months = {eia.months_back("2026-07", k): (1.0, 10.0) for k in range(1, 25, 2)}
    assert eia.latest_complete_window(months, "2026-07") is None


# Shape copied from URDB's current Con Edison SC-1 Zone I [NYC] rate (label shortened).
CONED = {
    "label": "coned-sc1", "name": "SC-1 - Residential & Religious Service - Zone I [NYC]",
    "utility": "Consolidated Edison Co-NY Inc", "eiaid": 4226, "uri": "https://apps.openei.org/IURDB/rate/view/x",
    "startdate": 1738368000,
    "energyratestructure": [
        [{"unit": "kWh", "rate": 0.26472, "adj": 0.07884}],
        [{"max": 250, "unit": "kWh", "rate": 0.26472, "adj": 0.07884},
         {"unit": "kWh", "rate": 0.28883, "adj": 0.07884}],
    ],
    "energyweekdayschedule": [[0] * 24] * 5 + [[1] * 24] * 4 + [[0] * 24] * 3,
    "energyweekendschedule": [[0] * 24] * 5 + [[1] * 24] * 4 + [[0] * 24] * 3,
    "fixedchargefirstmeter": 20, "fixedchargeunits": "$/month",
}


def test_openei_tiered_rate_has_no_single_price():
    rec = openei.to_record("10001", CONED)
    assert not list(TARIFF.iter_errors(rec))
    assert rec["price_per_kwh"] is None
    assert rec["structure"] == {"type": ["tiered", "seasonal"], "fixed_monthly": 20,
                                "energy_rate_min": 0.34356, "energy_rate_max": 0.36767}


def test_openei_flat_rate_includes_adjustments():
    flat = dict(CONED, energyratestructure=[[{"rate": 0.10, "adj": 0.02}]],
                energyweekdayschedule=[[0] * 24] * 12, energyweekendschedule=[[0] * 24] * 12)
    rec = openei.to_record("10001", flat)
    assert rec["price_per_kwh"] == 0.12
    assert rec["structure"]["type"] == ["flat"]
