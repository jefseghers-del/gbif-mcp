"""Tests voor de dataset-uitsplitsing per soort (gebiedsanalyse.datasets_per_soort en datasets.py).

Geen netwerk: alles draait op de fixture hieronder.
"""
from __future__ import annotations

import asyncio

import pytest

from gbif_mcp import gbif
from gbif_mcp import gebiedsanalyse as ga
from gbif_mcp.datasets import afkorting, compact
from gbif_mcp.geo import Gebied

# Drie datasets, twee soorten, twintig records.
DS_WNM = "280674cb-42f8-4959-b6aa-eee663157965"  # wnm.be-gewervelden
DS_EBIRD = "4fa7b334-ce0d-4e88-aaae-2e0c138d049e"  # eBird
DS_ONBEKEND = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"  # niet in de mapping
SOORT_A = 2481819  # watersnip
SOORT_B = 5218465  # gewone dwergvleermuis


def _record(key: int, soort: int, ds: str, jaar: int, naam: str | None = None, **rest) -> dict:
    return {
        "key": key, "speciesKey": soort, "taxonKey": soort, "year": jaar, "eventDate": f"{jaar}-05-01",
        "decimalLatitude": 51.05, "decimalLongitude": 3.77, "coordinateUncertaintyInMeters": 10.0,
        "datasetKey": ds, "datasetName": naam, "basisOfRecord": "HUMAN_OBSERVATION", **rest,
    }


@pytest.fixture
def records() -> list[dict]:
    uit: list[dict] = []
    n = 0
    # Soort A: 7 wnm.be (t/m 2024), 4 eBird (t/m 2022), 2 onbekend (t/m 2021) = 13
    for jaar in (2020, 2021, 2021, 2022, 2023, 2024, 2024):
        n += 1
        uit.append(_record(n, SOORT_A, DS_WNM, jaar, "INBO collaborator Occurrences of vertebrates recorded in waarnemingen.be"))
    for jaar in (2020, 2021, 2022, 2022):
        n += 1
        uit.append(_record(n, SOORT_A, DS_EBIRD, jaar, "EOD – eBird Observation Dataset"))
    for jaar in (2020, 2021):
        n += 1
        uit.append(_record(n, SOORT_A, DS_ONBEKEND, jaar, "Een heel lange datasetnaam die zeker meer dan dertig tekens telt"))
    # Soort B: 5 eBird (t/m 2025), 2 wnm.be (t/m 2023) = 7
    for jaar in (2021, 2023, 2024, 2025, 2025):
        n += 1
        uit.append(_record(n, SOORT_B, DS_EBIRD, jaar, "EOD – eBird Observation Dataset"))
    for jaar in (2022, 2023):
        n += 1
        uit.append(_record(n, SOORT_B, DS_WNM, jaar, "INBO collaborator Occurrences of vertebrates recorded in waarnemingen.be"))
    assert len(uit) == 20
    return uit


def _van_soort(records: list[dict], soort: int) -> list[dict]:
    return [o for o in records if o["speciesKey"] == soort]


def test_som_per_soort_klopt(records):
    for soort in (SOORT_A, SOORT_B):
        recs = _van_soort(records, soort)
        uitsplitsing = ga.datasets_per_soort(recs)
        assert sum(d["aantal"] for d in uitsplitsing) == len(recs)


def test_sortering_is_aflopend_op_aantal(records):
    uitsplitsing = ga.datasets_per_soort(_van_soort(records, SOORT_A))
    aantallen = [d["aantal"] for d in uitsplitsing]
    assert aantallen == sorted(aantallen, reverse=True)
    assert [d["dataset_key"] for d in uitsplitsing] == [DS_WNM, DS_EBIRD, DS_ONBEKEND]
    assert aantallen == [7, 4, 2]


def test_laatste_jaar_per_dataset(records):
    per = {d["dataset_key"]: d for d in ga.datasets_per_soort(_van_soort(records, SOORT_A))}
    assert per[DS_WNM]["laatste_jaar"] == 2024
    assert per[DS_EBIRD]["laatste_jaar"] == 2022
    assert per[DS_ONBEKEND]["laatste_jaar"] == 2021


def test_records_zonder_datasetkey_krijgen_vraagteken():
    uit = ga.datasets_per_soort([{"speciesKey": 1, "year": 2024}, {"speciesKey": 1, "datasetKey": DS_WNM, "year": 2024}])
    assert {d["dataset_key"] for d in uit} == {"?", DS_WNM}
    assert sum(d["aantal"] for d in uit) == 2


def test_namen_worden_aangevuld_uit_tabel():
    recs = [{"speciesKey": 1, "datasetKey": DS_EBIRD, "year": 2024}]
    uit = ga.datasets_per_soort(recs, namen={DS_EBIRD: "EOD – eBird Observation Dataset"})
    assert uit[0]["dataset"] == "EOD – eBird Observation Dataset"


