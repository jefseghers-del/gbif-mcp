# Onderzoek: Rode Lijst broedvogels Vlaanderen (2016) en Habitatrichtlijn-bijlagen op GBIF/INBO

Datum onderzoek: 2026-09-17. Methode: `curl -s` tegen `api.gbif.org` en `natuurdata.inbo.be`, verwerkt met `python3 -c` (geen extra packages). Alle URL's zijn getest en hieronder letterlijk overgenomen.

---

## Vraag 1 — Rode Lijst broedvogels Vlaanderen 2016 (Devos et al.)

### 1a. Zit de gevalideerde GBIF-checklist bird-data?

Dataset: `fc18b0b1-8777-4c8a-8cb8-f9f15870d6a9` ("Validated red lists of Flanders, Belgium").

- Totaal aantal taxa: **4771** (`https://api.gbif.org/v1/species/search?datasetKey=fc18b0b1-8777-4c8a-8cb8-f9f15870d6a9&limit=0`).
- `&facet=class` levert geen bruikbare facetten op (lege `facets`-array, ook al is `count` correct). Facetten werken dus **niet** op deze checklist-endpoint voor dit veld.
- Werkende telling via hiërarchie: de dataset gebruikt **eigen, dataset-interne hoger-taxon-keys**, niet de GBIF-backbone-keys. Backbone-key `212` (Aves) geeft `count: 0`. De juiste key vind je door eerst te zoeken naar de CLASS-rang binnen de dataset:
  `https://api.gbif.org/v1/species/search?datasetKey=fc18b0b1-8777-4c8a-8cb8-f9f15870d6a9&q=Aves&rank=CLASS&limit=5` → key `337487720`.
  Daarmee: `https://api.gbif.org/v1/species/search?datasetKey=fc18b0b1-8777-4c8a-8cb8-f9f15870d6a9&highertaxonKey=337487720&limit=0` → **count: 629** Aves-taxa.
- Vogels zitten dus wél in deze checklist, en zelfs dubbel: telkens een taxon-record voor de 2004-beoordeling én voor de 2016-beoordeling van dezelfde soort (zie hieronder), wat het hoge totaal mede verklaart.

Testsoorten (`https://api.gbif.org/v1/species/search?datasetKey=fc18b0b1-8777-4c8a-8cb8-f9f15870d6a9&q=<naam>&limit=5`, gevolgd door `/species/<key>/distributions`):

| Soort | GBIF-key | `taxonID` | `threatStatuses` (search) | distributions: `threatStatus` / `temporal` / `source` |
|---|---|---|---|---|
| Turdus pilaris | 152628117 | INBO_RL_BIR_2016_VAL_212 | CRITICALLY_ENDANGERED | — |
| Turdus philomelos | 152628115 | INBO_RL_BIR_2016_VAL_211 | LEAST_CONCERN | — |
| Turdus torquatus | 152628120 | INBO_RL_BIR_2016_VAL_213 | NOT_EVALUATED | — |
| Luscinia svecica | 152628324 | INBO_RL_BIR_2016_VAL_131 | LEAST_CONCERN | `threatStatus: LEAST_CONCERN`, `temporal: 2016`, `source: Devos et al. (2016)`, `locationId: ISO_3166:BE-VLG`, `remarks: "Momenteel niet in gevaar"` |
| Luscinia svecica (oud) | 152628328 | INBO_RL_BIR_2004_VAL_125 | LEAST_CONCERN | `temporal: 2004`, `source: Devos et al. (2004)` |
| Porzana porzana | 152627698 | INBO_RL_BIR_2016_VAL_174 | CRITICALLY_ENDANGERED | idem patroon, `source: Devos et al. (2016)` |
| Porzana porzana (oud) | 152627705 | INBO_RL_BIR_2004_VAL_167 | ENDANGERED | `source: Devos et al. (2004)` |
| Emberiza citrinella | 152628051 | INBO_RL_BIR_2016_VAL_91 | LEAST_CONCERN | `source: Devos et al. (2016)` |
| Emberiza citrinella (oud) | 152628064 | INBO_RL_BIR_2004_VAL_86 | ENDANGERED | `source: Devos et al. (2004)` |

