# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Datarapport natuur als PDF: het vaste rapportsjabloon van de connector.

Bouwt uit de uitvoer van de tools (telling, kernsoorten, gebieden, kaarten, onderliggende records)
een rapport met een vaste opbouw: titelblad, samenvatting, situering met kaarten, statussen in
cijfers, kernsoorten met herkomst, gebiedsstatuten, onderliggende waarnemingen, verantwoording
van de bronnen en beperkingen.

Alles in het rapport komt letterlijk uit de tool-respons; er wordt niets bijgeschat.
Conventies: beide zoekstralen worden overal expliciet genoemd; terminologie strikt/striktst
beschermd; kaarten leesbaar zonder kleuronderscheid (nummers en arceringen).
"""
from __future__ import annotations

from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from . import DISCLAIMER, DISCLAIMER_KORT, PRIVACY
from .datasets import afkorting

from reportlab.platypus import (
    BaseDocTemplate,
    Image as RLImage,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

GRIJS = colors.HexColor("#4a4a4a")
LICHT = colors.HexColor("#f2f2f2")
LIJN = colors.HexColor("#c8c8c8")
ACCENT = colors.HexColor("#1f4e3d")

ss = getSampleStyleSheet()
S = {
    "titel": ParagraphStyle("titel", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=ACCENT, alignment=0, spaceAfter=2),
    "ondertitel": ParagraphStyle("ondertitel", parent=ss["Normal"], fontName="Helvetica", fontSize=11, leading=15, textColor=GRIJS, spaceAfter=14),
    "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=ACCENT, spaceBefore=14, spaceAfter=5),
    "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=GRIJS, spaceBefore=9, spaceAfter=3),
    "tekst": ParagraphStyle("tekst", parent=ss["Normal"], fontName="Helvetica", fontSize=9, leading=12.6, alignment=TA_JUSTIFY, spaceAfter=5),
    "klein": ParagraphStyle("klein", parent=ss["Normal"], fontName="Helvetica", fontSize=7.6, leading=10.4, textColor=GRIJS),
    "cel": ParagraphStyle("cel", parent=ss["Normal"], fontName="Helvetica", fontSize=7.4, leading=9.6),
    "celv": ParagraphStyle("celv", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=7.4, leading=9.6),
    "kop": ParagraphStyle("kop", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=7.4, leading=9.6, textColor=colors.white),
}

P = lambda t, s="tekst": Paragraph(t, S[s])


def tabel(kop: list[str], rijen: list[list[str]], breedtes: list[float], klein: bool = False) -> Table:
    data = [[Paragraph(k, S["kop"]) for k in kop]]
    for r in rijen:
        data.append([Paragraph(str(c), S["cel"]) for c in r])
    t = Table(data, colWidths=breedtes, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LICHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, LIJN),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    return t


def kv(rijen: list[tuple[str, str]], breedte: float = 168) -> Table:
    data = [[Paragraph(k, S["celv"]), Paragraph(v, S["cel"])] for k, v in rijen]
    t = Table(data, colWidths=[breedte, 460 - breedte], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, LIJN),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
    ]))
    return t


def kaartlegende(regels: list[dict], kolommen: int = 2) -> Table:
    """Legende van de kaart als tabel met kleurvlakjes, opgemaakt in de PDF zelf."""
    import math as _m

    per_kolom = _m.ceil(len(regels) / kolommen)
    kolomdata: list[list] = []
    stijl = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
             ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]
    rijen = [["", "", "", ""] for _ in range(per_kolom)]
    for i, r in enumerate(regels):
        kol, rij = divmod(i, per_kolom)
        naam = legendenaam(r)
        # Het nummer staat ook in elk vlak op de kaart: zo is de legende leesbaar zonder kleur.
        if r.get("nummer"):
            naam = f"<b>{r['nummer']}.</b> {naam}"
        rijen[rij][kol * 2] = Paragraph(f"<font color='white' size='6'><b>{r['nummer']}</b></font>", S["cel"]) if r.get("nummer") else ""
        rijen[rij][kol * 2 + 1] = Paragraph(naam, S["cel"])
        stijl.append(("BACKGROUND", (kol * 2, rij), (kol * 2, rij), colors.HexColor(r["kleur"])))
        stijl.append(("BOX", (kol * 2, rij), (kol * 2, rij), 0.4, colors.HexColor("#555555")))
    stijl.append(("ALIGN", (0, 0), (-1, -1), "CENTER"))
    for kol in range(kolommen):
        stijl.append(("ALIGN", (kol * 2 + 1, 0), (kol * 2 + 1, -1), "LEFT"))
    t = Table(rijen, colWidths=[12, 218, 12, 218], rowHeights=[11.5] * per_kolom, hAlign="LEFT")
    t.setStyle(TableStyle(stijl))
    return t


def tijd(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y om %H:%M")
    except Exception:
        return iso


def datum(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y")
    except Exception:
        return iso




def _kader(tekst: str) -> Table:
    """Opvallend omkaderd blok voor de disclaimer op het titelblad."""
    stijl = ParagraphStyle("kader", parent=S["tekst"], fontSize=8.6, leading=11.5, textColor=colors.HexColor("#3a3a3a"))
    t = Table([[Paragraph(tekst, stijl)]], colWidths=[460], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff4e0")),
        ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#e69f00")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _getal(n) -> str:
    """Getal met punt als duizendtalscheiding, onafhankelijk van de locale van het systeem."""
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def _kort(d: dict) -> str:
    """Korte datasetnaam; eerst de vaste afkortingen, anders op woordgrens ingekorte titel."""
    naam = afkorting(d["dataset_key"], d.get("dataset"))
    if len(naam) <= 25:
        return naam
    stuk = naam[:24]
    return (stuk.rsplit(" ", 1)[0] if " " in stuk else stuk) + "…"



def bwk_zin(sb: dict, straal: int) -> str:
    """Samenvattende zin over de BWK; 'gh' komt nooit als losse code in de tekst ('geen habitat')."""
    b = sb.get("binnen_straal") or {}
    zelf = sb.get("locatie_zelf") or []
    delen = []
    if zelf:
        delen.append("De projectlocatie ligt in BWK-eenheid " + "; ".join(
            f"<b>{z['label']}</b> ({z['waardering']}; habitat: {z['habitat']})" for z in zelf) + ".")
    delen.append(f"Binnen {straal} m liggen {b.get('totaal', 0)} BWK-eenheden, waarvan <b>{b.get('waardevol', 0)}</b> biologisch "
                 f"waardevol en <b>{b.get('zeer_waardevol', 0)}</b> biologisch zeer waardevol (zuiver of als complex).")
    hab = sb.get("habitattypes_binnen_straal") or []
    rbb = sb.get("rbb_binnen_straal") or []
    if hab:
        delen.append("Habitattypes binnen de straal: " + "; ".join(
            f"{h['code']} {h['naam']} ({h['aandeel_pct']} % van eenheid {h['label']}, op {h['afstand_m']} m"
            + (f", in {h['aantal_eenheden']} eenheden" if h['aantal_eenheden'] > 1 else "") + ")" for h in hab) + ".")
    else:
        delen.append("Binnen de straal staat in de BWK geen Natura 2000-habitattype.")
    if rbb:
        delen.append("Regionaal belangrijke biotopen: " + "; ".join(
            f"{h['code']} {h['naam']} ({h['aandeel_pct']} % van eenheid {h['label']}, op {h['afstand_m']} m)" for h in rbb) + ".")
    else:
        delen.append("Binnen de straal staat in de BWK geen regionaal belangrijk biotoop.")
    if sb.get("dichtste_waardevol"):
        d = sb["dichtste_waardevol"]
        delen.append(f"Dichtste (zeer) waardevolle eenheid: {d['label']} ({d['waardering']}), op {d['afstand_m']} m.")
    return " ".join(delen)


def bwk_kaartnummers(kaarten: list[dict]) -> dict[str, int]:
    """Kaartsleutel (bwk.kaartsleutel) -> nummer van de legenderegel op de BWK-kaart."""
    nummers: dict[str, int] = {}
    for k in kaarten:
        for r in k.get("legende") or []:
            if str(r.get("laag", "")).startswith("bwk_habitat:") and r.get("nummer"):
                nummers[r["laag"].split(":", 1)[1]] = r["nummer"]
    return nummers


def bwk_rijen(laag: dict, kaarten: list[dict]) -> list[list[str]]:
    """Rijen van tabel 5.1, in de volgorde van de treffers (overlap eerst, dan afstand)."""
    from .bwk import habitat_tekst, wordt_getekend

    nummers = bwk_kaartnummers(kaarten)
    rijen = []
    for t in laag["treffers"]:
        e = t.get("bwk") or {}
        oms = "<br/>".join(f"<b>{x['code']}</b> {x['omschrijving']}" for x in e.get("eenheden") or []) or "—"
        rijen.append([
            str(nummers.get(e.get("kaartsleutel"), "—")) if e and wordt_getekend(e, t["overlapt"]) else "—",
            "0 (ligt in)" if t["overlapt"] else f"{t['afstand_m']}",
            e.get("bwklabel") or "—",
            oms,
            (e.get("eval") or "—") + (f" — {e['waardering']}" if e.get("waardering") else ""),
            habitat_tekst(e) if e else "—",
            e.get("karteerjaar_of_versie") or "—",
        ])
    return rijen


# ---------------------------------------------------------------- inhoud, gedeeld door PDF en Word
# De functies hieronder leveren tekst (met de beperkte markup <b>, <i>, <br/>) en tabelrijen. Zowel
# schrijf_pdf als rapport_docx.schrijf_docx bouwen daarmee, zodat beide formaten dezelfde inhoud dragen.

LIJSTNAMEN = {
    "hrl_iv_vl": "Habitatrichtlijn bijlage IV — soorten die in het Vlaamse Gewest (kunnen) voorkomen, Soortenbesluit bijlage 1 categorie 3",
    "hrl_ii": "Habitatrichtlijn bijlage II",
    "vrl": "Vogelrichtlijn bijlagen I, II.1 en II.2",
    "rodelijst_vl": "Gevalideerde Rode Lijsten van Vlaanderen (INBO)",
    "rodelijst_broedvogels_2016": "Rode Lijst van de broedvogels in Vlaanderen 2016 (Devos et al. 2016)",
    "soortenbesluit": "Soortenbesluit, bijlage 1, categorieën 1 tot 3",
    "bern": "Verdrag van Bern, bijlagen I tot III",
    "bonn": "Verdrag van Bonn (CMS)",
    "unielijst": "Unielijst invasieve uitheemse soorten, Verordening (EU) nr. 1143/2014",
    "invasief_uitgebreid": "Uitgebreide lijst invasieve uitheemse soorten (INBO)",
    "hrl_v": "Habitatrichtlijn bijlage V",
    "iucn": "IUCN Red List (wereldwijd)",
}

KADER = (f"<b>{DISCLAIMER_KORT}</b> De resultaten zijn een geautomatiseerde bronnenscan en vervangen geen "
         "terreininventarisatie, deskundige beoordeling of juridisch advies. Volledige disclaimer in hoofdstuk 8.")


def stralen(D: dict) -> tuple[float, int]:
    return D["straal_m"], int(D["gebieden"]["straal_m"])


def kaartlijst(D: dict) -> list[dict]:
    """Eén kaart (sleutel `kaart`) of meerdere thematische kaarten (sleutel `kaarten`)."""
    return D.get("kaarten") or ([D["kaart"]] if D.get("kaart") else [])


def ondertitel(D: dict) -> str:
    # Soorten en gebieden worden met een eigen zoekstraal bevraagd; de ondertitel noemt ze allebei,
    # anders suggereert één afstand ten onrechte dat beide even ver reiken.
    straal_soorten, straal_gebieden = stralen(D)
    adres = D["locatie"]["adres"]
    if float(straal_soorten) == float(straal_gebieden):
        return f"Beschermde soorten en gebiedsstatuten binnen {straal_soorten:.0f} m<br/>{adres}"
    return (f"Beschermde soorten binnen {straal_soorten:.0f} m, gebiedsstatuten binnen "
            f"{straal_gebieden} m<br/>{adres}")


def voettekst(D: dict) -> str:
    straal_soorten, straal_gebieden = stralen(D)
    return (f"Datarapport natuur — {D['locatie']['adres']} — soorten {straal_soorten:.0f} m, "
            f"gebieden {straal_gebieden} m — bevraagd {datum(D['kern']['geraadpleegd_op'])}")


VOETTEKST_2 = "Betaversie — zonder garantie; de gebruiker is zelf verantwoordelijk voor het gebruik."


def titelgegevens(D: dict) -> list[tuple[str, str]]:
    loc, kern = D["locatie"], D["kern"]
    straal_soorten, straal_gebieden = stralen(D)
    connector = D.get("connector") or "MCP-connector BE-biodiversiteit"
    return [
        ("Projectlocatie", f"{loc['adres']} ({loc['gemeente']})"),
        ("Coördinaten WGS 84", f"{loc['lat']:.5f} N / {loc['lon']:.5f} O"),
        ("Coördinaten Lambert 72", f"x {loc['x_lambert72']:.2f} / y {loc['y_lambert72']:.2f}"),
        ("Geocodering", f"{loc['type']} — {loc['bron']}"),
        ("Zoekgebied soorten", f"straal {straal_soorten:.0f} m rond de projectlocatie"),
        ("Zoekgebied gebieden", f"straal {straal_gebieden} m rond de projectlocatie"),
        ("Periode", f"{D['jaar_van']} tot heden"),
        ("Bevraging uitgevoerd", tijd(kern["geraadpleegd_op"])),
        ("Instrument", f"{connector} (GBIF + Vlaams Biodiversiteitsportaal)"),
        ("Datalicenties", (kern.get("licentiefilter") or "—")
         + (f" ({_getal(kern['uitgesloten_niet_commercieel'])} records weggelaten)" if kern.get("uitgesloten_niet_commercieel") else "")
         + (". <b>Bevat gegevens onder CC BY-NC (alleen niet-commercieel gebruik): intern werkdocument, niet "
            "delen of publiceren zonder de licenties na te gaan.</b>"
            if (kern.get("licenties") or {}).get("CC BY-NC 4.0") and not kern.get("uitgesloten_niet_commercieel") else "")),
    ]


def samenvatting(D: dict) -> list[str]:
    """Alinea's van hoofdstuk 1."""
    tel, geb = D["telling"], D["gebieden"]
    straal_soorten, straal_gebieden = stralen(D)
    uit = [
        f"Binnen een straal van {straal_soorten:.0f} m rond de projectlocatie zijn sinds {D['jaar_van']} in totaal "
        f"<b>{_getal(tel['totaal_waarnemingen'])}</b> waarnemingen van <b>{tel['totaal_soorten']}</b> soorten gemeld in GBIF. "
        f"Daarvan hebben <b>{tel['totaal_soorten_met_status']}</b> soorten een beschermings-, Rode-Lijst- of exotenstatus. "
        f"<b>{tel['kern']}</b> soorten hebben een kernstatus voor de natuurtoets: bijlage IV van de Habitatrichtlijn "
        f"(categorie 3 van het Soortenbesluit), bijlage II van de Habitatrichtlijn, bijlage I van de Vogelrichtlijn, "
        f"of een Rode-Lijstcategorie RE, CR, EN of VU. Daarnaast zijn <b>{tel['exoten']}</b> soorten met status "
        f"geregistreerd als uitheems."
    ]
    samenvatting_geb = geb.get("samenvatting") or {}
    laagnamen = {l["laag"]: l["naam"] for l in geb["lagen"]}
    if straal_gebieden > straal_soorten:
        straal_zin = f"Voor de gebiedsstatuten is een ruimere straal van {straal_gebieden} m gehanteerd."
    elif straal_gebieden < straal_soorten:
        straal_zin = f"Voor de gebiedsstatuten is een kleinere straal van {straal_gebieden} m gehanteerd."
    else:
        straal_zin = f"Ook de gebiedsstatuten zijn binnen {straal_gebieden} m bevraagd."
    tekst_geb = {k: v for k, v in samenvatting_geb.items() if isinstance(v, str)}
    if tekst_geb:
        uit.append(f"{straal_zin} Daarbinnen zijn treffers gevonden in de volgende gebiedslagen: "
                   + "; ".join(f"{laagnamen.get(k, k)}: {v}" for k, v in tekst_geb.items()) + ".")
    elif samenvatting_geb.get("bwk"):
        uit.append(f"{straal_zin} Daarbinnen is in geen van de beschermingslagen een gebied aangetroffen; "
                   "de Biologische Waarderingskaart volgt hieronder.")
    else:
        uit.append(f"{straal_zin} Daarbinnen is in geen van de {len(geb['lagen'])} geraadpleegde gebiedslagen een "
                   "beschermd gebied of gebiedsstatuut aangetroffen.")
    if samenvatting_geb.get("bwk"):
        uit.append(bwk_zin(samenvatting_geb["bwk"], straal_gebieden))
    if samenvatting_geb.get("ecotoopkwetsbaarheid"):
        uit.append(ecotoop_zin(samenvatting_geb["ecotoopkwetsbaarheid"], straal_gebieden))
    return uit


