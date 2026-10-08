# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Beschermde gebieden rond een punt of polygoon: Natura 2000, VEN/IVON, natuurbeheerplannen, HPG,
erfgoed, BWK … via de WFS-diensten van het Departement Omgeving (Mercator), Digitaal Vlaanderen (BWK) en INBO
(ecotoopkwetsbaarheid).

Werkt intern in Lambert 72 (EPSG:31370) zodat afstanden metrisch zijn. Per laag: ALLE gebieden of
eenheden binnen de straal, met afstand (0 = overlap), gesorteerd met de overlappende eerst. Dat geldt
voor elke laag, ook voor de BWK, die heel Vlaanderen dekt: het punt ligt daar vrijwel altijd in een
eenheid, en de waardevolle eenheden ernaast moeten zichtbaar blijven. Een laag die niet antwoordt,
wordt als `niet_geraadpleegd` gerapporteerd, nooit als afwezig.

Ophalen: BBOX rond het doel (straal + marge). Paginering met STARTINDEX is bij deze diensten niet
betrouwbaar (vastgesteld 7 oktober 2026 op BWK:Bwkhab: features dubbel of weggelaten tussen pagina's,
met of zonder SORTBY). Daarom: één oproep met een ruime COUNT; is die pagina vol, dan wordt de BBOX in
vier tegels gesplitst en herhaald, met ontdubbeling op feature-id.
Laaginventaris en werkende query-vorm: docs/gebieden-lagen.md (17 september 2026).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from pyproj import Transformer
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely import wkt as shapely_wkt

from . import bwk, ecokwets
from .http import get_json, nu_iso
from .schema import GebiedTreffer, GebiedenLaag

MERCATOR = "https://www.mercator.vlaanderen.be/raadpleegdienstenmercatorpubliek/ows"
BWK = "https://geo.api.vlaanderen.be/BWK/wfs"
ECOKWETS = ecokwets.DIENST

_naar_l72 = Transformer.from_crs("EPSG:4326", "EPSG:31370", always_xy=True)


@dataclass(frozen=True)
class Laag:
    code: str
    naam: str
    dienst: str
    typename: str
    geom: str
    naamvelden: tuple[str, ...]
    codeveld: str | None = None
    extra: tuple[str, ...] = ()
    groep: str = "natuur"  # natura2000 | natuur | beheer | erfgoed | bwk | ecotoop
    max_features: int = 1000  # paginagrootte (COUNT) per oproep; een volle pagina wordt in tegels gesplitst
    uitvoerformaat: str = "application/json"  # de ArcGIS-WFS van INBO aanvaardt alleen 'GEOJSON'
    idveld: str | None = None  # eigenschap met het feature-id wanneer de dienst geen 'id' meegeeft (INBO: GmlID)

    @property
    def url(self) -> str:
        return f"{self.dienst}?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities#{self.typename}"


