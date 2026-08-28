# Task: E-ink dashboard (UTKAST — steg 2, mockup inväntar godkännande)

## Vad som ska byggas

En e-inkskärm i hallen som visar dagens relevanta information för familjen:
klocka, väder, skolmat, familjekalender, nästa avgång mot stan.

Skärmen ska se ut som en tavla, inte som ett bygge. Den ska uppdateras utan
att blinka varje minut, och göra en hel omritning varje timme.

## Arkitektur (beslutad)

All datainsamling OCH all rendering sker på användarens Linux-server.
Raspberry Pi:n är en ren visningsklient utan egen layoutlogik.

    [Linux-server]  varje minut
      befintliga kalender- och API-integrationer
        -> normaliserad JSON
        -> HTML-mall
        -> headless Chromium screenshot 800x480
        -> 1-bitars PNG till en statisk sokvag
      webbserver serverar filen med ETag

    [Pi Zero 2 WH]  systemd-tjanst, evig loop
      GET dashboard.png med If-None-Match
        304 -> sov till nasta minut
        200 -> diffa mot foregaende bild
               liten andring -> partiell uppdatering
               stor andring eller hel timme -> full uppdatering
               satt panelen i vilolage

### Varfor rendering pa servern

Anvandaren kommer vilja justera layouten lopande. Om Pi:n ager layouten
kraver varje justering filoverforing och SSH. Med rendering pa servern
sker all iteration dar koden redan finns, med forhandsgranskning i
webblasare istallet for i hallen.

## Hardvara (inkopt)

- Waveshare 7.5" e-Paper HAT V2, 800x480, svart/vit, 884 kr
- Raspberry Pi Zero 2 WH (fyrkarnig, fardig stiftlist), 700 kr
- microSD 16-32 GB A1
- Micro-USB-strom
- Ram ca 21x30 cm

## Kontrakt mellan server och Pi

Ett enda anrop. Pi:n hamtar en statisk bild och behover inte forsta nagot
om innehallet.

    GET /eink/dashboard.png
      -> 800x480, 1-bitars PNG
      -> ETag satt av webbservern
      -> 304 nar inget andrats

## Hardvarukrav som maste respekteras

- Panelen ska alltid sattas i vilolage efter varje uppdatering. Att lamna
  den under spanning kan skada den.
- Partiella uppdateringar lamnar spokrester. Full omritning varje hel timme
  suddar dem.
- Vid partiell uppdatering maste x-koordinat och bredd vara jamnt delbara
  med 8, eftersom bilden ar packad en bit per pixel.

## Beslut om framstallning

- Tunnelbanetider visas som klockslag, inte nedrakning. En nedrakning blir
  direkt felaktig om skarmen inte uppdaterats pa en kvart.
- Om servern inte svarar pa 15 minuter: behall bilden men markera diskret,
  sa att "inget nytt" gar att skilja fran "trasigt".

## Besvarade fragor

- Servern ar en VPS ute pa internet. Dashboard-endpointen maste darfor
  skyddas med bearer-token over HTTPS. Bilden innehaller familjekalendern
  i klartext och far inte ligga oppen.
- Befintliga integrationer ar skrivna i Python. Renderaren laggs i samma
  projekt och laser datakallorna direkt.
- Rendering sker via HTML-mall plus headless Chromium, inte Pillow.
  Motivering: layouten kommer justeras lopande, och HTML/CSS gar att
  forhandsgranska i webblasare istallet for att skickas till hallen.

## Teknikval som foljer av ovanstaende

- Jinja2 for HTML-mallen
- Playwright med varmhallen Chromium-instans for skarmdumpen
- Pillow enbart for sista steget: 800x480 till 1-bitars PNG
- FastAPI for endpointen, med egen ETag och 304-hantering
- Per-kalla cache med olika livslangd, sa att rendering varje minut inte
  innebar externa anrop varje minut

## Oppna fragor (blockerar kravspecen)

- [ ] Godkannande av layouten i tasks/mockup-eink-dashboard.html
- [ ] Vilken hallplats och riktning galler for avgangstiderna
- [ ] Vilken skola galler for skolmaten, och vilka barn
- [ ] Hur nas de befintliga kalendrarna: Python-objekt eller eget API

## Success Criteria (utkast)

- [ ] Skarmen visar korrekt tid, uppdaterad varje minut utan synlig blinkning
- [ ] Hel omritning varje timme, utan spokrester efterat
- [ ] Layouten gar att andra utan att rora Pi:n
- [ ] Server nere -> skarmen behaller senaste bilden och markerar det
- [ ] Pi:n aterupptar visning automatiskt efter stromavbrott
- [ ] Panelen satts i vilolage efter varje uppdatering

## Mockup

tasks/mockup-eink-dashboard.html — publicerad for granskning.
Innehaller layouten i skala, kallan for varje yta, och pipelinen.
