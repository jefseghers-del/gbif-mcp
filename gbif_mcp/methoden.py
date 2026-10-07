# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Methode van een GBIF-record (batdetector, uitwerpselen, zicht …) uit de letterlijke bronvelden.

De vertaaltabel staat in `data/methoden.json` en is zonder codewijziging aan te vullen. Volgorde:
samplingProtocol (exacte waarde, dan eenduidige deeltekst), dan basisOfRecord. Een protocol dat niet
in de tabel staat, blijft letterlijk ('niet vertaald: …'); zonder bruikbare gegevens: 'onbekend'.
`behavior` met een term voor dood gevonden zet 'dood gevonden' vooraan. Vrije tekst
(occurrenceRemarks) wordt niet geïnterpreteerd: dat zou gokken zijn.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ONBEKEND = "onbekend"


@lru_cache(maxsize=1)
def tabel() -> dict[str, Any]:
    return json.loads((Path(__file__).parent / "data" / "methoden.json").read_text(encoding="utf-8"))


def methode(o: dict[str, Any]) -> tuple[str, str | None]:
    """(methode, bronveld) voor een GBIF-record (dict met de originele GBIF-veldnamen)."""
    t = tabel()
    m: str | None = None
    bron: str | None = None
    protocol = str(o.get("samplingProtocol") or "").strip()
    p = protocol.lower()
    if p:
        if p in t["protocol_exact"]:
            m = t["protocol_exact"][p]  # None voor 'unknown': verder kijken
        else:
            m = next((v for k, v in t["protocol_bevat"] if k in p), None) or f"niet vertaald: '{protocol}'"
        bron = "samplingProtocol" if m else None
    if not m and o.get("basisOfRecord") in t["basis"]:
        m, bron = t["basis"][o["basisOfRecord"]], "basisOfRecord"
    gedrag = str(o.get("behavior") or "").lower()
    if gedrag and any(w in gedrag for w in t["dood_in_behavior"]):
        return ("dood gevonden" + (f" ({m})" if m else "")), ("behavior" + (f", {bron}" if bron else ""))
    return (m or ONBEKEND), bron


def tel(records: list[dict[str, Any]]) -> dict[str, int]:
    uit: dict[str, int] = {}
    for o in records:
        k = methode(o)[0]
        uit[k] = uit.get(k, 0) + 1
    return dict(sorted(uit.items(), key=lambda kv: -kv[1]))