def situering(kaarten: list[dict]) -> str:
    return (
        f"Uitsnede rond de projectlocatie, straal {int(kaarten[0]['straal_m'])} m. De rode stip is de "
        f"projectlocatie, de rode cirkel de zoekstraal. Ondergrond: {kaarten[0]['achtergrond']}. "
        f"Coördinaatstelsel Lambert 72; de schaalbalk is metrisch. "
        + ("De kaarten hebben dezelfde uitsnede en schaal en zijn dus over elkaar te leggen. " if len(kaarten) > 1 else "")
        + "Elk vlak draagt het nummer van zijn legenderegel, en elke laag heeft een eigen arcering: "
        "de kaart is dus ook leesbaar zonder kleuronderscheid en in grijswaarden."
    )


def legendenaam(r: dict) -> str:
    """Tekst van één legenderegel (zonder het nummer)."""
    naam = r["naam"] if r["status"] == "ok" else r["naam"] + " — niet geraadpleegd"
    if r.get("aantal_vlakken") and r["laag"] != "_zoek":
        naam += f" ({r['aantal_vlakken']})"
    return naam


def statussen_rijen(tel: dict) -> list[list[str]]:
    return [[c, cat, str(n)] for c, cats in tel["per_categorie"].items() for cat, n in sorted(cats.items(), key=lambda kv: -kv[1])]