LAGEN: list[Laag] = [
    Laag("hrl_gebied", "Habitatrichtlijngebied (SBZ-H)", MERCATOR, "ps:ps_hbtrl", "geom", ("naam",), "gebcode", groep="natura2000"),
    Laag("hrl_deelgebied", "Habitatrichtlijn-deelgebied", MERCATOR, "ps:ps_hbtrl_deel", "geom", ("naam", "deelgebied"), "gebcode", groep="natura2000"),
    Laag("vrl_gebied", "Vogelrichtlijngebied (SBZ-V)", MERCATOR, "ps:ps_vglrl", "geom", ("gebnaam",), "na2000code", groep="natura2000"),
    Laag("ramsar", "Ramsar-gebied", MERCATOR, "ps:ps_ramsar", "geom", ("naam_",), "ramsar_no", groep="natura2000"),
    Laag("ven_ivon", "VEN/IVON-gebied", MERCATOR, "ps:ps_ven", "geom", ("naam",), "gebiedsnr", extra=("categorie",), groep="natuur"),
    Laag("nationaal_park", "Natuurkerngebied Nationaal Park", MERCATOR, "ps:ps_nationaleparken", "geom", ("naam",), None, groep="natuur"),
    Laag("natuurreservaat_uitbreiding", "Uitbreidingszone erkend/Vlaams natuurreservaat", MERCATOR, "ps:ps_uznres_anb", "geom", ("resnaam",), "resnr", groep="natuur"),
    Laag("natuurbeheerplan", "Natuurbeheerplan", MERCATOR, "ps:ps_nbhp", "geom", ("naamdossier",), "registratienummer", extra=("type",), groep="beheer"),
    Laag("natuurrichtplan", "Natuurrichtplan", MERCATOR, "lu:lu_nrp", "geom", ("naam",), "code", groep="beheer"),
    Laag("sigma_natuurdoel", "Natuurdoel Sigmaplan", MERCATOR, "lu:lu_ndl_sigma", "geom", ("gebied",), None, groep="beheer"),
    Laag("anb_domein", "Openbaar bos/natuurdomein ANB", MERCATOR, "am:am_patdat", "geom", ("domeinnaam",), None, groep="beheer"),
    Laag("hpg", "Historisch permanent grasland / beschermd grasland", MERCATOR, "ps:ps_hpg_bsch_grsl", "geom", ("statuut",), None, extra=("basis_statuut",), groep="natuur"),
    Laag("poldergrasland", "Poldergrasland", MERCATOR, "ps:ps_pldgrsl", "geom", ("status",), None, groep="natuur"),
    Laag("duinendecreet", "Beschermd duingebied (Duinendecreet)", MERCATOR, "ps:ps_duin", "geom", ("categorie",), None, groep="natuur"),
    Laag("beschermd_landschap", "Beschermd cultuurhistorisch landschap", MERCATOR, "ps:ps_bes_land", "geom", ("naam", "alt_naam"), "aanduid_id", groep="erfgoed"),
    Laag("beschermd_dorpsgezicht", "Beschermd stads- of dorpsgezicht", MERCATOR, "ps:ps_bes_sd_gezicht", "geom", ("naam", "alt_naam"), "aanduid_id", groep="erfgoed"),
    Laag("beschermd_monument", "Beschermd monument", MERCATOR, "ps:ps_bes_monument", "geom", ("naam", "alt_naam"), "aanduid_id", groep="erfgoed"),
    Laag("bwk_habitat", "BWK 2 — BWK-zone en Natura 2000-habitat (Bwkhab)", BWK, "BWK:Bwkhab", "SHAPE", ("BWKLABEL",), "UIDN", extra=("EVAL", "HAB1", "PHAB1", "HAB2", "PHAB2"), groep="bwk"),
    Laag("bwk_fauna", "BWK 2 — faunistisch belangrijk gebied", BWK, "BWK:Bwkfauna", "SHAPE", ("FAUNAID",), None, groep="bwk"),
    Laag("bwk_3260", "BWK 2 — habitattype 3260 (waterlopen)", BWK, "BWK:Hab3260", "SHAPE", ("NAAM",), None, extra=("BRON",), groep="bwk"),
    # De drie INBO-lagen (verdroging, eutrofiering, verzuring) hebben dezelfde polygonen en velden; één laag volstaat.
    Laag("ecotoopkwetsbaarheid", "Ecotoopkwetsbaarheid (INBO): verdroging, eutrofiëring, verzuring", ECOKWETS,
         "Ecotoopkwetsbaarheid:verdroging", "Shape", ("label_BWK_eenheden",), "TAG", groep="ecotoop",
         uitvoerformaat="GEOJSON", idveld="GmlID"),
]
PER_CODE = {l.code: l for l in LAGEN}
GROEPEN = {
    "natura2000": [l.code for l in LAGEN if l.groep == "natura2000"],
    "natuur": [l.code for l in LAGEN if l.groep == "natuur"],
    "beheer": [l.code for l in LAGEN if l.groep == "beheer"],
    "erfgoed": [l.code for l in LAGEN if l.groep == "erfgoed"],
    "bwk": [l.code for l in LAGEN if l.groep == "bwk"],
    "ecotoop": [l.code for l in LAGEN if l.groep == "ecotoop"],
}


def ontleed_lagen(filter_: str | None) -> list[Laag]:
    if not filter_:
        return list(LAGEN)
    uit: list[Laag] = []
    for deel in (d.strip() for d in filter_.split(",")):
        if deel in GROEPEN:
            uit.extend(PER_CODE[c] for c in GROEPEN[deel])
        elif deel in PER_CODE:
            uit.append(PER_CODE[deel])
        elif deel:
            raise ValueError(f"Onbekende laag- of groepscode '{deel}'. Geldig: {', '.join(list(GROEPEN) + list(PER_CODE))}")
    return list(dict.fromkeys(uit))


