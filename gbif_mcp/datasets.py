# Copyright (c) 2026 Jef Seghers
# In licentie gegeven krachtens de EUPL
# SPDX-License-Identifier: EUPL-1.2
"""Korte, stabiele afkortingen per GBIF-dataset, voor de compacte dataset-notatie in tabellen en CSV.

De afkortingen zijn louter een leesbare verkorting van de datasettitel. Ze zeggen niets over de
kwaliteit of de validatiestatus van de records: de beoordeling van de herkomst is aan de gebruiker.
Onbekende datasets vallen terug op de eerste dertig tekens van de datasetnaam (of de sleutel).
Peildatum van de lijst: 17 september 2026 (de 25 grootste Belgische datasets in GBIF).
"""
from __future__ import annotations

AFKORTINGEN: dict[str, str] = {
    # waarnemingen.be / observations.be (Natuurpunt en INBO-collaborator-publicaties)
    "280674cb-42f8-4959-b6aa-eee663157965": "wnm.be-gewervelden",
    "4718437d-76c6-432b-9883-4b9a253ac53f": "wnm.be-ongewervelden",
    "74ca7ce5-9a5b-46a6-b7d4-f60bab77900f": "wnm.be-planten",
    "9a0b66df-7535-4f28-9f4e-5bc11b8b096c": "wnm.be-exoten-dieren",
    "7f5e4129-0717-428e-876a-464fbd5d9a47": "wnm.be-exoten-planten",
    "629befd5-fb45-4365-95c4-d07e72479b37": "obs.be-exoten-Wallonie",
    "2c38cf8a-f981-4dfb-bc9d-dd2b6fc792ed": "wnm.be-soortenlijst",
    # INBO-meetnetten en -databanken
    "271c444f-f8d8-4986-b748-e7367755c0c1": "Florabank1",
    "7f9eb622-c036-44c6-8be9-5793eaa1fa1e": "INBO-watervogels",
    "99047b1e-ee53-4053-ba69-2e28eaaa45d9": "INBO-ABV-broedvogels",
    "ab6a6c25-1562-426d-9fdd-c4d9529f076c": "INBO-MAS-akkervogels",
    "e2fb42ca-e408-4aa2-a7bd-a9bb4ddcc83a": "INBO-roofvogels",
    "0b499d5e-c359-4cce-b817-d6f588988441": "INBO-zilvermeeuw-juv",
    "6c860eb3-83ba-48c3-9328-a7b3c7a3c7b4": "INBO-zilvermeeuw-Oostende",
    "39ca385b-6f25-402c-aa92-a76c89ecda0a": "INBO-meeuwen-DELTATRACK",
    "df50c722-070a-4c6a-a260-3a186ce72fe1": "INBO-kleine-mantelmeeuw",
    "83de99ee-92bd-4dc2-a038-a4856f13cd29": "INBO-meeuwen-juv",
    "dde71542-ad2d-4ec7-a93c-eb18bc0f432b": "Zwin-vogeltellingen",
    # geluidsopnamen en overige Vlaamse bronnen
    "b1047888-ae52-4179-9dd5-5448ea342a24": "Xeno-canto",
    "69351197-880d-4100-8e69-e80babf3fdd7": "RATO-Oost-Vlaanderen",
    # internationale platformen
    "4fa7b334-ce0d-4e88-aaae-2e0c138d049e": "eBird",
    "50c9509d-22c7-4a22-a47d-8c48425ef4a7": "iNaturalist-RG",
    "14d5676a-2c54-4f94-9023-1e8dcd822aa0": "Pl@ntNet-automatisch",
    # overige
    "ea410929-015a-4093-9c7e-7be2482668c9": "Natagriwal",
}


def afkorting(dataset_key: str, dataset_naam: str | None = None) -> str:
    """Korte naam voor een dataset; terugval op de eerste 30 tekens van de titel, anders de sleutel."""
    kort = AFKORTINGEN.get(dataset_key)
    if kort:
        return kort
    if dataset_naam:
        naam = dataset_naam.strip()
        return naam if len(naam) <= 30 else naam[:30].rstrip() + "…"
    return dataset_key[:8]


def compact(datasets: list[dict]) -> str:
    """[{dataset_key, dataset, aantal}, …] -> 'wnm.be-gewervelden 5 / iNaturalist-RG 2'.

    Scheidingsteken is ' / ' (geen puntkomma: die is het CSV-scheidingsteken)."""
    return " / ".join(f"{afkorting(d['dataset_key'], d.get('dataset'))} {d['aantal']}" for d in datasets)
