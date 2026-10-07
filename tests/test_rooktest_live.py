"""Rooktest tegen de ECHTE GBIF- en INBO-diensten. Staat standaard uit (marker `live`).

Draaien:  pytest -m live
Neutraal adres, geen dossiergegevens.
"""
from __future__ import annotations

import asyncio

import pytest

ADRES = "Kortrijksesteenweg 100, 9000 Gent"
STRAAL = 500
VANAF = 2023

pytestmark = pytest.mark.live


def test_soorten_in_gebied_met_dataset_uitsplitsing():
    from gbif_mcp import server

    r = asyncio.run(
        server.soorten_in_gebied(adres=ADRES, straal_m=STRAAL, jaar_van=VANAF, per_dataset_per_soort=True, max_soorten=25)
    )
    assert r.soorten, "geen soorten teruggekregen"
    met_datasets = [s for s in r.soorten if s.datasets]
    assert met_datasets, "geen enkele soort kreeg een dataset-uitsplitsing"
    for s in met_datasets:
        assert sum(d["aantal"] for d in s.datasets) == s.aantal_waarnemingen
        aantallen = [d["aantal"] for d in s.datasets]
        assert aantallen == sorted(aantallen, reverse=True)
        assert all(d["dataset_key"] for d in s.datasets)


def test_tabel_bevat_datasetkolom():
    from gbif_mcp import server

    r = asyncio.run(
        server.soorten_in_gebied(adres=ADRES, straal_m=STRAAL, jaar_van=VANAF, per_dataset_per_soort=True, formaat="tabel", max_soorten=25)
    )
    assert r.tabel and r.tabel.splitlines()[0].rstrip().endswith("datasets |")


def test_waarnemingen_gefilterd_op_dataset():
    # Beide oproepen in ÉÉN event loop: de httpx-client is een module-singleton die aan de
    # draaiende loop hangt, dus twee keer asyncio.run() in dezelfde test faalt.
    from gbif_mcp import server

    async def scenario():
        alles = await server.waarnemingen("merel", adres=ADRES, straal_m=STRAAL, jaar_van=VANAF, max_resultaten=20)
        assert alles.per_dataset, "geen datasetverdeling"
        sleutel = alles.per_dataset[0]["dataset_key"]
        deel = await server.waarnemingen("merel", adres=ADRES, straal_m=STRAAL, jaar_van=VANAF, max_resultaten=20, dataset_key=sleutel)
        return alles, sleutel, deel

    alles, sleutel, deel = asyncio.run(scenario())
    assert 0 < deel.totaal <= alles.totaal
    assert all(w.dataset_key == sleutel for w in deel.waarnemingen)
    assert deel.per_verificatiestatus


def test_telling_per_dataset():
    from gbif_mcp import server

    async def scenario():
        zonder = await server.telling_in_gebied(adres=ADRES, straal_m=STRAAL, jaar_van=VANAF)
        met = await server.telling_in_gebied(adres=ADRES, straal_m=STRAAL, jaar_van=VANAF, soorten_per_dataset=True)
        return zonder, met

    r, met = asyncio.run(scenario())
    assert r.per_dataset and all("aantal_records" in d for d in r.per_dataset)
    assert all("aantal_soorten_met_status" not in d for d in r.per_dataset), "standaard moet de trage variant uit staan"

    ingevuld = [d for d in met.per_dataset if "aantal_soorten_met_status" in d]
    assert ingevuld and all(d["aantal_soorten_met_status"] <= met.totaal_soorten_met_status for d in ingevuld)


def test_bwk_alle_eenheden_binnen_straal_zoals_rechtstreekse_wfs():
    """`gebieden_rond` (lagen=bwk_habitat, 200 m) telt evenveel eenheden als een rechtstreekse WFS-bevraging.
    Publieke testlocatie: natuurcentrum Bourgoyen-Ossemeersen, Gent (Lambert 72 x 101896 / y 195419)."""
    import httpx
    from shapely.geometry import Point, shape

    from gbif_mcp import gebieden

    x, y, r = 101896, 195419, 200
    d = httpx.get(gebieden.BWK, params={
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": "BWK:Bwkhab", "SRSNAME": "EPSG:31370",
        "BBOX": f"{x - r},{y - r},{x + r},{y + r},EPSG:31370", "OUTPUTFORMAT": "application/json", "COUNT": 1000,
    }, timeout=60).json()
    rechtstreeks = {f["id"] for f in d["features"] if shape(f["geometry"]).distance(Point(x, y)) <= r}
    laag = asyncio.run(gebieden.bevraag_laag(gebieden.PER_CODE["bwk_habitat"], Point(x, y), r, 10_000))
    assert laag.status == "ok"
    assert {t.id for t in laag.treffers} == rechtstreeks
    assert laag.aantal_binnen_straal == len(rechtstreeks)
    assert laag.samenvatting_bwk["locatie_zelf"]
