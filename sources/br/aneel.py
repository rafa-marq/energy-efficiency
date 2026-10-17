"""Brazil residential electricity tariffs per distributor, from ANEEL open data.

    uv run python -m sources.br.aneel

Writes data/br/tariffs/aneel_residential.json: one record per distribution
utility, with the conventional residential tariff (subgroup B1) in force today.
Price = TUSD + TE as homologated by ANEEL, converted from R$/MWh to R$/kWh.

These are regulated tariffs *before* taxes (ICMS, PIS/COFINS), the public
lighting fee (CIP/COSIP) and tariff flag surcharges (bandeiras tarifárias),
so customers' bills are higher. No API key needed.
"""
import json
import sys
from datetime import date

from sources.common.dataset import clean, write_dataset
from sources.common.http import get_json

DATASET_URL = "https://dadosabertos.aneel.gov.br/dataset/tarifas-distribuidoras-energia-eletrica"
API = "https://dadosabertos.aneel.gov.br/api/3/action/datastore_search"
RESOURCE = "fcf2906c-7c32-4b9b-a637-054e7a5234f4"  # tarifas-homologadas-distribuidoras-energia-eletrica.csv
PAGE = 5000

# Server-side filter: residential class, low-voltage B1, final applied tariff.
FILTERS = {
    "DscSubGrupo": "B1",
    "DscClasse": "Residencial",
    "DscSubClasse": "Residencial",
    "DscBaseTarifaria": "Tarifa de Aplicação",
}
FIELDS = {"SigAgente", "NumCNPJDistribuidora", "DscREH", "DatInicioVigencia", "DatFimVigencia",
          "DscModalidadeTarifaria", "DscDetalhe", "NomPostoTarifario", "DscUnidadeTerciaria",
          "VlrTUSD", "VlrTE"}


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


def fetch_rows():
    rows, offset = [], 0
    while True:
        page = get_json(API, {"resource_id": RESOURCE, "filters": json.dumps(FILTERS),
                              "limit": PAGE, "offset": offset})["result"]["records"]
        rows += page
        if len(page) < PAGE:
            return rows
        offset += PAGE


def check_fields(rows):
    """Fail loudly if ANEEL renames or drops a column, instead of writing empty data."""
    if not rows:
        raise RuntimeError("ANEEL returned no residential B1 rows; did the filters or resource change?")
    missing = FIELDS - set(rows[0])
    if missing:
        raise RuntimeError(f"ANEEL rows are missing fields: {sorted(missing)}")


def current_conventional(rows, today):
    """The conventional (non-time-of-use, non-prepaid) tariff in force on `today`, per
    distributor. When resolutions overlap, the one that started most recently wins."""
    best = {}
    for r in rows:
        if (r["DscModalidadeTarifaria"] != "Convencional" or r["DscDetalhe"] != "Não se aplica"
                or r["NomPostoTarifario"] != "Não se aplica"):
            continue
        if not r["DatInicioVigencia"] <= today <= r["DatFimVigencia"]:
            continue
        if r["DscUnidadeTerciaria"] != "MWh":
            raise RuntimeError(f"unexpected unit {r['DscUnidadeTerciaria']!r} for {r['SigAgente']}")
        key = r["NumCNPJDistribuidora"]
        if key not in best or r["DatInicioVigencia"] > best[key]["DatInicioVigencia"]:
            best[key] = r
    return list(best.values())


def normalize(r):
    tusd, te = br_num(r["VlrTUSD"]), br_num(r["VlrTE"])
    price = round((tusd + te) / 1000, 5) if tusd is not None and te is not None else None
    cnpj = r["NumCNPJDistribuidora"]
    reh = clean(r["DscREH"])
    name = clean(r["SigAgente"])
    if name is None or name.lower() == "não informado":
        name = f"CNPJ {cnpj}"
    return {
        "id": f"br-aneel-{cnpj}",
        "country": "BR",
        "region": None,
        "utility": {"id": cnpj, "name": name},
        "currency": "BRL",
        "price_per_kwh": price if price else None,
        "price_basis": (f"ANEEL homologated residential tariff (subgroup B1, conventional): "
                        f"TUSD {r['VlrTUSD']} + TE {r['VlrTE']} R$/MWh, divided by 1000. "
                        f"Excludes ICMS, PIS/COFINS, public lighting fee and tariff flag "
                        f"surcharges." + (f" {reh}." if reh else "")),
        "taxes_included": False,
        "period": {"from": r["DatInicioVigencia"], "to": r["DatFimVigencia"]},
        "source_record_id": f"{RESOURCE}/{r['_id']}",
    }


def main():
    today = date.today().isoformat()
    rows = fetch_rows()
    check_fields(rows)
    records = [normalize(r) for r in current_conventional(rows, today)]
    print(f"  {len(rows)} residential B1 rows -> {len(records)} distributors in force on {today}",
          file=sys.stderr)
    write_dataset(
        "br/tariffs/aneel_residential", "tariff",
        {"name": "Tarifas de aplicação das distribuidoras de energia elétrica",
         "publisher": "Agência Nacional de Energia Elétrica (ANEEL)",
         "url": DATASET_URL,
         "license": "Open Data Commons Open Database License (ODbL)",
         "notes": "Tariffs before taxes (ICMS, PIS/COFINS), public lighting fee and tariff flag "
                  "surcharges. ANEEL does not map distributors to states in this dataset."},
        records,
    )


if __name__ == "__main__":
    main()
