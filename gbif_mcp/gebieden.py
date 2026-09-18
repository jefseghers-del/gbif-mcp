"""Beschermde gebieden rond een punt of polygoon: Natura 2000, VEN/IVON, natuurbeheerplannen, HPG,
erfgoed, BWK … via de WFS-diensten van het Departement Omgeving (Mercator) en Digitaal Vlaanderen (BWK).

Werkt intern in Lambert 72 (EPSG:31370) zodat afstanden metrisch zijn. Per laag: welke gebieden het
punt/de polygoon overlappen, en anders de dichtstbijzijnde binnen de straal. Een laag die niet
antwoordt, wordt als `niet_geraadpleegd` gerapporteerd, nooit als afwezig.
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

from .http import get_json, nu_iso
from .schema import GebiedTreffer, GebiedenLaag

MERCATOR = "https://www.mercator.vlaanderen.be/raadpleegdienstenmercatorpubliek/ows"
BWK = "https://geo.api.vlaanderen.be/BWK/wfs"

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
    groep: str = "natuur"  # natura2000 | natuur | beheer | erfgoed | bwk
    max_features: int = 50

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
    Laag("hpg", "Historisch permanent grasland / beschermd grasland", MERCATOR, "ps:ps_hpg_bsch_grsl", "geom", ("statuut",), None, extra=("basis_statuut",), groep="natuur", max_features=100),
    Laag("poldergrasland", "Poldergrasland", MERCATOR, "ps:ps_pldgrsl", "geom", ("status",), None, groep="natuur", max_features=100),
    Laag("duinendecreet", "Beschermd duingebied (Duinendecreet)", MERCATOR, "ps:ps_duin", "geom", ("categorie",), None, groep="natuur"),
    Laag("beschermd_landschap", "Beschermd cultuurhistorisch landschap", MERCATOR, "ps:ps_bes_land", "geom", ("naam", "alt_naam"), "aanduid_id", groep="erfgoed"),
    Laag("beschermd_dorpsgezicht", "Beschermd stads- of dorpsgezicht", MERCATOR, "ps:ps_bes_sd_gezicht", "geom", ("naam", "alt_naam"), "aanduid_id", groep="erfgoed"),
    Laag("beschermd_monument", "Beschermd monument", MERCATOR, "ps:ps_bes_monument", "geom", ("naam", "alt_naam"), "aanduid_id", groep="erfgoed"),
    Laag("bwk_habitat", "BWK 2 — Natura 2000-habitat (Bwkhab)", BWK, "BWK:Bwkhab", "SHAPE", ("HAB1",), None, extra=("PHAB1", "HAB2", "EVAL", "BWKLABEL", "EENH1"), groep="bwk", max_features=300),
    Laag("bwk_fauna", "BWK 2 — faunistisch belangrijk gebied", BWK, "BWK:Bwkfauna", "SHAPE", ("FAUNAID",), None, groep="bwk", max_features=100),
    Laag("bwk_3260", "BWK 2 — habitattype 3260 (waterlopen)", BWK, "BWK:Hab3260", "SHAPE", ("NAAM",), None, extra=("BRON",), groep="bwk"),
]
PER_CODE = {l.code: l for l in LAGEN}
GROEPEN = {
    "natura2000": [l.code for l in LAGEN if l.groep == "natura2000"],
    "natuur": [l.code for l in LAGEN if l.groep == "natuur"],
    "beheer": [l.code for l in LAGEN if l.groep == "beheer"],
    "erfgoed": [l.code for l in LAGEN if l.groep == "erfgoed"],
    "bwk": [l.code for l in LAGEN if l.groep == "bwk"],
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


async def haal_features(laag: Laag, doel: BaseGeometry, straal_m: float) -> tuple[list[dict], int | None, str | None]:
    """Ruwe WFS-features rond het doel (Lambert 72). Geeft (features, numberMatched, foutmelding)."""
    minx, miny, maxx, maxy = doel.bounds
    # DWITHIN op het centroid + straal die de hele doelgeometrie omvat.
    c = doel.centroid
    halve_diag = max(maxx - minx, maxy - miny) / 2
    params = {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": laag.typename,
        "outputFormat": "application/json", "srsName": "EPSG:31370", "count": laag.max_features,
        "CQL_FILTER": f"DWITHIN({laag.geom},POINT({c.x:.2f} {c.y:.2f}),{straal_m + halve_diag:.0f},meters)",
    }
    try:
        d = await get_json(laag.dienst, params, ttl=1800)
    except Exception as e:
        return [], None, f"{type(e).__name__}: {str(e)[:160]}"
    feats = d.get("features") or []
    totaal = d.get("numberMatched") or d.get("totalFeatures")
    return feats, totaal if isinstance(totaal, int) else None, None


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
    """Of een feature op de kaart hoort. BWK-karteringseenheid 'gh' (geen habitat) alleen bij overlap."""
    if laag.code == "bwk_habitat" and not overlapt:
        return str((f.get("properties") or {}).get("HAB1", "")).lower() not in ("gh", "")
    return True


async def bevraag_laag(laag: Laag, doel: BaseGeometry, straal_m: float, max_treffers: int) -> GebiedenLaag:
    """Eén WFS-laag: DWITHIN rond het doel, dan exacte afstand/overlap met shapely."""
    geraadpleegd = nu_iso()
    feats, numberMatched, fout = await haal_features(laag, doel, straal_m)
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
        # BWK: 'gh' = geen habitat; alleen relevant als het doel erin ligt, niet als 'dichtstbijzijnde'.
        if laag.code == "bwk_habitat" and not overlapt and str(props.get("HAB1", "")).lower() in ("gh", ""):
            continue
        opp = None
        if g.geom_type in ("Polygon", "MultiPolygon"):
            opp = round(g.area / 10_000, 2)
        treffers.append(GebiedTreffer(naam=naam, code=code, overlapt=overlapt, afstand_m=round(afstand), oppervlakte_ha=opp, extra=extra))
    treffers.sort(key=lambda t: (not t.overlapt, t.afstand_m))
    totaal = numberMatched if numberMatched is not None else len(feats)
    melding = None
    if isinstance(totaal, int) and totaal > len(feats):
        melding = f"WFS gaf {len(feats)} van {totaal} features (count-limiet); verre treffers kunnen ontbreken."
    return GebiedenLaag(
        laag=laag.code, naam=laag.naam, url=laag.url, geraadpleegd_op=geraadpleegd, status="ok",
        aantal_overlappend=sum(1 for t in treffers if t.overlapt), aantal_binnen_straal=len(treffers),
        treffers=treffers[:max_treffers], melding=melding,
    )


async def gebieden_rond(doel: BaseGeometry, lagen: list[Laag], straal_m: float, max_treffers: int, parallel: int = 4) -> list[GebiedenLaag]:
    sem = asyncio.Semaphore(parallel)

    async def _een(l: Laag) -> GebiedenLaag:
        async with sem:
            return await bevraag_laag(l, doel, straal_m, max_treffers)

    return list(await asyncio.gather(*(_een(l) for l in lagen)))
