#!/usr/bin/env python3
"""
Full Notion to Airtable Import with Images

Flow:
1. Upload all images to ASSET table → create mapping
2. Import DOCUMENT records → replace ![[image]] with ![](asset:recID:attID)

Usage:
    AIRTABLE_API_KEY=your_key python3 full_import.py

Requirements:
    pip3 install requests
"""

import os
import re
import json
import time
import warnings
import requests
from pathlib import Path
from collections import defaultdict

# Suppress LibreSSL/OpenSSL warning
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

# === CONFIGURATION ===
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "app7rJKwiEkVKn79v")

# Tables
DOCUMENT_TABLE = "DOCUMENT"
ASSET_TABLE = "ASSET"
PROJECT_TABLE = "PROJECT"

# Paths
IMAGES_DIR = Path("./notion_export/images")
CONTENT_JSON = Path("./notion_export/content.json")

# GitHub configuration for image URLs
GITHUB_OWNER = "larssonhthomas-afk"
GITHUB_REPO = "WriteBase-Notion_Import"
GITHUB_BRANCH = "main"
GITHUB_IMAGE_PATH = "notion_export/images"

# Project name for imported documents
PROJECT_NAME = "Notion_Import"

# Field mapping: Notion -> Airtable
FIELD_MAPPING = {
    "title": "Title",
    "body": "Content",
    "status": "Status",
    "notion_id": "Notion_ID",
    "tags": "Notion_Tag",
    "publish_date": "Publish_Date",
}

# Status mapping
STATUS_MAPPING = {
    "Published": "Published",
    "Inbox": "Inbox",
    "#reference": "Inbox",
    "#idea": "Inbox",
    "": None,
}

# Rate limiting
DELAY = 0.25
BATCH_SIZE = 10


def get_github_raw_url(filename: str) -> str:
    """Generate GitHub raw URL for an image file"""
    encoded = filename.replace(" ", "%20")
    return f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_IMAGE_PATH}/{encoded}"


def extract_image_name(filename: str) -> str:
    """Extract clean image name from filename (remove notion_id prefix)"""
    match = re.match(r'^[a-f0-9]{8}_(.+)$', filename)
    return match.group(1) if match else filename


# ============================================================
# STEP 1: Upload images to ASSET
# ============================================================

