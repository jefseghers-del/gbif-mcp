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
        naam = r["naam"] if r["status"] == "ok" else r["naam"] + " — niet geraadpleegd"
        if r.get("aantal_vlakken") and r["laag"] != "_zoek":
            naam += f" ({r['aantal_vlakken']})"
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



def schrijf_pdf(D: dict, pad: str) -> dict:
    """Schrijf het datarapport natuur naar `pad`. `D` bevat de sleutels locatie, telling, kern,
    gebieden, kaarten (lijst, mag leeg), detail, straal_m, jaar_van en connector."""
    verhaal: list = []
    P = lambda t, s="tekst": Paragraph(t, S[s])  # noqa: E731
    loc, tel, kern, geb = D["locatie"], D["telling"], D["kern"], D["gebieden"]
    periode = f"{D['jaar_van']} tot heden"
    straal_soorten = D["straal_m"]
    straal_gebieden = int(geb["straal_m"])
    # Soorten en gebieden worden met een eigen zoekstraal bevraagd; de ondertitel noemt ze allebei,
    # anders suggereert één afstand ten onrechte dat beide even ver reiken.
    if float(straal_soorten) == float(straal_gebieden):
        ondertitel = f"Beschermde soorten en gebiedsstatuten binnen {straal_soorten:.0f} m<br/>{loc['adres']}"
    else:
        ondertitel = (f"Beschermde soorten binnen {straal_soorten:.0f} m, gebiedsstatuten binnen "
                      f"{straal_gebieden} m<br/>{loc['adres']}")
    connector = D.get("connector") or "MCP-connector BE-biodiversiteit"

    # ---------------------------------------------------------------- blad 1: titel + situering
    verhaal += [
        P("Datarapport natuur", "titel"),
        P(ondertitel, "ondertitel"),
        kv([
            ("Projectlocatie", f"{loc['adres']} ({loc['gemeente']})"),
            ("Coördinaten WGS 84", f"{loc['lat']:.5f} N / {loc['lon']:.5f} O"),
            ("Coördinaten Lambert 72", f"x {loc['x_lambert72']:.2f} / y {loc['y_lambert72']:.2f}"),
            ("Geocodering", f"{loc['type']} — {loc['bron']}"),
            ("Zoekgebied soorten", f"straal {straal_soorten:.0f} m rond de projectlocatie"),
            ("Zoekgebied gebieden", f"straal {straal_gebieden} m rond de projectlocatie"),
            ("Periode", periode),
            ("Bevraging uitgevoerd", tijd(kern["geraadpleegd_op"])),
            ("Instrument", f"{connector} (GBIF + Vlaams Biodiversiteitsportaal)"),
            ("Datalicenties", (kern.get("licentiefilter") or "—")
             + (f" ({_getal(kern['uitgesloten_niet_commercieel'])} records weggelaten)" if kern.get("uitgesloten_niet_commercieel") else "")),
        ]),
        Spacer(1, 8),
        _kader(f"<b>{DISCLAIMER_KORT}</b> De resultaten zijn een geautomatiseerde bronnenscan en vervangen geen "
               "terreininventarisatie, deskundige beoordeling of juridisch advies. Volledige disclaimer in hoofdstuk 8."),
        Spacer(1, 8),
        P("1. Samenvatting", "h1"),
        P(
            f"Binnen een straal van {straal_soorten:.0f} m rond de projectlocatie zijn sinds {D['jaar_van']} in totaal "
            f"<b>{_getal(tel['totaal_waarnemingen'])}</b> waarnemingen van <b>{tel['totaal_soorten']}</b> soorten gemeld in GBIF. "
            f"Daarvan hebben <b>{tel['totaal_soorten_met_status']}</b> soorten een beschermings-, Rode-Lijst- of exotenstatus. "
            f"<b>{tel['kern']}</b> soorten hebben een kernstatus voor de natuurtoets: bijlage IV van de Habitatrichtlijn "
            f"(categorie 3 van het Soortenbesluit), bijlage II van de Habitatrichtlijn, bijlage I van de Vogelrichtlijn, "
            f"of een Rode-Lijstcategorie RE, CR, EN of VU. Daarnaast zijn <b>{tel['exoten']}</b> soorten met status "
            f"geregistreerd als uitheems."
        ),
    ]

    samenvatting_geb = geb.get("samenvatting") or {}
    laagnamen = {l["laag"]: l["naam"] for l in geb["lagen"]}
    if straal_gebieden > straal_soorten:
        straal_zin = f"Voor de gebiedsstatuten is een ruimere straal van {straal_gebieden} m gehanteerd."
    elif straal_gebieden < straal_soorten:
        straal_zin = f"Voor de gebiedsstatuten is een kleinere straal van {straal_gebieden} m gehanteerd."
    else:
        straal_zin = f"Ook de gebiedsstatuten zijn binnen {straal_gebieden} m bevraagd."
    if samenvatting_geb:
        verhaal.append(P(
            f"{straal_zin} Daarbinnen zijn treffers gevonden in de volgende gebiedslagen: "
            + "; ".join(f"{laagnamen.get(k, k)}: {v}" for k, v in samenvatting_geb.items()) + "."
        ))
    else:
        verhaal.append(P(
            f"{straal_zin} Daarbinnen is in geen van de {len(geb['lagen'])} geraadpleegde gebiedslagen een "
            "beschermd gebied of gebiedsstatuut aangetroffen."
        ))

    # Eén kaart (sleutel `kaart`) of meerdere thematische kaarten (sleutel `kaarten`).
    kaarten = D.get("kaarten") or ([D["kaart"]] if D.get("kaart") else [])
    kaart = kaarten[0] if kaarten else None
    if kaarten:
        from PIL import Image as PILImage

        verhaal += [PageBreak(), P("2. Situering", "h1"), P(
            f"Uitsnede rond de projectlocatie, straal {int(kaarten[0]['straal_m'])} m. De rode stip is de "
            f"projectlocatie, de rode cirkel de zoekstraal. Ondergrond: {kaarten[0]['achtergrond']}. "
            f"Coördinaatstelsel Lambert 72; de schaalbalk is metrisch. "
            + ("De kaarten hebben dezelfde uitsnede en schaal en zijn dus over elkaar te leggen. " if len(kaarten) > 1 else "")
            + "Elk vlak draagt het nummer van zijn legenderegel, en elke laag heeft een eigen arcering: "
            "de kaart is dus ook leesbaar zonder kleuronderscheid en in grijswaarden."
        )]
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
        tabel(
            ["Lijst", "Categorie", "Aantal soorten"],
            [[c, cat, str(n)] for c, cats in tel["per_categorie"].items() for cat, n in sorted(cats.items(), key=lambda kv: -kv[1])],
            [170, 200, 90],
        ),
        Spacer(1, 6),
        P(
            "De lijstcodes verwijzen naar de gezaghebbende soortenlijsten van het Vlaams Biodiversiteitsportaal; "
            "de volledige benaming en de bron-URL per lijst staan in hoofdstuk 7.",
            "klein",
        ),
        PageBreak(),
    ]

    # ---------------------------------------------------------------- blad 2: kernsoorten
    verhaal += [P("4. Kernsoorten", "h1"), P(
        f"Alle soorten met kernstatus, gesorteerd van strikt naar minder strikt beschermd en daarna op aantal waarnemingen. "
        f"De kolom <i>herkomst</i> geeft de brondatasets waaruit de waarnemingen van die soort komen, met hun "
        f"aandeel. <i>onz.</i> is de grootste opgegeven coördinaatonzekerheid in meter; <i>zeker</i> is het aantal "
        f"records waarvan de locatie inclusief die onzekerheid met zekerheid binnen de zoekstraal voor soorten "
        f"({straal_soorten:.0f} m) valt. Een onzekerheid van 707 m wijst op een naar een hok vervaagde locatie."
    )]

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

    verhaal += [
        Spacer(1, 3),
        tabel(["Soort", "Status", "n", "jaar", "onz.", "zek.", "Herkomst van de waarnemingen"],
              rijen, [104, 116, 16, 24, 24, 22, 154]),
        Spacer(1, 6),
        P(
            f"Aantal kernsoorten: {len(kern['soorten'])}. Volledigheid van de bevraging: "
            + ("alle gevraagde gegevens zijn opgehaald." if kern["volledig"] else "onvolledig — " + "; ".join(kern["ontbrekend"]) + "."),
            "klein",
        ),
        PageBreak(),
    ]

    # ---------------------------------------------------------------- blad 3: gebieden + detail
    verhaal += [P("5. Beschermde gebieden en gebiedsstatuten", "h1"), P(
        f"Resultaat per geraadpleegde laag binnen {int(geb['straal_m'])} m. Een afstand van 0 m betekent dat de "
        "projectlocatie binnen het gebied ligt. Lagen met de vermelding <i>niet geraadpleegd</i> gaven een fout: "
        "daaruit volgt niet dat er geen gebied ligt."
    )]

    grijs_rijen = []
    for laag in geb["lagen"]:
        if laag["status"] != "ok":
            res = f"niet geraadpleegd — {laag.get('melding') or ''}"
        elif not laag["treffers"]:
            res = f"geen treffer binnen {straal_gebieden} m"
        else:
            t = laag["treffers"][0]
            naam = t["naam"] or t["code"] or "(zonder naam)"
            if laag["laag"].startswith("bwk_habitat") and naam == "gh":
                naam = "karteringseenheid gh (geen Natura 2000-habitat ter plaatse)"
            res = (f"<b>ligt binnen</b> {naam}" if t["overlapt"] else f"dichtstbij {naam}, op {t['afstand_m']} m")
            if t["code"] and t["naam"]:
                res += f" (code {t['code']})"
            if laag["aantal_binnen_straal"] > 1:
                res += f" — {laag['aantal_binnen_straal']} treffers in totaal"
        grijs_rijen.append([laag["naam"], res])

    verhaal += [
        Spacer(1, 3),
        tabel(["Laag", "Resultaat"], grijs_rijen, [175, 285]),
        Spacer(1, 6),
        P(geb["kanttekening"], "klein"),
        Spacer(1, 10),
        P("6. Onderliggende waarnemingen van de striktst beschermde soorten", "h1"),
        P(
            "Per soort de individuele records uit de dataset die er de meeste levert. De verificatiestatus is "
            "letterlijk overgenomen uit GBIF (veld <i>identificationVerificationStatus</i>); een leeg veld betekent "
            "dat de bron die informatie niet meelevert, niet dat het record onbetrouwbaar is."
        ),
    ]

    for blok in D["detail"]:
        s, w = blok["soort"], blok["waarnemingen"]
        ds_naam = next((d.get("dataset") for d in (s["datasets"] or []) if d["dataset_key"] == blok["dataset_key"]), blok["dataset_key"])
        rijen = [[
            x["datum"] or "", x["plaats"] or x["gemeente"] or "", f"{x['onzekerheid_m']:.0f}" if x["onzekerheid_m"] else "",
            x["verificatiestatus"] or "—", x.get("basis") or "",
        ] for x in w["waarnemingen"]]
        verhaal.append(KeepTogether([
            Spacer(1, 6),
            P(f"{s['nederlandse_naam']} ({s['wetenschappelijke_naam']}) — {s['samenvatting'].get('hrl_iv_vl') or list(s['samenvatting'].values())[0]}", "h2"),
            P(f"Bron: {ds_naam}. Records getoond: {len(rijen)} van {w['totaal']} in deze dataset. "
              f"Verificatiestatus: {', '.join(f'{k} ({v})' for k, v in w['per_verificatiestatus'].items())}.", "klein"),
            Spacer(1, 2),
            tabel(["Datum", "Plaats", "onz. (m)", "Verificatie", "Soort record"], rijen, [52, 168, 38, 110, 92]),
        ]))

    verhaal.append(PageBreak())

    # ---------------------------------------------------------------- blad 4: verantwoording
    verhaal += [P("7. Verantwoording van de bronnen", "h1"), P("7.1 Geraadpleegde soortenlijsten", "h2")]

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
    rijen = [[c, LIJSTNAMEN.get(c, c), tijd(v) if v else "—"] for c, v in kern["lijstversies"].items()]
    verhaal += [
        tabel(["Code", "Lijst", "Opgehaald op"], rijen, [80, 270, 110]),
        Spacer(1, 4),
        P("Dekking van de Rode Lijsten: " + "; ".join(f"<b>{k}</b> — {v}" for k, v in kern["rodelijst_dekking"].items())
          + ". Soortengroepen die hier niet in staan, zijn niet op een Rode Lijst beoordeeld.", "klein"),
        Spacer(1, 10),
        P("7.2 Brondatasets in het zoekgebied", "h2"),
        P(f"Alle GBIF-datasets die records leveren binnen de zoekstraal voor soorten ({straal_soorten:.0f} m), met hun "
          "aandeel en hun licentie. De kolom <i>soorten</i> telt hoeveel van de soorten met status uit die dataset komen. "
          "Voor datasets onder CC BY is naamsvermelding vereist; neem deze tabel over bij hergebruik van de gegevens.", "klein"),
        Spacer(1, 3),
        tabel(
            ["Dataset", "Licentie", "Records", "Soorten"],
            [[(d.get("dataset") or d["dataset_key"]), d.get("licentie") or "—", _getal(d['aantal_records']),
              str(d.get("aantal_soorten_met_status", "—"))] for d in tel["per_dataset"][:12]],
            [270, 70, 60, 60],
        ),
        Spacer(1, 4),
        P("Licentiekeuze: " + (kern.get("licentiefilter") or "—") + ". "
          + ("Verdeling van alle records in het gebied vóór die keuze: "
             + "; ".join(f"{k}: {_getal(v)}" for k, v in (kern.get("licenties") or {}).items()) + "."
             if kern.get("licenties") else ""), "klein"),
        Spacer(1, 10),
        P("7.3 Kaartlagen", "h2"),
        tabel(["Laag", "Kleur op de kaart", f"Vlakken binnen {int(kaart['straal_m']) if kaart else straal_gebieden} m"],
              [[l["naam"], l["kleur"], str(l["aantal_vlakken"])] for l in (kaart or {}).get("legende", [])],
              [260, 90, 110]) if kaart else Spacer(1, 0),
        Spacer(1, 10),
        P("7.4 Reproduceerbaarheid", "h2"),
        kv([
            ("Bevraging", tijd(kern["geraadpleegd_op"])),
            ("Filter", kern["filter"]),
            ("GBIF-zoekopdracht", f'<font size="6.6">{kern["zoek_url"][:300]}</font>'),
            ("Occurrence-API", "https://api.gbif.org/v1/occurrence/search"),
            ("Soortenlijsten", "https://natuurdata.inbo.be (Vlaams Biodiversiteitsportaal, INBO)"),
            ("Gebiedslagen", "WFS Departement Omgeving (Mercator) en Digitaal Vlaanderen (BWK)"),
            ("Kaartondergrond", "GRB-basiskaart, WMS Digitaal Vlaanderen (https://geo.api.vlaanderen.be/GRB/wms)"),
            ("Geocodering", "https://geo.api.vlaanderen.be/geolocation/v4/Location"),
        ], 120),
        Spacer(1, 12),
        P("8. Beperkingen", "h1"),
    ]

    for zin in [
        kern["kanttekening"],
        "De brondataset zegt iets over de herkomst van de determinatie, niet over de validatiestatus van het "
        "individuele record. Waarnemingen.be stuurt niet alle validatieklassen door naar GBIF, en verscheidene "
        "datasets vullen het veld identificationVerificationStatus niet in. Uit een datasetnaam mag geen "
        "betrouwbaarheidsklasse worden afgeleid.",
        "De koppeling tussen waarneming en soortenlijst gebeurt op de GBIF-taxonsleutel. Ondersoorten en "
        "synoniemen kunnen daardoor buiten de koppeling vallen.",
        "De erkende en Vlaamse natuurreservaten (kernzones) en de bosreservaten zitten niet in de geraadpleegde "
        "WFS-diensten. Habitatcodes uit de Biologische Waarderingskaart zijn karteringseenheden, geen juridisch "
        "statuut. Verifieer voor het dossier op Geopunt.",
        "Dit rapport is een bronnenscan, geen terreininventarisatie en geen passende beoordeling. Het bevat "
        "uitsluitend wat de geraadpleegde databanken op het genoemde tijdstip teruggaven.",
        PRIVACY,
        DISCLAIMER,
    ]:
        verhaal.append(P("• " + zin))

    for w in kern.get("waarschuwingen", []):
        verhaal.append(P("• <b>Waarschuwing uit de bevraging:</b> " + w))


    # ---------------------------------------------------------------- opmaak
    def voet(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GRIJS)
        canvas.drawString(20 * mm, 12 * mm, f"Datarapport natuur — {loc['adres']} — soorten {straal_soorten:.0f} m, "
                          f"gebieden {straal_gebieden} m — bevraagd {datum(kern['geraadpleegd_op'])}")
        canvas.drawString(20 * mm, 8.5 * mm, "Betaversie — zonder garantie; de gebruiker is zelf verantwoordelijk voor het gebruik.")
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