STATUSSEN_NOOT = ("De lijstcodes verwijzen naar de gezaghebbende soortenlijsten van het Vlaams Biodiversiteitsportaal; "
                  "de volledige benaming en de bron-URL per lijst staan in hoofdstuk 7.")


def kernsoorten_inleiding(D: dict) -> str:
    return (
        f"Alle soorten met kernstatus, gesorteerd van strikt naar minder strikt beschermd en daarna op aantal waarnemingen. "
        f"De kolom <i>herkomst</i> geeft de brondatasets waaruit de waarnemingen van die soort komen, met hun "
        f"aandeel. <i>onz.</i> is de grootste opgegeven coördinaatonzekerheid in meter; <i>zeker</i> is het aantal "
        f"records waarvan de locatie inclusief die onzekerheid met zekerheid binnen de zoekstraal voor soorten "
        f"({D['straal_m']:.0f} m) valt. Een onzekerheid van 707 m wijst op een naar een hok vervaagde locatie."
    )


KERNSOORTEN_KOP = ["Soort", "Status", "n", "jaar", "onz.", "zek.", "Herkomst van de waarnemingen"]


def kernsoorten_rijen(kern: dict) -> list[list[str]]:
    rijen = []
    for s in kern["soorten"]:
        status = "; ".join(f"{c} {v}" for c, v in s["samenvatting"].items())
        herkomst = " / ".join(f"{_kort(d)} {d['aantal']}" for d in (s["datasets"] or []))
        rijen.append([
            f"<b>{s['nederlandse_naam'] or ''}</b><br/><i>{s['wetenschappelijke_naam']}</i>",
            status,
            str(s["aantal_waarnemingen"]),
            str(s["laatste_jaar"] or ""),
            f"{s['onzekerheid_max_m']:.0f}" if s["onzekerheid_max_m"] else "",
            "" if s["zeker_binnen_straal"] is None else str(s["zeker_binnen_straal"]),
            herkomst,
        ])
    return rijen