def upload_images_to_asset(session: requests.Session) -> dict:
    """
    Upload all images to ASSET table.
    Returns mapping: {image_name: (rec_id, att_id)}
    """
    print("=" * 55)
    print("STEP 1: Upload images to ASSET")
    print("=" * 55)
    print()

    mapping = {}

    if not IMAGES_DIR.exists():
        print(f"  Images directory not found: {IMAGES_DIR}")
        return mapping

    image_files = [f for f in IMAGES_DIR.iterdir()
                   if f.is_file() and f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp']]

    print(f"  Found {len(image_files)} images")
    print()

    for i, img_file in enumerate(image_files, 1):
        image_name = extract_image_name(img_file.name)
        caption = image_name.rsplit('.', 1)[0]  # Remove extension for caption
        image_url = get_github_raw_url(img_file.name)

        print(f"  [{i}/{len(image_files)}] {caption}...", end=" ")

        # Create ASSET record
        url = f"https://api.airtable.com/v0/{BASE_ID}/{ASSET_TABLE}"
        payload = {
            "fields": {
                "Caption": caption,
                "Attachment": [{"url": image_url}]
            }
        }

        response = session.post(url, json=payload)

        if response.status_code == 200:
            data = response.json()
            rec_id = data["id"]
            attachments = data.get("fields", {}).get("Attachment", [])
            att_id = attachments[0].get("id", "") if attachments else ""

            if att_id:
                mapping[image_name] = (rec_id, att_id)
                print(f"OK ({rec_id})")
            else:
                print("OK (no att_id)")
        else:
            print(f"FAILED: {response.text[:80]}")

        time.sleep(DELAY)

    print()
    print(f"  Uploaded {len(mapping)} images successfully")
    print()

    return mapping


# ============================================================
# STEP 2: Import documents
# ============================================================

def replace_image_references(content: str, image_mapping: dict) -> str:
    """
    Replace Obsidian image references with Airtable asset links.
    ![[filename.png]] or ![[filename.png|alt]] → ![caption](asset:recID:attID)
    """
    def replace_match(match):
        full_match = match.group(0)
        filename = match.group(1)

        # Handle |alt syntax: ![[file.png|alt text]]
        if '|' in filename:
            filename = filename.split('|')[0]

        # Try exact match first
        if filename in image_mapping:
            rec_id, att_id = image_mapping[filename]
            caption = filename.rsplit('.', 1)[0]
            return f"![{caption}](asset:{rec_id}:{att_id})"

        # Try matching without numbers at end (e.g., "Untitled 1 4.png" -> "Untitled 1.png")
        base_name = re.sub(r'\s+\d+(\.[^.]+)$', r'\1', filename)
        if base_name in image_mapping:
            rec_id, att_id = image_mapping[base_name]
            caption = base_name.rsplit('.', 1)[0]
            return f"![{caption}](asset:{rec_id}:{att_id})"

        # Try fuzzy match - find closest
        filename_base = filename.rsplit('.', 1)[0].lower()
        for img_name, (rec_id, att_id) in image_mapping.items():
            img_base = img_name.rsplit('.', 1)[0].lower()
            # Check if one contains the other
            if filename_base in img_base or img_base in filename_base:
                caption = img_name.rsplit('.', 1)[0]
                return f"![{caption}](asset:{rec_id}:{att_id})"

        # No match found, keep original
        return full_match

    # Pattern for Obsidian image syntax: ![[filename]] or ![[filename|alt]]
    pattern = r'!\[\[([^\]]+)\]\]'
    return re.sub(pattern, replace_match, content)


def get_or_create_project(session: requests.Session) -> str:
    """Get or create the project record"""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{PROJECT_TABLE}"
    params = {"filterByFormula": f"{{Title}}='{PROJECT_NAME}'"}

    response = session.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data.get("records"):
            return data["records"][0]["id"]

    # Create project
    response = session.post(url, json={"fields": {"Title": PROJECT_NAME}})
    if response.status_code == 200:
        return response.json()["id"]

    return None


def import_documents(session: requests.Session, image_mapping: dict):
    """Import documents from content.json, replacing image references"""
    print("=" * 55)
    print("STEP 2: Import documents to DOCUMENT")
    print("=" * 55)
    print()

    if not CONTENT_JSON.exists():
        print(f"  Content file not found: {CONTENT_JSON}")
        return

    with open(CONTENT_JSON, 'r', encoding='utf-8') as f:
        records = json.load(f)

    print(f"  Found {len(records)} documents")
    print()

    # Get/create project
    project_id = get_or_create_project(session)
    if project_id:
        print(f"  Project: {PROJECT_NAME} ({project_id})")
    print()

    # Prepare records
    airtable_records = []
    for record in records:
        fields = {}

        for notion_key, airtable_key in FIELD_MAPPING.items():
            value = record.get(notion_key, "")
            if value:
                value = str(value).strip().strip('"').strip("'")

                # Status mapping
                if notion_key == "status":
                    mapped = STATUS_MAPPING.get(value)
                    if mapped is None:
                        continue
                    value = mapped

                # Replace image references in content
                if notion_key == "body":
                    value = replace_image_references(value, image_mapping)

                fields[airtable_key] = value

        if project_id:
            fields["PROJECT"] = [project_id]

        if fields:
            airtable_records.append({"fields": fields})

    # Upload in batches
    print(f"  Uploading {len(airtable_records)} documents...")
    print()

    success = 0
    failed = 0

    for i in range(0, len(airtable_records), BATCH_SIZE):
        batch = airtable_records[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(airtable_records) + BATCH_SIZE - 1) // BATCH_SIZE

        url = f"https://api.airtable.com/v0/{BASE_ID}/{DOCUMENT_TABLE}"
        response = session.post(url, json={"records": batch})

        if response.status_code == 200:
            success += len(batch)
            print(f"    Batch {batch_num}/{total_batches}: {len(batch)} OK")
        else:
            failed += len(batch)
            print(f"    Batch {batch_num}/{total_batches}: FAILED - {response.text[:100]}")

        time.sleep(DELAY)

    print()
    print(f"  Imported: {success}")
    print(f"  Failed: {failed}")
    print()


# ============================================================
# Main
# ============================================================

def main():
    print()
    print("=" * 55)
    print("Full Notion → Airtable Import")
    print("=" * 55)
    print()

    if not AIRTABLE_API_KEY:
        print("ERROR: AIRTABLE_API_KEY not set")
        print()
        print("Run with:")
        print("  AIRTABLE_API_KEY=your_key python3 full_import.py")
        return

    # Setup session
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    })

    # Step 1: Upload images
    image_mapping = upload_images_to_asset(session)

    # Step 2: Import documents
    import_documents(session, image_mapping)

    print("=" * 55)
    print("DONE!")
    print("=" * 55)


if __name__ == "__main__":
    main()
