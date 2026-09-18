"""Situeringskaart: de projectlocatie met de beschermde gebieden eromheen, als PNG.

Achtergrond: de GRB-basiskaart van Digitaal Vlaanderen (WMS, Lambert 72). Daarop worden de
gebieden getekend die `gebieden_rond` aanlevert, elk in een eigen kleur, met een legende, een
schaalbalk, een noordpijl en de zoekcirkel. Alles rekent in Lambert 72 (EPSG:31370), zodat
afstanden en de schaalbalk metrisch kloppen.

De kaart toont uitsluitend wat de WFS-diensten teruggeven; een laag die niet antwoordt, staat
in de legende als 'niet geraadpleegd' en niet als afwezig.
"""
from __future__ import annotations

import asyncio
import io
import math
from dataclasses import dataclass, field

import httpx
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from . import gebieden as gb
from .http import USER_AGENT, nu_iso

GRB_WMS = "https://geo.api.vlaanderen.be/GRB/wms"
GRB_LAAG = "GRB_BSK"  # GRB-basiskaart

# Kleuren per laag, uit het palet van Okabe & Ito: onderscheidbaar bij deuteranopie, protanopie
# en tritanopie. Kleur is hier nooit de énige drager van betekenis — elk vlak krijgt ook een
# nummer op de kaart en een arcering, zodat de kaart ook in grijswaarden en op papier werkt.
OKABE_ITO: tuple[tuple[int, int, int], ...] = (
    (0, 114, 178),    # blauw
    (230, 159, 0),    # oranje
    (0, 158, 115),    # blauwgroen
    (204, 121, 167),  # roodpaars
    (86, 180, 233),   # lichtblauw
    (213, 94, 0),     # vermiljoen
    (240, 228, 66),   # geel
    (90, 90, 90),     # grijs
)

KLEUREN: dict[str, tuple[int, int, int]] = {
    "hrl_gebied": OKABE_ITO[0],
    "hrl_deelgebied": OKABE_ITO[4],
    "vrl_gebied": OKABE_ITO[3],
    "ramsar": OKABE_ITO[2],
    "ven_ivon": OKABE_ITO[2],
    "nationaal_park": OKABE_ITO[0],
    "natuurreservaat_uitbreiding": OKABE_ITO[4],
    "natuurbeheerplan": OKABE_ITO[1],
    "natuurrichtplan": OKABE_ITO[6],
    "sigma_natuurdoel": OKABE_ITO[2],
    "anb_domein": OKABE_ITO[2],
    "hpg": OKABE_ITO[1],
    "poldergrasland": OKABE_ITO[6],
    "duinendecreet": OKABE_ITO[6],
    "beschermd_landschap": OKABE_ITO[5],
    "beschermd_dorpsgezicht": OKABE_ITO[1],
    "beschermd_monument": OKABE_ITO[5],
    "bwk_habitat": OKABE_ITO[2],
    "bwk_fauna": OKABE_ITO[3],
    "bwk_3260": OKABE_ITO[0],
}
STANDAARD = (120, 120, 120)

# Lagen die per waarde worden opgesplitst (BWK-habitatcodes) doorlopen hetzelfde palet; het nummer
# en de arcering houden ze uit elkaar wanneer de kleuren beginnen te herhalen.
PALET: tuple[tuple[int, int, int], ...] = OKABE_ITO
# Lagen die per attribuutwaarde in aparte legenderegels worden getekend.
SPLITS_OP: dict[str, str] = {"bwk_habitat": "HAB1"}


# Arceringen als tweede, kleurloze onderscheidingsdrager.
ARCERINGEN: tuple[str, ...] = ("geen", "schuin", "tegenschuin", "kruis", "horizontaal", "verticaal", "stippen")


@dataclass
class KaartLaag:
    code: str
    naam: str
    kleur: tuple[int, int, int]
    nummer: int = 0
    arcering: str = "geen"
    geometrieen: list[BaseGeometry] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    status: str = "ok"
    melding: str | None = None


