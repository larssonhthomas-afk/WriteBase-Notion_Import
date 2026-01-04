#!/usr/bin/env python3
"""
Import Notion export to Airtable

Användning:
    python3 import_to_airtable.py ./output/content.json

Kräver:
    pip3 install requests
"""

import json
import sys
import time
import warnings
import requests
from pathlib import Path

# Suppress LibreSSL/OpenSSL warning from urllib3
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

# === KONFIGURATION ===
# API keys from environment variables
import os
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "app7rJKwiEkVKn79v")
TABLE_NAME = "DOCUMENT"
PROJECT_NAME = "Notion_Import"

# PROJECT table field name (often "Name" or "Title" - adjust to match your Airtable schema)
PROJECT_NAME_FIELD = "Title"  # Changed from "Name" to match Airtable schema

# Fältmappning: Notion -> Airtable
FIELD_MAPPING = {
    "title": "Title",
    "body": "Content",
    "status": "Status",
    "notion_id": "Notion_ID",
    "tags": "Notion_Tag",  # Textfält - länkas manuellt senare
    "publish_date": "Publish_Date",
    # "content_type": "Type",  # Beräknat fält - kan inte skrivas
}

# Status value mapping: Notion status -> Airtable status
# Map invalid values to valid Airtable select options
# Set to None to skip records with unmapped status values
STATUS_MAPPING = {
    "Published": "Published",
    "Inbox": "Inbox",
    "#reference": "Inbox",    # Map #reference -> Inbox (or change to valid option)
    "#idea": "Inbox",         # Map #idea -> Inbox (or change to valid option)
    "": None,                 # Skip empty status
}

# Rate limiting
BATCH_SIZE = 10  # Airtable max 10 per request
DELAY_BETWEEN_BATCHES = 0.25  # sekunder


def load_json(filepath: Path) -> list:
    """Ladda JSON-filen"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def clean_value(value: str) -> str:
    """Rensa bort extra citattecken och whitespace"""
    if isinstance(value, str):
        # Ta bort ledande/avslutande citattecken
        value = value.strip().strip('"').strip("'")
    return value


def map_record(notion_record: dict, project_id: str = None) -> dict:
    """Mappa ett Notion-record till Airtable-format"""
    fields = {}

    for notion_key, airtable_key in FIELD_MAPPING.items():
        value = notion_record.get(notion_key, "")
        if value:  # Skippa tomma värden
            cleaned = clean_value(value)

            # Special handling for Status field - map to valid Airtable options
            if notion_key == "status":
                mapped_status = STATUS_MAPPING.get(cleaned)
                if mapped_status is None:
                    # Skip status if not in mapping or mapped to None
                    continue
                cleaned = mapped_status

            fields[airtable_key] = cleaned

    # Lägg till PROJECT om vi har ett ID
    if project_id:
        fields["PROJECT"] = [project_id]

    return {"fields": fields}


def create_project_if_needed(session: requests.Session) -> str:
    """Kolla om PROJECT finns, annars skapa"""
    # Först kolla om projektet redan finns
    url = f"https://api.airtable.com/v0/{BASE_ID}/PROJECT"
    params = {"filterByFormula": f"{{{PROJECT_NAME_FIELD}}}='{PROJECT_NAME}'"}

    response = session.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        if data.get("records"):
            record_id = data["records"][0]["id"]
            print(f"✅ Projekt '{PROJECT_NAME}' finns redan (ID: {record_id})")
            return record_id

    # Skapa projektet om det inte finns
    print(f"📁 Skapar projekt '{PROJECT_NAME}'...")
    response = session.post(url, json={"fields": {PROJECT_NAME_FIELD: PROJECT_NAME}})

    if response.status_code == 200:
        record_id = response.json()["id"]
        print(f"✅ Projekt skapat (ID: {record_id})")
        return record_id
    else:
        print(f"⚠️  Kunde inte skapa/hitta projekt: {response.text}")
        return None


def upload_batch(session: requests.Session, records: list) -> tuple[int, int]:
    """Ladda upp en batch med records. Returnerar (success, failed)"""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    
    payload = {"records": records}
    response = session.post(url, json=payload)
    
    if response.status_code == 200:
        return len(records), 0
    else:
        print(f"❌ Batch misslyckades: {response.status_code}")
        print(f"   {response.text[:200]}")
        return 0, len(records)


def main():
    # Check for required API key
    if not AIRTABLE_API_KEY:
        print("❌ AIRTABLE_API_KEY environment variable not set.")
        print()
        print("Set it with:")
        print("  export AIRTABLE_API_KEY=your_api_key")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Användning: python3 import_to_airtable.py ./output/content.json")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"❌ Filen finns inte: {json_path}")
        sys.exit(1)
    
    # Ladda data
    print(f"📂 Laddar {json_path}...")
    records = load_json(json_path)
    print(f"   {len(records)} poster att importera")
    print()
    
    # Setup session
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    })
    
    # Kolla/skapa projekt
    project_id = create_project_if_needed(session)
    print()
    
    # Mappa alla records
    print("🔄 Mappar fält...")
    airtable_records = []
    for r in records:
        mapped = map_record(r, project_id)
        airtable_records.append(mapped)
    
    # Ladda upp i batchar
    print(f"📤 Laddar upp till Airtable ({BATCH_SIZE} åt gången)...")
    print()
    
    total_success = 0
    total_failed = 0
    
    for i in range(0, len(airtable_records), BATCH_SIZE):
        batch = airtable_records[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(airtable_records) + BATCH_SIZE - 1) // BATCH_SIZE
        
        success, failed = upload_batch(session, batch)
        total_success += success
        total_failed += failed
        
        print(f"   Batch {batch_num}/{total_batches}: {success} ✓ {failed} ✗")
        
        if i + BATCH_SIZE < len(airtable_records):
            time.sleep(DELAY_BETWEEN_BATCHES)
    
    print()
    print("=" * 40)
    print(f"✅ Klart!")
    print(f"   Importerade: {total_success}")
    print(f"   Misslyckade: {total_failed}")


if __name__ == "__main__":
    main()
