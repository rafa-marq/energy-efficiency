import json
from pathlib import Path

from jsonschema import Draft202012Validator

from sources.br import aneel

ROOT = Path(__file__).resolve().parents[1]
TARIFF = Draft202012Validator(json.loads((ROOT / "schema/tariff.schema.json").read_text()))


def rows():
    return json.loads((ROOT / "tests/fixtures/aneel_b1_residencial.json").read_text())


def test_br_num_parses_brazilian_format():
    assert aneel.br_num("1.346,09") == 1346.09
    assert aneel.br_num("715,85") == 715.85
    assert aneel.br_num(",00") == 0.0
    assert aneel.br_num("") is None
    assert aneel.br_num(None) is None


def test_picks_one_conventional_tariff_per_distributor():
    cur = aneel.current_conventional(rows(), "2026-10-17")
    assert sorted(r["SigAgente"] for r in cur) == ["CEA", "EAC"]
    assert all(r["DscModalidadeTarifaria"] == "Convencional" for r in cur)


def test_overlapping_resolutions_latest_start_wins():
    # EAC has two conventional tariffs in force on this date; the newer one supersedes.
    eac = next(r for r in aneel.current_conventional(rows(), "2026-10-17") if r["SigAgente"] == "EAC")
    assert eac["DatInicioVigencia"] == "2026-08-26"
    rec = aneel.normalize(eac)
    assert rec["price_per_kwh"] == round((715.85 + 113.86) / 1000, 5)


def test_records_match_schema_and_say_taxes_excluded():
    for r in aneel.current_conventional(rows(), "2026-10-17"):
        rec = aneel.normalize(r)
        assert not list(TARIFF.iter_errors(rec))
        assert rec["taxes_included"] is False
        assert rec["utility"]["id"] == r["NumCNPJDistribuidora"]


def test_nothing_in_force_outside_validity():
    assert aneel.current_conventional(rows(), "2030-01-01") == []


def test_renamed_field_fails_loudly():
    broken = [{k: v for k, v in r.items() if k != "VlrTE"} for r in rows()]
    try:
        aneel.check_fields(broken)
    except RuntimeError as e:
        assert "VlrTE" in str(e)
    else:
        raise AssertionError("expected RuntimeError")
