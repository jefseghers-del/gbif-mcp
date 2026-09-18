# CLAUDE.md

## Project

gbif-mcp is een MCP-server die Claude toegang geeft tot Belgische biodiversiteitsdata: de
GBIF occurrence API (waarnemingen), het Vlaams Biodiversiteitsportaal (INBO) met de
gezaghebbende lijsten (Soortenbesluit, Habitat- en Vogelrichtlijnbijlagen, Rode Lijsten,
Unielijst invasieve soorten …), en de WFS-diensten van het Departement Omgeving (Mercator) en
Digitaal Vlaanderen (BWK) voor beschermde gebieden. Zie `README.md` voor de tien tools, de
gebiedsparameters en het volledige overzicht van lijst- en laagcodes (ook opvraagbaar via de
tool `bronnen`).

## Dataset-herkomst

`gbif_mcp/datasets.py` bevat de afkortingen per GBIF-dataset (louter een leesbare verkorting van de
titel, géén kwaliteitsoordeel). `gebiedsanalyse.datasets_per_soort()` splitst de al opgehaalde
records per soort uit over de brondatasets; dat kost geen extra API-verkeer. De connector leidt
nooit een betrouwbaarheidsklasse af uit een datasetnaam of uit `identificationVerificationStatus`:
dat veld wordt letterlijk doorgegeven, de weging is aan de gebruiker.

## Kaart

`gbif_mcp/kaart.py` tekent de situeringskaart met Pillow: GRB-basiskaart als WMS-ondergrond
(Lambert 72, asvolgorde x,y — met y,x komt er een blanco beeld terug), daarop de WFS-vlakken uit
`gebieden.haal_features`. Alle versieringen schalen met `breedte_px`.
Toegankelijkheid: kleur is nooit de enige drager van betekenis. Elk vlak krijgt het nummer van zijn
legenderegel, elke laag een arcering uit `ARCERINGEN`, en het palet is Okabe-Ito (`OKABE_ITO`).
Nieuwe lagen of kaartelementen houden zich daaraan. Tests mocken `gb.haal_features`
en `kaart.achtergrond`; nooit netwerk.

## Disclaimer en privacy

De teksten `DISCLAIMER`, `DISCLAIMER_KORT` en `PRIVACY` staan in `gbif_mcp/__init__.py` en zijn
de enige bron; README, handleiding, manifest, rapport en tool-antwoorden nemen ze over. Persoonsgegevens
van waarnemers (`gbif.PERSOONSVELDEN`) worden bij ontvangst verwijderd via `get_json(verwijder_velden=...)`,
vóór caching. Nieuwe GBIF-oproepen doen dat ook. Geen dossieradressen of -coördinaten in tests, docs of
voorbeelden.

## Datalicenties

Standaard alle licenties (intern werkdocument); met `ook_niet_commercieel=False` alleen CC0 en CC BY
(`gbif.VRIJE_LICENTIES`), gezet per tool-oproep via
`gbif.zet_licentiefilter(ook_niet_commercieel)` als eerste statement na de docstring, en gelezen in
`_occurrence_params`. Elke nieuwe tool die waarnemingen ophaalt, krijgt de parameter
`ook_niet_commercieel: bool = True` en zet de filter; een tool die andere tools oproept, geeft de
vlag expliciet door. `tests/test_server.py::test_licentiefilter_wordt_echt_gezet` bewaakt dat.

## Harde regels

- **Anti-hallucinatie**: elke tool geeft uitsluitend terug wat de bron (GBIF, INBO-portaal,
  Digitaal Vlaanderen) effectief oplevert. Nul treffers is "niet gevonden in deze bron", niet
  "afwezig" — zeg dat er expliciet bij (zie `KANTTEKENING_WAARNEMINGEN` en de `melding`-velden
  in `server.py`). Vul nooit een categorie, status of waarneming aan die niet letterlijk uit
  een API-respons komt.
- **Bron-URL's**: elk teruggegeven feit (`Soort`, `LijstVermelding`, `Waarneming`, …) draagt
  een controleerbare `url` mee. Nieuwe velden zonder brontraceerbaarheid niet toevoegen.
- **`hrl_iv` (dr570) is bewust als onvolledig gemarkeerd** (afgeleid van een Britse
  NBN-lijst); `hrl_iv_vl` (Soortenbesluit categorie 3) is de primaire bijlage IV-bron voor
  Vlaanderen. Verwar de twee niet in nieuwe code of documentatie.
- **Rate limiting en User-Agent**: alle HTTP-verkeer loopt via `gbif_mcp/http.py`
  (`get_json`), met een herkenbare `User-Agent`, timeouts, retry met backoff op 429/5xx, een
  in-memory cache (`ttl`) en optioneel een schijfcache (`schijf_ttl`, map `~/.cache/gbif-mcp`
  of env `GBIF_MCP_CACHE`) voor bronnen die zelden wijzigen (lijstitems, checklist-sleutels).
  Nieuwe bronnen hier doorheen leiden, niet buiten deze module om rechtstreeks met `httpx`
  werken.

## Technisch

- Python 3.12+, `MCPServer` uit `mcp.server.mcpserver` (mcp-package 2.0+), httpx, pydantic,
  shapely, pyproj.
- Structuur: `gbif.py` (GBIF-client), `inbo.py` (INBO-portaal-client), `geo.py` (geocodering,
  cirkel-/gemeentegeometrie, WKT), `gebieden.py` (WFS-lagen Mercator/BWK, Lambert 72, afstand/
  overlap met shapely; laagregister `LAGEN`/`GROEPEN`), `gebiedsanalyse.py` (gedeelde engine
  voor `soorten_in_gebied`/`telling_in_gebied`: facet éénmalig, lijsten parallel + schijfcache,
  records via `gbif.records_in_gebied` binnen een tijdsbudget — zie de moduledocstring voor de
  vier stappen), `lijsten.py` (register van lijstcodes/groepen, geen netwerk), `schema.py`
  (Pydantic-modellen), `http.py` (gedeelde httpx-client + schijfcache), `server.py` (de tien
  MCP-tools).
- Bij een wijziging aan `gebiedsanalyse.py` of `gebieden.py`: hou de "nooit stilzwijgend
  weglaten"-regel aan (`ontbrekend`, `niet_geraadpleegd`, `volledig`) — een tijdsbudget of een
  falende bron mag nooit een leeg resultaat opleveren zonder melding.
- Installatie: `uv venv --python 3.12 && source .venv/bin/activate && uv pip install -e ".[test]"`.
- Tests: `pytest -q`, geen netwerk. Mock `get_json` per module (`gbif_mcp.gbif.get_json`,
  `gbif_mcp.inbo.get_json`, `gbif_mcp.geo.get_json`, `gbif_mcp.gebieden.get_json`, …) via
  `monkeypatch`, of gebruik `respx` voor httpx-niveau-mocks. Functies die zelf weer
  netwerkfuncties aanroepen (bv. `gebiedsanalyse._exoot_keys`, `gebiedsanalyse.hrl_eu_keys`)
  monkeypatch je rechtstreeks naar een vaste return-waarde in plaats van hun onderliggende
  `get_json`-calls te mocken. Nieuwe bronvelden of lijstcodes krijgen een test op een vast
  fixture-item, geen live calls.

## Taal en stijl

Nederlands voor documentatie, docstrings en commitboodschappen. Beknopt, geen ophef.
Onzekere of tijdelijke beperkingen (bv. een onvolledige portaal-lijst) expliciet benoemen in
de tool-docstring, niet verzwijgen.
