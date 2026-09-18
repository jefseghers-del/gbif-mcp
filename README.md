# gbif-mcp — BE-biodiversiteit (beta)

> [!WARNING]
> **Betaversie — geen product, geen garantie, geen aansprakelijkheid.** Deze software is een experimenteel
> hulpmiddel in ontwikkeling, geen commercieel product of dienst. De software en de rapporten die ze maakt, worden
> kosteloos aangeboden zoals ze zijn,
> zonder enige uitdrukkelijke of stilzwijgende garantie, onder meer over juistheid, volledigheid, actualiteit of
> geschiktheid voor een bepaald doel. De resultaten zijn een geautomatiseerde bronnenscan van publieke databanken;
> ze vervangen geen terreininventarisatie, deskundige beoordeling of juridisch advies. **De gebruiker is zelf
> volledig verantwoordelijk** voor het controleren van de resultaten en voor elk gebruik dat ervan wordt gemaakt.
> De auteur is niet aansprakelijk voor schade die voortvloeit uit het gebruik van de software of de resultaten.

MCP-server die Claude toegang geeft tot Belgische biodiversiteitsdata: GBIF-waarnemingen,
Vlaamse Rode Lijsten, het Soortenbesluit, Habitat- en Vogelrichtlijnbijlagen, de Unielijst
invasieve soorten, beschermde gebieden (Natura 2000, VEN/IVON, BWK …) en de overige
gezaghebbende lijsten van het Vlaams Biodiversiteitsportaal (INBO). Typisch gebruik:
soortenstatus opzoeken, welke soorten en welke beschermde gebieden rond een perceel liggen,
voor m.e.r.-dossiers, passende beoordelingen en omgevingsvergunningen.

**Anti-hallucinatie**: elke tool geeft uitsluitend terug wat de bron effectief oplevert, met
een controleerbare URL. Nul treffers betekent "niet gevonden in deze bron", niet "afwezig".
Zie **Harde regels** hieronder.

## De dertien tools

| Tool | Doel | Belangrijkste parameters | Geeft terug |
|------|------|---------------------------|-------------|
| `zoek_soort` | Naam (wetenschappelijk of Nederlands) → GBIF-taxonsleutel(s) | `naam`, `max_resultaten` | lijst `Soort` |
| `soort_status` | Beschermings-, Rode-Lijst- en exotenstatus van één soort | `soort` (naam of taxonKey) | `SoortStatus`: `vermeldingen` per lijst, `samenvatting` per lijstcode, `exoot`, `koppeling_twijfel` |
| `waarnemingen` | GBIF-waarnemingen van één soort in een gebied/periode | `soort`, gebied (zie onder), `jaar_van`, `jaar_tot`, `max_resultaten`, `offset`, `dataset_key` | `WaarnemingenRespons`: totaal, steekproef, verdeling per dataset/jaar, `per_verificatiestatus`, `zoek_url` |
| `soorten_in_gebied` | Alle soorten waargenomen in een gebied, gekoppeld aan hun status | gebied, `filter`, `alleen_bedreigd`, `per_dataset_per_soort`, `formaat`, `max_soorten`, `offset`, `tijdsbudget_s` | `SoortenInGebiedRespons`: compacte soortenlijst (of `tabel`), legende, dekking, reproduceerbaarheid |
| `telling_in_gebied` | Alleen aantallen: hoeveel beschermde/Rode-Lijst-/invasieve soorten in een gebied | gebied, `filter`, `soorten_per_dataset` | `TellingRespons`: aantal per lijst/categorie, `per_dataset`, `kern`, `exoten` |
| `gebieden_rond` | Beschermde gebieden en gebiedsstatuten rond een punt/polygoon | `adres`/`lat`+`lon`/`wkt`, `straal_m`, `lagen` | `GebiedenRespons`: per laag de overlappende of dichtstbijzijnde gebieden |
| `datarapport_natuur` | Het vaste rapportsjabloon: telling, kernsoorten, gebieden, kaarten en onderliggende records in één PDF | adres of lat/lon, `pad`, `straal_soorten_m`, `straal_gebieden_m`, `jaar_van`, `kaarten`, `bwk_kaart` | pad, aantal pagina's, kaarten, samenvatting, waarschuwingen |
| `kaart_gebieden` | Situeringskaart (PNG of JPEG): de locatie met de beschermde gebieden eromheen | `pad`, gebied, `straal_m`, `lagen`, `breedte_px`, `met_legende`, `per_groep` | bestandspad, legende per laag met kleur, bbox, schaal |
| `exporteer_bevraging` | Volledige gebiedsbevraging wegschrijven als CSV of JSON (alle soorten, optioneel alle records) met metadata voor een datarapport | `pad` (.csv/.json), zelfde gebied- en filterparameters, `met_records` | bestandspaden, aantallen, metadata |
| `lijst` | Inhoud van één gezaghebbende soortenlijst | `code`, `zoek`, `categorie`, `max_resultaten` | `LijstRespons`: items (soort + vermelding) |
| `geocodeer_adres` | Adres/plaatsnaam → WGS84-coördinaten en gemeente | `adres` | `Locatie` |
| `dataset_info` | Herkomst, licentie, DOI en citatie van een GBIF-dataset | `dataset_key` | `DatasetInfo` |
| `bronnen` | Overzicht van alle geraadpleegde bronnen en lijst-/groepscodes | — | lijst `Bron` |