def kernsoorten_noot(kern: dict) -> str:
    return (f"Aantal kernsoorten: {len(kern['soorten'])}. Volledigheid van de bevraging: "
            + ("alle gevraagde gegevens zijn opgehaald." if kern["volledig"] else "onvolledig — " + "; ".join(kern["ontbrekend"]) + "."))


def gebieden_inleiding(geb: dict) -> str:
    return (f"Resultaat per geraadpleegde laag binnen {int(geb['straal_m'])} m. Een afstand van 0 m betekent dat de "
            "projectlocatie binnen het gebied ligt. Lagen met de vermelding <i>niet geraadpleegd</i> gaven een fout: "
            "daaruit volgt niet dat er geen gebied ligt.")


def gebieden_rijen(geb: dict) -> tuple[list[list[str]], dict | None]:
    """Rijen (laag, resultaat) van hoofdstuk 5 en de BWK-laag voor tabel 5.1 (of None)."""
    straal_gebieden = int(geb["straal_m"])
    samenvatting_geb = geb.get("samenvatting") or {}
    rijen = []
    bwk_laag = None
    for laag in geb["lagen"]:
        if laag["status"] != "ok":
            res = f"niet geraadpleegd — {laag.get('melding') or ''}"
        elif not laag.get("aantal_binnen_straal") and not laag["treffers"]:
            res = f"geen treffer binnen {straal_gebieden} m"
        elif laag["laag"] == "bwk_habitat":
            bwk_laag = laag
            sb = laag.get("samenvatting_bwk") or {}
            b = sb.get("binnen_straal") or {}
            zelf = "; ".join(f"<b>ligt in</b> {z['label']} ({z['waardering']}, {z['habitat']})" for z in sb.get("locatie_zelf") or [])
            res = (zelf + ("; " if zelf else "") + f"{b.get('totaal', laag['aantal_binnen_straal'])} eenheden binnen "
                   f"{straal_gebieden} m, waarvan {b.get('waardevol', 0)} waardevol en {b.get('zeer_waardevol', 0)} zeer waardevol "
                   "— zie tabel 5.1")
        elif laag["laag"] == "ecotoopkwetsbaarheid":
            sb = laag.get("samenvatting_ecotoop") or {}
            res = (f"{(sb.get('binnen_straal') or {}).get('totaal', laag['aantal_binnen_straal'])} polygonen binnen "
                   f"{straal_gebieden} m; hoogste kwetsbaarheid: "
                   + "; ".join(f"{d} {h['hoogste']['klasse']}" for d, h in ((sb.get("binnen_straal") or {}).get("per_druk") or {}).items()
                               if h.get("hoogste"))
                   + " — zie tabel 5.2")
        else:
            res = samenvatting_geb.get(laag["laag"]) or ""
            res = res.replace("ligt in ", "<b>ligt in</b> ", 1)
        if laag.get("melding") and laag["status"] == "ok" and laag["laag"] not in ("bwk_habitat", "ecotoopkwetsbaarheid"):
            res += f" <i>({laag['melding']})</i>"
        rijen.append([laag["naam"], res])
    return rijen, bwk_laag


