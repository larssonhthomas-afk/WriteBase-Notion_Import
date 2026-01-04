#!/usr/bin/env python3
"""
Upload images to Airtable from Notion export

Matches images to Airtable records using the first 8 characters of the Notion ID.

Usage:
    python3 upload_images_to_airtable.py [--use-imgbb]

Options:
    --use-imgbb    Upload images to imgbb.com first (for private repos)

Requirements:
    pip3 install requests
"""

import os
import re
import sys
import time
import base64
import warnings
import requests
from pathlib import Path
from collections import defaultdict

# Suppress LibreSSL/OpenSSL warning
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

# === CONFIGURATION ===
AIRTABLE_API_KEY = "pat9ReEZaYqZY5m9e.59f37b6fe74a579ccc56879abd34ed14c27c99bd9333226a2f631be03fe2007b"
BASE_ID = "app7rJKwiEkVKn79v"
TABLE_NAME = "DOCUMENT"

# Image configuration
IMAGES_DIR = Path("./notion_export/images")
IMAGE_FIELD = "Images"  # Airtable attachment field name

# imgbb.com API (free image hosting)
# Get your API key at: https://api.imgbb.com/
IMGBB_API_KEY = ""  # Set this or use environment variable IMGBB_API_KEY

# GitHub configuration for public URLs
GITHUB_OWNER = "larssonhthomas-afk"
GITHUB_REPO = "WriteBase-Notion_Import"
GITHUB_BRANCH = "main"
GITHUB_IMAGE_PATH = "notion_export/images"

# Rate limiting
DELAY_BETWEEN_REQUESTS = 0.25  # seconds


def get_github_raw_url(filename: str) -> str:
    """Generate GitHub raw URL for an image file"""
    # URL-encode spaces and special characters
    encoded_filename = filename.replace(" ", "%20")
    return f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{GITHUB_IMAGE_PATH}/{encoded_filename}"


def extract_notion_id_prefix(filename: str) -> str:
    """Extract the first 8 characters (Notion ID prefix) from filename"""
    # Format: {notion_id_8_chars}_{original_name}.ext
    match = re.match(r'^([a-f0-9]{8})_', filename)
    return match.group(1) if match else None


def get_images_by_notion_id() -> dict:
    """
    Scan images directory and group by Notion ID prefix.
    Returns: {notion_id_prefix: [list of image files]}
    """
    images = defaultdict(list)

    if not IMAGES_DIR.exists():
        print(f"Images directory not found: {IMAGES_DIR}")
        return images

    for img_file in IMAGES_DIR.iterdir():
        if img_file.is_file() and img_file.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
            prefix = extract_notion_id_prefix(img_file.name)
            if prefix:
                images[prefix].append(img_file.name)

    return images


def find_airtable_record(session: requests.Session, notion_id_prefix: str) -> dict:
    """
    Find Airtable record where Notion_ID starts with the given prefix.
    Returns the record or None.
    """
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"

    # Use SEARCH function to find records where Notion_ID starts with prefix
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
        print(f"  API error: {response.status_code} - {response.text[:100]}")

    return None


def update_record_with_images(session: requests.Session, record_id: str, image_urls: list) -> bool:
    """
    Update an Airtable record with image attachments.
    """
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}/{record_id}"

    # Format for Airtable attachments
    attachments = [{"url": url} for url in image_urls]

    payload = {
        "fields": {
            IMAGE_FIELD: attachments
        }
    }

    response = session.patch(url, json=payload)

    if response.status_code == 200:
        return True
    else:
        print(f"  Update failed: {response.status_code} - {response.text[:200]}")
        return False


def check_github_url_accessible(url: str) -> bool:
    """Check if a GitHub raw URL is accessible (repo is public)"""
    try:
        response = requests.head(url, timeout=5)
        return response.status_code == 200
    except:
        return False