## Gebiedsparameters

`waarnemingen`, `soorten_in_gebied` en `telling_in_gebied` aanvaarden een gebied op één van
vier manieren (volgorde bij meerdere: `wkt` > `lat`/`lon` > `adres` > `gemeente`):

- `adres` + `straal_m` (standaard 500 m) — geocodering via Digitaal Vlaanderen, cirkel als WKT.
- `lat`/`lon` + `straal_m` — cirkel rond het punt, geen geocodering nodig.
- `wkt` — een POLYGON of MULTIPOLYGON in WGS84 (lon lat, tegenwijzerzin).
- `gemeente` — naam van een Belgische gemeente. In Vlaanderen wordt de echte gemeentegrens
  gebruikt (VRBG). **Buiten Vlaanderen** kent GBIF voor België geen gemeentegrenzen; de tool
  valt dan terug op het GADM-arrondissement (niveau 3), met een expliciete melding.

Zonder gebiedsparameter zoekt `waarnemingen` in heel België; `soorten_in_gebied`,
`telling_in_gebied` en `gebieden_rond` vereisen een gebied (`gebieden_rond`: punt of polygoon,
geen `gemeente`-optie).

## `soorten_in_gebied`: compact, tabel, en de `kern`-groep

De engine (`gebiedsanalyse.py`) haalt in één GBIF-facetbevraging alle soorten met aantal op,
koppelt ze parallel aan de gevraagde lijsten (schijfgecachet), filtert en sorteert op
juridische relevantie, en verrijkt pas voor de overblijvende pagina de records (laatste jaar,
coördinaatonzekerheid, broedindicatie) — nooit voor de volledige, ongefilterde soortenlijst.

- Standaard krijg je per soort een compacte regel (`SoortInGebied`): naam, aantal, laatste
  jaar, `samenvatting` per lijstcode, `exoot`, `onzekerheid_max_m`, `zeker_binnen_straal`,
  `records_met_broedindicatie`, `koppeling_twijfel`. `detail=True` voegt de volledige
  `vermeldingen` toe. Categorie-toelichtingen staan één keer in `legende`, niet per soort.
- `formaat='tabel'` geeft dezelfde inhoud als een markdown-tabel in het veld `tabel` (≈4x
  compacter dan JSON-objecten; aanbevolen bij meer dan een 50-tal soorten). `soorten` blijft
  dan leeg.
- `filter='kern'` beperkt tot wat in een natuurtoets/m.e.r. telt: bijlage IV (Vlaanderen,
  Soortenbesluit cat. 3), bijlage II HRL, VRL bijlage I, en Rode Lijst RE/CR/EN/VU (incl. de
  broedvogel-Rode-Lijst 2016). Andere groepscodes: `beschermd`, `europees`, `rodelijst`,
  `invasief`, `prioritair`, `provinciaal`.
- `max_onzekerheid_m` sluit vervaagde records uit (aantallen worden dan herteld op de
  overblijvende records). `alleen_broedindicatie` houdt alleen soorten met minstens één record
  met een broed-/voortplantingsaanwijzing over.
- `exoot`: `True`/`False`/`None` (niet gecontroleerd, bv. bij een bronfout) — uitheems volgens
  GRIIS België, de Unielijst of de uitgebreide INBO-exotenlijst.

## `telling_in_gebied`

