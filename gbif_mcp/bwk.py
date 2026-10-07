# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Interpretatie van BWK-karteringseenheden (laag BWK:Bwkhab) op basis van de INBO-legende.

De opzoektabel `data/bwk_legende.json` wordt gebouwd door `scripts/bwk_legende_bouwen.py` uit de
officiële INBO-bronnen (folder karteringseenheden versie 2025; De Saeger et al. 2025 voor EVAL en
HABLEGENDE; n2khab voor de namen van habitattypes en rbb). Niets wordt geraden: een code die niet
in de legende staat, krijgt "onbekend in legende".

Afleidingsregels die de folder zelf geeft en die hier worden toegepast:
- `+`/`-` achter een code (in publicaties * en °): vegetatiekundig goed/zwak ontwikkeld;
- `b` achter een code: open vegetatie met beperkte opslag van struiken en bomen.
Een eenheid met een eigen legendeomschrijving (bv. `lhb`, `hp+`) gaat altijd voor op die regels.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ONBEKEND = "onbekend in legende"
GEEN_HABITAT = "geen habitat"


@lru_cache(maxsize=1)
def legende() -> dict[str, Any]:
    return json.loads((Path(__file__).parent / "data" / "bwk_legende.json").read_text(encoding="utf-8"))


def bronvermelding() -> str:
    b = legende()["bronnen"]
    return "; ".join(f"{v['titel']} ({v['url']})" for v in b.values())


def waardering(eval_: str | None) -> str:
    """EVAL-code -> omschrijving volgens tabel 2-1 van De Saeger et al. 2025."""
    code = (eval_ or "").strip().lower()
    return legende()["eval"].get(code, ONBEKEND if code else "geen waardering in de bron")


def is_waardevol(eval_: str | None) -> bool:
    """Bevat de waardering een biologisch waardevol (w) of zeer waardevol (z) element (zuiver of in complex)."""
    return any(c in (eval_ or "").lower() for c in "wz")


def eenheid_omschrijving(code: str) -> str:
    """Leesbare omschrijving van één karteringseenheid (EENHx)."""
    e = legende()["eenheden"]
    c = code.strip()
    if not c:
        return ONBEKEND
    if c in e:
        return e[c]
    if c.lower() in e:
        return e[c.lower()]
    regels = legende()["regels"]
    # Boomcode als losse eenheid (bv. 'sam', 'cra' in een complex).
    if c.lower() in legende()["bomen"]:
        return f"boomsoort: {legende()['bomen'][c.lower()]}"
    if c[-1] in "+-" and len(c) > 1:
        basis = eenheid_omschrijving(c[:-1])
        if basis != ONBEKEND:
            # Bij bomenrij en houtkant heeft * of ° een eigen betekenis (kb°: recent aangeplant …).
            for prefix in ("khw", "kh", "kb"):
                if c.startswith(prefix) and prefix + c[-1] in e and prefix in e:
                    return f"{basis}, {e[prefix + c[-1]][len(e[prefix]) + 2:]}"
            return f"{basis}, {regels[c[-1]]}"
    if c.endswith("b") and len(c) > 2 and c[:-1] in e:
        return f"{e[c[:-1]]}, {regels['b']}"
    return ONBEKEND


def habitatnaam(code: str) -> str:
    """Naam van een habitattype of rbb (INBO n2khab); voor een subtype zonder eigen naam die van het hoofdtype."""
    h = legende()["habitats"]
    c = code.strip()
    if c.lower() == "gh":
        return GEEN_HABITAT
    if c in h:
        return h[c]
    hoofd = c.split("_")[0]
    if hoofd in h and hoofd != c:
        return f"{h[hoofd]} (subtype {c})"
    return ONBEKEND


def soort_code(code: str) -> str:
    c = code.strip().lower()
    if c == "gh":
        return "geen habitat"
    if c[:1].isdigit():
        return "habitattype"
    if c.startswith("rbb"):
        return "rbb"
    return "onbekend"


def habitats(props: dict) -> list[dict]:
    """HAB1..HAB5 met PHAB1..PHAB5. Een veld met meerdere codes (bv. '6430,rbbhf') is een onzekere
    bepaling volgens de legende; elke code krijgt dan dat aandeel met `onzeker=True`."""
    uit: list[dict] = []
    for i in range(1, 6):
        veld = str(props.get(f"HAB{i}") or "").strip()
        if not veld:
            continue
        aandeel = props.get(f"PHAB{i}")
        codes = [c.strip() for c in veld.split(",") if c.strip()]
        for c in codes:
            uit.append({
                "veld": f"HAB{i}", "code": c, "soort": soort_code(c), "naam": habitatnaam(c),
                "aandeel_pct": int(aandeel) if isinstance(aandeel, (int, float)) else None,
                "onzeker": len(codes) > 1,
            })
    return uit


def karteerversie(tag: str | None) -> str | None:
    """Uit TAG (bv. '326375_v2014') de karteerversie ('v2014')."""
    t = str(tag or "")
    return t.rsplit("_", 1)[-1] if "_" in t else (t or None)


