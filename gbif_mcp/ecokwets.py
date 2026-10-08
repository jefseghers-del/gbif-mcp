# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Ecotoopkwetsbaarheidskaarten (INBO, versie 2 - 2025): interpretatie van de WFS-velden. Geen netwerk.

De WFS van INBO publiceert drie lagen (verdroging, eutrofiering, verzuring) met dezelfde polygonen en
dezelfde velden: elke polygoon draagt de kwetsbaarheid voor alle drie de milieudrukken (`kwetsverd`,
`kwetseutr`, `kwetsverz`) en de legendeklasse die de bron er zelf aan geeft (`kwetsverdr_legende`,
`kwetseutr_legende`, `kwetsverz_legende`). Daarom volstaat één bevraging (laag verdroging); vastgesteld
op 8 oktober 2026 (zie docs/gebieden-lagen.md).

De klasse wordt letterlijk uit het legendeveld overgenomen, nooit afgeleid uit het getal. Ontbreekt
het veld, dan heet de klasse "klasse niet omschreven in bron". De BWK-gegevens (waardering,
karteringseenheden met omschrijving) komen eveneens letterlijk uit de velden van deze dienst.
"""
from __future__ import annotations

DIENST = "https://gisservices.inbo.be/arcgis/services/Ecotoopkwetsbaarheid/MapServer/WFSServer"
METADATA = "https://metadata.vlaanderen.be/srv/api/records/67636b22-0e85-4ff3-9594-f77f3bc65754"
DATASET = "Ecotoopkwetsbaarheidskaarten voor Vlaanderen versie 2 - 2025"
BRONVERMELDING = "Bron: Instituut voor Natuur- en Bosonderzoek (INBO)"
LICENTIE = "Vlaamse Open Data-licentie v1.2"
# Letterlijk uit het veld useLimitation van het metadatarecord (geraadpleegd 8 oktober 2026).
GEBRUIKSBEPERKING = ("Het betreft signaalkaarten op schaal Vlaanderen. Bij gebruik voor lokale situaties is het wenselijk "
                     "een bijkomende controle op lokaal niveau uit te voeren.")

ONBEKEND = "klasse niet omschreven in bron"

# milieudruk -> (veld met de waarde, veld met de legendeklasse)
DRUKKEN: dict[str, tuple[str, str]] = {
    "verdroging": ("kwetsverd", "kwetsverdr_legende"),
    "eutrofiëring": ("kwetseutr", "kwetseutr_legende"),
    "verzuring": ("kwetsverz", "kwetsverz_legende"),
}


def _tekst(v) -> str | None:
    """Lege waarden van de dienst (' ', 'null') worden None."""
    if v is None:
        return None
    s = str(v).strip()
    return None if s in ("", "null", "None") else s


def _getal(v) -> float | None:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def eenheid(props: dict) -> dict:
    """Bronvelden van één polygoon, letterlijk, plus de kwetsbaarheid per milieudruk."""
    eenheden = []
    for i in range(1, 6):
        code = _tekst(props.get(f"eenheid_{i}"))
        if code:
            eenheden.append({"code": code, "omschrijving": _tekst(props.get(f"EENH{i}_omschrijving")) or "niet omschreven in bron"})
    tag = _tekst(props.get("TAG"))
    return {
        "bwklabel": _tekst(props.get("label_BWK_eenheden")),
        "eval": _tekst(props.get("waardering")),
        "waardering": _tekst(props.get("EVAL_omschrijving")),
        "eenheden": eenheden,
        "herk": _tekst(props.get("HERK")),
        "tag": tag,
        "versie_bwk": tag.rsplit("_", 1)[1] if tag and "_" in tag else None,
        "kwetsbaarheid": {
            druk: {"waarde": _getal(props.get(veld)), "klasse": _tekst(props.get(legende)) or ONBEKEND}
            for druk, (veld, legende) in DRUKKEN.items()
        },
    }


def klassen_tekst(e: dict) -> str:
    """'verdroging: zeer kwetsbaar (4.0); eutrofiëring: …' voor één polygoon."""
    k = e.get("kwetsbaarheid") or {}
    return "; ".join(f"{d}: {k[d]['klasse']}" + (f" ({k[d]['waarde']:g})" if k[d]["waarde"] is not None else "")
                     for d in DRUKKEN if d in k)


def samenvatting(treffers: list) -> dict:
    """Over ALLE polygonen binnen de straal (vóór inkorting). `treffers`: GebiedTreffer-objecten met `.ecotoop`.

    Per milieudruk: de hoogste waarde binnen de straal (met de klasse die de bron eraan geeft, het
    BWK-label en de afstand) en het aantal polygonen per klasse; daarnaast de kwetsbaarheid op de
    projectlocatie zelf."""
    met = [t for t in treffers if t.ecotoop]
    per_druk: dict[str, dict] = {}
    for druk in DRUKKEN:
        aantallen: dict[str, int] = {}
        laagste: dict[str, float] = {}  # om de klassen te ordenen volgens de bronwaarden, niet volgens voorkomen
        hoogste = None
        for t in met:  # al gesorteerd: overlap eerst, dan afstand; bij gelijke waarde wint de dichtste
            k = t.ecotoop["kwetsbaarheid"][druk]
            aantallen[k["klasse"]] = aantallen.get(k["klasse"], 0) + 1
            if k["waarde"] is not None:
                laagste[k["klasse"]] = min(laagste.get(k["klasse"], k["waarde"]), k["waarde"])
            if k["waarde"] is not None and (hoogste is None or k["waarde"] > hoogste[0]):
                hoogste = (k["waarde"], k["klasse"], t)
        per_druk[druk] = {
            "hoogste": ({"waarde": hoogste[0], "klasse": hoogste[1], "label": hoogste[2].ecotoop.get("bwklabel"),
                         "afstand_m": hoogste[2].afstand_m} if hoogste else None),
            "per_klasse": dict(sorted(aantallen.items(), key=lambda kv: laagste.get(kv[0], float("inf")))),
        }
    return {
        "locatie_zelf": [{"label": t.ecotoop.get("bwklabel"), "waardering": t.ecotoop.get("waardering"),
                          "kwetsbaarheid": t.ecotoop["kwetsbaarheid"]} for t in met if t.overlapt],
        "binnen_straal": {"totaal": len(met), "per_druk": per_druk},
        "toelichting": "Klassen letterlijk uit de legendevelden van de INBO-dienst; 'hoogste' = hoogste numerieke "
                       "kwetsbaarheid binnen de straal (bij gelijke waarde de dichtste polygoon). " + GEBRUIKSBEPERKING,
    }


def bronvermelding() -> str:
    return f"{BRONVERMELDING}, {DATASET} ({LICENTIE}; metadata {METADATA})"
