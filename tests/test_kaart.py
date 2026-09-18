"""Tests voor de situeringskaart (gbif_mcp/kaart.py). Geen netwerk: WMS en WFS zijn gemockt."""
from __future__ import annotations

import asyncio
import io

import pytest
from PIL import Image
from shapely.geometry import Point, Polygon

from gbif_mcp import gebieden as gb
from gbif_mcp import kaart

# Testpunt in Lambert 72 (Bourgoyen, Gent) en een vierkant vlak eromheen.
X, Y = 101896.22, 195418.48


def _vlak(dx: float, dy: float, zijde: float = 200.0) -> dict:
    x, y = X + dx, Y + dy
    h = zijde / 2
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[[x - h, y - h], [x + h, y - h], [x + h, y + h], [x - h, y + h], [x - h, y - h]]]},
        "properties": {"naam": f"Testgebied {dx:.0f}/{dy:.0f}", "gebiedsnr": "42", "categorie": "gen", "HAB1": "6510"},
    }


def _png(kleur=(200, 200, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), kleur).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def geen_netwerk(monkeypatch):
    """WFS geeft twee vlakken voor ven_ivon, niets voor de rest; WMS geeft een grijze afbeelding."""

    async def nep_features(laag, doel, straal_m):
        if laag.code == "ven_ivon":
            return [_vlak(0, 0), _vlak(600, 0)], 2, None
        if laag.code == "hpg":
            return [], None, "TimeoutException: bron antwoordde niet"
        return [], 0, None

    async def nep_achtergrond(bbox, breedte, hoogte):
        return Image.new("RGBA", (breedte, hoogte), (230, 230, 230, 255))

    monkeypatch.setattr(gb, "haal_features", nep_features)
    monkeypatch.setattr(kaart, "achtergrond", nep_achtergrond)


_teller = 0


def _teken(tmp_path, lagen=("ven_ivon", "hpg", "ramsar"), **kw) -> dict:
    global _teller
    _teller += 1
    doel = Point(X, Y)
    keuze = [gb.PER_CODE[c] for c in lagen]
    pad = str(tmp_path / f"kaart{_teller}.png")  # elke oproep een eigen bestand
    return asyncio.run(kaart.teken(doel, keuze, straal_m=1000, pad=pad, breedte_px=800, **kw))


def test_kaart_wordt_geschreven_en_is_leesbaar(tmp_path, geen_netwerk):
    meta = _teken(tmp_path)
    with Image.open(meta["pad"]) as im:
        assert im.width == 800
        assert im.height >= 800  # legende komt eronder
    assert meta["breedte_px"] == 800
    assert meta["achtergrond"].startswith("GRB")


def test_bbox_is_vierkant_en_omvat_de_straal(tmp_path, geen_netwerk):
    meta = _teken(tmp_path)
    minx, miny, maxx, maxy = meta["bbox_lambert72"]
    assert maxx - minx == pytest.approx(maxy - miny)
    assert maxx - minx == pytest.approx(2 * 1000 * 1.25, rel=1e-6)
    assert minx < X < maxx and miny < Y < maxy


def test_legende_telt_alleen_zichtbare_lagen(tmp_path, geen_netwerk):
    meta = _teken(tmp_path)
    per_code = {l["laag"]: l for l in meta["legende"]}
    assert per_code["ven_ivon"]["aantal_vlakken"] == 2
    assert per_code["ven_ivon"]["status"] == "ok"
    # ramsar gaf niets terug en hoort niet in de legende; hpg faalde en hoort er wél in
    assert "ramsar" not in per_code
    assert per_code["hpg"]["status"] == "niet_geraadpleegd"
    assert meta["niet_geraadpleegd"] == ["hpg"]
    assert per_code["_zoek"]["kleur"] == "#c81e1e"


def test_vlakken_buiten_de_straal_vallen_weg(tmp_path, monkeypatch):
    async def ver_weg(laag, doel, straal_m):
        return ([_vlak(5000, 0)], 1, None) if laag.code == "ven_ivon" else ([], 0, None)

    async def nep_achtergrond(bbox, breedte, hoogte):
        return Image.new("RGBA", (breedte, hoogte), (255, 255, 255, 255))

    monkeypatch.setattr(gb, "haal_features", ver_weg)
    monkeypatch.setattr(kaart, "achtergrond", nep_achtergrond)
    meta = _teken(tmp_path, lagen=("ven_ivon",))
    assert not [l for l in meta["legende"] if l["laag"] == "ven_ivon"]


def test_zonder_achtergrond_wordt_de_kaart_toch_getekend(tmp_path, monkeypatch):
    async def nep_features(laag, doel, straal_m):
        return ([_vlak(0, 0)], 1, None) if laag.code == "ven_ivon" else ([], 0, None)

    async def stukke_wms(bbox, breedte, hoogte):
        raise RuntimeError("WMS gaf geen afbeelding")

    monkeypatch.setattr(gb, "haal_features", nep_features)
    monkeypatch.setattr(kaart, "achtergrond", stukke_wms)
    meta = _teken(tmp_path, lagen=("ven_ivon",))
    assert meta["achtergrond"] == "geen"
    assert "GRB-basiskaart niet opgehaald" in meta["melding"]


def test_legende_kan_uit_de_afbeelding_blijven(tmp_path, geen_netwerk):
    met = _teken(tmp_path, met_legende=True)
    zonder = _teken(tmp_path, met_legende=False)
    with Image.open(met["pad"]) as a, Image.open(zonder["pad"]) as b:
        assert a.height > 800 and b.height == 800
    assert zonder["hoogte_px"] == 800 and met["hoogte_px"] > 800
    assert zonder["legende_in_afbeelding"] is False
    # de legendegegevens blijven wél beschikbaar voor opmaak in het document zelf
    assert any(l["laag"] == "ven_ivon" for l in zonder["legende"])


