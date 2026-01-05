# Notion → Airtable Import

Importera Notion-export till Airtable med bilder.

## Översikt

Denna process tar en Notion-export och importerar den till Airtable:
1. **Bilder** → ASSET-tabellen
2. **Dokument** → DOCUMENT-tabellen (med bildlänkar ersatta)

## Förutsättningar

- Python 3.9+
- `requests`-biblioteket: `pip3 install requests`
- Airtable API-nyckel från https://airtable.com/create/tokens
- GitHub-konto (för bildhosting)

## Airtable-struktur

### ASSET-tabell
| Fält | Typ |
|------|-----|
| Caption | Text |
| Attachment | Attachment |
| Type | Formula (beräknat) |

### DOCUMENT-tabell
| Fält | Typ |
|------|-----|
| Title | Text |
| Content | Long text |
| Status | Single select |
| Notion_ID | Text |
| Notion_Tag | Text |
| Publish_Date | Text |
| PROJECT | Link to PROJECT |

### PROJECT-tabell
| Fält | Typ |
|------|-----|
| Title | Text |

## Steg-för-steg

### 1. Exportera från Notion

1. Öppna Notion
2. Gå till **Settings & Members** → **Settings**
3. Scrolla ned till **Export all workspace content**
4. Välj **Markdown & CSV**
5. Ladda ner ZIP-filen

### 2. Förbered exporten

1. Packa upp ZIP-filen
2. Kör `notion_to_airtable.py` för att konvertera:

```bash
python3 notion_to_airtable.py /sökväg/till/notion/export ./notion_export
```

Detta skapar:
- `notion_export/content.json` - Alla dokument
- `notion_export/images/` - Alla bilder med Notion ID-prefix
- `notion_export/broken_images.txt` - Bilder som saknas

### 3. Ladda upp till GitHub

Bilderna måste vara tillgängliga via publika URL:er:

```bash
git add notion_export/
git commit -m "Add Notion export"
git push origin main
```

**Viktigt:** Repot måste vara **publikt** för att bildlänkarna ska fungera.

### 4. Konfigurera scriptet

Öppna `full_import.py` och kontrollera att dessa värden stämmer:

```python
BASE_ID = "app7rJKwiEkVKn79v"  # Din Airtable Base ID
GITHUB_OWNER = "ditt-användarnamn"
GITHUB_REPO = "ditt-repo"
GITHUB_BRANCH = "main"
```

### 5. Kör importen

```bash
AIRTABLE_API_KEY=din_api_nyckel python3 full_import.py
```

Scriptet kommer att:
1. Ladda upp alla bilder till ASSET-tabellen
2. Skapa en mappning mellan bildnamn och Airtable-ID:n
3. Importera alla dokument till DOCUMENT-tabellen
4. Ersätta bildlänkar med `![caption](asset:recID:attID)`-format

### 6. Verifiera

Kontrollera i Airtable att:
- ASSET-tabellen innehåller alla bilder
- DOCUMENT-tabellen innehåller alla dokument
- Bildlänkar i Content-fältet har formatet `![caption](asset:recXXX:attXXX)`

## Felsökning

### "GitHub URLs are not accessible"
- Kontrollera att repot är publikt
- Kontrollera att bilderna är pushade till main-branchen
- Vänta några minuter om du nyss gjort repot publikt

### "AIRTABLE_API_KEY not set"
Sätt API-nyckeln före kommandot:
```bash
AIRTABLE_API_KEY=patXXXXX python3 full_import.py
```

### "Field cannot accept value because it's computed"
Fältet är en formel i Airtable och kan inte skrivas till. Ta bort det fältet från scriptet.

### Bilder ersätts inte
- Kontrollera att bildnamnen i `notion_export/images/` matchar referenserna i content.json
- Scriptet försöker matcha både exakt och fuzzy (delvis matchning)

## Filstruktur

```
├── notion_to_airtable.py    # Konvertera Notion-export till JSON
├── full_import.py           # Huvudscript - importera bilder + dokument
├── import_to_airtable.py    # Endast dokument (utan bilder)
├── upload_images_to_airtable.py  # Endast bilder
└── notion_export/
    ├── content.json         # Dokument i JSON-format
    ├── content.csv          # Dokument i CSV-format
    ├── images/              # Bilder med Notion ID-prefix
    └── broken_images.txt    # Saknade bilder
```

## Bildlänk-format

Scriptet ersätter dessa format:

| Ursprungligt format | Ersätts med |
|---------------------|-------------|
| `![[bild.png]]` | `![bild](asset:recXXX:attXXX)` |
| `![[bild.png\|alt]]` | `![bild](asset:recXXX:attXXX)` |
| `![alt](path/bild.png)` | `![alt](asset:recXXX:attXXX)` |

## Säkerhet

**Viktigt:** Lägg aldrig API-nycklar i koden. Använd alltid miljövariabler:

```bash
# Sätt temporärt (bara för detta kommando)
AIRTABLE_API_KEY=din_nyckel python3 full_import.py

# Eller exportera för sessionen
export AIRTABLE_API_KEY=din_nyckel
python3 full_import.py
```