def _habitatnaam(code: str) -> str:
    """Leesbare naam voor een BWK-karteringseenheid; de code blijft altijd zichtbaar."""
    kort = {
        "gh": "geen habitattype",
        "1130": "estuaria",
        "3150": "voedselrijke plassen",
        "3260": "submontane waterlopen",
        "2310": "psammofiele heide",
        "2330": "open grasland op landduinen",
        "3130": "oligotrofe plas",
        "3160": "dystrofe plas",
        "4010": "vochtige heide",
        "4030": "droge heide",
        "5130": "jeneverbesstruweel",
        "9190": "oud zuur eikenbos",
        "6230": "heischraal grasland",
        "6410": "blauwgrasland",
        "6430": "ruigte en zoom",
        "6510": "glanshavergrasland",
        "7140": "overgangsveen",
        "9120": "zuur eiken-beukenbos",
        "9130": "eiken-beukenbos",
        "9160": "essen-eikenbos",
        "91E0": "alluviaal bos",
        "91F0": "hardhoutooibos",
    }
    def _een(d: str) -> str:
        # rbb = regionaal belangrijk biotoop; de precieze biotoop staat achter de code zelf en
        # wordt hier niet geraden.
        if d.lower().startswith("rbb"):
            return "regionaal belangrijk biotoop"
        return kort.get(d, kort.get(d.split("_")[0], kort.get(d.upper(), "")))

    delen = [d.strip() for d in code.split(",") if d.strip()]
    omschrijvingen = [x for x in (_een(d) for d in delen) if x]
    omschrijving = ", ".join(dict.fromkeys(omschrijvingen))
    return f"BWK {code}" + (f" — {omschrijving}" if omschrijving else "")