Zelfde gebiedsparameters, alleen aantallen: per lijstcode en per categorie het aantal soorten,
het aantal kernsoorten en het aantal soorten met status dat tegelijk exoot is — geen
per-soort-records nodig, dus snel. Gebruik daarna `soorten_in_gebied` (bv. `filter='kern'`)
voor de namen.

## Herkomst van de waarnemingen: uitsplitsing per brondataset

In een vergunningsdossier telt de herkomst van een determinatie. `soorten_in_gebied` met
`per_dataset_per_soort=True` geeft daarom per soort het veld `datasets`: uit welke GBIF-datasets
haar waarnemingen komen, met `aantal` en `laatste_jaar`, aflopend gesorteerd. De som van `aantal`
is gelijk aan `aantal_waarnemingen` van die soort. Het kost geen extra GBIF-oproepen: de records
zijn al opgehaald voor het laatste jaar en de coördinaatonzekerheid.

Bij `formaat='tabel'` komt er een kolom `datasets` met een compacte notatie, bijvoorbeeld
`wnm.be-gewervelden 5 / eBird 2`. De afkortingen staan in `gbif_mcp/datasets.py`; onbekende
datasets vallen terug op de eerste dertig tekens van hun titel. `exporteer_bevraging` schrijft de
uitsplitsing altijd weg: in CSV als de kolommen `datasets` en `n_datasets`, in JSON als de
volledige lijst per soort.

Doorklikken naar de onderliggende records kan met `waarnemingen(..., dataset_key=...)`.
`telling_in_gebied` geeft een `per_dataset`-blok met het aantal records per dataset; met
`soorten_per_dataset=True` komt daar het aantal soorten met status bij (tien parallelle extra
GBIF-oproepen, in de praktijk ±2 s; daarom standaard uit).

Elke waarneming draagt ook `verificatiestatus` (het GBIF-veld `identificationVerificationStatus`,
letterlijk overgenomen), en `waarnemingen` telt die in `per_verificatiestatus`. Waarnemingen.be en
Florabank vullen dat veld, eBird, iNaturalist en Pl@ntNet niet; dan staat er `(leeg)`.

## `kaart_gebieden`: situeringskaart

Tekent de gebieden van `gebieden_rond` op de GRB-basiskaart van Digitaal Vlaanderen (WMS), in
Lambert 72, met legende, schaalbalk, noordpijl en de zoekcirkel. Het resultaat is een PNG plus
de legende als gegevens (per laag: kleur, aantal getekende vlakken, status).

Komt de kaart verkleind in een document, zet dan `met_legende=False` en maak de legende in het
document zelf op met het veld `legende`: een ingebakken legende wordt onleesbaar bij verkleining.
`voorbeeld/maak_rapport.py` doet dat zo.

De Biologische Waarderingskaart krijgt een kleur per karteringseenheid: elk habitattype is een
eigen legenderegel (`BWK 4030 — droge heide`), zodat de kaart toont wélke habitats er liggen.
Omdat die laag het hele beeld dekt, is `per_groep=True` daar aan te raden: dan komt er één kaart
per thema (natura2000, natuur, beheer, erfgoed, bwk) met dezelfde uitsnede en schaal, dus over
elkaar te leggen. De bestandsnamen krijgen de groep als achtervoegsel.

**Leesbaar zonder kleur.** Kleur is nooit de enige drager van betekenis: elk vlak krijgt het nummer
van zijn legenderegel op de kaart, elke laag een eigen arcering, en het palet is dat van Okabe en
Ito (onderscheidbaar bij deuteranopie, protanopie en tritanopie). De kaart blijft daardoor bruikbaar
in grijswaarden en bij kleurenblindheid. Labels van grote gebieden worden in het zichtbare deel van
het vlak geplaatst en wijken uit bij overlap, zodat ook geneste aanduidingen hun nummer houden.

Grote vlakken worden eerst getekend, zodat kleine percelen zichtbaar blijven.
De kaartversieringen schalen mee met `breedte_px`, dus een kaart van 1800 px blijft leesbaar op
een halve A4. Valt de WMS uit, dan wordt de kaart zonder ondergrond getekend en staat dat in
`melding`; een WFS-laag die faalt, staat in de legende als `niet_geraadpleegd`.

## `gebieden_rond`: beschermde gebieden en gebiedsstatuten

Bevraagt de WFS-diensten van het Departement Omgeving (Mercator) en Digitaal Vlaanderen (BWK)
rond een punt of polygoon, intern in Lambert 72 (metrische afstanden). Per laag: de gebieden
die het punt bevatten of de polygoon overlappen (`overlapt`, afstand 0), anders de
dichtstbijzijnde binnen `straal_m` (standaard 1000 m).

