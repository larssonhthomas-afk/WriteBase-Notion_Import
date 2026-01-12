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

# Field mapping: JSON key -> Airtable field name
FIELD_MAPPING = {
    "title": "Title",
    "content": "Content",  # FIXED: was "body"
    "status": "Status",
    "notion_id": "Notion_ID",
    "tags": "Notion_Tag",
    "publish_date": "Publish_Date",
}

# Status mapping
STATUS_MAPPING = {
    "Published": "Published",
    "Inbox": "Inbox",
    "Imported": "Inbox",  # ADDED: Map "Imported" status
    "#reference": "Inbox",
    "#idea": "Inbox",
    "": None,
}

# Rate limiting
DELAY = 0.25
BATCH_SIZE = 10

# Cache for project lookups
PROJECT_CACHE = {}


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
    Replace image references with Airtable asset links.
    Handles both:
    - Obsidian: ![[filename.png]] or ![[filename.png|alt]]
    - Markdown: ![alt](path/filename.png)
    """

    def find_asset_match(filename: str) -> tuple:
        """Try to find matching asset for a filename"""
        # Clean the filename
        filename = filename.strip()

        # Try exact match
        if filename in image_mapping:
            return image_mapping[filename]

        # Try case-insensitive match
        filename_lower = filename.lower()
        for img_name, ids in image_mapping.items():
            if img_name.lower() == filename_lower:
                return ids

        # Try matching just the base filename (without path)
        base_filename = filename.split('/')[-1]
        if base_filename in image_mapping:
            return image_mapping[base_filename]

        for img_name, ids in image_mapping.items():
            if img_name.lower() == base_filename.lower():
                return ids

        # Try fuzzy match - filename contains or is contained
        filename_base = filename.rsplit('.', 1)[0].lower()
        for img_name, ids in image_mapping.items():
            img_base = img_name.rsplit('.', 1)[0].lower()
            if filename_base in img_base or img_base in filename_base:
                return ids

        return None, None

    def replace_obsidian(match):
        """Replace ![[filename]] syntax"""
        filename = match.group(1)

        # Handle |alt syntax: ![[file.png|alt text]]
        if '|' in filename:
            filename = filename.split('|')[0]

        rec_id, att_id = find_asset_match(filename)
        if rec_id and att_id:
            caption = filename.rsplit('.', 1)[0]
            return f"![{caption}](asset:{rec_id}:{att_id})"

        return match.group(0)  # Keep original if no match

    def replace_markdown(match):
        """Replace ![alt](path/filename.png) syntax"""
        alt_text = match.group(1)
        file_path = match.group(2)

        # Extract just the filename from the path
        filename = file_path.split('/')[-1]
        # URL decode spaces
        filename = filename.replace('%20', ' ')

        rec_id, att_id = find_asset_match(filename)
        if rec_id and att_id:
            # Use alt text if available, otherwise use filename without extension
            caption = alt_text if alt_text and not alt_text.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) else filename.rsplit('.', 1)[0]
            return f"![{caption}](asset:{rec_id}:{att_id})"

        return match.group(0)  # Keep original if no match

    # Replace Obsidian syntax: ![[filename]] or ![[filename|alt]]
    content = re.sub(r'!\[\[([^\]]+)\]\]', replace_obsidian, content)

    # Replace Markdown syntax: ![alt](path/to/image.png)
    # But NOT asset: links (already converted)
    content = re.sub(r'!\[([^\]]*)\]\((?!asset:)([^)]+\.(?:png|jpg|jpeg|gif|webp))\)', replace_markdown, content, flags=re.IGNORECASE)

    return content


def get_project_id(session: requests.Session, project_name: str) -> str:
    """Get project ID by name, with caching"""
    # Check cache first
    if project_name in PROJECT_CACHE:
        return PROJECT_CACHE[project_name]
    
    # Query Airtable for the project
    url = f"https://api.airtable.com/v0/{BASE_ID}/{PROJECT_TABLE}"
    params = {"filterByFormula": f"{{Title}}='{project_name}'"}

    response = session.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data.get("records"):
            project_id = data["records"][0]["id"]
            PROJECT_CACHE[project_name] = project_id
            return project_id
    
    # Project not found
    print(f"    WARNING: Project '{project_name}' not found in Airtable")
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

    # Prepare records
    airtable_records = []
    skipped = 0
    
    for record in records:
        fields = {}

        for json_key, airtable_key in FIELD_MAPPING.items():
            value = record.get(json_key, "")
            if value:
                value = str(value).strip().strip('"').strip("'")

                # Status mapping
                if json_key == "status":
                    mapped = STATUS_MAPPING.get(value)
                    if mapped is None:
                        continue
                    value = mapped

                # Replace image references in content
                if json_key == "content":
                    value = replace_image_references(value, image_mapping)

                fields[airtable_key] = value

        # Set project name as text field
        project_name = record.get("project", "")
        if project_name:
            fields["Import_Project"] = project_name

        if fields and fields.get("Title"):  # Must have at least a title
            airtable_records.append({"fields": fields})
        else:
            skipped += 1

    # Upload in batches
    print(f"  Uploading {len(airtable_records)} documents (skipped {skipped})...")
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