BWK_KOP = ["Kaart", "Afstand (m)", "Label", "Karteringseenheden", "Waardering", "Habitat / rbb (aandeel)", "Versie"]
BWK_TITEL = "5.1 Biologische Waarderingskaart: alle eenheden binnen de straal"


def bwk_inleiding(laag: dict, straal: int) -> str:
    return (f"Alle {laag['aantal_binnen_straal']} BWK-eenheden binnen {straal} m, ook die zonder habitat of met waardering "
            "minder waardevol, gesorteerd op afstand tot de rand van de polygoon. <i>Kaart</i> is het nummer van de "
            "legenderegel op de BWK-kaart (— = niet getekend: geen habitat, rbb of waardevol element en geen overlap). "
            "Omschrijvingen en waarderingen volgens de INBO-legende; een code die daar niet in staat, heet "
            "<i>onbekend in legende</i>.")


def bwk_noten(laag: dict) -> list[str]:
    from .bwk import bronvermelding

    uit = ["Legende: " + bronvermelding() + "."]
    if laag["aantal_binnen_straal"] > len(laag["treffers"]):
        uit.append(f"Let op: {len(laag['treffers'])} van {laag['aantal_binnen_straal']} eenheden opgenomen.")
    return uit


def ecotoop_zin(sb: dict, straal: int) -> str:
    """Samenvattende zin over de ecotoopkwetsbaarheid: klassen letterlijk uit de bron."""
    from .ecokwets import klassen_tekst

    b = sb.get("binnen_straal") or {}
    delen = []
    zelf = sb.get("locatie_zelf") or []
    if zelf:
        delen.append("Ecotoopkwetsbaarheid (INBO) op de projectlocatie: " + "; ".join(
            f"eenheid <b>{z['label']}</b>: {klassen_tekst(z)}" for z in zelf) + ".")
    hoogste = [(d, h["hoogste"]) for d, h in (b.get("per_druk") or {}).items() if h.get("hoogste")]
    if hoogste:
        delen.append(f"Hoogste kwetsbaarheid binnen {straal} m ({b.get('totaal', 0)} polygonen): " + "; ".join(
            f"{d} <b>{h['klasse']}</b> ({h['label']}, op {h['afstand_m']} m)" for d, h in hoogste)
            + ". Het gaat om signaalkaarten op schaal Vlaanderen.")
    return " ".join(delen)


def ecotoop_laag(geb: dict) -> dict | None:
    """De laag ecotoopkwetsbaarheid voor tabel 5.2, als ze geraadpleegd is en treffers heeft."""
    return next((l for l in geb["lagen"] if l["laag"] == "ecotoopkwetsbaarheid" and l["status"] == "ok" and l["treffers"]), None)


ECOTOOP_KOP = ["Afstand (m)", "Label", "Waardering", "Verdroging", "Eutrofiëring", "Verzuring", "Versie"]
ECOTOOP_TITEL = "5.2 Ecotoopkwetsbaarheid: alle polygonen binnen de straal"


def ecotoop_inleiding(laag: dict, straal: int) -> str:
    return (f"Alle {laag['aantal_binnen_straal']} polygonen van de ecotoopkwetsbaarheidskaarten (INBO) binnen {straal} m, "
            "gesorteerd op afstand tot de rand van de polygoon. Per milieudruk de klasse en tussen haakjes de waarde, "
            "beide letterlijk zoals de INBO-dienst ze levert. De kwetsbaarheid volgt uit de gevoeligheid van het ecotoop "
            "en de biologische waardering van de BWK-eenheid; label en waardering komen uit dezelfde dienst.")


def ecotoop_rijen(laag: dict) -> list[list[str]]:
    from .ecokwets import DRUKKEN

    rijen = []
    for t in laag["treffers"]:
        e = t.get("ecotoop") or {}
        k = e.get("kwetsbaarheid") or {}
        rijen.append([
            "0 (ligt in)" if t["overlapt"] else f"{t['afstand_m']}",
            e.get("bwklabel") or "—",
            (e.get("eval") or "—") + (f" — {e['waardering']}" if e.get("waardering") else ""),
        ] + [(f"{k[d]['klasse']} ({k[d]['waarde']:g})" if k.get(d) and k[d].get("waarde") is not None
              else (k.get(d) or {}).get("klasse", "—")) for d in DRUKKEN] + [e.get("versie_bwk") or "—"])
    return rijen


