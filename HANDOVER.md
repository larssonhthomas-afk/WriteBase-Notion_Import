# Handover: Hallskärmen (e-ink dashboard)

Det här dokumentet är skrivet för en Claude-agent som ska fortsätta arbetet
på användarens riktiga Linux-server. Det gör dig i stånd att fortsätta utan
att behöva rekonstruera beslut som redan är tagna. Läs hela filen innan du
ändrar något — flera val ser godtyckliga ut isolerat men är det inte.

Repot du eventuellt läser detta i (`larssonhthomas-afk/writebase-notion_import`,
branch `claude/delete-and-restart-gj7kw4`) var alltid en tillfällig
arbetsyta — användaren sa det uttryckligen i första meddelandet i den här
tråden. Koden nedan ska flyttas in i ett riktigt projekt på servern, inte
fortsätta leva här.

## Vad det här är

En e-inkskärm i familjens hall som visar klocka, väder, skolmat, dagens
kalender och nästa avgångar mot stan. Kravet som formade hela arkitekturen:
användaren kommer justera layouten löpande, och det får inte innebära att
röra Raspberry Pi:n varje gång.

## Arkitekturen (beslutad, lägg inte upp den för diskussion igen)

```
[Linux-server, VPS på internet]  körs varje minut
  källorna (väder, skolmat, avgångar, kalender)
    -> cachas var för sig, olika livslängd per källa
    -> Jinja2-mall -> HTML
    -> Playwright/Chromium, skärmdump 800x480
    -> tröskling till rent svartvitt (ingen gråskala i panelen)
  FastAPI serverar bilden på /dashboard.png bakom ett bearer-token

[Raspberry Pi 3A+ i hallen]  systemd-tjänst, loop var 60:e sekund
  GET /dashboard.png med If-None-Match
    304 -> rör inte panelen
    200 -> diffa mot förra bilden
           liten ändring -> partiell uppdatering (tyst, ingen blinkning)
           stor ändring eller hel timme -> full omritning
           panelen sövs efter varje uppdatering
```

**Varför servern renderar och Pi:n bara visar:** All logik och all layout
bor på servern, där den går att förhandsgranska i en webbläsarflik. Pi:n är
avsiktligt dum — cirka 200 rader som aldrig behöver ändras när layouten
ändras. En layoutjustering ska aldrig kräva SSH mot hallen.

**Varför HTML/Chromium och inte Pillow:** Layouten kommer justeras löpande.
CSS går att iterera på i en webbläsare. Pixel-för-pixel-koordinater i
Pillow gör varje layoutändring till räknearbete.

**Varför bearer-token, inte öppen endpoint:** Servern står på internet.
Bilden innehåller familjens dag i klartext — namn, tider, var barnen är.
Servern VÄGRAR starta utan `DASHBOARD_TOKEN` satt (se `server/config.py`,
`ConfigError`). Det är avsiktligt, inte en bugg att runda.

## Hårdvara (inköpt, konfirmerat av användaren)

- Waveshare 7.5" e-Paper HAT **V2**, 800×480, ren svartvit (ingen
  gråskala) — inte (B) eller (H), de är trefärgade och saknar partiell
  uppdatering
- Raspberry Pi **3 Model A+** (inte Zero — Zero 2 WH var slutsåld
  överallt när det begav sig). Har färdig 40-pin stiftlist.
  **Kräver 5V/2,5Aström**, mer än en Zero drar. Bekräfta att laddaren
  klarar det innan något monteras — underspänning ger slumpmässiga
  hängningar, inte ett tydligt fel.
- microSD, 128 GB, A1-märkt (Lexar eller likvärt märke)
- Ram, ~21×30 cm — inte inköpt än vid handover

## Vad som redan finns och är testat

Allt nedan ligger i det tillfälliga repot, 70 pytest-tester gröna, inget
beroende av riktig hårdvara eller nätverk för att köras.

```
server/
  config.py       Settings-laddning från config.yaml + miljövariabler.
                   Vägrar starta utan giltig DASHBOARD_TOKEN.
  cache.py         TTLCache: en hållbarhetstid per källa. Misslyckas en
                   hämtning lämnas det gamla värdet ut, märkt stale.
  clock.py         All tid i hushållets tidszon (Europe/Stockholm), inte
                   serverns (en VPS står nästan alltid i UTC).
  framebuffer.py    Bild <-> panelens 1-bit-format. dirty_region() räknar
                   ut vad som ändrats, snappat till 8-pixel bytegräns.
  dashboard.py     Sätter ihop källornas data till mallens sammanhang.
  app.py           FastAPI: /dashboard.png, /dashboard.bin (rå buffer),
                   /healthz (bara åldrar, aldrig innehåll). Token-check i
                   konstant tid.
  sources/
    weather.py      SMHI öppna data. OBS: SMHI stängde sitt gamla api i
                    mars 2026 -- gamla kodexempel på nätet stämmer inte.
    meals.py        skolmaten.se via RSS, ingen inloggning.
    transit.py      SL öppna api. Tider visas som klockslag, INTE
                    nedräkning (en nedräkning blir fel om skärmen legat
                    stilla en kvart).
    agenda.py       ICS-länkar OCH/ELLER calendar_provider (se nedan).
                    RRULE expanderas via recurring_ical_events.
    almanac.py      Namnsdag (lokal json, se Kvarstående) + Wikipedia
                    "detta hände idag".
  render/
    template.html   HELA layouten. Ändra HÄR, aldrig i pi/.
    renderer.py     Playwright, varmhållen Chromium-instans.

pi/
  client.py        Hämta/jämför/uppdatera-loopen. Diffar mot senaste
                    bilden, väljer partiell/full/ingen uppdatering.
                    Markerar diskret vid >15 min utan svar från servern,
                    tar bort markeringen automatiskt vid återhämtning.
  epaper.py        Tunn insvepning kring waveshare_epd som tål att
                    metodnamnen skiljer sig mellan drivrutinsversioner.
                    Faller tillbaka till en loggande NullPanel om
                    drivrutinen saknas (så klienten går att köra/testa
                    på vilken maskin som helst).

tests/              70 tester. `pytest -q` (kräver Chromium, se nedan).
config.yaml.example  Mall för config.yaml. Kommentarer förklarar varje fält.
deploy/              systemd-enheter, se "Driftsättning" nedan.
requirements.txt     Serverns beroenden.
requirements-pi.txt  Pi-klientens beroenden (mycket smalare -- ingen
                    Playwright, ingen FastAPI).
```