def test_projectie_zet_lambert72_om_naar_pixels():
    naar_pixel = kaart._projector((0.0, 0.0, 1000.0, 1000.0), 500, 500)
    assert naar_pixel(0, 0) == (0.0, 500.0)  # linksonder
    assert naar_pixel(1000, 1000) == (500.0, 0.0)  # rechtsboven
    assert naar_pixel(500, 500) == (250.0, 250.0)


def test_ringen_van_polygoon_en_multipolygoon():
    p = Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])
    assert len(kaart._ringen(p)) == 1
    from shapely.geometry import MultiPolygon

    m = MultiPolygon([p, Polygon([(5, 5), (6, 5), (6, 6), (5, 5)])])
    assert len(kaart._ringen(m)) == 2


def test_bwk_gh_alleen_bij_overlap():
    laag = gb.PER_CODE["bwk_habitat"]
    gh = {"properties": {"HAB1": "gh"}}
    echt = {"properties": {"HAB1": "6510"}}
    assert gb.toon_op_kaart(laag, gh, overlapt=True) is True
    assert gb.toon_op_kaart(laag, gh, overlapt=False) is False
    assert gb.toon_op_kaart(laag, echt, overlapt=False) is True
    assert gb.toon_op_kaart(gb.PER_CODE["ven_ivon"], gh, overlapt=False) is True


def test_nummers_en_arceringen_per_zichtbare_laag(tmp_path, monkeypatch):
    """Kleur mag nooit de enige drager zijn: elke zichtbare laag krijgt een nummer en een arcering."""

    async def twee_lagen(laag, doel, straal_m):
        return ([_vlak(0, 0)], 1, None) if laag.code in ("ven_ivon", "ramsar") else ([], 0, None)

    async def nep_achtergrond(bbox, breedte, hoogte):
        return Image.new("RGBA", (breedte, hoogte), (255, 255, 255, 255))

    monkeypatch.setattr(gb, "haal_features", twee_lagen)
    monkeypatch.setattr(kaart, "achtergrond", nep_achtergrond)
    meta = _teken(tmp_path, lagen=("ven_ivon", "ramsar", "hpg"))
    zichtbaar = [l for l in meta["legende"] if l["laag"] != "_zoek" and l["status"] == "ok"]
    assert [l["nummer"] for l in zichtbaar] == [1, 2]
    assert len({l["arcering"] for l in zichtbaar}) == 2
    assert all(l["arcering"] in kaart.ARCERINGEN for l in zichtbaar)


def test_palet_is_kleurenblindvriendelijk():
    # Okabe-Ito; geen rood-groen-paar dat bij deuteranopie samenvalt.
    assert kaart.PALET is kaart.OKABE_ITO
    assert (0, 114, 178) in kaart.OKABE_ITO and (230, 159, 0) in kaart.OKABE_ITO
    assert len(set(kaart.OKABE_ITO)) == 8


def test_arcering_blijft_binnen_het_vlak():
    beeld = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
    driehoek = [(5.0, 5.0), (55.0, 5.0), (5.0, 55.0)]
    kaart._arceer(beeld, driehoek, "kruis", (0, 0, 0), stap=6, dikte=1)
    # rechtsonder ligt buiten de driehoek en moet leeg blijven
    assert beeld.getpixel((50, 50))[3] == 0
    assert any(beeld.getpixel((x, 10))[3] > 0 for x in range(8, 40))


def test_arcering_knipt_af_op_de_kaartuitsnede():
    """Een vlak dat ver buiten het beeld ligt, mag geen reusachtig tussenbeeld opbouwen."""
    beeld = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
    enorm = [(-40000.0, -40000.0), (40000.0, -40000.0), (40000.0, 40000.0), (-40000.0, 40000.0)]
    kaart._arceer(beeld, enorm, "schuin", (0, 0, 0), stap=6, dikte=1)  # mag niet ontploffen
    assert any(beeld.getpixel((x, y))[3] > 0 for x in range(50) for y in range(50))


def test_groot_vlak_krijgt_zijn_nummer_binnen_beeld(tmp_path, monkeypatch):
    """Een gebied dat de hele uitsnede beslaat, moet toch een leesbaar nummer krijgen."""

    async def enorm(laag, doel, straal_m):
        if laag.code != "ven_ivon":
            return [], 0, None
        h = 20000.0  # veel groter dan de kaartuitsnede
        ring = [[X - h, Y - h], [X + h, Y - h], [X + h, Y + h], [X - h, Y + h], [X - h, Y - h]]
        return [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": {"naam": "Groot"}}], 1, None

    async def wit(bbox, breedte, hoogte):
        return Image.new("RGBA", (breedte, hoogte), (255, 255, 255, 255))

    monkeypatch.setattr(gb, "haal_features", enorm)
    monkeypatch.setattr(kaart, "achtergrond", wit)
    meta = _teken(tmp_path, lagen=("ven_ivon",))
    assert [l["nummer"] for l in meta["legende"] if l["laag"] == "ven_ivon"] == [1]
    with Image.open(meta["pad"]) as im:
        midden = im.convert("L").crop((300, 300, 500, 500))
    # zwarte cijfertekst met witte rand => donkere pixels in het midden van de kaart
    assert min(midden.getdata()) < 90