def test_afkorting_bekend_en_terugval():
    assert afkorting(DS_WNM) == "wnm.be-gewervelden"
    assert afkorting(DS_EBIRD, "EOD – eBird Observation Dataset") == "eBird"
    lang = afkorting(DS_ONBEKEND, "Een heel lange datasetnaam die zeker meer dan dertig tekens telt")
    assert lang.startswith("Een heel lange datasetnaam die") and lang.endswith("…") and len(lang) <= 31
    assert afkorting(DS_ONBEKEND) == DS_ONBEKEND[:8]


def test_compacte_notatie_zonder_puntkomma(records):
    tekst = compact(ga.datasets_per_soort(_van_soort(records, SOORT_A)))
    assert tekst.startswith("wnm.be-gewervelden 7 / eBird 4 / ")
    assert ";" not in tekst


def _analyse(gebied: Gebied) -> ga.Analyse:
    return ga.Analyse(
        geraadpleegd_op="2026-09-17T12:00:00+02:00", gebied=gebied, codes=[], totaal_waarnemingen=20, aantal_soorten=2,
        regels=[], per_dataset=[], gbif_parameters={}, zoek_url="https://example.invalid", lijstversies={}, legende={},
        waarschuwingen=[], ontbrekend=[], exoot_keys=set(),
    )


def _verrijk(records, *, per_dataset_per_soort, monkeypatch) -> list[ga.SoortRegel]:
    async def nep_records(keys, **kw):
        return records, True, []

    monkeypatch.setattr(gbif, "records_in_gebied", nep_records)
    gebied = Gebied(wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))", omschrijving="test", centrum=(51.05, 3.77), straal_m=500)
    an = _analyse(gebied)
    regels = [ga.SoortRegel(key=SOORT_A, aantal=13), ga.SoortRegel(key=SOORT_B, aantal=7)]
    asyncio.run(ga.verrijk_met_records(an, regels, jaar_van=None, jaar_tot=None, budget_s=5, per_dataset_per_soort=per_dataset_per_soort))
    return regels


def test_uitsplitsing_sluit_aan_op_aantal_waarnemingen(records, monkeypatch):
    regels = _verrijk(records, per_dataset_per_soort=True, monkeypatch=monkeypatch)
    for r in regels:
        assert r.datasets is not None
        assert sum(d["aantal"] for d in r.datasets) == r.aantal


def test_zonder_vlag_blijft_de_uitvoer_ongewijzigd(records, monkeypatch):
    met = _verrijk(records, per_dataset_per_soort=True, monkeypatch=monkeypatch)
    zonder = _verrijk(records, per_dataset_per_soort=False, monkeypatch=monkeypatch)
    for r in zonder:
        assert r.datasets is None
        assert ga.naar_uitvoer(r, detail=False).datasets is None
    # Alle andere velden zijn identiek met en zonder de vlag.
    velden = ("key", "aantal", "laatste_jaar", "onz_max", "onz_med", "zeker", "broed", "exoot", "twijfel")
    assert [tuple(getattr(r, v) for v in velden) for r in met] == [tuple(getattr(r, v) for v in velden) for r in zonder]
    # En de JSON-uitvoer verschilt enkel in het veld `datasets`.
    a = ga.naar_uitvoer(met[0], detail=False).model_dump()
    b = ga.naar_uitvoer(zonder[0], detail=False).model_dump()
    a.pop("datasets"), b.pop("datasets")
    assert a == b


def test_tabelkolom_datasets(records, monkeypatch):
    regels = _verrijk(records, per_dataset_per_soort=True, monkeypatch=monkeypatch)
    for r in regels:
        r.soort = None
    zonder = ga.naar_tabel(regels, met_straal=True, met_datasets=False)
    met = ga.naar_tabel(regels, met_straal=True, met_datasets=True)
    assert "datasets" not in zonder.splitlines()[0]
    assert met.splitlines()[0].rstrip().endswith("datasets |")
    assert "wnm.be-gewervelden 7 / eBird 4" in met


def test_verificatiestatus_wordt_letterlijk_overgenomen():
    w = gbif._waarneming(_record(1, SOORT_A, DS_WNM, 2024, identificationVerificationStatus="approved on expert judgement"))
    assert w.verificatiestatus == "approved on expert judgement"
    assert gbif._waarneming(_record(2, SOORT_A, DS_EBIRD, 2024)).verificatiestatus is None


def test_telling_verificatiestatus():
    from gbif_mcp.server import _tel_verificatie

    lijst = [
        gbif._waarneming(_record(1, SOORT_A, DS_WNM, 2024, identificationVerificationStatus="unverified")),
        gbif._waarneming(_record(2, SOORT_A, DS_WNM, 2024, identificationVerificationStatus="unverified")),
        gbif._waarneming(_record(3, SOORT_A, DS_EBIRD, 2024)),
    ]
    assert _tel_verificatie(lijst) == {"unverified": 2, "(leeg)": 1}