def ecotoop_noten(laag: dict) -> list[str]:
    from .ecokwets import GEBRUIKSBEPERKING, bronvermelding

    uit = [bronvermelding() + ".", "Gebruiksbeperking volgens de metadata: " + GEBRUIKSBEPERKING]
    if laag["aantal_binnen_straal"] > len(laag["treffers"]):
        uit.append(f"Let op: {len(laag['treffers'])} van {laag['aantal_binnen_straal']} polygonen opgenomen.")
    return uit


DETAIL_TITEL = "6. Onderliggende waarnemingen van de striktst beschermde soorten"
DETAIL_INLEIDING = (
    "Per soort de individuele records uit de dataset die er de meeste levert. De verificatiestatus is "
    "letterlijk overgenomen uit GBIF (veld <i>identificationVerificationStatus</i>); een leeg veld betekent "
    "dat de bron die informatie niet meelevert, niet dat het record onbetrouwbaar is. De methode is afgeleid uit "
    "de GBIF-velden samplingProtocol en basisOfRecord (batdetector, uitwerpselen, zicht …); <i>onbekend</i> "
    "betekent dat de bron het niet vermeldt."
)
DETAIL_KOP = ["Datum", "Plaats", "onz. (m)", "Verificatie", "Methode"]


def detail_blok(blok: dict) -> tuple[str, str, list[list[str]]]:
    """Titel, bronnoot en rijen voor één soort in hoofdstuk 6."""
    s, w = blok["soort"], blok["waarnemingen"]
    ds_naam = next((d.get("dataset") for d in (s["datasets"] or []) if d["dataset_key"] == blok["dataset_key"]), blok["dataset_key"])
    rijen = [[
        x["datum"] or "", x["plaats"] or x["gemeente"] or "", f"{x['onzekerheid_m']:.0f}" if x["onzekerheid_m"] else "",
        x["verificatiestatus"] or "—", x.get("methode") or x.get("basis") or "onbekend",
    ] for x in w["waarnemingen"]]
    titel = f"{s['nederlandse_naam']} ({s['wetenschappelijke_naam']}) — {s['samenvatting'].get('hrl_iv_vl') or list(s['samenvatting'].values())[0]}"
    noot = (f"Bron: {ds_naam}. Records getoond: {len(rijen)} van {w['totaal']} in deze dataset. "
            f"Verificatiestatus: {', '.join(f'{k} ({v})' for k, v in w['per_verificatiestatus'].items())}."
            + (f" Methode: {', '.join(f'{k} ({v})' for k, v in w['per_methode'].items())}." if w.get("per_methode") else ""))
    return titel, noot, rijen


def lijst_rijen(kern: dict) -> list[list[str]]:
    return [[c, LIJSTNAMEN.get(c, c), tijd(v) if v else "—"] for c, v in kern["lijstversies"].items()]


def rodelijst_noot(kern: dict) -> str:
    return ("Dekking van de Rode Lijsten: " + "; ".join(f"<b>{k}</b> — {v}" for k, v in kern["rodelijst_dekking"].items())
            + ". Soortengroepen die hier niet in staan, zijn niet op een Rode Lijst beoordeeld.")


def datasets_inleiding(D: dict) -> str:
    return (f"Alle GBIF-datasets die records leveren binnen de zoekstraal voor soorten ({D['straal_m']:.0f} m), met hun "
            "aandeel en hun licentie. De kolom <i>soorten</i> telt hoeveel van de soorten met status uit die dataset komen. "
            "Voor datasets onder CC BY is naamsvermelding vereist; neem deze tabel over bij hergebruik van de gegevens.")


def dataset_rijen(tel: dict) -> list[list[str]]:
    return [[(d.get("dataset") or d["dataset_key"]), d.get("licentie") or "—", _getal(d['aantal_records']),
             str(d.get("aantal_soorten_met_status", "—"))] for d in tel["per_dataset"][:12]]


def licentie_noot(kern: dict) -> str:
    return ("Licentiekeuze: " + (kern.get("licentiefilter") or "—") + ". "
            + ("Verdeling van alle records in het gebied vóór die keuze: "
               + "; ".join(f"{k}: {_getal(v)}" for k, v in (kern.get("licenties") or {}).items()) + "."
               if kern.get("licenties") else ""))


def dekking_inleiding(D: dict) -> str:
    return ("Soortgroepen die als onvolledig gedekt op GBIF gemarkeerd zijn: ze worden vooral via waarnemingen.be gemeld, "
            "waarvan het grootste deel niet op GBIF staat. Aandeel van de GBIF-records in het zoekgebied voor soorten "
            f"({D['straal_m']:.0f} m) per brondataset.")


DEKKING_KOP = ["Groep", "Records", "Grootste brondatasets (aandeel)", "Waarschuwing"]


def dekking_rijen(kern: dict) -> list[list[str]]:
    return [[f"{g['groep']}<br/><i>{g.get('wetenschappelijke_naam') or ''}</i>",
             str(g.get("totaal", "—")) if g.get("status") == "ok" else "niet geraadpleegd",
             "<br/>".join(f"{_kort({'dataset_key': d['dataset_key']})} {d['aandeel']:.0%}" for d in (g.get("per_dataset") or [])[:3]) or "—",
             g.get("waarschuwing") or "—"] for g in kern["dekking"]]


def kaartlagen(D: dict) -> tuple[list[str], list[list[str]]] | None:
    kaarten = kaartlijst(D)
    if not kaarten:
        return None
    kaart = kaarten[0]
    return (["Laag", "Kleur op de kaart", f"Vlakken binnen {int(kaart['straal_m'])} m"],
            [[l["naam"], l["kleur"], str(l["aantal_vlakken"])] for l in kaart.get("legende", [])])