Lagen (`gebieden.LAGEN`) en groepen voor `lagen`:

| Groep | Lagen |
|-------|-------|
| `natura2000` | Habitatrichtlijngebied + deelgebied (SBZ-H), Vogelrichtlijngebied (SBZ-V), Ramsar |
| `natuur` | VEN/IVON, nationaal park, natuurreservaat-uitbreidingszone, HPG/beschermd grasland, poldergrasland, Duinendecreet |
| `beheer` | Natuurbeheerplan, natuurrichtplan, Sigma-natuurdoel, ANB-domein |
| `erfgoed` | Beschermd landschap, dorpsgezicht, monument |
| `bwk` | BWK-habitat (incl. Natura 2000-habitattype), BWK-fauna, BWK-habitattype 3260 (waterlopen) |

Leeg `lagen` = alle lagen bevragen. Een laag met `status='niet_geraadpleegd'` gaf een fout bij
de WFS-dienst: dat is geen "geen gebied", niet stilzwijgend weglaten. `melding` waarschuwt ook
als de `count`-limiet van een laag is bereikt (verre treffers kunnen dan ontbreken).

**Beperkingen** (zie ook `docs/gebieden-lagen.md`, peildatum 17 september 2026):
- Alleen Vlaanderen; de twee gebruikte diensten dekken Wallonië/Brussel niet.
- Erkende/Vlaamse **natuurreservaten zelf (de kernzones)** en specifieke **bosreservaten**
  zitten niet in deze diensten — enkel de uitbreidingszones (`natuurreservaat_uitbreiding`) en
  de brede laag openbare bossen/natuurdomeinen ANB. Verifieer op Geopunt.
- BWK-habitatcodes zijn karteringseenheden, geen juridisch statuut. Een niet-overlappende
  BWK-habitatvlek zonder habitat ("gh") wordt niet als "dichtstbijzijnde" gerapporteerd.

## Rode-Lijstdekking en de broedvogel-Rode-Lijst 2016

De "meest recente gevalideerde Rode Lijsten van Vlaanderen" (`rodelijst_vl`, dr606) dekt geen
vogels (macro-nachtvlinders, wilde bijen, zweefvliegen, dagvlinders, libellen, pissebedden,
amfibieën, reptielen — zie `rodelijst_dekking` in de respons). De enige beschikbare Rode Lijst
voor broedvogels is die van Devos et al. (2016), die op het portaal verstopt zit in de
verzamellijst "Validated red lists 2015" (dr552, gefilterd op KVP `source=Devos_etal_2016`,
naast een oudere 2004-beoordeling in dezelfde lijst). Deze zit als aparte lijstcode
`rodelijst_broedvogels_2016` in de `rodelijst`- en `kern`-groep. Zie
`docs/onderzoek-rodelijst-hrl.md` voor het volledige brononderzoek.

## Kruiscontrole Habitatrichtlijn-bijlagen

Voor HRL-vermeldingen (bijlage II, IV, V) uit het INBO-portaal wordt de soort ook opgezocht in
de bijbehorende EU-brede GBIF-checklist van die bijlage (`HRL_EU_CHECKLISTS`, uitgever
Ukrainian Nature Conservation Group, wel de volledige EU-soortenlijst). Wijkt het portaal af
van die checklist, dan verschijnt `koppeling_twijfel` met de reden — bedoeld als signaal, geen
bewijs van fout in één van beide bronnen.

## Exotenvlag

`exoot` (in `soort_status`, `soorten_in_gebied`, `telling_in_gebied`) is `True` als de soort
voorkomt op de Unielijst invasieve uitheemse soorten, de uitgebreide INBO-exotenlijst, of GRIIS
België (GBIF); `None` als één van die bronnen niet geraadpleegd kon worden (zie `melding`/
`ontbrekend`) — dan is er dus geen uitspraak, geen "nee".

## Schijfcache en reproduceerbaarheid

Lijsten en checklists die zelden wijzigen (INBO-lijstitems, GBIF-checklist-sleutels) worden
naast de geheugencache ook op schijf gecachet onder `~/.cache/gbif-mcp` (te overschrijven via
de omgevingsvariabele `GBIF_MCP_CACHE`), zodat een herstart van de server geen nieuwe download
vergt. `lijstversies` in de respons geeft per lijstcode het ISO-tijdstip waarop die versie
effectief is opgehaald.

