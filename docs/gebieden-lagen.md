# Inventaris WFS-lagen voor `gebieden_rond`

Onderzoek uitgevoerd 2026-09-17, read-only via `curl`/`python3` (GetCapabilities, DescribeFeatureType, GetFeature). Getest op een testpunt in Oost-Vlaanderen; de voorbeelden hieronder gebruiken het publieke natuurcentrum Bourgoyen-Ossemeersen, Driepikkelstraat 32, Gent (Lambert 72 x=101896 y=195419).

## 1. Departement Omgeving — Mercator WFS

Basis-URL: `https://www.mercator.vlaanderen.be/raadpleegdienstenmercatorpubliek/ows`
GetCapabilities bevat 360 FeatureTypes in totaal (namespaces `ps:`, `am:`, `lu:`, `nz:`, `ni:`, `er:`, ...). Onderstaande tabel beperkt zich tot de relevante natuurbeschermings- en erfgoedlagen.

| Categorie | Name | Title | Geom-kolom | Naamveld(en) | Codeveld | Testresultaat (DWITHIN, 1000 m) |
|---|---|---|---|---|---|---|
| Habitatrichtlijn | `ps:ps_hbtrl` | Habitatrichtlijngebieden | `geom` (MultiSurface) | `naam` | `gebcode` | OK (DWITHIN getest) |
| Habitatrichtlijn (detail) | `ps:ps_hbtrl_deel` | Habitatrichtlijn(deel)gebieden | `geom` | `naam`, `deelgebied` | `gebcode` | OK (DWITHIN getest) |
| Vogelrichtlijn | `ps:ps_vglrl` | Vogelrichtlijngebieden | `geom` | `gebnaam` | `na2000code` | OK (DWITHIN getest) |
| VEN/IVON | `ps:ps_ven` | VEN en IVON gebieden | `geom` | `naam` | `gebiedsnr` | OK (DWITHIN getest) |
| Ramsar | `ps:ps_ramsar` | Ramsar-gebieden | `geom` | `naam_` | `ramsar_no` | OK (DWITHIN getest) |
| Nationale parken | `ps:ps_nationaleparken` | Natuurkerngebieden Nationale Parken | `geom` | `naam` | — (`objectid`) | OK (DWITHIN getest) |
| Natuurbeheerplannen | `ps:ps_nbhp` | Natuurbeheerplannen | `geom` | `naamdossier` | `registratienummer` | OK (DWITHIN getest) |
| Uitbreidingszones erkende/Vlaamse natuurreservaten | `ps:ps_uznres_anb` | Uitbreidingszones van de erkende en Vlaamse natuurreservaten | `geom` | `resnaam` | `resnr` | OK (DWITHIN getest) |
| HPG/beschermd grasland | `ps:ps_hpg_bsch_grsl` | Historisch permanente graslanden (HPG) en andere door natuurwetgeving beschermde permanente graslanden | `geom` | — (geen naamveld, wel `statuut`/`basis_statuut`) | — (`objectid`) | OK (DWITHIN getest) |
| Poldergraslanden | `ps:ps_pldgrsl` | Poldergraslanden | `geom` | — (`status`) | — (`objectid`) | OK (DWITHIN getest) |
| Beschermde cultuurhistorische landschappen | `ps:ps_bes_land` | Beschermde cultuurhistorische landschappen | `geom` | `naam`, `alt_naam` | `aanduid_id` | OK (DWITHIN getest) |
| Beschermde monumenten | `ps:ps_bes_monument` | Beschermde monumenten | `geom` | `naam`, `alt_naam` | `aanduid_id` | OK (DWITHIN getest) |
| Beschermde stads-/dorpsgezichten | `ps:ps_bes_sd_gezicht` | Beschermde stads- en dorpsgezichten | `geom` | `naam`, `alt_naam` | `aanduid_id` | OK (DWITHIN getest) |
| Duinendecreet | `ps:ps_duin` | Beschermde gebieden Duinendecreet | `geom` | — (`categorie`) | — (`globalid`) | OK (DWITHIN getest) |
| Natuurrichtplannen | `lu:lu_nrp` | Natuurrichtplannen | `geom` | `naam` | `code` | OK (DWITHIN getest) |
| Natuurdoelen Sigmaplan | `lu:lu_ndl_sigma` | Natuurdoelen Sigmaplan | `geom` | `gebied` | — | OK (DWITHIN getest) |
| Openbare bossen/natuurdomeinen ANB | `am:am_patdat` | Openbare bossen en natuurdomeinen beheerd door ANB | `geom` | `domeinnaam` | — | OK (DWITHIN getest) |

### BWK (Biologische Waarderingskaart)

Basis-URL: `https://geo.api.vlaanderen.be/BWK/wfs`

| Name | Title | Geom-kolom | Relevante velden | Testresultaat |
|---|---|---|---|---|
| `BWK:Bwkhab` | BWK 2 - BWK-zone en Natura 2000 Habitat | `SHAPE` (MultiSurface) | `HAB1..HAB5` (habitatcode), `PHAB1..PHAB5` (%), `EVAL` (waardering), `BWKLABEL`, `EENH1..8` (karteringseenheden) | OK (DWITHIN getest) |
| `BWK:Bwkfauna` | BWK 2 - Faunistisch belangrijke gebieden | `SHAPE` (Surface) | `FAUNAID` | OK (DWITHIN getest) |
| `BWK:Hab3260` | BWK 2 - Habitattype 3260 | `SHAPE` (Curve) | `NAAM`, `BRON` | OK (DWITHIN getest) |