def reproduceerbaarheid(kern: dict) -> list[tuple[str, str]]:
    return [
        ("Bevraging", tijd(kern["geraadpleegd_op"])),
        ("Filter", kern["filter"]),
        ("GBIF-zoekopdracht", f'<font size="6.6">{kern["zoek_url"][:300]}</font>'),
        ("Occurrence-API", "https://api.gbif.org/v1/occurrence/search"),
        ("Soortenlijsten", "https://natuurdata.inbo.be (Vlaams Biodiversiteitsportaal, INBO)"),
        ("Gebiedslagen", "WFS Departement Omgeving (Mercator), Digitaal Vlaanderen (BWK) en INBO (ecotoopkwetsbaarheid, "
                         "https://gisservices.inbo.be/arcgis/services/Ecotoopkwetsbaarheid/MapServer/WFSServer)"),
        ("Kaartondergrond", "GRB-basiskaart, WMS Digitaal Vlaanderen (https://geo.api.vlaanderen.be/GRB/wms)"),
        ("Geocodering", "https://geo.api.vlaanderen.be/geolocation/v4/Location"),
    ]


def beperkingen(kern: dict) -> list[str]:
    """Opsomming van hoofdstuk 8, inclusief de waarschuwingen uit de bevraging."""
    uit = [
        kern["kanttekening"],
        "De brondataset zegt iets over de herkomst van de determinatie, niet over de validatiestatus van het "
        "individuele record. Waarnemingen.be stuurt niet alle validatieklassen door naar GBIF, en verscheidene "
        "datasets vullen het veld identificationVerificationStatus niet in. Uit een datasetnaam mag geen "
        "betrouwbaarheidsklasse worden afgeleid.",
        "De koppeling tussen waarneming en soortenlijst gebeurt op de GBIF-taxonsleutel. Ondersoorten en "
        "synoniemen kunnen daardoor buiten de koppeling vallen.",
        "De erkende en Vlaamse natuurreservaten (kernzones) en de bosreservaten zitten niet in de geraadpleegde "
        "WFS-diensten. Verifieer voor het dossier op Geopunt.",
        "Biologische Waarderingskaart: eenheden en habitatcodes zijn karteringseenheden, geen juridisch statuut. "
        "Afstanden zijn berekend tot de rand van de gepubliceerde polygoon. De karteringen dateren van verschillende "
        "jaren (kolom versie en veld HERK); een oude kartering kan achterhaald zijn. Aandelen van habitattypes "
        "(PHAB) kunnen het resultaat zijn van een automatische verdeling en lokaal sterk afwijken van het terrein.",
        "Ecotoopkwetsbaarheid: INBO omschrijft de kaarten als signaalkaarten op schaal Vlaanderen; bij gebruik voor lokale "
        "situaties is een bijkomende controle op lokaal niveau wenselijk. De kwetsbaarheid steunt op de BWK-kartering "
        "van de polygoon (kolom BWK-versie) en is geen juridisch statuut.",
        "Dit rapport is een bronnenscan, geen terreininventarisatie en geen passende beoordeling. Het bevat "
        "uitsluitend wat de geraadpleegde databanken op het genoemde tijdstip teruggaven.",
        PRIVACY,
        DISCLAIMER,
    ]
    uit += ["<b>Waarschuwing uit de bevraging:</b> " + w for w in kern.get("waarschuwingen", [])]
    return uit


# ---------------------------------------------------------------- PDF


def bwk_tabel(laag: dict, kaarten: list[dict], straal: int) -> list:
    """Tabel 5.1: alle BWK-eenheden binnen de straal; kolom 'kaart' = nummer van de legenderegel op de BWK-kaart."""
    return [
        Spacer(1, 8),
        P(BWK_TITEL, "h2"),
        P(bwk_inleiding(laag, straal), "klein"),
        Spacer(1, 3),
        tabel(BWK_KOP, bwk_rijen(laag, kaarten), [26, 36, 58, 160, 72, 70, 38], klein=True),
        Spacer(1, 3),
    ] + [P(n, "klein") for n in bwk_noten(laag)]


def ecotoop_tabel(laag: dict, straal: int) -> list:
    """Tabel 5.2: alle polygonen van de ecotoopkwetsbaarheidskaarten binnen de straal."""
    return [
        Spacer(1, 8),
        P(ECOTOOP_TITEL, "h2"),
        P(ecotoop_inleiding(laag, straal), "klein"),
        Spacer(1, 3),
        tabel(ECOTOOP_KOP, ecotoop_rijen(laag), [40, 70, 92, 72, 72, 72, 42], klein=True),
        Spacer(1, 3),
    ] + [P(n, "klein") for n in ecotoop_noten(laag)]


