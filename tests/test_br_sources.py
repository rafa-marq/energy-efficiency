import json
from pathlib import Path

from jsonschema import Draft202012Validator

from sources.br import aneel

ROOT = Path(__file__).resolve().parents[1]
TARIFF = Draft202012Validator(json.loads((ROOT / "schema/tariff.schema.json").read_text()))
COMPONENT = Draft202012Validator(json.loads((ROOT / "schema/tariff_component.schema.json").read_text()))
TODAY = "2026-10-17"


def rows():
    return json.loads((ROOT / "tests/fixtures/aneel_tarifas_aplicacao.json").read_text())


def lines():
    return aneel.current_lines(rows(), TODAY)


def test_br_num_parses_brazilian_format():
    assert aneel.br_num("1.346,09") == 1346.09
    assert aneel.br_num("715,85") == 715.85
    assert aneel.br_num("-166,06") == -166.06
    assert aneel.br_num("-,12") == -0.12
    assert aneel.br_num(",00") == 0.0
    assert aneel.br_num("") is None
    assert aneel.br_num(None) is None


def test_taxes_are_charged_on_the_gross_amount():
    # por dentro: 100 / (1 - 0.18 - 0.0365), not 100 * 1.2165
    assert aneel.with_taxes(100) == round(100 / 0.7835, 5)


def test_keeps_consumer_lines_only():
    got = lines()
    assert all(r["DscModalidadeTarifaria"] in aneel.CONSUMER_MODALITIES for r in got)
    assert all(r["SigAgenteAcessante"] == aneel.NA for r in got)
    assert {r["DscSubGrupo"] for r in got} == {"A2", "A4", "B1"}


def test_group_a_has_demand_and_energy_by_time_slot():
    a4 = [aneel.normalize_line(r) for r in lines() if r["DscSubGrupo"] == "A4"]
    assert {(r["modality"], r["unit"]) for r in a4} >= {("Azul", "BRL/kW"), ("Azul", "BRL/MWh"),
                                                        ("Verde", "BRL/kW"), ("Verde", "BRL/MWh")}
    assert {r["time_slot"] for r in a4 if r["unit"] == "BRL/MWh"} == {"Ponta", "Fora ponta"}


def test_component_records_match_schema():
    recs = [aneel.normalize_line(r) for r in lines()]
    ids = [r["id"] for r in recs]
    assert len(ids) == len(set(ids))
    for rec in recs:
        assert not list(COMPONENT.iter_errors(rec))
        assert rec["total"] == round(rec["tusd"] + rec["te"], 5)
        assert rec["total_with_assumed_taxes"] == aneel.with_taxes(rec["total"])


def test_scee_credit_stays_negative():
    scee = [aneel.normalize_line(r) for r in lines() if r["DscDetalhe"] == "SCEE"]
    assert scee and any(r["tusd"] < 0 or r["te"] < 0 for r in scee)


def test_residential_one_per_distributor_latest_resolution_wins():
    res = aneel.residential(lines())
    assert sorted(r["SigAgente"] for r in res) == ["CEA", "EAC"]
    eac = next(r for r in res if r["SigAgente"] == "EAC")
    assert eac["DatInicioVigencia"] == "2026-08-26"  # supersedes the 2026-01-01 resolution
    rec = aneel.normalize_residential(eac)
    assert rec["price_per_kwh"] == round((715.85 + 113.86) / 1000, 5)
    assert rec["taxes_included"] is False
    assert rec["with_assumed_taxes"]["value"] == aneel.with_taxes(rec["price_per_kwh"])
    assert not list(TARIFF.iter_errors(rec))


def test_nothing_in_force_outside_validity():
    assert aneel.current_lines(rows(), "2040-01-01") == []


def test_renamed_field_fails_loudly():
    broken = [{k: v for k, v in r.items() if k != "VlrTE"} for r in rows()]
    try:
        aneel.check_fields(broken)
    except RuntimeError as e:
        assert "VlrTE" in str(e)
    else:
        raise AssertionError("expected RuntimeError")
