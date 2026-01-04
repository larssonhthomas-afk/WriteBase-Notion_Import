#!/usr/bin/env python3
"""
Upload images to Airtable ASSET table and link to DOCUMENT

Flow:
1. Upload image to ASSET table (Attachment field)
2. Get record ID (recXXX) and attachment ID (attXXX)
3. Update DOCUMENT Content field with markdown link: ![Caption](asset:recID:attID)

Usage:
    AIRTABLE_API_KEY=your_key python3 upload_images_to_airtable.py

Requirements:
    pip3 install requests
"""

import os
import re
import sys
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

# Image configuration
IMAGES_DIR = Path("./notion_export/images")

# GitHub configuration for public URLs
GITHUB_OWNER = "larssonhthomas-afk"
GITHUB_REPO = "WriteBase-Notion_Import"
GITHUB_BRANCH = "main"
GITHUB_IMAGE_PATH = "notion_export/images"

# Rate limiting
DELAY_BETWEEN_REQUESTS = 0.3  # seconds


def get_github_raw_url(filename: str) -> str:
    """Generate GitHub raw URL for an image file"""
    encoded_filename = filename.replace(" ", "%20")
    return f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_IMAGE_PATH}/{encoded_filename}"


def extract_notion_id_prefix(filename: str) -> str:
    """Extract the first 8 characters (Notion ID prefix) from filename"""
    match = re.match(r'^([a-f0-9]{8})_', filename)
    return match.group(1) if match else None


def get_image_caption(filename: str) -> str:
    """Extract a clean caption from the filename"""
    # Remove notion_id prefix and extension
    match = re.match(r'^[a-f0-9]{8}_(.+)\.[^.]+$', filename)
    if match:
        caption = match.group(1)
        # Clean up underscores and common patterns
        caption = caption.replace("_", " ")
        return caption
    return filename


def get_images_by_notion_id() -> dict:
    """Scan images directory and group by Notion ID prefix"""
    images = defaultdict(list)

    if not IMAGES_DIR.exists():
        print(f"  Images directory not found: {IMAGES_DIR}")
        return images

    for img_file in IMAGES_DIR.iterdir():
        if img_file.is_file() and img_file.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
            prefix = extract_notion_id_prefix(img_file.name)
            if prefix:
                images[prefix].append(img_file.name)

    return images


def check_github_url_accessible(url: str) -> bool:
    """Check if a GitHub raw URL is accessible"""
    try:
        response = requests.head(url, timeout=5)
        return response.status_code == 200
    except:
        return False


def create_asset_record(session: requests.Session, image_url: str, caption: str) -> tuple:
    """
    Create a new record in ASSET table with the image.
    Returns (record_id, attachment_id) or (None, None) on failure.
    """
    url = f"https://api.airtable.com/v0/{BASE_ID}/{ASSET_TABLE}"

    payload = {
        "fields": {
            "Caption": caption,
            "Attachment": [{"url": image_url}],
            "Type": "Image"
        }
    }

    response = session.post(url, json=payload)

    if response.status_code == 200:
        data = response.json()
        record_id = data["id"]
        # Get attachment ID from the response
        attachments = data.get("fields", {}).get("Attachment", [])
        if attachments:
            attachment_id = attachments[0].get("id", "")
            return record_id, attachment_id
        return record_id, None
    else:
        print(f"      ASSET create failed: {response.status_code} - {response.text[:150]}")
        return None, None


def find_document_record(session: requests.Session, notion_id_prefix: str) -> dict:
    """Find DOCUMENT record where Notion_ID starts with the given prefix"""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{DOCUMENT_TABLE}"

    formula = f"SEARCH('{notion_id_prefix}', {{Notion_ID}}) = 1"
    params = {
        "filterByFormula": formula,
        "maxRecords": 1
    }

    response = session.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        if data.get("records"):
            return data["records"][0]
    else:
        print(f"      API error: {response.status_code} - {response.text[:100]}")

    return None