def upload_to_imgbb(image_path: Path) -> str:
    """
    Upload an image to imgbb.com and return the URL.
    Returns None on failure.
    """
    api_key = IMGBB_API_KEY or os.environ.get("IMGBB_API_KEY", "")

    if not api_key:
        return None

    url = "https://api.imgbb.com/1/upload"

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "key": api_key,
        "image": image_data,
        "name": image_path.stem
    }

    try:
        response = requests.post(url, data=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return data["data"]["url"]
    except Exception as e:
        print(f"    imgbb upload error: {e}")

    return None


def main():
    use_imgbb = "--use-imgbb" in sys.argv

    print("=" * 50)
    print("Upload Notion Images to Airtable")
    print("=" * 50)
    print()

    # Scan images
    print(f"Scanning images in {IMAGES_DIR}...")
    images_by_id = get_images_by_notion_id()

    total_images = sum(len(imgs) for imgs in images_by_id.values())
    print(f"  Found {total_images} images for {len(images_by_id)} Notion records")
    print()

    if not images_by_id:
        print("No images found to upload.")
        return

    # Determine upload method
    if use_imgbb:
        api_key = IMGBB_API_KEY or os.environ.get("IMGBB_API_KEY", "")
        if not api_key:
            print("ERROR: imgbb API key not set.")
            print()
            print("Get a free API key at: https://api.imgbb.com/")
            print("Then either:")
            print("  1. Set IMGBB_API_KEY in this script")
            print("  2. Set environment variable: export IMGBB_API_KEY=your_key")
            return
        print("Using imgbb.com for image hosting")
        print()
    else:
        # Check if GitHub URLs are accessible
        first_image = list(images_by_id.values())[0][0]
        test_url = get_github_raw_url(first_image)
        print(f"Testing GitHub URL accessibility...")
        print(f"  URL: {test_url[:80]}...")

        if not check_github_url_accessible(test_url):
            print()
            print("ERROR: GitHub raw URLs are not accessible.")
            print("This usually means the repository is private.")
            print()
            print("Options:")
            print("  1. Make the repository public, then run this script again")
            print("  2. Use imgbb: python3 upload_images_to_airtable.py --use-imgbb")
            print("     (Requires free API key from https://api.imgbb.com/)")
            print("  3. Upload images manually to Airtable")
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

    success_count = 0
    not_found_count = 0
    error_count = 0
    upload_errors = 0

    for notion_id_prefix, image_files in images_by_id.items():
        print(f"  [{notion_id_prefix}] {len(image_files)} image(s)")

        # Find matching Airtable record
        record = find_airtable_record(session, notion_id_prefix)

        if not record:
            print(f"    No Airtable record found")
            not_found_count += 1
            time.sleep(DELAY_BETWEEN_REQUESTS)
            continue

        record_id = record["id"]
        title = record.get("fields", {}).get("Title", "Untitled")[:40]
        print(f"    Found: {title}...")

        # Generate URLs for all images
        image_urls = []
        for img in image_files:
            if use_imgbb:
                img_path = IMAGES_DIR / img
                print(f"    Uploading {img} to imgbb...")
                url = upload_to_imgbb(img_path)
                if url:
                    image_urls.append(url)
                else:
                    print(f"    Failed to upload {img}")
                    upload_errors += 1
                time.sleep(0.5)  # Rate limit for imgbb
            else:
                image_urls.append(get_github_raw_url(img))

        if not image_urls:
            print(f"    No images to attach")
            error_count += 1
            continue

        # Update record
        if update_record_with_images(session, record_id, image_urls):
            print(f"    Attached {len(image_urls)} image(s) to Airtable")
            success_count += 1
        else:
            error_count += 1

        time.sleep(DELAY_BETWEEN_REQUESTS)

    # Summary
    print()
    print("=" * 50)
    print("Summary")
    print("=" * 50)
    print(f"  Records updated:   {success_count}")
    print(f"  Records not found: {not_found_count}")
    print(f"  Airtable errors:   {error_count}")
    if use_imgbb:
        print(f"  Upload errors:     {upload_errors}")
    print()

    if not_found_count > 0:
        print("Note: 'Not found' means no Airtable record matched the Notion ID prefix.")
        print("This can happen if those records weren't imported or have different IDs.")


if __name__ == "__main__":
    main()
