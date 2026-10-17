"""Brazil electricity tariffs per distributor, from ANEEL open data.

    uv run python -m sources.br.aneel

Writes two files from the applied tariffs ("Tarifa de Aplicação") in force today:

  data/br/tariffs/aneel_components.json   every consumer tariff line: groups A
      (A1-A4, AS; Azul, Verde, Convencional) and B (B1-B4; Convencional, Branca,
      pre-paid), each subclass and time slot, demand (R$/kW) and energy (R$/MWh)
  data/br/tariffs/aneel_residential.json  one price per distributor: the
      conventional residential B1 tariff, TUSD + TE in R$/kWh

Tariffs for generators and distributors ("Geração", "Distribuição" modalities)
and agent-specific lines are left out: they aren't consumer tariffs.

ANEEL publishes tariffs *before* taxes (ICMS, PIS/COFINS), the public lighting
fee and tariff flag surcharges (bandeiras). Each record keeps that official
value and adds a with-taxes figure, using the project-standard rates below.
No API key needed.
"""
import json
import re
import sys
import unicodedata
from datetime import date

from sources.common.dataset import clean, write_dataset
from sources.common.http import get_json

DATASET_URL = "https://dadosabertos.aneel.gov.br/dataset/tarifas-distribuidoras-energia-eletrica"
API = "https://dadosabertos.aneel.gov.br/api/3/action/datastore_search"
RESOURCE = "fcf2906c-7c32-4b9b-a637-054e7a5234f4"  # tarifas-homologadas-distribuidoras-energia-eletrica.csv
PAGE = 10000
SOURCE = {
    "name": "Tarifas de aplicação das distribuidoras de energia elétrica",
    "publisher": "Agência Nacional de Energia Elétrica (ANEEL)",
    "url": DATASET_URL,
    "license": "Open Data Commons Open Database License (ODbL)",
}

# Project-standard tax assumptions, not ANEEL data. Real ICMS varies by state
# (and some states exempt low-consumption households); PIS/COFINS varies monthly.
# Brazilian taxes are charged "por dentro" (included in their own base), so
# price with taxes = tariff / (1 - ICMS - PIS/COFINS), not tariff * (1 + rates).
ASSUMED_TAXES = {"ICMS": 0.18, "PIS/COFINS": 0.0365}
TAX_BASIS = ("Project-standard assumption, not published by ANEEL: ICMS 18% and PIS/COFINS "
             "3.65%, charged on the gross amount (por dentro): tariff / (1 - 0.18 - 0.0365). "
             "Excludes the public lighting fee and tariff flag surcharges.")

CONSUMER_MODALITIES = {"Azul", "Verde", "Convencional", "Branca", "Convencional pré-pagamento"}
FIELDS = {"_id", "SigAgente", "NumCNPJDistribuidora", "DscREH", "DatInicioVigencia",
          "DatFimVigencia", "DscBaseTarifaria", "DscSubGrupo", "DscModalidadeTarifaria",
          "DscClasse", "DscSubClasse", "DscDetalhe", "NomPostoTarifario",
          "DscUnidadeTerciaria", "SigAgenteAcessante", "VlrTUSD", "VlrTE"}
UNITS = {"MWh": "BRL/MWh", "kW": "BRL/kW"}
NA = "Não se aplica"