def naar_lambert(geom_wgs84: BaseGeometry) -> BaseGeometry:
    from shapely.ops import transform

    return transform(_naar_l72.transform, geom_wgs84)


def doelgeometrie(*, lat: float | None, lon: float | None, wkt: str | None) -> tuple[BaseGeometry, str]:
    """Punt of polygoon (WGS84-invoer) -> Lambert 72-geometrie + omschrijving."""
    from shapely.geometry import Point

    if wkt:
        g = shapely_wkt.loads(wkt)
        return naar_lambert(g), f"polygoon (WKT, {g.geom_type})"
    if lat is None or lon is None:
        raise ValueError("Geef `adres`, `lat`/`lon` of `wkt`.")
    x, y = _naar_l72.transform(lon, lat)
    return Point(x, y), f"punt {lat:.5f} N / {lon:.5f} O (Lambert 72 x {x:.2f} / y {y:.2f})"


MARGE_M = 10.0
MAX_SPLITSDIEPTE = 4


def feature_url(laag: Laag, fid: str | None) -> str | None:
    """WFS-oproep die precies deze ene feature teruggeeft."""
    if not fid:
        return None
    return (f"{laag.dienst}?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES={laag.typename}"
            f"&RESOURCEID={fid}&OUTPUTFORMAT={laag.uitvoerformaat}&SRSNAME=EPSG:31370")


def _sleutel(f: dict) -> str:
    import json

    # Zonder feature-id: eigenschappen én geometrie, zodat twee verschillende vlakken met dezelfde attributen
    # niet samenvallen.
    return str(f.get("id") or json.dumps([f.get("properties") or {}, f.get("geometry")], sort_keys=True, default=str))


async def haal_features(laag: Laag, doel: BaseGeometry, straal_m: float) -> tuple[list[dict], str | None, str | None]:
    """Alle ruwe WFS-features in de BBOX rond het doel (Lambert 72), ontdubbeld.
    Geeft (features, melding_onvolledig, foutmelding)."""
    minx, miny, maxx, maxy = doel.bounds
    r = straal_m + MARGE_M
    gezien: dict[str, dict] = {}
    onvolledig: list[str] = []

    async def _tegel(b: tuple[float, float, float, float], diepte: int) -> None:
        params = {
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": laag.typename,
            "OUTPUTFORMAT": laag.uitvoerformaat, "SRSNAME": "EPSG:31370", "COUNT": laag.max_features,
            "BBOX": f"{b[0]:.2f},{b[1]:.2f},{b[2]:.2f},{b[3]:.2f},EPSG:31370",
        }
        d = await get_json(laag.dienst, params, ttl=1800)
        feats = d.get("features") or []
        for f in feats:
            if not f.get("id") and laag.idveld and (f.get("properties") or {}).get(laag.idveld):
                f["id"] = str(f["properties"][laag.idveld])
            gezien.setdefault(_sleutel(f), f)
        if len(feats) < laag.max_features:
            return
        if diepte >= MAX_SPLITSDIEPTE:
            onvolledig.append(f"tegel {b[0]:.0f},{b[1]:.0f},{b[2]:.0f},{b[3]:.0f} gaf een volle pagina ({len(feats)}) "
                              f"na {diepte} splitsingen")
            return
        mx, my = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        for t in ((b[0], b[1], mx, my), (mx, b[1], b[2], my), (b[0], my, mx, b[3]), (mx, my, b[2], b[3])):
            await _tegel(t, diepte + 1)

    try:
        await _tegel((minx - r, miny - r, maxx + r, maxy + r), 0)
    except Exception as e:
        return [], None, f"{type(e).__name__}: {str(e)[:160]}"
    melding = ("WFS-bevraging mogelijk onvolledig: " + "; ".join(onvolledig) + ".") if onvolledig else None
    return list(gezien.values()), melding, None