Voor herleidbaarheid geeft `soorten_in_gebied` ook `geraadpleegd_op` (tijdstip van deze
bevraging), `gbif_parameters` (de exacte GBIF-API-parameters van de facetbevraging) en
`zoek_url` (dezelfde zoekopdracht op gbif.org).

## Tijdsbudget en `volledig`

Stap 4 van de engine (records per overblijvende soort ophalen voor laatste jaar, onzekerheid en
broedindicatie) loopt binnen `tijdsbudget_s` (standaard 40 s). Wat niet op tijd binnenkomt,
wordt nooit stilzwijgend weggelaten: `volledig=False` en `ontbrekend` somt op voor welke
soorten/lagen het niet lukte. Verhoog `tijdsbudget_s` bij grote gebieden met veel soorten.

## Bronnen

- **GBIF occurrence API** (`api.gbif.org`) — waarnemingen, landsfilter België. Dezelfde data
  als gbif.biodiversity.be (hosted portal van Belspo/BBPF). Licentie per onderliggende
  dataset (meestal CC0 of CC BY; zie `dataset_info`).
- **Vlaams Biodiversiteitsportaal** (`natuurdata.inbo.be`, INBO, Atlas of Living
  Australia-stack) — naamzoeken (Nederlandse namen) en de gezaghebbende lijsten hieronder.
  Licentie: CC0.
- **GBIF-checklists** — als aanvulling/controle op de INBO-lijsten: Validated Red Lists of
  Flanders (`gbif_rodelijst_vl`), GRIIS België (`gbif_griis_be`), Unielijst (`gbif_unielijst`),
  Belgian Species List (`gbif_belgian_species_list`), en de EU-brede HRL-bijlagechecklists
  (kruiscontrole, zie hierboven).
- **Digitaal Vlaanderen geolocation v4** (`geo.api.vlaanderen.be`) — adres → coördinaten.
  Modellicentie gratis hergebruik van overheidsinformatie.
- **VRBG-gemeentegrenzen** (Voorlopig Referentiebestand Gemeentegrenzen, Digitaal
  Vlaanderen, WFS) — gemeentegeometrie voor `gemeente`. Modellicentie gratis hergebruik.
- **WFS Departement Omgeving (Mercator)** en **WFS Digitaal Vlaanderen (BWK)** — beschermde
  gebieden en BWK voor `gebieden_rond` (zie hierboven). Modellicentie gratis hergebruik.

### Lijsten op het Vlaams Biodiversiteitsportaal (`lijst`, `soorten_in_gebied`)

| Code | Naam | Groep |
|------|------|-------|
| `soortenbesluit` | Soortenbesluit (bijlage 1, categorieën 1-3) | bescherming |
| `jachtdecreet` | Jachtdecreet — jachtwild (checklist) | bescherming |
| `hrl_ii` | Habitatrichtlijn bijlage II | bescherming |
| `hrl_iv_vl` | Habitatrichtlijn bijlage IV — soorten die in het Vlaamse Gewest voorkomen of kunnen voorkomen (Soortenbesluit categorie 3) | bescherming |
| `hrl_iv` | Habitatrichtlijn bijlage IV (portaal-lijst, 83 soorten; **onvolledig**, gebruik `hrl_iv_vl`) | bescherming |
| `hrl_v` | Habitatrichtlijn bijlage V | bescherming |
| `vrl` | Vogelrichtlijn bijlagen I, II.1 en II.2 (gecombineerd) | bescherming |
| `vrl_iii` | Vogelrichtlijn bijlage III | bescherming |
| `bern` | Verdrag van Bern — bijlagen I, II en III | verdrag |
| `bonn` | Verdrag van Bonn (CMS) — trekkende soorten | verdrag |
| `cites` | EU CITES-verordening — bijlagen | verdrag |
| `unielijst` | Unielijst invasieve uitheemse soorten (Verordening (EU) nr. 1143/2014) | invasief |
| `invasief_uitgebreid` | Uitgebreide lijst invasieve uitheemse soorten (INBO) | invasief |
| `rodelijst_vl` | Meest recente gevalideerde Rode Lijsten van Vlaanderen (INBO); **geen vogels** | rodelijst |
| `rodelijst_broedvogels_2016` | Rode Lijst van de broedvogels in Vlaanderen 2016 (Devos et al. 2016) | rodelijst |
| `rodelijst_vl_nietgevalideerd` | Niet-gevalideerde Rode Lijsten van Vlaanderen | rodelijst |
| `iucn` | IUCN Red List (wereldwijd; niet de Vlaamse status) | rodelijst |
| `prioritair_vl` | Prioritaire soorten Vlaanderen | beleid |
| `prov_antwerpen`, `prov_limburg`, `prov_oost_vlaanderen`, `prov_vlaams_brabant`, `prov_west_vlaanderen` | Provinciaal belangrijke soorten (per provincie) | beleid |
| `soortenmeetnetten` | Checklist Soortenmeetnetten INBO | beleid |