def _font(grootte: int, vet: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    paden = (
        ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc", "C:/Windows/Fonts/arialbd.ttf"]
        if vet
        else ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc", "C:/Windows/Fonts/arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for pad in paden:
        try:
            return ImageFont.truetype(pad, grootte)
        except OSError:
            continue
    return ImageFont.load_default()


async def achtergrond(bbox: tuple[float, float, float, float], breedte: int, hoogte: int) -> Image.Image:
    """GRB-basiskaart als PNG voor de opgegeven Lambert 72-bbox (minx, miny, maxx, maxy)."""
    minx, miny, maxx, maxy = bbox
    params = {
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": GRB_LAAG, "STYLES": "",
        "CRS": "EPSG:31370", "BBOX": f"{minx},{miny},{maxx},{maxy}",  # Lambert 72 is x,y-geordend
        "WIDTH": breedte, "HEIGHT": hoogte, "FORMAT": "image/png",
    }
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=60.0, follow_redirects=True) as c:
        r = await c.get(GRB_WMS, params=params)
        r.raise_for_status()
        if "image" not in r.headers.get("content-type", ""):
            raise RuntimeError(f"WMS gaf geen afbeelding: {r.text[:160]}")
        basis = Image.open(io.BytesIO(r.content)).convert("RGBA")
        # De GRB-basiskaart is kleurrijk; licht verbleken houdt de gebiedsvlakken leesbaar.
        wit = Image.new("RGBA", basis.size, (255, 255, 255, 255))
        return Image.blend(basis, wit, 0.35)


def _arceer(doelbeeld: Image.Image, punten: list[tuple[float, float]], soort: str, kleur: tuple[int, int, int], stap: float, dikte: int) -> None:
    """Teken een arcering binnen één vlak. Tweede, kleurloze onderscheidingsdrager naast de kleur."""
    if soort == "geen" or len(punten) < 3:
        return
    xs = [p[0] for p in punten]
    ys = [p[1] for p in punten]
    # Vlakken lopen vaak ver buiten de kaartuitsnede; zonder afknippen bouwt het masker hieronder
    # een beeld van tientallen duizenden pixels per zijde op.
    x0 = max(0.0, min(xs))
    y0 = max(0.0, min(ys))
    x1 = min(float(doelbeeld.width), max(xs))
    y1 = min(float(doelbeeld.height), max(ys))
    b, h = int(x1 - x0) + 2, int(y1 - y0) + 2
    if b < 8 or h < 8:
        return
    masker = Image.new("L", (b, h), 0)
    ImageDraw.Draw(masker).polygon([(p[0] - x0 + 1, p[1] - y0 + 1) for p in punten], fill=255)
    laagje = Image.new("RGBA", (b, h), (0, 0, 0, 0))
    dl = ImageDraw.Draw(laagje)
    if soort == "stippen":
        y = 0.0
        rij = 0
        while y < h:
            x = stap / 2 if rij % 2 else 0.0
            while x < b:
                dl.ellipse([x - dikte, y - dikte, x + dikte, y + dikte], fill=kleur + (215,))
                x += stap
            y += stap
            rij += 1
    else:
        if soort in ("schuin", "kruis"):
            v = -h
            while v < b:
                dl.line([(v, h), (v + h, 0)], fill=kleur + (200,), width=dikte)
                v += stap
        if soort in ("tegenschuin", "kruis"):
            v = 0.0
            while v < b + h:
                dl.line([(v, h), (v - h, 0)], fill=kleur + (200,), width=dikte)
                v += stap
        if soort == "horizontaal":
            v = 0.0
            while v < h:
                dl.line([(0, v), (b, v)], fill=kleur + (200,), width=dikte)
                v += stap
        if soort == "verticaal":
            v = 0.0
            while v < b:
                dl.line([(v, 0), (v, h)], fill=kleur + (200,), width=dikte)
                v += stap
    laagje.putalpha(Image.composite(laagje.getchannel("A"), Image.new("L", (b, h), 0), masker))
    doelbeeld.alpha_composite(laagje, (int(x0) - 1, int(y0) - 1))


def _tekst_met_rand(d: ImageDraw.ImageDraw, xy: tuple[float, float], tekst: str, f, kleur=(20, 20, 20, 255), rand=(255, 255, 255, 235), dikte: int = 3) -> None:
    """Tekst met witte contour, zodat ze op elke ondergrond leesbaar blijft."""
    x, y = xy
    for dx in range(-dikte, dikte + 1):
        for dy in range(-dikte, dikte + 1):
            if dx or dy:
                d.text((x + dx, y + dy), tekst, font=f, fill=rand)
    d.text((x, y), tekst, font=f, fill=kleur)


def _punt_terug(px: float, py: float, bbox: tuple[float, float, float, float], breedte: int, hoogte: int):
    """Pixelpositie terug naar een Lambert 72-punt, om te toetsen of een label binnen zijn vlak valt."""
    from shapely.geometry import Point

    minx, miny, maxx, maxy = bbox
    x = minx + px * (maxx - minx) / breedte
    y = miny + (hoogte - py) * (maxy - miny) / hoogte
    return Point(x, y)


def _projector(bbox: tuple[float, float, float, float], breedte: int, hoogte: int):
    minx, miny, maxx, maxy = bbox
    sx = breedte / (maxx - minx)
    sy = hoogte / (maxy - miny)

    def naar_pixel(x: float, y: float) -> tuple[float, float]:
        return (x - minx) * sx, hoogte - (y - miny) * sy

    return naar_pixel


def _ringen(g: BaseGeometry) -> list[list[tuple[float, float]]]:
    """Buitenringen van een (Multi)Polygon, of de lijn van een (Multi)LineString."""
    uit: list[list[tuple[float, float]]] = []
    soort = g.geom_type
    if soort == "Polygon":
        uit.append(list(g.exterior.coords))
    elif soort == "MultiPolygon":
        for deel in g.geoms:
            uit.append(list(deel.exterior.coords))
    elif soort in ("LineString", "LinearRing"):
        uit.append(list(g.coords))
    elif soort == "MultiLineString":
        for deel in g.geoms:
            uit.append(list(deel.coords))
    elif soort == "GeometryCollection":
        for deel in g.geoms:
            uit.extend(_ringen(deel))
    return uit


def _schaalbalk(d: ImageDraw.ImageDraw, breedte: int, hoogte: int, meter_per_pixel: float, k: float) -> None:
    """Schaalbalk linksonder. `k` schaalt alle maten mee met de beeldbreedte, zodat de kaart ook
    verkleind in een document leesbaar blijft."""
    f = _font(int(15 * k), vet=True)
    kandidaten = [25, 50, 100, 200, 250, 500, 1000, 2000, 5000]
    doel_px = breedte * 0.18
    lengte_m = min(kandidaten, key=lambda m: abs(m / meter_per_pixel - doel_px))
    px = lengte_m / meter_per_pixel
    x0, y0 = 16 * k, hoogte - 26 * k
    d.rectangle([x0 - 7 * k, y0 - 20 * k, x0 + px + 10 * k, y0 + 11 * k], fill=(255, 255, 255, 220), outline=(90, 90, 90, 255), width=max(1, int(k)))
    d.line([(x0, y0), (x0 + px, y0)], fill=(20, 20, 20, 255), width=max(2, int(3 * k)))
    for x in (x0, x0 + px):
        d.line([(x, y0 - 6 * k), (x, y0 + 6 * k)], fill=(20, 20, 20, 255), width=max(2, int(3 * k)))
    d.text((x0, y0 - 18 * k), f"{lengte_m} m", font=f, fill=(20, 20, 20, 255))


def _noordpijl(d: ImageDraw.ImageDraw, breedte: int, k: float) -> None:
    f = _font(int(14 * k), vet=True)
    x, y = breedte - 34 * k, 34 * k
    d.ellipse([x - 19 * k, y - 21 * k, x + 19 * k, y + 25 * k], fill=(255, 255, 255, 220), outline=(90, 90, 90, 255), width=max(1, int(k)))
    d.polygon([(x, y - 15 * k), (x - 8 * k, y + 8 * k), (x, y + 2 * k), (x + 8 * k, y + 8 * k)], fill=(20, 20, 20, 255))
    d.text((x - 4.5 * k, y + 7 * k), "N", font=f, fill=(20, 20, 20, 255))


def _legende(afb: Image.Image, lagen: list[KaartLaag], titel: str) -> Image.Image:
    """Legende onder de kaart, in kolommen. Alleen voor de zelfstandige PNG."""
    k = max(1.0, afb.width / 900)
    f = _font(int(13 * k))
    fv = _font(int(14 * k), vet=True)
    regels = [((f"{l.nummer}. " if l.nummer else "") + (l.naam if l.status == "ok" else f"{l.naam} — niet geraadpleegd"),
               l.kleur, l.status == "ok") for l in lagen]
    kolommen = 2 if len(regels) > 6 else 1
    per_kolom = math.ceil(len(regels) / kolommen) if regels else 0
    regelhoogte = int(19 * k)
    hoogte = int(30 * k) + per_kolom * regelhoogte + int(10 * k)
    uit = Image.new("RGBA", (afb.width, afb.height + hoogte), (255, 255, 255, 255))
    uit.paste(afb, (0, 0))
    d = ImageDraw.Draw(uit)
    y0 = afb.height + int(8 * k)
    d.line([(10 * k, afb.height + 2), (afb.width - 10 * k, afb.height + 2)], fill=(150, 150, 150, 255), width=max(1, int(k)))
    d.text((12 * k, y0), titel, font=fv, fill=(30, 30, 30, 255))
    kolombreedte = (afb.width - int(24 * k)) // kolommen
    for i, (tekst, kleur, ok) in enumerate(regels):
        kol, rij = divmod(i, per_kolom)
        x = 12 * k + kol * kolombreedte
        y = y0 + int(22 * k) + rij * regelhoogte
        d.rectangle([x, y + 2 * k, x + 15 * k, y + 13 * k], fill=kleur + (110,), outline=kleur + (255,), width=max(2, int(2 * k)))
        d.text((x + 22 * k, y), tekst[:58], font=f, fill=((30, 30, 30, 255) if ok else (150, 60, 60, 255)))
    return uit


async def teken(
    doel: BaseGeometry,
    lagen: list[gb.Laag],
    *,
    straal_m: float,
    pad: str,
    breedte_px: int = 1500,
    marge: float = 1.25,
    met_legende: bool = True,
) -> dict:
    """Bouw de kaart en schrijf ze naar `pad` (PNG). Geeft metadata terug voor het rapport."""
    c = doel.centroid
    half = straal_m * marge
    bbox = (c.x - half, c.y - half, c.x + half, c.y + half)
    breedte = hoogte = min(max(breedte_px, 600), 2400)
    meter_per_pixel = (bbox[2] - bbox[0]) / breedte

    # Achtergrond en features parallel ophalen.
    async def _laag(l: gb.Laag) -> list[KaartLaag]:
        """Eén WFS-laag -> één kaartlaag, of meerdere wanneer ze per attribuutwaarde wordt gesplitst."""
        kl = KaartLaag(code=l.code, naam=l.naam, kleur=KLEUREN.get(l.code, STANDAARD))
        feats, _, fout = await gb.haal_features(l, doel, straal_m)
        if fout is not None:
            kl.status, kl.melding = "niet_geraadpleegd", fout
            return [kl]
        veld = SPLITS_OP.get(l.code)
        per_waarde: dict[str, KaartLaag] = {}
        for f in feats:
            try:
                g = shape(f["geometry"])
            except Exception:
                continue
            overlapt = g.intersects(doel)
            if not overlapt and g.distance(doel) > straal_m:
                continue
            if not gb.toon_op_kaart(l, f, overlapt):
                continue
            naam, code, _ = gb.beschrijf(l, f)
            doelkl = kl
            if veld:
                waarde = str((f.get("properties") or {}).get(veld) or "").strip() or "(leeg)"
                doelkl = per_waarde.get(waarde)
                if doelkl is None:
                    doelkl = KaartLaag(code=f"{l.code}:{waarde}", naam=f"{_habitatnaam(waarde)}", kleur=(0, 0, 0))
                    per_waarde[waarde] = doelkl
            doelkl.geometrieen.append(g)
            doelkl.labels.append(naam or code or "")
        if not veld:
            return [kl]
        # Meeste vlakken eerst, zodat de opvallendste habitats bovenaan de legende staan.
        gesorteerd = sorted(per_waarde.values(), key=lambda x: -len(x.geometrieen))
        for i, deel in enumerate(gesorteerd):
            deel.kleur = PALET[i % len(PALET)]
        return gesorteerd

    sem = asyncio.Semaphore(4)

    async def _beperkt(l: gb.Laag) -> list[KaartLaag]:
        async with sem:
            return await _laag(l)

    achtergrond_taak = asyncio.ensure_future(achtergrond(bbox, breedte, hoogte))
    kaartlagen = [kl for groep in await asyncio.gather(*(_beperkt(l) for l in lagen)) for kl in groep]
    try:
        basis = await achtergrond_taak
        achtergrond_melding = None
    except Exception as e:  # zonder GRB tekenen we op een egale ondergrond
        basis = Image.new("RGBA", (breedte, hoogte), (245, 245, 242, 255))
        achtergrond_melding = f"GRB-basiskaart niet opgehaald ({type(e).__name__}); kaart zonder ondergrond."

    naar_pixel = _projector(bbox, breedte, hoogte)
    k_versiering = max(1.0, breedte / 900)
    lijndikte = max(2, int(3 * k_versiering))
    vlakken = Image.new("RGBA", (breedte, hoogte), (0, 0, 0, 0))
    dv = ImageDraw.Draw(vlakken)
    getekend: list[KaartLaag] = []
    # Grootste vlakken eerst: anders verdwijnen kleine, vaak juist betekenisvolle percelen onder een
    # groot omhullend vlak, en stapelen doorschijnende vullingen tot een egale waas.
    te_tekenen: list[tuple[float, KaartLaag, BaseGeometry]] = []
    for kl in kaartlagen:
        if kl.status != "ok":
            getekend.append(kl)
            continue
        if not kl.geometrieen:
            continue
        for g in kl.geometrieen:
            te_tekenen.append((getattr(g, "area", 0.0), kl, g))
        getekend.append(kl)
    # Nummer en arcering per zichtbare laag: kleur is nooit de enige drager van betekenis.
    zichtbare_lagen = [kl for kl in getekend if kl.geometrieen]
    for i, kl in enumerate(zichtbare_lagen):
        kl.nummer = i + 1
        kl.arcering = ARCERINGEN[i % len(ARCERINGEN)]
    for _, kl, g in sorted(te_tekenen, key=lambda t: -t[0]):
        for ring in _ringen(g):
            punten = [naar_pixel(x, y) for x, y in ring]
            if len(punten) < 2:
                continue
            if len(punten) >= 3:
                dv.polygon(punten, fill=kl.kleur + (70,))
                _arceer(vlakken, punten, kl.arcering, kl.kleur, stap=11 * k_versiering, dikte=max(1, int(1.6 * k_versiering)))
            dv.line(punten + [punten[0]] if len(punten) >= 3 else punten, fill=kl.kleur + (245,), width=lijndikte)

    afb = Image.alpha_composite(basis, vlakken)
    d = ImageDraw.Draw(afb, "RGBA")

    # Nummer in elk vlak dat groot genoeg is; verwijst naar de legende, ook in grijswaarden leesbaar.
    # Het label wordt geplaatst in het ZICHTBARE deel van het vlak: een groot gebied dat de hele
    # uitsnede beslaat heeft zijn zwaartepunt vaak buiten beeld en zou anders geen nummer krijgen.
    from shapely.geometry import box as _box

    venster = _box(*bbox)
    f_nummer = _font(int(15 * k_versiering), vet=True)
    geplaatst: list[tuple[float, float]] = []
    for _, kl, g in sorted(te_tekenen, key=lambda t: -t[0]):
        if not kl.nummer:
            continue
        try:
            zichtbaar_deel = g.intersection(venster)
        except Exception:
            zichtbaar_deel = g
        if zichtbaar_deel.is_empty:
            continue
        minx, miny, maxx, maxy = zichtbaar_deel.bounds
        (px0, py1), (px1, py0) = naar_pixel(minx, miny), naar_pixel(maxx, maxy)
        if abs(px1 - px0) < 26 * k_versiering or abs(py1 - py0) < 22 * k_versiering:
            continue
        try:
            punt = zichtbaar_deel.representative_point()
        except Exception:
            continue
        x, y = naar_pixel(punt.x, punt.y)
        # Botsende labels wijken uit in plaats van te verdwijnen: overlappende aanduidingen (een SBZ
        # binnen een VEN-gebied) hebben vrijwel hetzelfde zwaartepunt en zouden elkaar anders wissen.
        stap_px = 22 * k_versiering
        plek = None
        for dx, dy in ((0, 0), (stap_px, 0), (-stap_px, 0), (0, stap_px), (0, -stap_px),
                       (stap_px, stap_px), (-stap_px, -stap_px), (stap_px, -stap_px), (-stap_px, stap_px)):
            kx, ky = x + dx, y + dy
            if not (8 < kx < breedte - 8 and 8 < ky < hoogte - 8):
                continue
            if not zichtbaar_deel.intersects(_punt_terug(kx, ky, bbox, breedte, hoogte)):
                continue
            if any(abs(kx - ox) < 20 * k_versiering and abs(ky - oy) < 16 * k_versiering for ox, oy in geplaatst):
                continue
            plek = (kx, ky)
            break
        if plek is None:
            continue
        geplaatst.append(plek)
        _tekst_met_rand(d, (plek[0] - 5 * k_versiering, plek[1] - 9 * k_versiering), str(kl.nummer), f_nummer,
                        kleur=(20, 20, 20, 255), dikte=max(2, int(2 * k_versiering)))

    # Zoekcirkel en middelpunt.
    px_straal = straal_m / meter_per_pixel
    cx, cy = naar_pixel(c.x, c.y)
    k = max(1.0, breedte / 900)  # schaalfactor voor alle kaartversieringen
    d.ellipse([cx - px_straal, cy - px_straal, cx + px_straal, cy + px_straal], outline=(200, 30, 30, 220), width=max(2, int(3 * k)))
    if doel.geom_type in ("Polygon", "MultiPolygon"):
        for ring in _ringen(doel):
            d.polygon([naar_pixel(x, y) for x, y in ring], fill=(200, 30, 30, 60), outline=(200, 30, 30, 255))
    straal_stip = 9 * k
    d.ellipse([cx - straal_stip, cy - straal_stip, cx + straal_stip, cy + straal_stip], fill=(200, 30, 30, 255),
              outline=(255, 255, 255, 255), width=max(2, int(3 * k)))

    _schaalbalk(d, breedte, hoogte, meter_per_pixel, k)
    _noordpijl(d, breedte, k)

    zichtbaar = [kl for kl in getekend if kl.geometrieen or kl.status != "ok"]
    zichtbaar.append(KaartLaag(code="_zoek", naam=f"projectlocatie en zoekstraal ({straal_m:.0f} m)", kleur=(200, 30, 30)))
    for kl in zichtbaar:
        if kl.status != "ok" and not kl.nummer:
            kl.arcering = "geen"
    if met_legende:
        # In een verkleinde figuur is een ingebakken legende onleesbaar; zet `met_legende=False`
        # en gebruik het veld `legende` uit de respons om ze in het document zelf op te maken.
        afb = _legende(afb, zichtbaar, "Legende")

    # JPEG bij een .jpg-pad: de GRB-ondergrond is rasterbeeld, dus JPEG is er tot tienmaal kleiner
    # dan PNG — merkbaar in een rapport met meerdere kaarten.
    plat = afb.convert("RGB")
    if pad.lower().endswith((".jpg", ".jpeg")):
        plat.save(pad, "JPEG", quality=88, optimize=True, progressive=True)
    else:
        plat.save(pad, "PNG", optimize=True)
    return {
        "pad": pad,
        "geraadpleegd_op": nu_iso(),
        "bbox_lambert72": [round(v, 2) for v in bbox],
        "breedte_px": afb.width,
        "hoogte_px": afb.height,
        "meter_per_pixel": round(meter_per_pixel, 3),
        "achtergrond": "GRB-basiskaart (Digitaal Vlaanderen, WMS)" if achtergrond_melding is None else "geen",
        "legende": [
            {"laag": kl.code, "naam": kl.naam, "nummer": kl.nummer, "kleur": "#%02x%02x%02x" % kl.kleur,
             "arcering": kl.arcering, "aantal_vlakken": len(kl.geometrieen), "status": kl.status}
            for kl in zichtbaar
        ],
        "legende_in_afbeelding": met_legende,
        "niet_geraadpleegd": [kl.code for kl in kaartlagen if kl.status != "ok"],
        "melding": achtergrond_melding,
    }
