"""Geografie: adres -> coördinaten (Digitaal Vlaanderen), cirkelbuffer -> WKT, gebiedsomschrijving."""
from __future__ import annotations

import math

from .http import get_json
from .schema import Locatie

GEOLOCATION = "https://geo.api.vlaanderen.be/geolocation/v4/Location"
VRBG_WFS = "https://geo.api.vlaanderen.be/VRBG/wfs"  # Voorlopig Referentiebestand Gemeentegrenzen (Digitaal Vlaanderen)


async def geocodeer(adres: str) -> Locatie | None:
    """Adres of plaatsnaam in Vlaanderen/Brussel -> WGS84-coördinaten via de geolocation-service van Digitaal Vlaanderen."""
    d = await get_json(GEOLOCATION, {"q": adres, "c": 1}, ttl=86400)
    res = d.get("LocationResult") or []
    if not res:
        return None
    r = res[0]
    loc = r.get("Location", {})
    soort = (r.get("LocationType") or "").lower()
    waarschuwing = None
    if "huisnummer" not in soort and "perceel" not in soort:
        if "straat" in soort:
            waarschuwing = "Geen huisnummer herkend: het resultaat is het straatmidden. Bij een lange straat kan het perceel buiten de zoekstraal liggen; geef een huisnummer of lat/lon."
        elif "gemeente" in soort or "postcode" in soort:
            waarschuwing = "Alleen een gemeente of postcode herkend: het resultaat is het gemeentecentrum, niet een perceel."
        elif soort:
            waarschuwing = f"Geocodering van het type '{r.get('LocationType')}' (geen huisnummer)."
    return Locatie(
        invoer=adres,
        adres=r.get("FormattedAddress"),
        gemeente=r.get("Municipality"),
        postcode=r.get("Zipcode"),
        lat=loc["Lat_WGS84"],
        lon=loc["Lon_WGS84"],
        x_lambert72=loc.get("X_Lambert72"),
        y_lambert72=loc.get("Y_Lambert72"),
        type=r.get("LocationType"),
        waarschuwing=waarschuwing,
    )


def afstand_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine-afstand in meter."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def cirkel_wkt(lat: float, lon: float, straal_m: float, n: int = 36) -> str:
    """Benaderende cirkel als WKT-polygoon (WGS84), tegenwijzerzin zoals GBIF verlangt."""
    dlat = straal_m / 111_320.0
    dlon = straal_m / (111_320.0 * math.cos(math.radians(lat)))
    punten = []
    for i in range(n):
        hoek = 2 * math.pi * i / n
        punten.append((lon + dlon * math.cos(hoek), lat + dlat * math.sin(hoek)))
    punten.append(punten[0])
    return "POLYGON((" + ",".join(f"{x:.6f} {y:.6f}" for x, y in punten) + "))"


def bbox_wkt(lat_min: float, lon_min: float, lat_max: float, lon_max: float) -> str:
    return f"POLYGON(({lon_min} {lat_min},{lon_max} {lat_min},{lon_max} {lat_max},{lon_min} {lat_max},{lon_min} {lat_min}))"