**Conclusie 1a**: de gevalideerde GBIF-checklist `fc18b0b1-...` bevat wel degelijk de Rode Lijst broedvogels 2016 (Devos et al. 2016), naast een historische kopie van de 2004-lijst (Devos et al. 2004) als apart taxon-record per soort. Het onderscheid tussen beide jaren zit in `taxonID` (bv. `INBO_RL_BIR_2016_VAL_*` vs `INBO_RL_BIR_2004_VAL_*`) én in het veld `source`/`temporal` van `/species/{key}/distributions`.

### 1b. Aparte of niet-gevalideerde checklist?

- `https://api.gbif.org/v1/dataset/search?q=red%20list%20birds%20Flanders&type=CHECKLIST` (count 21) en varianten leveren **geen aparte "breeding birds red list Flanders 2016"-dataset** op. Relevante treffers zijn steeds dezelfde twee INBO-checklists:
  - `fc18b0b1-8777-4c8a-8cb8-f9f15870d6a9` — "Validated red lists of Flanders, Belgium"
  - `2fc23906-38f3-4bb6-a4a4-4dad908602a2` — "Non-validated red list of Flanders, Belgium" (4373 taxa, pubDate 2020-04-09)
- Zoekopdracht `q=Rode%20Lijst%20broedvogels` → **count 0** (geen Nederlandstalige titelmatch op GBIF).
- Getest of vogels in de niet-gevalideerde checklist zitten: `https://api.gbif.org/v1/species/search?datasetKey=2fc23906-38f3-4bb6-a4a4-4dad908602a2&q=Turdus&limit=5` → **count: 0**. Geen vogels in de niet-gevalideerde checklist (bevestigd door INBO-portaalcijfers hieronder, 1c).

**Conclusie 1b**: er bestaat geen aparte GBIF-checklist specifiek voor broedvogels Vlaanderen; de 2016-lijst leeft uitsluitend binnen de gecombineerde "Validated red lists of Flanders" checklist.

### 1c. INBO-portaal — dr606, dr572, dr552

Opgehaald met paginering (`?max=1000&includeKVP=true&offset=0,1000,2000,...` tot lege pagina):

| dataResourceUid | Portaalnaam | Aantal items | Bevat vogels? |
|---|---|---|---|
| dr606 | "Most recent Validated red lists of Flanders, Belgium" | 1566 | **Nee** |
| dr572 | "Non-validated red list of Flanders, Belgium" | 3161 | **Nee** |
| dr552 | "Validated red lists of Flanders, Belgium 2015" | 3063 | **Ja** |

**dr606** — tally van KVP-veld `taxonomische_groep` (`JaarPublicatie` / `source` per groep):
- Macro-nachtvlinders: 717 (2023, Veraghtert_etal_2023)
- Wilde bijen: 340 (2025, DHaeseleer_etal_2025)
- Zweefvliegen: 309 (2021, VandeMeutter_etal_2021)
- Dagvlinders: 75 (2021, Maes_etal_2021)
- Libellen: 70 (2021, DeKnijf_etal_2021)
- Pissebedden: 34 (2022, DeSmet_etal_2021)
- Amfibieen: 15 (2024, Speybroeck_etal_2024)
- Reptielen: 6 (2024, Speybroeck_etal_2024)

Geen enkele groep is vogels — dr606 is de "meest recente" gevalideerde-lijst-verzameling, maar de broedvogel-Rode-Lijst is daarin (nog) niet opgenomen/vernieuwd sinds 2016.