### Köra testerna

```
pip install -r requirements-dev.txt
playwright install chromium   # eller sätt CHROMIUM_PATH till en befintlig binär
pytest -q
```

## Kvarstående arbete (i rekommenderad ordning)

1. **Flytta koden till en riktig plats på servern.** Antingen genom att
   klona det tillfälliga repots gren, eller genom att be användaren
   kopiera `server/`, `pi/`, `tests/`, `requirements*.txt`,
   `config.yaml.example`, `deploy/` till projektets riktiga hemvist.

2. **Fyll i `config.yaml`** utifrån `config.yaml.example`. Tre uppgifter
   saknas fortfarande från användaren (loggade i `tasks/task-eink-dashboard.md`):
   - Vilken hållplats och riktning för `place.site_id` / `place.direction`
   - Vilken skola för `school_slug`, och barnens namn/scheman
   - Hur befintliga kalendrar på servern nås — fråga rakt ut: går de att
     importera som Python-objekt (då: skriv en `calendar_provider`-
     funktion, se docstring i `server/sources/agenda.py`), eller finns
     redan ett internt API (då: överväg om `calendar_urls` räcker, eller
     om `calendar_provider` ska anropa det API:et istället)?

3. **Generera och lagra `DASHBOARD_TOKEN` säkert.**
   `openssl rand -hex 32`, in i en EnvironmentFile med 600-rättigheter.
   ALDRIG i config.yaml, ALDRIG committat. Se `deploy/hallskarmen-server.service`.

4. **Sätt en reverse proxy med TLS framför servern** (Caddy eller nginx).
   `server/app.py` binder avsiktligt bara till `127.0.0.1` i unit-mallen —
   den ska aldrig exponeras direkt. Ett bearer-token utan HTTPS skickar
   hemligheten i klartext, vilket gör hela skyddet meningslöst.

5. **Installera systemd-enheterna.** Mallarna i `deploy/` har kommentarer
   om vad som måste anpassas (användare, sökvägar). Server-enheten och
   Pi-enheten är TVÅ OLIKA maskiner — blanda inte ihop dem.

6. **På Pi:n:** aktivera SPI (`raspi-config` → Interface Options → SPI),
   installera Waveshares `waveshare_epd`-paket enligt deras egen
   dokumentation, sätt `DASHBOARD_URL` och `DASHBOARD_TOKEN` i
   `pi.env`. Testa först med `python -m pi.client --dry-run --once` --
   det kör hela hämta/jämför-loopen utan att röra panelen, bra för att
   verifiera nätverk och token innan hårdvaran är inkopplad.

7. **(Valfritt) `data/namnsdagar.json`.** Ytan lämnas tom om filen
   saknas -- den är utfyllnad, inte kritisk. Formen är
   `{"08-28": "Gunnar, Gunder"}`. Finns inget bra öppet api för svenska
   namnsdagar; en handskriven tabell är hederligare än ett skört scrape.

8. **Provkör mot riktig hårdvara** när Pi:n och skärmen är hopkopplade.
   Kör en full uppdatering (`--clear` rensar panelen om något ser
   konstigt ut), sedan `--once` upprepade gånger med olika data för att
   se att partiell uppdatering faktiskt är tyst.

## Beslut att INTE ifrågasätta utan att fråga användaren igen

- **Touch-skärm**: avfärdad. Ingen touch-variant finns i 7,5-tumsformatet,
  och e-ink är för långsamt (2–5 sekunder per tryck genom hela kedjan)
  för att kännas som ett gränssnitt. Om interaktion efterfrågas: föreslå
  två fysiska GPIO-knappar, inte touch.
- **Batteridrift**: avfärdad för Pi 3A+ (tömmer en powerbank på under ett
  dygn). Kräver ESP32 + djupsömn, vilket i sin tur kräver att
  minut-uppdateringen av klockan släpps (var 15:e minut i bästa fall).
  Ett annat projekt än det som är byggt.
- **Raspberry Pi Pico**: teknisk möjlig väg (finns en färdig
  Pico-ePaper-7.5), men medvetet avfärdad till förmån för en riktig Pi
  med Linux, eftersom felsökning annars kräver USB-seriekonsol istället
  för SSH.

## Om du fastnar

`tasks/task-eink-dashboard.md` i det tillfälliga repot har hela
beslutsloggen i kronologisk ordning, inklusive varför Pi 3A+ valdes över
Zero 2 WH. `tasks/mockup-eink-dashboard.html` visar layouten användaren
godkände i skala (öppna den i en webbläsare).