def _afstand_tot_lijn(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def vereenvoudig(punten: list[tuple[float, float]], tolerantie: float) -> list[tuple[float, float]]:
    """Douglas-Peucker (iteratief). Tolerantie in graden (0.0005 ≈ 50 m)."""
    if len(punten) < 3:
        return punten
    behoud = [False] * len(punten)
    behoud[0] = behoud[-1] = True
    stapel = [(0, len(punten) - 1)]
    while stapel:
        i, j = stapel.pop()
        if j <= i + 1:
            continue
        k, dmax = i, 0.0
        for m in range(i + 1, j):
            d = _afstand_tot_lijn(punten[m], punten[i], punten[j])
            if d > dmax:
                k, dmax = m, d
        if dmax > tolerantie:
            behoud[k] = True
            stapel.append((i, k))
            stapel.append((k, j))
    return [p for p, b in zip(punten, behoud) if b]


def _ccw(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    opp = sum((x2 - x1) * (y2 + y1) for (x1, y1), (x2, y2) in zip(ring, ring[1:]))
    return ring if opp < 0 else ring[::-1]  # negatief = tegenwijzerzin


def geojson_naar_wkt(geom: dict, tolerantie: float = 0.0005, max_tekens: int = 6000) -> str:
    """(Multi)Polygon-GeoJSON -> vereenvoudigde WKT (alleen buitenringen, tegenwijzerzin). Verhoogt de tolerantie tot de WKT past."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for _ in range(8):
        ringen = []
        for poly in polys:
            ring = [(float(x), float(y)) for x, y in poly[0]]
            ring = vereenvoudig(ring, tolerantie)
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            if len(ring) >= 4:
                ringen.append(_ccw(ring))
        delen = ["((" + ",".join(f"{x:.5f} {y:.5f}" for x, y in r) + "))" for r in ringen]
        wkt = "MULTIPOLYGON(" + ",".join(delen) + ")" if len(delen) > 1 else "POLYGON" + delen[0]
        if len(wkt) <= max_tekens:
            return wkt
        tolerantie *= 2
    return wkt


async def gemeente_wkt(naam: str) -> tuple[str, str] | None:
    """Vlaamse gemeente -> (WKT, omschrijving) via het Voorlopig Referentiebestand Gemeentegrenzen (WFS, WGS84)."""
    veilig = naam.replace("'", "''")
    d = await get_json(
        VRBG_WFS,
        {
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": "VRBG:Refgem",
            "CQL_FILTER": f"NAAM ILIKE '{veilig}'", "outputFormat": "application/json", "srsName": "EPSG:4326",
        },
        ttl=86400,
    )
    feats = d.get("features") or []
    if not feats:
        return None
    f = feats[0]
    props = f.get("properties", {})
    return geojson_naar_wkt(f["geometry"]), f"gemeente {props.get('NAAM', naam)} (NIS {props.get('NISCODE', '?')}, grens VRBG vereenvoudigd tot ±50-100 m)"


def is_wkt(s: str) -> bool:
    return s.strip().upper().startswith(("POLYGON", "MULTIPOLYGON"))


class Gebied:
    """Genormaliseerd gebied: ofwel een WKT-geometrie, ofwel een GADM-gid (gemeente)."""

    def __init__(
        self, *, wkt: str | None = None, gadm_gid: str | None = None, omschrijving: str,
        centrum: tuple[float, float] | None = None, straal_m: float | None = None, waarschuwing: str | None = None,
    ):
        self.wkt = wkt
        self.gadm_gid = gadm_gid
        self.omschrijving = omschrijving
        self.centrum = centrum  # (lat, lon) bij een cirkelgebied
        self.straal_m = straal_m
        self.waarschuwing = waarschuwing


async def bepaal_gebied(
    *,
    adres: str | None,
    lat: float | None,
    lon: float | None,
    straal_m: float | None,
    wkt: str | None,
    gemeente: str | None,
) -> Gebied:
    """Zet de gebiedsparameters van een tool om in één Gebied. Volgorde: wkt > lat/lon > adres > gemeente."""
    from .gbif import gadm_gemeente

    if wkt:
        if not is_wkt(wkt):
            raise ValueError("`wkt` moet een POLYGON of MULTIPOLYGON in WGS84 zijn (lon lat).")
        return Gebied(wkt=wkt.strip(), omschrijving=f"WKT-polygoon ({wkt.strip()[:60]}…)" if len(wkt) > 60 else f"WKT-polygoon {wkt.strip()}")
    straal = straal_m or 500.0
    if lat is not None and lon is not None:
        return Gebied(wkt=cirkel_wkt(lat, lon, straal), omschrijving=f"straal {straal:.0f} m rond {lat:.5f}, {lon:.5f}", centrum=(lat, lon), straal_m=straal)
    if adres:
        loc = await geocodeer(adres)
        if loc is None:
            raise ValueError(f"Adres niet gevonden door de geolocation-service: '{adres}'. Geef lat/lon of een gemeente.")
        return Gebied(
            wkt=cirkel_wkt(loc.lat, loc.lon, straal), omschrijving=f"straal {straal:.0f} m rond {loc.adres or adres} ({loc.lat:.5f}, {loc.lon:.5f})",
            centrum=(loc.lat, loc.lon), straal_m=straal, waarschuwing=loc.waarschuwing,
        )
    if gemeente:
        vl = await gemeente_wkt(gemeente)
        if vl is not None:
            return Gebied(wkt=vl[0], omschrijving=vl[1])
        # Buiten Vlaanderen: GBIF kent voor België enkel GADM-niveau 3 (arrondissement).
        g = await gadm_gemeente(gemeente)
        if g is None:
            raise ValueError(f"Gemeente niet gevonden (Vlaamse gemeentegrenzen noch GADM-arrondissement): '{gemeente}'. Geef een adres, lat/lon of wkt.")
        return Gebied(gadm_gid=g[0], omschrijving=f"arrondissement {g[1]} (GADM {g[0]}; geen gemeentegrens beschikbaar buiten Vlaanderen)")
    raise ValueError("Geef een gebied: `adres` (+ `straal_m`), `lat`/`lon` (+ `straal_m`), `wkt` of `gemeente`.")
