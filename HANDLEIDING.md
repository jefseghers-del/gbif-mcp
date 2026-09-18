# BE-biodiversiteit — handleiding

Voor wie de connector gewoon wil gebruiken. Geen programmeerkennis nodig.

> [!WARNING]
> **Betaversie — geen product, geen garantie, geen aansprakelijkheid.** Deze software is een experimenteel
> hulpmiddel in ontwikkeling, geen commercieel product of dienst. De software en de rapporten die ze maakt, worden
> kosteloos aangeboden zoals ze zijn,
> zonder enige uitdrukkelijke of stilzwijgende garantie, onder meer over juistheid, volledigheid, actualiteit of
> geschiktheid voor een bepaald doel. De resultaten zijn een geautomatiseerde bronnenscan van publieke databanken;
> ze vervangen geen terreininventarisatie, deskundige beoordeling of juridisch advies. **De gebruiker is zelf
> volledig verantwoordelijk** voor het controleren van de resultaten en voor elk gebruik dat ervan wordt gemaakt.
> De auteur is niet aansprakelijk voor schade die voortvloeit uit het gebruik van de software of de resultaten.

BE-biodiversiteit geeft Claude toegang tot de officiële Belgische natuurdatabanken: de
waarnemingen van GBIF (waaronder waarnemingen.be, Florabank en de INBO-meetnetten), de Vlaamse
soortenlijsten van het INBO (Soortenbesluit, Habitat- en Vogelrichtlijn, Rode Lijsten, Unielijst
invasieve soorten) en de kaartlagen van de Vlaamse overheid (Natura 2000, VEN/IVON,
natuurbeheerplannen, beschermd erfgoed, Biologische Waarderingskaart).

U stelt uw vraag gewoon in het Nederlands. Claude kiest zelf de juiste opzoeking.

---

## 1. Installeren

**Wat u eerst nodig hebt**