**dr572** (niet-gevalideerd): het veld `taxonomische_groep` ontbreekt in de KVP's van deze dataset; groepering gebeurt hier via `source` (auteursjaar): Bauwens and Claus (1996), Dekoninck et al. (2003), Devos and Anselin (1999) [vogels-gerelateerd broedvogelatlasproject, geen Rode Lijst], Desender et al. (1995), Pollet (2000), De Knijf and Anselin (1996), Grootaert et al. (2001), Vandelannoote and Coeck (1998), Walleyn and Verbeken (1999), Lock et al. (2011), Meerhaeghe and Grootaert (1998), Criel (1994), van Loen et al. (2006), Maelfait et al. (1998), Bosmans (1994), Scheers (2012), Bonte et al. (2001). Geen enkele bron is de broedvogel-Rode-Lijst van Devos et al.; geen `Devos_etal_2016`/`2004` hier.

**dr552** ("2015"): ook hier geen `taxonomische_groep`-veld; groepering via `source`, met o.a. **`Devos_etal_2004`: 211 items** en **`Devos_etal_2016`: 217 items** — dit zijn de broedvogel-Rode-Lijsten. Andere bronnen in dr552: Jooris_etal_2012, Maes_VanDyck_1999, Maes_etal_2011, Desender_etal_2008, DeKnijf_2006, Verreycken_etal_2014, Decleer_etal_2000, Maes_etal_2017, VanLanduytDeBeer_2017, Adriaens_etal_2015, Maes_etal_2014, VanLanduyt_etal_2006, Thomaes_etal_2015, Lock_etal_2013.

Voorbeeld-item dr552 (havik, `Devos_etal_2016`):
```json
{
  "kvpValues": [
    {"key": "taxonID", "value": "INBO_RL_BIR_2016_VAL_1"},
    {"key": "references", "value": "Devos_etal_2016"},
    {"key": "datasetID", "value": "https://doi.org/10.15468/8tk3tk"},
    {"key": "class", "value": "Aves"},
    {"key": "occurrenceRemarks", "value": "D1"},
    {"key": "eventDate", "value": "2016"},
    {"key": "source", "value": "Devos_etal_2016"},
    {"key": "threatStatus", "value": "Near Threatened (NT)"},
    {"key": "status", "value": "Near Threatened (NT)"}
  ]
}
```
De categorie zelf staat in `threatStatus`/`status` (tekstwaarde incl. IUCN-code, bv. "Near Threatened (NT)"), het jaar in `eventDate`, de herkomst in `source`/`references`.

Dataset-metadata dr552 (`https://natuurdata.inbo.be/species-list/ws/speciesList/dr552`): `listName: "Validated red lists of Flanders, Belgium 2015"`, `itemCount: 3063`, beschrijving verwijst naar Maes et al. 2019b (DOI 10.3897/BDJ.7.e34089) en licht toe dat dit de 19 gevalideerde Vlaamse Rode Lijsten zijn (kwantitatieve criteria, representatieve steekproef, cf. Maes et al. 2015).