def schrijf_pdf(D: dict, pad: str) -> dict:
    """Schrijf het datarapport natuur naar `pad`. `D` bevat de sleutels locatie, telling, kern,
    gebieden, kaarten (lijst, mag leeg), detail, straal_m, jaar_van en connector."""
    verhaal: list = []
    tel, kern, geb = D["telling"], D["kern"], D["gebieden"]
    straal_soorten, straal_gebieden = stralen(D)

    # ---------------------------------------------------------------- blad 1: titel + situering
    verhaal += [
        P("Datarapport natuur", "titel"),
        P(ondertitel(D), "ondertitel"),
        kv(titelgegevens(D)),
        Spacer(1, 8),
        _kader(KADER),
        Spacer(1, 8),
        P("1. Samenvatting", "h1"),
    ] + [P(t) for t in samenvatting(D)]

    kaarten = kaartlijst(D)
    if kaarten:
        from PIL import Image as PILImage

        verhaal += [PageBreak(), P("2. Situering", "h1"), P(situering(kaarten))]
        for i, k in enumerate(kaarten, start=1):
            with PILImage.open(k["pad"]) as im:
                bpx, hpx = im.size
            max_breedte = 460 if len(kaarten) == 1 else 380
            schaal = max_breedte / bpx
            titel = k.get("titel") or f"Kaart {i}"
            verhaal += [
                Spacer(1, 8),
                P(f"Figuur {i} — {titel}", "h2"),
                RLImage(k["pad"], width=max_breedte, height=hpx * schaal),
                Spacer(1, 5),
                kaartlegende(k["legende"], kolommen=2 if len(k["legende"]) > 5 else 1),
            ]
            if i < len(kaarten):
                verhaal.append(PageBreak())
        verhaal += [Spacer(1, 6), P(kaarten[0]["kanttekening"], "klein"), PageBreak()]

    verhaal += [
        Spacer(1, 4),
        P("3. Statussen in cijfers", "h1"),
        tabel(["Lijst", "Categorie", "Aantal soorten"], statussen_rijen(tel), [170, 200, 90]),
        Spacer(1, 6),
        P(STATUSSEN_NOOT, "klein"),
        PageBreak(),
    ]

    # ---------------------------------------------------------------- blad 2: kernsoorten
    verhaal += [
        P("4. Kernsoorten", "h1"),
        P(kernsoorten_inleiding(D)),
        Spacer(1, 3),
        tabel(KERNSOORTEN_KOP, kernsoorten_rijen(kern), [104, 116, 16, 24, 24, 22, 154]),
        Spacer(1, 6),
        P(kernsoorten_noot(kern), "klein"),
        PageBreak(),
    ]

    # ---------------------------------------------------------------- blad 3: gebieden + detail
    grijs_rijen, bwk_laag = gebieden_rijen(geb)
    verhaal += [
        P("5. Beschermde gebieden en gebiedsstatuten", "h1"),
        P(gebieden_inleiding(geb)),
        Spacer(1, 3),
        tabel(["Laag", "Resultaat"], grijs_rijen, [175, 285]),
        Spacer(1, 6),
        P(geb["kanttekening"], "klein"),
    ]
    if bwk_laag and bwk_laag["treffers"]:
        verhaal += bwk_tabel(bwk_laag, kaarten, straal_gebieden)
    eco_laag = ecotoop_laag(geb)
    if eco_laag:
        verhaal += ecotoop_tabel(eco_laag, straal_gebieden)
    verhaal += [Spacer(1, 10), P(DETAIL_TITEL, "h1"), P(DETAIL_INLEIDING)]

    for blok in D["detail"]:
        titel, noot, rijen = detail_blok(blok)
        verhaal.append(KeepTogether([
            Spacer(1, 6),
            P(titel, "h2"),
            P(noot, "klein"),
            Spacer(1, 2),
            tabel(DETAIL_KOP, rijen, [52, 158, 38, 100, 112]),
        ]))

    verhaal.append(PageBreak())

    # ---------------------------------------------------------------- blad 4: verantwoording
    verhaal += [
        P("7. Verantwoording van de bronnen", "h1"),
        P("7.1 Geraadpleegde soortenlijsten", "h2"),
        tabel(["Code", "Lijst", "Opgehaald op"], lijst_rijen(kern), [80, 270, 110]),
        Spacer(1, 4),
        P(rodelijst_noot(kern), "klein"),
        Spacer(1, 10),
        P("7.2 Brondatasets in het zoekgebied", "h2"),
        P(datasets_inleiding(D), "klein"),
        Spacer(1, 3),
        tabel(["Dataset", "Licentie", "Records", "Soorten"], dataset_rijen(tel), [270, 70, 60, 60]),
        Spacer(1, 4),
        P(licentie_noot(kern), "klein"),
    ]
    if kern.get("dekking"):
        verhaal += [
            Spacer(1, 10),
            P("7.2bis Dekking per soortgroep", "h2"),
            P(dekking_inleiding(D), "klein"),
            Spacer(1, 3),
            tabel(DEKKING_KOP, dekking_rijen(kern), [70, 45, 150, 195]),
        ]
    lagen = kaartlagen(D)
    verhaal += [
        Spacer(1, 10),
        P("7.3 Kaartlagen", "h2"),
        tabel(lagen[0], lagen[1], [260, 90, 110]) if lagen else Spacer(1, 0),
        Spacer(1, 10),
        P("7.4 Reproduceerbaarheid", "h2"),
        kv(reproduceerbaarheid(kern), 120),
        Spacer(1, 12),
        P("8. Beperkingen", "h1"),
    ]
    verhaal += [P("• " + zin) for zin in beperkingen(kern)]

    # ---------------------------------------------------------------- opmaak
    def voet(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GRIJS)
        canvas.drawString(20 * mm, 12 * mm, voettekst(D))
        canvas.drawString(20 * mm, 8.5 * mm, VOETTEKST_2)
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"{doc.page}")
        canvas.setStrokeColor(LIJN)
        canvas.line(20 * mm, 15 * mm, A4[0] - 20 * mm, 15 * mm)
        canvas.restoreState()


    doc = BaseDocTemplate(pad, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
                          title="Datarapport natuur", author="MCP-connector BE-biodiversiteit")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normaal")
    doc.addPageTemplates([PageTemplate(id="std", frames=[frame], onPage=voet)])
    doc.build(verhaal)

    return {"pad": pad, "paginas": doc.page}