- Claude Desktop (Mac of Windows).
- Python 3.12 of hoger. Nog niet geïnstalleerd? Haal het op bij [python.org](https://www.python.org/downloads/).
  Vink op Windows tijdens de installatie **"Add python.exe to PATH"** aan.

**Installeren in vier stappen**

1. Ga naar de [releases van de repository](https://github.com/jefseghers-del/gbif-mcp/releases)
   en download het bestand `be-biodiversiteit.mcpb` van de bovenste release.
2. Open Claude Desktop en ga naar **Instellingen → Extensies**.
3. Klik op **Geavanceerde instellingen → Extensie installeren** en kies het gedownloade bestand.
4. De eerste keer duurt het opstarten één tot drie minuten: de extensie zet dan haar eigen
   werkomgeving klaar. Daarvoor is internet nodig. Claude Desktop wacht daar niet altijd op en
   kan een time-out melden. **Wacht dan drie minuten en start Claude Desktop opnieuw**; de tweede
   keer start de extensie meteen.

**Controleren of het werkt**

Typ in een nieuw gesprek:

> Welke bronnen kan je raadplegen voor Belgische biodiversiteit?

Krijgt u een overzicht met lijsten als het Soortenbesluit en de Vlaamse Rode Lijsten, dan werkt de
connector. Ziet u bij Extensies de melding **Failed**, klik dan op **View logs** en stuur de regels
door die beginnen met `[be-biodiversiteit]`.

---

## 2. Het datarapport natuur in één vraag

De connector heeft een vast rapportsjabloon. Elk rapport heeft dezelfde opbouw: titelblad met
coördinaten en zoekstralen, samenvatting, situeringskaart en kaart van de Biologische
Waarderingskaart, statussen in cijfers, de kernsoorten met de herkomst van hun waarnemingen, de
beschermde gebieden met afstand, de onderliggende waarnemingen van de striktst beschermde soorten,
een verantwoording van de bronnen en de beperkingen.

**De eenvoudigste manier:** typ gewoon

> Maak een datarapport natuur voor Kerkstraat 12, 9070 Destelbergen.

Claude maakt dan de PDF en de kaarten, en zet ze in uw map Documenten. Wilt u andere afstanden of
een andere periode, zeg het erbij:

> Maak een datarapport natuur voor Kerkstraat 12, 9070 Destelbergen, soorten binnen 750 m,
> gebieden binnen 1,5 km, waarnemingen vanaf 2018, en bewaar het op mijn bureaublad.

**Via het sjabloon.** Claude Desktop toont het sjabloon ook als kant-en-klare opdracht
("Datarapport natuur") bij de extensie, via het plusteken in het invoerveld. U vult dan het adres
en eventueel de afstanden in.

Standaard gelden 500 m voor soorten, 1000 m voor gebieden en waarnemingen vanaf 2020. Welke
afstand gepast is, hangt af van het project en het type natuur; het rapport vermeldt beide
afstanden overal, zodat de keuze controleerbaar blijft.

## 3. Wat u verder kunt vragen

Hieronder staan voorbeelden die u letterlijk kunt overnemen. Vervang het adres en de afstanden
door die van uw dossier.

### Een projectlocatie doorlichten

> Ik bereid een omgevingsvergunningsaanvraag voor op Kerkstraat 12 in Destelbergen. Geef me eerst
> een telling van beschermde, Rode-Lijst- en invasieve soorten binnen 500 m sinds 2020.

> Welke beschermde gebieden en gebiedsstatuten liggen binnen 1 km van dat adres? Geef per laag de
> afstand.

> Maak een situeringskaart van die locatie met de beschermde gebieden binnen 1 km.

> Maak daarnaast een aparte kaart van de Biologische Waarderingskaart, met een kleur per
> habitattype.

> Zet alles samen in een datarapport als PDF: situering met kaart, de kernsoorten in een tabel, de
> gebieden met hun afstand, en een verantwoording van de bronnen.

### De strikt beschermde soorten

Met "kernsoorten" bedoelt de connector de soorten die in een natuurtoets het meest wegen: bijlage
IV en bijlage II van de Habitatrichtlijn, bijlage I van de Vogelrichtlijn, en de Rode-Lijstsoorten
in de categorieën uitgestorven, ernstig bedreigd, bedreigd of kwetsbaar.

> Geef de kernsoorten binnen 750 m van dat adres sinds 2020, in tabelvorm, met per soort uit welke
> brondatasets de waarnemingen komen.

> Welke vleermuizen zijn daar gemeld, en hoe nauwkeurig zijn die locaties?

### Eén soort opzoeken

> Wat is het beschermingsstatuut van de kamsalamander in Vlaanderen? Geef de bronnen erbij.

> Is de huismus een Rode-Lijstsoort?

> Waar is de vroedmeesterpad gemeld in de gemeente Zutendaal sinds 2015?

### Invasieve exoten

> Welke soorten van de Unielijst zijn sinds 2020 gemeld in de gemeente Zutendaal, met aantallen en
> het laatste jaar?

> Staat de nijlgans op de Unielijst?

### Lijsten raadplegen

> Toon me de soorten van categorie 3 van het Soortenbesluit.

> Welke soortengroepen dekt de Vlaamse Rode Lijst, en uit welk jaar dateert elke lijst?

### Een bestand voor het dossier

> Schrijf de volledige bevraging weg als CSV op mijn bureaublad, inclusief alle onderliggende
> waarnemingen, zodat ik ze als bijlage kan voegen.

---

## 4. Waar u op moet letten

Deze punten horen in elk rapport dat u op de connector baseert. Claude vermeldt ze zelf, maar u
blijft verantwoordelijk voor de juridische weging.

**U blijft zelf verantwoordelijk.** De connector is een betaversie en geeft geen enkele garantie over de
resultaten. Controleer wat u in een advies, nota of vergunningsdossier overneemt.

**Geen namen van waarnemers.** De connector verwijdert de namen van waarnemers en determinatoren bij
ontvangst. U vindt ze dus niet in de rapporten; wie ze nodig heeft, gaat naar de bron op gbif.org.

**Geen waarneming betekent niet: soort afwezig.** De waarnemingen zijn meldingen van vrijwilligers
en onderzoekers, geen systematische inventarisatie. Een terreinbezoek blijft nodig.

**Locaties van gevoelige soorten zijn vervaagd.** Vleermuizen, roofvogels en zeldzame planten
krijgen vaak een onnauwkeurigheid van 707 m of meer: het record is dan naar een hok verschoven. De
werkelijke vindplaats kan buiten uw zoekstraal liggen. De connector waarschuwt daarvoor.

**De herkomst van een waarneming bepaalt haar gewicht.** Een determinatie uit een INBO-meetnet
weegt anders dan een geluidsopname op Xeno-canto of een automatische determinatie door Pl@ntNet.
De connector toont per soort uit welke databank de waarnemingen komen, maar velt daarover geen
oordeel. Dat is uw werk.

**De kaarten werken ook zonder kleuronderscheid.** Elk vlak draagt het nummer van zijn legenderegel
en elke laag heeft een eigen arcering. Het kleurenpalet is gekozen zodat de kleuren ook bij
kleurenblindheid uit elkaar te houden zijn. Print u in grijswaarden, dan blijft de kaart leesbaar.

**De gebiedslagen zijn niet volledig.** De kernzones van erkende natuurreservaten en de
bosreservaten zitten niet in de geraadpleegde diensten. Controleer een dossier altijd nog op
[Geopunt](https://www.geopunt.be).

**Alleen Vlaanderen voor adressen en gebieden.** Het opzoeken van een adres, de gemeentegrenzen en
alle kaartlagen werken enkel in Vlaanderen. Voor Wallonië en Brussel geeft u coördinaten mee; de
soortwaarnemingen werken wel voor heel België.

**Vraag altijd naar de bronnen.** Elk antwoord bevat het tijdstip van de bevraging, de versiedatum
van elke gebruikte lijst en een link naar dezelfde zoekopdracht op gbif.org. Neem die op in uw
rapport, dan is de bevraging later na te doen.

---

## 5. Handige preciseringen in uw vraag

| Wat u toevoegt | Wat het doet |
|---|---|
| "sinds 2020" | beperkt tot recente waarnemingen; zonder jaartal komt alles mee, ook oude meldingen |
| "binnen 500 m" | bepaalt de zoekstraal; u mag voor soorten en gebieden een andere straal kiezen |
| "in tabelvorm" | compacte tabel in plaats van een lange opsomming; aan te raden vanaf 50 soorten |
| "alleen de kernsoorten" | beperkt tot de strikt beschermde en bedreigde soorten |
| "met de brondatasets" | toont per soort waar de waarnemingen vandaan komen |
| "alleen bedreigde soorten" | beperkt de Rode-Lijstsoorten tot de bedreigde categorieën |
| "als PDF" of "als CSV" | levert een bestand op in plaats van een antwoord in het gesprek |
| "een aparte kaart per thema" | voorkomt dat de Biologische Waarderingskaart de beschermde gebieden overdekt |

---

## 6. Als er iets misloopt

**De extensie start niet.** Instellingen → Extensies → View logs, en kijk naar de regels met
`[be-biodiversiteit]`. Meestal ontbreekt Python 3.12 of was er bij de eerste start geen internet.

**Bij de eerste start: "Request timed out".** Dat is normaal. De extensie installeert op de
achtergrond verder; staat er in het log "Omgeving klaar", start dan Claude Desktop opnieuw.

**Windows: Python gevonden?** De extensie start Python met de opdracht `python`. Werkt die opdracht
niet in een opdrachtprompt, installeer Python dan opnieuw via python.org en vink "Add python.exe
to PATH" aan.

**Een adres wordt niet gevonden.** De adressendienst dekt alleen Vlaanderen en Brussel. Geef in dat
geval coördinaten mee, bijvoorbeeld "51.06691 noorderbreedte, 3.68249 oosterlengte".

**Een straatnaam zonder huisnummer.** Dan neemt de connector het midden van de straat en zegt dat
erbij. Bij een lange straat kan uw perceel daardoor buiten de zoekstraal vallen. Geef een
huisnummer of coördinaten.

**Het antwoord duurt lang.** Een gebied met veel soorten kan tot een halve minuut vragen. Vraagt u
alleen een telling, dan gaat het sneller.

**Een laag is "niet geraadpleegd".** De dienst van de Vlaamse overheid antwoordde niet. Dat is iets
anders dan "er ligt geen gebied". Vraag het even later opnieuw.