def br_num(value):
    """Parse ANEEL's Brazilian-format numbers: '1.346,09' -> 1346.09, ',00' -> 0.0."""
    if value is None:
        return None
    s = str(value).strip().replace(".", "").replace(",", ".")
    if s in ("", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def with_taxes(value):
    return round(value / (1 - sum(ASSUMED_TAXES.values())), 5)


def na(value):
    """ANEEL's 'Não se aplica' (not applicable) -> None."""
    v = clean(value)
    return None if v == NA else v


def slug(value):
    s = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()


def fetch_rows():
    rows, offset = [], 0
    while True:
        page = get_json(API, {"resource_id": RESOURCE, "limit": PAGE, "offset": offset,
                              "filters": json.dumps({"DscBaseTarifaria": "Tarifa de Aplicação"})}
                        )["result"]["records"]
        rows += page
        print(f"  fetched {len(rows)} rows", file=sys.stderr)
        if len(page) < PAGE:
            return rows
        offset += PAGE


def check_fields(rows):
    """Fail loudly if ANEEL renames or drops a column, instead of writing empty data."""
    if not rows:
        raise RuntimeError("ANEEL returned no applied-tariff rows; did the filter or resource change?")
    missing = FIELDS - set(rows[0])
    if missing:
        raise RuntimeError(f"ANEEL rows are missing fields: {sorted(missing)}")
    units = {r["DscUnidadeTerciaria"] for r in rows} - set(UNITS)
    if units:
        raise RuntimeError(f"unexpected ANEEL units: {sorted(units)}")


def line_key(r):
    return (r["NumCNPJDistribuidora"], r["DscSubGrupo"], r["DscModalidadeTarifaria"], r["DscClasse"],
            r["DscSubClasse"], r["DscDetalhe"], r["NomPostoTarifario"], r["DscUnidadeTerciaria"])


def current_lines(rows, today):
    """Consumer tariff lines in force on `today`, one per distributor and line. When
    resolutions overlap, the one that started most recently wins."""
    best = {}
    for r in rows:
        if (r["DscModalidadeTarifaria"] not in CONSUMER_MODALITIES
                or r["SigAgenteAcessante"] != NA
                or not r["DatInicioVigencia"] <= today <= r["DatFimVigencia"]):
            continue
        k = line_key(r)
        if k not in best or r["DatInicioVigencia"] > best[k]["DatInicioVigencia"]:
            best[k] = r
    return list(best.values())


def utility(r):
    cnpj = r["NumCNPJDistribuidora"]
    name = clean(r["SigAgente"])
    if name is None or name.lower() == "não informado":
        name = f"CNPJ {cnpj}"
    return {"id": cnpj, "name": name}


def normalize_line(r):
    tusd, te = br_num(r["VlrTUSD"]), br_num(r["VlrTE"])
    total = round(tusd + te, 5) if tusd is not None and te is not None else None
    return {
        "id": "br-aneel-" + "-".join(slug(p) for p in line_key(r)),
        "country": "BR",
        "utility": utility(r),
        "currency": "BRL",
        "subgroup": r["DscSubGrupo"],
        "modality": r["DscModalidadeTarifaria"],
        "class": na(r["DscClasse"]),
        "subclass": na(r["DscSubClasse"]),
        "detail": na(r["DscDetalhe"]),
        "time_slot": na(r["NomPostoTarifario"]),
        "unit": UNITS[r["DscUnidadeTerciaria"]],
        "tusd": tusd,
        "te": te,
        "total": total,
        "taxes_included": False,
        "total_with_assumed_taxes": None if total is None else with_taxes(total),
        "resolution": clean(r["DscREH"]),
        "period": {"from": r["DatInicioVigencia"], "to": r["DatFimVigencia"]},
        "source_record_id": f"{RESOURCE}/{r['_id']}",
    }


def residential(lines):
    """The conventional residential B1 line per distributor (no social-tariff
    subclass, no net-metering detail)."""
    return [r for r in lines
            if r["DscSubGrupo"] == "B1" and r["DscModalidadeTarifaria"] == "Convencional"
            and r["DscSubClasse"] == "Residencial" and r["DscDetalhe"] == NA
            and r["NomPostoTarifario"] == NA and r["DscUnidadeTerciaria"] == "MWh"]


def normalize_residential(r):
    tusd, te = br_num(r["VlrTUSD"]), br_num(r["VlrTE"])
    price = round((tusd + te) / 1000, 5) if tusd is not None and te is not None else None
    reh = clean(r["DscREH"])
    u = utility(r)
    return {
        "id": f"br-aneel-{u['id']}",
        "country": "BR",
        "region": None,
        "utility": u,
        "currency": "BRL",
        "price_per_kwh": price if price else None,
        "price_basis": (f"ANEEL homologated residential tariff (subgroup B1, conventional): "
                        f"TUSD {r['VlrTUSD']} + TE {r['VlrTE']} R$/MWh, divided by 1000. "
                        f"Excludes ICMS, PIS/COFINS, public lighting fee and tariff flag "
                        f"surcharges." + (f" {reh}." if reh else "")),
        "taxes_included": False,
        "with_assumed_taxes": None if not price else
            {"value": with_taxes(price), "rates": ASSUMED_TAXES, "basis": TAX_BASIS},
        "period": {"from": r["DatInicioVigencia"], "to": r["DatFimVigencia"]},
        "source_record_id": f"{RESOURCE}/{r['_id']}",
    }


def main():
    today = date.today().isoformat()
    rows = fetch_rows()
    check_fields(rows)
    lines = current_lines(rows, today)
    res = residential(lines)
    print(f"  {len(rows)} applied-tariff rows -> {len(lines)} lines in force on {today}, "
          f"{len(res)} residential distributors", file=sys.stderr)
    notes = ("Values are ANEEL tariffs before taxes, public lighting fee and tariff flag "
             "surcharges. ANEEL does not map distributors to states in this dataset. "
             "With-taxes figures: " + TAX_BASIS)
    write_dataset("br/tariffs/aneel_components", "tariff_component",
                  {**SOURCE, "notes": notes}, [normalize_line(r) for r in lines])
    write_dataset("br/tariffs/aneel_residential", "tariff",
                  {**SOURCE, "notes": notes}, [normalize_residential(r) for r in res])


if __name__ == "__main__":
    main()