**Conclusie 1c**: ondanks de naam "2015" is dr552 de bron die de broedvogel-Rode-Lijst bevat, met zowel de 2004- als de 2016-beoordeling (Devos et al.) als afzonderlijke `source`-waarden. dr606 ("meest recent") is een latere, nog niet met vogels aangevulde selectie van gevalideerde lijsten (macro-nachtvlinders t.e.m. reptielen, 2021-2025). dr572 bevat geen vogels. De GBIF-checklist `fc18b0b1-...` volgt inhoudelijk dr552 voor de vogel-taxa (zelfde `taxonID`-patroon `INBO_RL_BIR_2016_VAL_*`/`INBO_RL_BIR_2004_VAL_*`), aangevuld met recentere groepen uit dr606 voor de niet-vogelsoorten — vandaar het hogere totaal (4771 t.o.v. dr552's 3063).

### Aanbeveling voor de connector (Vraag 1)

- Voor "Rode Lijst broedvogels Vlaanderen": gebruik GBIF-checklist **`fc18b0b1-8777-4c8a-8cb8-f9f15870d6a9`**, endpoint `/v1/species/search?datasetKey=fc18b0b1-...&q=<soortnaam>`, filter resultaten op `taxonID` die start met `INBO_RL_BIR_2016_VAL_` voor de actuele (2016) beoordeling; gebruik `/v1/species/{key}/distributions` voor het canonieke `threatStatus`-veld, `temporal` (jaar) en `source` (Devos et al. 2016).
- Als rechtstreeks-INBO-alternatief (ALA-stack): `dr552` via `https://natuurdata.inbo.be/species-list/ws/speciesListItems/dr552?...&includeKVP=true`, filter op KVP `source=Devos_etal_2016`; categorie in KVP `threatStatus`/`status`.
- Vermijd `dr606` voor vogels (bevat ze niet) en `dr572`/niet-gevalideerde checklist voor Rode-Lijst-vogelstatus (evenmin vogels; wel andere taxongroepen).
- Voor Aves-telling binnen een GBIF-checklist: gebruik **niet** `&facet=class` (werkt niet) en **niet** de backbone-classKey (212); zoek eerst de dataset-eigen classKey op via `q=Aves&rank=CLASS` en gebruik die in `&highertaxonKey=`.

---

## Vraag 2 — Habitatrichtlijn-bijlagen II, IV, V

### Gevonden GBIF-checklists

Zoekopdracht `https://api.gbif.org/v1/dataset/search?q=habitats%20directive%20annex&type=CHECKLIST` (en varianten) levert drie aparte, expliciet per bijlage opgesplitste checklists op, alle gepubliceerd door **"Ukrainian Nature Conservation Group (NGO)"** (organizationKey `ca2fd897-6108-4361-91f8-b39dc8d12d13`, land UA):

| Bijlage | datasetKey | Titel | Taxa | pubDate |
|---|---|---|---|---|
| II | `2f845607-9b6a-4b31-b283-b87b89241e20` | "List of representatives of fauna and flora species protected according to the Annex II of the Council Directive 92/43/EEC ... (Habitats Directive)" | 1101 | 2024-05-27 |
| IV | `d1baf4e0-db47-4802-bce0-87881bc105d5` | idem, Annex IV | 1110 | 2024-05-29 |
| V | `0bc4fb0e-a8f2-4e77-a3cf-be1ed4c028bb` | idem, Annex V | 215 | 2024-05-29 |

Ondanks de Ukraïnse uitgever bevatten de lijsten de **volledige EU-soortenlijst** van elke bijlage, niet enkel Ukraïnse soorten — bv. Annex II bevat ook zuiver mediterrane/Italiaanse endemen (Speleomantes imperialis, Salamandra atra aurorae, Phyllodactylus europaeus, ...), dus geen landbeperking.

De bijlage-informatie zit **uitsluitend in `taxonID`**, met patroon `HABITATDIRECT-<landcode>-ANNEX.<cijfer>:<volgnr>`, bv. `HABITATDIRECT-UA-ANNEX.II:007` voor Triturus cristatus. Er is **geen** aparte bijlage-indicatie in:
- `/species/{key}/distributions` → leeg (`results: []`) voor de geteste taxa;
- `/species/{key}/verbatim` → bevat wel `taxonID`, `scientificName`, `kingdom/phylum/class/order/family`, en soms een `VernacularName`-extensie met brontekst "Council Directive 92/43/EEC ..." — géén los bijlage-veld, de bijlage is enkel af te leiden uit `taxonID` (of uit de keuze van dataset zelf, want elke bijlage is een aparte checklist).
- `/species/{key}/descriptions` → niet apart getest maar structureel niet gebruikt in dit voorbeeld (verbatim liet geen description-extensie zien).

### Testresultaten onderscheidend vermogen

`https://api.gbif.org/v1/species/search?datasetKey=<ds>&q=<naam>&limit=5` per bijlage-dataset:

| Soort | Annex II | Annex IV | Annex V |
|---|---|---|---|
| Triturus cristatus | **count 1** (key 221282305, taxonID `HABITATDIRECT-UA-ANNEX.II:007`) | **count 1** (key 221283336, taxonID `HABITATDIRECT-UA-ANNEX.IV:024`) | count 0 |
| Lissotriton vulgaris | count 0 | count 0 | count 0 |
| Dactylorhiza majalis | count 0 | count 0 | count 0 |

Dit klopt volledig met de juridische werkelijkheid: Triturus cristatus (kamsalamander) staat op bijlage II én IV; Lissotriton vulgaris (kleine watersalamander, wel Bern-bijlage III maar niet HRL) en Dactylorhiza majalis (brede orchis, niet in de HRL) komen terecht in geen van de drie datasets voor. De drie afzonderlijke checklists laten dus een **betrouwbare per-bijlage-toets** toe via een simpele aanwezigheids-/afwezigheidscheck per dataset (geen categorie-veld nodig, het is een set-lidmaatschap).

### EUNIS / EEA als alternatief

- `https://eunis.eea.europa.eu/api/` → **HTTP 404**, geen publiek gedocumenteerde REST-API op dat pad.
- `https://eunis.eea.europa.eu/species/2421` → **HTTP 301** (redirect; pagina bestaat, maar is een HTML-soortenfiche, geen API-endpoint — niet verder getest op JSON-content-negotiation, want buiten scope van "geen extra packages"/read-only quick check).
- `https://www.eea.europa.eu/data-and-maps/data/article-17-database-habitats-directive-92-43-eec-1` → **HTTP 302** (redirect, waarschijnlijk naar een vernieuwde EEA-datasetpagina); de Art. 17-rapportagedatabank bestaat bij de EEA maar vergt verdere navigatie (download als GDB/CSV via een aparte, wisselende download-URL) — niet bruikbaar als stabiel machine-leesbaar endpoint zonder handmatige verificatie van de actuele downloadlink.

**Conclusie**: voor de connector is de GBIF-drieluik (bijlage II/IV/V als aparte checklists) de meest bruikbare, stabiele, machineleesbare bron; EUNIS/EEA leveren geen kant-en-klare API en zijn enkel relevant als handmatig te verversen fallback.

### Aanbeveling voor de connector (Vraag 2)

- Voor "zit soort X op HRL-bijlage Y": doe een `/v1/species/search?datasetKey=<annex-datasetKey>&q=<wetenschappelijke naam>` op de betreffende bijlage-dataset(s); `count > 0` = lidmaatschap. Doe dit voor alle drie de datasetKeys (II, IV, V) om het volledige bijlage-profiel van een soort op te bouwen.
- DatasetKeys om te hardcoden in de connector:
  - Bijlage II: `2f845607-9b6a-4b31-b283-b87b89241e20`
  - Bijlage IV: `d1baf4e0-db47-4802-bce0-87881bc105d5`
  - Bijlage V: `0bc4fb0e-a8f2-4e77-a3cf-be1ed4c028bb`
- Gebruik niet `/distributions` voor de bijlage (leeg); het bijlagenummer zelf hoeft niet uit een veld gelezen te worden zolang de connector per dataset weet welke bijlage het is — `taxonID`-prefix (`HABITATDIRECT-<land>-ANNEX.<cijfer>`) kan dienen als extra sanity-check.
- Vermeld in de connector-documentatie dat de uitgever een Ukraïnse NGO is (mogelijke datakwaliteits-/onderhoudsrisico's; geen officiële EU-bron), en overweeg periodieke steekproefcontrole tegen de officiële EU-bijlagen (Richtlijn 92/43/EEG, laatst geconsolideerd) bij twijfel over volledigheid/actualiteit.
