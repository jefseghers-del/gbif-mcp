# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Bouwt gbif_mcp/data/bwk_legende.json uit de officiële INBO-bronnen. Eenmalig, met netwerk.

Bronnen (geen enkele omschrijving komt uit het geheugen):
- Karteringseenheden: INBO-folder "Biologische Waarderingskaart — overzicht van de karteringseenheden,
  versie 2025" (pdftotext -layout).
- Waardering (EVAL) en HABLEGENDE: De Saeger et al. (2025), BWK en Natura 2000 Habitatkaart, uitgave
  2025, tabellen 2-1 en 2-8 (doi:10.21436/inbor.129502912). Die twee kleine tabellen staan hieronder
  letterlijk overgenomen.
- Habitattypes en regionaal belangrijke biotopen: INBO-pakket n2khab, inst/textdata/namelist.tsv
  (Nederlandse namen).

Gebruik:  python scripts/bwk_legende_bouwen.py
"""
from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

FOLDER_URL = "https://www.vlaanderen.be/inbo/media/2742/folder-karteringseenheden-bwk-v2025.pdf"
N2KHAB_REF = "master"
N2KHAB_URL = f"https://raw.githubusercontent.com/inbo/n2khab/{N2KHAB_REF}/inst/textdata/namelist.tsv"
RAPPORT_DOI = "https://doi.org/10.21436/inbor.129502912"
UIT = Path(__file__).resolve().parents[1] / "gbif_mcp" / "data" / "bwk_legende.json"

# De Saeger et al. 2025, tabel 2-1 (attribuutveld EVAL).
EVAL = {
    "z": "biologisch zeer waardevol",
    "w": "biologisch waardevol",
    "m": "biologisch minder waardevol",
    "wz": "complex van biologisch waardevolle en zeer waardevolle elementen",
    "mwz": "complex van biologisch minder waardevolle, waardevolle en zeer waardevolle elementen",
    "mz": "complex van biologisch minder waardevolle en zeer waardevolle elementen",
    "mw": "complex van biologisch minder waardevolle en waardevolle elementen",
}
# De Saeger et al. 2025, tabel 2-8 (attribuutveld HABLEGENDE).
HABLEGENDE = {
    "gh": "geen Natura 2000-habitattype aanwezig",
    "hab": "habitat: het volledige kaartvlak is habitatwaardig",
    "phab": "deels habitat: het kaartvlak bevat habitatwaardige en niet-habitatwaardige delen",
    "ohab": "onzeker habitat (kennislacune)",
}


def _haal(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (gbif-mcp legendebouwer)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _digitaal(code: str) -> str:
    """Notatie uit de publicatie (* en °) naar die van het digitale bestand (+ en -)."""
    return code.replace("*", "+").replace("°", "-")


def ontleed_folder(tekst: str) -> tuple[dict[str, str], dict[str, str]]:
    """Karteringseenheden en boomcodes uit de pdftotext-uitvoer van de folder."""
    eenheden: dict[str, str] = {}
    bomen: dict[str, str] = {}
    regels = tekst.splitlines()
    start = next(i for i, r in enumerate(regels) if r.strip().startswith("Karteringseenheden per klasse"))
    boom_start = next(i for i, r in enumerate(regels) if r.strip().startswith("Overzicht van de boomcodes"))
    code_re = re.compile(r"^\s*([a-zA-Z][\w()*°+\-]*)(?:\s+(kt\([^)]*\))\s+|\s{2,})(\S.*)$")
    vorige: list[str] = []
    for r in regels[start + 1:boom_start]:
        s = r.rstrip()
        if not s.strip():
            vorige = []
            continue
        # Klassekoppen ('a      STILSTAANDE WATEREN') en generieke regels ('c..b', 'h .b') overslaan.
        if re.match(r"^\s*[a-zA-Z]\s{2,}[A-Z ,\-()]+$", s) or ".." in s.split()[0] or re.search(r"\s\.b\s", s):
            vorige = []
            continue
        m = code_re.match(s)
        if m and m.group(1)[0].islower() and not m.group(1).startswith("kh(bos") and "(biotoop)" not in s:
            codes = [m.group(1)] + ([m.group(2)] if m.group(2) else [])
            oms = m.group(3).strip()
            for c in codes:
                eenheden[_digitaal(c)] = oms
            vorige = [_digitaal(c) for c in codes]
        elif vorige and re.match(r"^\s{10,}\S", s):
            for c in vorige:  # vervolgregel van een lange omschrijving
                eenheden[c] += " " + s.strip()
        else:
            vorige = []
    # Varianten die in de folder alleen hun toevoeging vermelden (kb*, kh° …) krijgen de basisomschrijving erbij.
    for c, oms in list(eenheden.items()):
        if c[-1:] in "+-" and c[:-1] in eenheden and oms.startswith(("goed ontwikkeld", "recent aangeplant", "jong of sterk")):
            eenheden[c] = f"{eenheden[c[:-1]]}, {oms}"
    # Boomcodes: boomcode, bomenrij, houtkant, houtwal (kolommen), naam.
    kop = None
    for r in regels[boom_start:]:
        s = r.rstrip()
        if s.strip().startswith("boomcode"):
            kop = [s.index("bomenrij"), s.index("houtkant"), s.index("houtwal")]
            naam_kol = None
            continue
        if kop is None or not s.strip() or s.strip().startswith("Notering"):
            continue
        boom = s.split()[0]
        # De naam begint na de laatste kolom; zoek ze vanaf de houtwalkolom.
        rest = s[kop[2]:]
        m = re.search(r"\S+\s{2,}(.+)$", rest) if rest[:1].strip() else re.search(r"^\s*(.+)$", rest)
        naam = (m.group(1) if m else rest).strip()
        if not naam:
            continue
        bomen[boom.lower()] = naam
        for kol, soort in zip(kop, ("bomenrij", "houtkant", "houtwal")):
            cel = s[kol:kol + 12].split()
            if cel and cel[0].startswith(("kb", "kh")):
                eenheden[cel[0]] = f"{soort} — {naam}"
    return eenheden, bomen


def ontleed_namelist(tsv: str) -> dict[str, str]:
    uit: dict[str, str] = {}
    for rij in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
        if rij["lang"] == "nl" and (rij["code"][:1].isdigit() or rij["code"].startswith("rbb")):
            uit[rij["code"]] = rij["name"]
    return uit


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "folder.pdf"
        pdf.write_bytes(_haal(FOLDER_URL))
        tekst = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    eenheden, bomen = ontleed_folder(tekst)
    habitats = ontleed_namelist(_haal(N2KHAB_URL).decode("utf-8"))
    data = {
        "bronnen": {
            "karteringseenheden": {"titel": "INBO — Biologische Waarderingskaart, overzicht van de karteringseenheden, versie 2025",
                                   "url": FOLDER_URL},
            "eval_hablegende": {"titel": "De Saeger et al. (2025), Biologische Waarderingskaart en Natura 2000 Habitatkaart, "
                                "uitgave 2025, tabellen 2-1 en 2-8", "url": RAPPORT_DOI},
            "habitats": {"titel": "INBO — n2khab, namelist.tsv (Nederlandse namen habitattypes en rbb)", "url": N2KHAB_URL},
        },
        "regels": {
            "+": "vegetatiekundig goed ontwikkeld",
            "-": "vegetatiekundig zwak ontwikkeld",
            "b": "open vegetatie met beperkte opslag van struiken en bomen",
        },
        "eval": EVAL,
        "hablegende": HABLEGENDE,
        "eenheden": dict(sorted(eenheden.items())),
        "bomen": dict(sorted(bomen.items())),
        "habitats": dict(sorted(habitats.items())),
    }
    UIT.parent.mkdir(parents=True, exist_ok=True)
    UIT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{UIT}: {len(eenheden)} karteringseenheden, {len(bomen)} boomcodes, {len(habitats)} habitatcodes")


if __name__ == "__main__":
    main()
