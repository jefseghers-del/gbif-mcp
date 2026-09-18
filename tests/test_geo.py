"""Tests voor gbif_mcp/geo.py: geometrieberekeningen, geen netwerk nodig."""
from __future__ import annotations

import asyncio
import math

import pytest

from gbif_mcp import geo
from gbif_mcp.geo import _ccw, bepaal_gebied, cirkel_wkt, geocodeer, geojson_naar_wkt, vereenvoudig


def test_cirkel_wkt_is_gesloten_en_telt_n_plus_1_punten():
    wkt = cirkel_wkt(51.05, 3.72, 500.0, n=36)
    assert wkt.startswith("POLYGON((") and wkt.endswith("))")
    binnen = wkt[len("POLYGON((") : -2]
    punten = [tuple(map(float, p.split())) for p in binnen.split(",")]
    assert len(punten) == 37  # n + het herhaalde startpunt
    assert punten[0] == punten[-1]


def test_cirkel_wkt_is_tegenwijzerzin():
    # GBIF verlangt tegenwijzerzin (counter-clockwise); shoelace-oppervlakte moet positief zijn
    # in een normaal (niet-geografisch gespiegeld) assenstelsel met x=lon, y=lat.
    wkt = cirkel_wkt(51.05, 3.72, 500.0, n=36)
    binnen = wkt[len("POLYGON((") : -2]
    punten = [tuple(map(float, p.split())) for p in binnen.split(",")]
    oppervlakte2 = sum(
        (x2 - x1) * (y2 + y1) for (x1, y1), (x2, y2) in zip(punten, punten[1:])
    )
    assert oppervlakte2 < 0  # negatief = tegenwijzerzin, cf. _ccw()


def test_vereenvoudig_verwijdert_collineaire_punten_en_behoudt_eindpunten():
    # Rechte lijn met een tussenpunt exact erop: Douglas-Peucker moet dat tussenpunt weglaten.
    punten = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (2.0, 1.0)]
    resultaat = vereenvoudig(punten, tolerantie=0.0001)
    assert resultaat[0] == punten[0]
    assert resultaat[-1] == punten[-1]
    assert (1.0, 0.0) not in resultaat


def test_vereenvoudig_behoudt_significante_afwijking():
    # Een duidelijke uitstulping (piek) mag niet wegvallen bij een kleine tolerantie.
    punten = [(0.0, 0.0), (1.0, 1.0), (2.0, 0.0)]
    resultaat = vereenvoudig(punten, tolerantie=0.01)
    assert (1.0, 1.0) in resultaat


def test_ccw_draait_wijzerzin_om():
    # Wijzerzin-vierkant (positieve shoelace-som) moet omgedraaid worden.
    wijzerzin = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)]
    opp_voor = sum((x2 - x1) * (y2 + y1) for (x1, y1), (x2, y2) in zip(wijzerzin, wijzerzin[1:]))
    assert opp_voor > 0  # bevestigt dat de testring effectief wijzerzin is
    resultaat = _ccw(wijzerzin)
    opp_na = sum((x2 - x1) * (y2 + y1) for (x1, y1), (x2, y2) in zip(resultaat, resultaat[1:]))
    assert opp_na < 0


def test_ccw_laat_reeds_tegenwijzerzin_ring_ongemoeid():
    tegenwijzerzin = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
    assert _ccw(tegenwijzerzin) == tegenwijzerzin


def _vierkant(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def test_geojson_naar_wkt_polygon():
    geom = {"type": "Polygon", "coordinates": [_vierkant(3.0, 51.0, 3.1, 51.1)]}
    wkt = geojson_naar_wkt(geom)
    assert wkt.startswith("POLYGON((")
    assert wkt.count("MULTIPOLYGON") == 0


def test_geojson_naar_wkt_multipolygon():
    geom = {
        "type": "MultiPolygon",
        "coordinates": [
            [_vierkant(3.0, 51.0, 3.1, 51.1)],
            [_vierkant(4.0, 50.0, 4.1, 50.1)],
        ],
    }
    wkt = geojson_naar_wkt(geom)
    assert wkt.startswith("MULTIPOLYGON(")
    assert wkt.count("((") == 2


def _fake_location_result(location_type: str) -> dict:
    return {
        "LocationResult": [
            {
                "Location": {"Lat_WGS84": 51.06691, "Lon_WGS84": 3.68249, "X_Lambert72": 101896, "Y_Lambert72": 195419},
                "LocationType": location_type,
                "FormattedAddress": "Kortrijksesteenweg, Gent",
                "Municipality": "Gent",
                "Zipcode": "9000",
            }
        ]
    }


def test_geocodeer_waarschuwt_bij_straat_zonder_huisnummer(monkeypatch: pytest.MonkeyPatch):
    async def _fake_get_json(url, params=None, *, ttl=3600):
        return _fake_location_result("basisregisters_straat")

    monkeypatch.setattr(geo, "get_json", _fake_get_json)
    loc = asyncio.run(geocodeer("Kortrijksesteenweg, Gent"))
    assert loc is not None
    assert loc.waarschuwing is not None
    assert "huisnummer" in loc.waarschuwing.lower()


def test_geocodeer_geen_waarschuwing_bij_huisnummer(monkeypatch: pytest.MonkeyPatch):
    async def _fake_get_json(url, params=None, *, ttl=3600):
        return _fake_location_result("basisregisters_huisnummer_lijnid")

    monkeypatch.setattr(geo, "get_json", _fake_get_json)
    loc = asyncio.run(geocodeer("Kortrijksesteenweg 100, Gent"))
    assert loc is not None
    assert loc.waarschuwing is None


def test_bepaal_gebied_met_lat_lon_zet_centrum_en_straal():
    gebied = asyncio.run(bepaal_gebied(adres=None, lat=51.06691, lon=3.68249, straal_m=300.0, wkt=None, gemeente=None))
    assert gebied.centrum == (51.06691, 3.68249)
    assert gebied.straal_m == 300.0
    assert gebied.wkt is not None


def test_geojson_naar_wkt_valt_onder_max_tekens():
    # Complexe ring (veel punten, geen twee collineair) forceert oplopende tolerantie
    # tot de WKT binnen de grens past.
    n = 500
    ring = [
        [3.0 + 0.01 * math.cos(2 * math.pi * i / n), 51.0 + 0.01 * math.sin(2 * math.pi * i / n)]
        for i in range(n)
    ]
    ring.append(ring[0])
    geom = {"type": "Polygon", "coordinates": [ring]}
    wkt = geojson_naar_wkt(geom, tolerantie=0.0001, max_tekens=500)
    assert len(wkt) <= 500