def kaartsleutel(props: dict) -> str:
    """Groep waarin een eenheid op de BWK-kaart wordt getekend; dezelfde sleutel staat in de rapporttabel,
    zodat kaartnummer en tabel overeenkomen. Volgorde: eerste habitattype uit HAB1..HAB5, anders eerste rbb,
    anders de waardering (EVAL)."""
    hs = habitats(props)
    for soort in ("habitattype", "rbb"):
        for h in hs:
            if h["soort"] == soort:
                return h["code"]
    return "eval:" + (str(props.get("EVAL") or "").strip().lower() or "?")


def kaartsleutel_naam(sleutel: str) -> str:
    if sleutel.startswith("eval:"):
        return f"BWK zonder habitat of rbb — {waardering(sleutel[5:])}"
    return f"BWK {sleutel} — {habitatnaam(sleutel)}"


def _getekend(sleutel: str, overlapt: bool) -> bool:
    return overlapt or not sleutel.startswith("eval:") or is_waardevol(sleutel[5:])


def toon_op_kaart(props: dict, overlapt: bool) -> bool:
    """Eenheden zonder habitat, rbb of waardevol element alleen tekenen als het doel erin ligt."""
    return _getekend(kaartsleutel(props), overlapt)


def wordt_getekend(e: dict, overlapt: bool) -> bool:
    """Zelfde regel als `toon_op_kaart`, op een al afgeleide eenheid (zie `eenheid`)."""
    return _getekend(e["kaartsleutel"], overlapt)


def eenheid(props: dict) -> dict:
    """Alle bronvelden plus de afgeleide velden van één BWK-eenheid."""
    eenh = [str(props.get(f"EENH{i}") or "").strip() for i in range(1, 9)]
    eenh = [e for e in eenh if e]
    hs = habitats(props)
    return {
        "uidn": props.get("UIDN"),
        "bwklabel": props.get("BWKLABEL") or None,
        "eenheden": [{"code": e, "omschrijving": eenheid_omschrijving(e)} for e in eenh],
        "eval": props.get("EVAL") or None,
        "waardering": waardering(props.get("EVAL")),
        "habitats": hs,
        "bevat_habitat": any(h["soort"] == "habitattype" for h in hs),
        "bevat_rbb": any(h["soort"] == "rbb" for h in hs),
        "hablegende": props.get("HABLEGENDE") or None,
        "info": props.get("INFO") or None,
        "tag": props.get("TAG") or None,
        "karteerjaar_of_versie": karteerversie(props.get("TAG")),
        "herk": props.get("HERK") or None,
        "kaartsleutel": kaartsleutel(props),
    }


def habitat_tekst(e: dict) -> str:
    """'6510_hu 40 %, rbbmr 30 %' of 'geen habitat'; 'gh' komt nooit als losse code in tekst."""
    delen = [f"{h['code']} {h['aandeel_pct']} %" if h["aandeel_pct"] is not None else h["code"]
             for h in e["habitats"] if h["soort"] in ("habitattype", "rbb")]
    return ", ".join(delen) if delen else GEEN_HABITAT


def samenvatting(treffers: list) -> dict:
    """Gestructureerde samenvatting over ALLE eenheden binnen de straal (vóór inkorting).
    `treffers`: GebiedTreffer-objecten met `.bwk`."""
    met = [t for t in treffers if t.bwk]
    zelf = [t for t in met if t.overlapt]
    per_waardering: dict[str, int] = {}
    for t in met:
        k = (t.bwk.get("eval") or "?")
        per_waardering[k] = per_waardering.get(k, 0) + 1
    zeer = sum(1 for t in met if "z" in (t.bwk.get("eval") or "").lower())
    waardevol = sum(1 for t in met if "w" in (t.bwk.get("eval") or "").lower() and "z" not in (t.bwk.get("eval") or "").lower())

    def _lijst(soort: str) -> list[dict]:
        uit: dict[str, dict] = {}
        for t in met:  # treffers zijn al gesorteerd: overlap eerst, dan afstand
            for h in t.bwk["habitats"]:
                if h["soort"] != soort:
                    continue
                vorige = uit.get(h["code"])
                if vorige is None:
                    uit[h["code"]] = {"code": h["code"], "naam": h["naam"], "aandeel_pct": h["aandeel_pct"],
                                      "afstand_m": t.afstand_m, "label": t.bwk.get("bwklabel"), "aantal_eenheden": 1}
                else:
                    vorige["aantal_eenheden"] += 1
        return list(uit.values())

    dichtste = next((t for t in met if is_waardevol(t.bwk.get("eval"))), None)
    return {
        "locatie_zelf": [{"label": t.bwk.get("bwklabel"), "waardering": t.bwk["waardering"], "habitat": habitat_tekst(t.bwk),
                          "karteerjaar_of_versie": t.bwk.get("karteerjaar_of_versie")} for t in zelf],
        "binnen_straal": {"totaal": len(met), "waardevol": waardevol, "zeer_waardevol": zeer, "per_eval": per_waardering},
        "habitattypes_binnen_straal": _lijst("habitattype"),
        "rbb_binnen_straal": _lijst("rbb"),
        "dichtste_waardevol": ({"label": dichtste.bwk.get("bwklabel"), "waardering": dichtste.bwk["waardering"],
                                "afstand_m": dichtste.afstand_m} if dichtste else None),
        "toelichting": "waardevol = EVAL bevat w maar geen z; zeer_waardevol = EVAL bevat z (zuiver of als complex). "
                       "habitattypes/rbb: eerste (dichtste) eenheid per code, met het aandeel in die eenheid.",
    }