## 2. Niet gevonden in deze diensten

- **Erkende/Vlaamse natuurreservaten zelf** (de kernzones, niet de uitbreidingszones): geen aparte laag gevonden in de Mercator-dienst. Enkel `ps:ps_uznres_anb` (uitbreidingszones) is aanwezig. Vermoedelijk zit de reservaatafbakening zelf in een andere dienst (Geopunt/ANB "Natuur en Bos"), niet onderzocht — buiten scope van deze twee opgegeven diensten.
- **Bosreservaten** (specifiek): geen dedicated laag gevonden onder `ps:`/`am:`/`lu:` in deze dienst; enkel de bredere laag `am:am_patdat` (openbare bossen/natuurdomeinen ANB, zonder onderscheid bosreservaat) en `lu:lu_natbos_toegang_anb` (toegankelijkheid, geen beschermingsstatus).
- **Archeologisch/UNESCO-erfgoed**: wel aanwezig (`ps:ps_bes_arch_site`, `ps:ps_vast_az`, `ps:ps_unesco_kern`, `ps:ps_unesco_buffer`, e.a.) maar buiten scope van de gevraagde "landschap/dorpsgezicht"-erfgoedlagen; niet getest.

## 3. Werkende query-sjabloon

Beide diensten (Mercator en BWK) ondersteunen `DWITHIN` als CQL-filter, met `outputFormat=application/json`, `srsName=EPSG:31370`, en respecteren `count`. Dit is de aanbevolen vorm:

```
GET {BASE_URL}?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature
    &TYPENAMES={laag}
    &outputFormat=application/json
    &srsName=EPSG:31370
    &count=5
    &CQL_FILTER=DWITHIN({geomkolom},POINT({x} {y}),1000,meters)
```

Concreet voorbeeld (Mercator, VEN):
```
https://www.mercator.vlaanderen.be/raadpleegdienstenmercatorpubliek/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=ps:ps_ven&outputFormat=application/json&srsName=EPSG:31370&count=5&CQL_FILTER=DWITHIN(geom,POINT(101896 195419),1000,meters)
```

Concreet voorbeeld (BWK, Bwkhab — let op hoofdletters `SHAPE`):
```
https://geo.api.vlaanderen.be/BWK/wfs?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=BWK:Bwkhab&outputFormat=application/json&srsName=EPSG:31370&count=5&CQL_FILTER=DWITHIN(SHAPE,POINT(101896 195419),1000,meters)
```

**Bevindingen bij het testen:**
- `DWITHIN` werkte op **alle** geteste lagen in beide diensten (17 Mercator-lagen + 3 BWK-lagen) — geen enkele gaf een fout. De `BBOX`-fallback was dus niet nodig, maar is ook getest en werkt (zie hieronder) als alternatief wanneer `DWITHIN` niet ondersteund zou zijn door een andere laag/dienst.
- `count` wordt gerespecteerd als hard limiet op het aantal teruggegeven features (`numberReturned`); het werkelijke aantal treffers staat in `numberMatched`/`totalFeatures` in de JSON-response. Test op `ps:ps_hpg_bsch_grsl`: `count=1` → 1 feature terug, maar `numberMatched=22`. Voor een "afstand tot dichtstbijzijnde" use-case is het dus nodig om met een ruimere `count` te werken en zelf de afstand te berekenen op de teruggegeven geometrieën (de WFS zelf sorteert niet op afstand).
- `outputFormat=application/json` werkt op alle geteste lagen in beide diensten. De verkorte vorm `outputFormat=json` werkt ook (getest op `ps:ps_ven`). Zonder `outputFormat`-parameter valt de dienst terug op GML/XML (getest, werkt ook, HTTP 200).
- BWK gebruikt een hoofdlettergevoelige geometriekolom `SHAPE` (i.p.v. `geom`); de attribuutvelden in BWK zijn eveneens in hoofdletters (`HAB1`, `EVAL`, ...), terwijl Mercator-velden in kleine letters staan (`naam`, `gebcode`, ...).

**BBOX-alternatief (getest, werkt eveneens):**
```
...&BBOX=107224,192800,109224,194800,urn:ogc:def:crs:EPSG::31370
```
(bevestigd op `ps:ps_ven`, identiek resultaat als DWITHIN 1000 m rond het testpunt.)

## 4. Niet bruikbaar / aandachtspunten

- Geen enkele geteste laag gaf een HTTP-fout of ongeldige CQL-fout — er zijn dus geen "niet bruikbare" lagen in strikte zin binnen deze steekproef.
- Lagen zonder herkenbaar naam- of codeveld (enkel technische/statuutvelden), waarvoor de tool een generieke omschrijving nodig heeft i.p.v. een "naam": `ps:ps_hpg_bsch_grsl` (`statuut`/`basis_statuut`), `ps:ps_pldgrsl` (`status`), `ps:ps_duin` (`categorie`).
- `ps:ps_nbhp`, `ps:ps_bes_land`, `ps:ps_bes_monument`, `ps:ps_bes_sd_gezicht` gebruiken `aanduid_id`/`registratienummer` als code i.p.v. een kort gebiedscode zoals bij VEN (`gebiedsnr`) of Natura 2000 (`gebcode`/`na2000code`).
- De erkende/Vlaamse natuurreservaten (kernzones) en specifieke bosreservaten zijn niet gevonden binnen de twee opgegeven diensten — voor volledige dekking is minstens één extra bron (Geopunt/ANB) nodig; dit valt buiten de scope van dit onderzoek.