Groepscodes voor `filter` in `soorten_in_gebied`/`telling_in_gebied`: `kern`, `beschermd`,
`europees`, `rodelijst`, `invasief`, `prioritair`, `provinciaal`. Volledig overzicht incl.
URL's: tool `bronnen`. Laaginventaris `gebieden_rond`: `docs/gebieden-lagen.md`.

## Voor gebruikers

Een handleiding zonder technische voorkennis, met installatie-instructies en voorbeeldvragen,
staat in [HANDLEIDING.md](HANDLEIDING.md).

## Rapportsjabloon

`datarapport_natuur` maakt in één oproep het vaste datarapport (`gbif_mcp/rapport.py`). De
bevragingen lopen parallel; een rapport met twee kaarten duurt enkele seconden. Zonder `pad`
belandt de PDF in `~/Documents` (op Windows de map Documenten). Daarnaast biedt de server een
MCP-prompt `datarapport_natuur`: een kant-en-klaar verzoek met adres en stralen als argumenten,
dat Claude laat samenvatten volgens de vaste conventies (beide stralen expliciet, strikt en
striktst beschermd, waarschuwingen letterlijk, niets toevoegen).

Het sjabloon houdt zich aan dezelfde conventies als de tools: beide zoekstralen worden overal
genoemd, "ruimere" of "kleinere" straal alleen wanneer dat klopt, getallen met punt als
duizendtalscheiding ongeacht de systeeminstelling, en laagnamen in plaats van interne codes.

## Voorbeeldrapport

`voorbeeld/datarapport-natuur.pdf` is een datarapport natuur dat volledig uit de tool-uitvoer is
opgebouwd (neutraal testadres, straal 500 m, vanaf 2020): samenvatting, statussen in cijfers,
kernsoorten met herkomst per brondataset, gebiedslagen met afstand, onderliggende records met
verificatiestatus, en een verantwoording met de versiedatum van elke lijst en de GBIF-zoek-URL.
`voorbeeld/datarapport-natuur-met-kaart.pdf` is dezelfde opzet met een situeringskaart als
hoofdstuk 2 (andere locatie, met beschermde gebieden in de buurt).
`voorbeeld/datarapport-kalmthout.pdf` toont twee thematische kaarten naast elkaar: de beschermde
gebieden en de Biologische Waarderingskaart, voor een locatie in de Kalmthoutse Heide.
`voorbeeld/datarapport-temse.pdf` is rechtstreeks door de tool `datarapport_natuur` gemaakt.
`voorbeeld/maak_rapport.py` maakt een bewaarde JSON-bevraging opnieuw op met hetzelfde sjabloon.

## Disclaimer en privacy

> [!WARNING]
> **Betaversie — geen product, geen garantie, geen aansprakelijkheid.** Deze software is een experimenteel
> hulpmiddel in ontwikkeling, geen commercieel product of dienst. De software en de rapporten die ze maakt, worden
> kosteloos aangeboden zoals ze zijn,
> zonder enige uitdrukkelijke of stilzwijgende garantie, onder meer over juistheid, volledigheid, actualiteit of
> geschiktheid voor een bepaald doel. De resultaten zijn een geautomatiseerde bronnenscan van publieke databanken;
> ze vervangen geen terreininventarisatie, deskundige beoordeling of juridisch advies. **De gebruiker is zelf
> volledig verantwoordelijk** voor het controleren van de resultaten en voor elk gebruik dat ervan wordt gemaakt.
> De auteur is niet aansprakelijk voor schade die voortvloeit uit het gebruik van de software of de resultaten.

**Privacy.** De connector verwerkt geen persoonsgegevens van waarnemers. GBIF levert bij een waarneming ook de
naam van de waarnemer en van wie de soort determineerde; die gegevens worden bij ontvangst verwijderd, nog vóór
ze worden bewaard, en komen niet in antwoorden, exports of rapporten terecht.