def update_document_content(session: requests.Session, record_id: str, current_content: str, image_links: list) -> bool:
    """
    Update DOCUMENT Content field by appending image links.
    """
    url = f"https://api.airtable.com/v0/{BASE_ID}/{DOCUMENT_TABLE}/{record_id}"

    # Append image links to content
    new_content = current_content
    if new_content and not new_content.endswith("\n"):
        new_content += "\n"
    new_content += "\n".join(image_links)

    payload = {
        "fields": {
            "Content": new_content
        }
    }

    response = session.patch(url, json=payload)

    if response.status_code == 200:
        return True
    else:
        print(f"      Update failed: {response.status_code} - {response.text[:150]}")
        return False


def main():
    print("=" * 55)
    print("Upload Notion Images to Airtable (ASSET + DOCUMENT)")
    print("=" * 55)
    print()

    # Check for required API key
    if not AIRTABLE_API_KEY:
        print("ERROR: AIRTABLE_API_KEY environment variable not set.")
        print()
        print("Run with:")
        print("  AIRTABLE_API_KEY=your_key python3 upload_images_to_airtable.py")
        print()
        return

    # Scan images
    print(f"Scanning images in {IMAGES_DIR}...")
    images_by_id = get_images_by_notion_id()

    total_images = sum(len(imgs) for imgs in images_by_id.values())
    print(f"  Found {total_images} images for {len(images_by_id)} Notion records")
    print()

    if not images_by_id:
        print("No images found to upload.")
        return

    # Check GitHub URL accessibility
    first_image = list(images_by_id.values())[0][0]
    test_url = get_github_raw_url(first_image)
    print(f"Testing GitHub URL accessibility...")

    if not check_github_url_accessible(test_url):
        print()
        print("ERROR: GitHub raw URLs are not accessible.")
        print("Make sure the repository is public and images are pushed to main.")
        return

    print("  GitHub URLs are accessible")
    print()

    # Setup Airtable session
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    })

    # Process each Notion ID
    print("Processing images...")
    print()

    assets_created = 0
    documents_updated = 0
    not_found_count = 0
    error_count = 0

    for notion_id_prefix, image_files in images_by_id.items():
        print(f"  [{notion_id_prefix}] {len(image_files)} image(s)")

        # Find matching DOCUMENT record
        doc_record = find_document_record(session, notion_id_prefix)

        if not doc_record:
            print(f"    No DOCUMENT record found")
            not_found_count += 1
            time.sleep(DELAY_BETWEEN_REQUESTS)
            continue

        doc_id = doc_record["id"]
        doc_title = doc_record.get("fields", {}).get("Title", "Untitled")[:40]
        current_content = doc_record.get("fields", {}).get("Content", "")
        print(f"    Found: {doc_title}...")

        # Process each image for this document
        image_links = []
        for img_filename in image_files:
            caption = get_image_caption(img_filename)
            image_url = get_github_raw_url(img_filename)

            print(f"      Creating ASSET: {caption}...")

            # Create ASSET record
            rec_id, att_id = create_asset_record(session, image_url, caption)
            time.sleep(DELAY_BETWEEN_REQUESTS)

            if rec_id and att_id:
                # Create markdown link
                markdown_link = f"![{caption}](asset:{rec_id}:{att_id})"
                image_links.append(markdown_link)
                assets_created += 1
                print(f"        Created: {rec_id}")
            else:
                error_count += 1

        # Update DOCUMENT with image links
        if image_links:
            print(f"    Updating DOCUMENT with {len(image_links)} image link(s)...")
            if update_document_content(session, doc_id, current_content, image_links):
                documents_updated += 1
                print(f"    Done!")
            else:
                error_count += 1

        time.sleep(DELAY_BETWEEN_REQUESTS)

    # Summary
    print()
    print("=" * 55)
    print("Summary")
    print("=" * 55)
    print(f"  ASSET records created:   {assets_created}")
    print(f"  DOCUMENT records updated: {documents_updated}")
    print(f"  Documents not found:     {not_found_count}")
    print(f"  Errors:                  {error_count}")
    print()

    if not_found_count > 0:
        print("Note: 'Not found' means no DOCUMENT record matched the Notion ID prefix.")


if __name__ == "__main__":
    main()