def beschrijf(laag: Laag, f: dict) -> tuple[str | None, str | None, dict[str, str]]:
    """Naam, code en extra velden van één feature, volgens de veldafspraken van de laag."""
    props = f.get("properties") or {}
    naam = " — ".join(str(props[v]) for v in laag.naamvelden if props.get(v) not in (None, "")) or None
    code = str(props[laag.codeveld]) if laag.codeveld and props.get(laag.codeveld) not in (None, "") else None
    extra = {k: str(props[k]) for k in laag.extra if props.get(k) not in (None, "")}
    # Lagen zonder naamveld tonen een statuutwaarde ('verbod'); zonder context leest dat als een naam.
    if naam and laag.code in ("hpg", "poldergrasland", "duinendecreet"):
        naam = f"perceel met statuut '{naam}'"
    return naam, code, extra


def toon_op_kaart(laag: Laag, f: dict, overlapt: bool) -> bool:
    """Of een feature op de kaart hoort. BWK: eenheden zonder habitat, rbb of waardevol element alleen bij overlap."""
    if laag.code == "bwk_habitat":
        return bwk.toon_op_kaart(f.get("properties") or {}, overlapt)
    return True


async def bevraag_laag(laag: Laag, doel: BaseGeometry, straal_m: float, max_treffers: int) -> GebiedenLaag:
    """Eén WFS-laag: alle features in de BBOX, dan exacte afstand/overlap met shapely; alles binnen de straal blijft."""
    geraadpleegd = nu_iso()
    feats, onvolledig, fout = await haal_features(laag, doel, straal_m)
    if fout is not None:
        return GebiedenLaag(laag=laag.code, naam=laag.naam, url=laag.url, geraadpleegd_op=geraadpleegd, status="niet_geraadpleegd",
                            melding=fout, treffers=[])
    treffers: list[GebiedTreffer] = []
    for f in feats:
        try:
            g = shape(f["geometry"])
        except Exception:
            continue
        props = f.get("properties") or {}
        naam, code, extra = beschrijf(laag, f)
        overlapt = g.intersects(doel)
        afstand = 0.0 if overlapt else float(g.distance(doel))
        if afstand > straal_m:
            continue
        opp = None
        if g.geom_type in ("Polygon", "MultiPolygon"):
            opp = round(g.area / 10_000, 2)
        treffers.append(GebiedTreffer(
            naam=naam, code=code, overlapt=overlapt, afstand_m=round(afstand), oppervlakte_ha=opp, extra=extra,
            id=f.get("id"), url=feature_url(laag, f.get("id")),
            bwk=bwk.eenheid(props) if laag.code == "bwk_habitat" else None,
            ecotoop=ecokwets.eenheid(props) if laag.code == "ecotoopkwetsbaarheid" else None,
        ))
    treffers.sort(key=lambda t: (not t.overlapt, t.afstand_m))
    meldingen = [onvolledig] if onvolledig else []
    teruggegeven = treffers[:max(0, max_treffers)]
    if len(treffers) > len(teruggegeven):
        meldingen.append(f"{len(treffers)} {'eenheden' if laag.groep in ('bwk', 'ecotoop') else 'gebieden'} binnen {straal_m:.0f} m, "
                         f"{len(teruggegeven)} teruggegeven (max_treffers_per_laag); verhoog die waarde voor de volledige lijst.")
    return GebiedenLaag(
        laag=laag.code, naam=laag.naam, url=laag.url, geraadpleegd_op=geraadpleegd, status="ok",
        aantal_overlappend=sum(1 for t in treffers if t.overlapt), aantal_binnen_straal=len(treffers),
        aantal_teruggegeven=len(teruggegeven), treffers=teruggegeven, melding=" ".join(meldingen) or None,
        samenvatting_bwk=bwk.samenvatting(treffers) if laag.code == "bwk_habitat" else None,
        samenvatting_ecotoop=ecokwets.samenvatting(treffers) if laag.code == "ecotoopkwetsbaarheid" else None,
    )


async def gebieden_rond(doel: BaseGeometry, lagen: list[Laag], straal_m: float, max_treffers: int, parallel: int = 4) -> list[GebiedenLaag]:
    sem = asyncio.Semaphore(parallel)

    async def _een(l: Laag) -> GebiedenLaag:
        async with sem:
            return await bevraag_laag(l, doel, straal_m, max_treffers)

    return list(await asyncio.gather(*(_een(l) for l in lagen)))