Zonder licentiebestand blijven alle rechten voorbehouden; neem contact op voor hergebruik van de code.

## Installatie

```bash
cd gbif-mcp
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[test]"
pytest -q          # tests draaien zonder netwerk
```

### Windows

Zie [docs/installeren-windows.md](docs/installeren-windows.md): extensiebundel of git-kloon,
met de PowerShell-stappen en de aandachtspunten. Dezelfde `.mcpb` werkt op macOS en Windows.

### Aansluiten op Claude Desktop

Eenvoudigste weg: de extensiebundel. Bouw ze met `zsh mcpb-src/bouw.sh` (vereist uv en npx),
en installeer `dist/be-biodiversiteit.mcpb` via Claude Desktop → Instellingen → Extensies →
Geavanceerde instellingen → Extensie installeren. De eerste start maakt eenmalig een venv aan
(±1 minuut, internet nodig). Alternatief, zonder bundel:

Voeg toe aan `claude_desktop_config.json` en herstart Claude Desktop:

```json
{
  "mcpServers": {
    "be-biodiversiteit": {
      "command": "/pad/naar/gbif-mcp/.venv/bin/gbif-mcp"
    }
  }
}
```

### Aansluiten op Claude Code

```bash
claude mcp add be-biodiversiteit /pad/naar/gbif-mcp/.venv/bin/gbif-mcp
```

## Harde regels

- **Geen namen van waarnemers.** Velden als `recordedBy` en `identifiedBy` worden bij ontvangst
  verwijderd (`gbif.PERSOONSVELDEN`); voeg ze nooit toe aan een antwoord, export of rapport.
- **Alleen wat een tool teruggeeft is gevonden.** Vul nooit soorten, statussen, gebieden of
  waarnemingen aan die niet letterlijk uit een tool-respons komen.
- **Nul waarnemingen ≠ afwezig.** GBIF-waarnemingen zijn opportunistische meldingen (vooral
  waarnemingen.be), geen systematische inventarisatie. Voor een dossier blijft een
  terreininventarisatie nodig.
- **Coördinaten van gevoelige soorten zijn vaak vervaagd.** Zie `onzekerheid_max_m`/
  `onzekerheid_m` op elke waarneming; waarden van 1-10 km wijzen op vervaging naar een hok.
  `soorten_in_gebied` waarschuwt expliciet (`signaleer_vervaging`) als een strikt beschermde soort
  geen enkel record heeft dat zeker binnen de straal ligt.
- **De brondataset zegt iets over de herkomst, niet over de validatiestatus.** Een dataset-
  uitsplitsing toont wie de determinatie deed en via welk platform. Waarnemingen.be stuurt niet
  alle validatieklassen door naar GBIF, en verscheidene datasets vullen
  `identificationVerificationStatus` niet in. De connector leidt géén betrouwbaarheidsklasse af uit
  een datasetnaam; die weging is aan de gebruiker.
- **`hrl_iv` is onvolledig** (afgeleid van een Britse NBN-lijst; mist o.m. wolf en bever).
  Gebruik voor Vlaamse dossiers `hrl_iv_vl` (Soortenbesluit categorie 3) als primaire bron.
- **Lege `vermeldingen` in `soort_status` betekent niet onbeschermd.** Een soort kan
  basisbescherming genieten (bv. alle inheemse vogels via het Soortenbesluit) zonder als
  aparte regel op een lijst te staan. `soort_status` vermeldt dat expliciet in `melding`.
- **`rodelijst_vl` (dr606) bevat geen vogels.** Gebruik `rodelijst_broedvogels_2016` (of de
  groepen `rodelijst`/`kern`, die beide al bevatten) voor de Rode-Lijststatus van vogels.
- **Een laag met `status='niet_geraadpleegd'` in `gebieden_rond`** is geen "geen gebied
  aanwezig" — de WFS-dienst gaf een fout. Zeg dat er expliciet bij.
- **`volledig=False`/`ontbrekend`** in `soorten_in_gebied` betekent dat niet alle records
  binnen het tijdsbudget zijn opgehaald; neem dat over, doe geen uitspraak over aantallen voor
  de vermelde soorten alsof ze compleet zijn.

## Lokaal draaien (stdio)

```bash
python -m gbif_mcp.server
```
