# Notion → Airtable Import

Import Notion exports to Airtable with images.

## Overview

This process takes a Notion export and imports it to Airtable:

1. **Convert** Notion export → JSON with `notion_to_airtable.py`
2. **Upload images** → ASSET table
3. **Import documents** → DOCUMENT table (with image links replaced)

## Prerequisites

* Python 3.9+
* `requests` library: `pip3 install requests`
* Airtable API key from https://airtable.com/create/tokens
* GitHub account (for image hosting)

## Airtable Structure

### ASSET table

| Field | Type |
| --- | --- |
| Caption | Text |
| Attachment | Attachment |

### DOCUMENT table

| Field | Type | Required |
| --- | --- | --- |
| Title | Text | ✓ |
| Content | Long text | ✓ |
| Status | Single select | |
| Notion_ID | Text | |
| Notion_Tag | Text | |
| Publish_Date | Date | |
| Import_Project | Text | ✓ **NEW** |

> **Note:** `Import_Project` is a simple text field that stores the project/folder name from Notion. You can later link these to a PROJECT table manually if needed.

### PROJECT table (optional)

| Field | Type |
| --- | --- |
| Title | Text |

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/larssonhthomas-afk/WriteBase-Notion_Import.git
cd WriteBase-Notion_Import

# 2. Create exports folder and add your Notion zip files
mkdir exports
# Copy your ExportBlock-xxx.zip files to exports/

# 3. Unzip all exports
mkdir temp_export
cd exports
for zip in *.zip; do unzip -o "$zip" -d ../temp_export/; done
cd ..

# 4. Unzip any nested zips
find temp_export -name "*.zip" -exec unzip -q -o {} -d temp_export \;

# 5. Convert to JSON (creates notion_export/ folder)
python3 notion_to_airtable.py temp_export ./notion_export

# 6. Push images to GitHub (required for image URLs)
git add notion_export/
git commit -m "Add Notion export"
git push origin main

# 7. Run the import
AIRTABLE_API_KEY=your_api_key python3 full_import.py

# 8. Clean up
rm -rf temp_export
```

## Step-by-Step Guide

### 1. Export from Notion

1. Open Notion
2. Go to **Settings & Members** → **Settings**
3. Scroll down to **Export all workspace content**
4. Select **Markdown & CSV** (Include Content "Everything", Include Subpages, Create Folders for Subpages)
5. Download the ZIP file(s)

### 2. Prepare the Export

1. Place ZIP files in `exports/` folder
2. Unzip all files to `temp_export/`
3. Run the conversion script:

```bash
python3 notion_to_airtable.py temp_export ./notion_export
```

This creates:

* `notion_export/content.json` - All documents with project mapping
* `notion_export/content.csv` - Backup in CSV format
* `notion_export/projects.json` - List of projects found
* `notion_export/images/` - All images with Notion ID prefix
* `notion_export/broken_images.txt` - Missing images (if any)

### 3. Project Mapping

The script maps folders to projects:

| Folder Structure | Import_Project |
| --- | --- |
| `Private & Shared/Matter/...` | Matter |
| `Private & Shared/Politik/...` | Politik |
| `Private & Shared/Projekt (egna)/Forefront/...` | Forefront |
| `Private & Shared/Projekt (egna)/Social Selling/...` | Social Selling |
| Root level files | Inbox |

### 4. Upload to GitHub

Images must be accessible via public URLs:

```bash
git add notion_export/
git commit -m "Add Notion export"
git push origin main
```

**Important:** The repository must be **public** for image links to work.

### 5. Configure the Script

Check `full_import.py` and verify these values:

```python
BASE_ID = "app7rJKwiEkVKn79v"  # Your Airtable Base ID
GITHUB_OWNER = "larssonhthomas-afk"
GITHUB_REPO = "WriteBase-Notion_Import"
GITHUB_BRANCH = "main"
```

### 6. Create Required Fields in Airtable

Make sure your DOCUMENT table has these fields:

- **Title** (Text)
- **Content** (Long text)
- **Import_Project** (Text) ← **Required for import**
- **Status** (Single select) - Optional
- **Notion_ID** (Text) - Optional
- **Notion_Tag** (Text) - Optional

### 7. Run the Import

```bash
AIRTABLE_API_KEY=your_api_key python3 full_import.py
```

The script will:

1. Upload all images to the ASSET table
2. Create a mapping between image names and Airtable IDs
3. Import all documents to the DOCUMENT table
4. Replace image links with `![caption](asset:recID:attID)` format
5. Set `Import_Project` to the folder/project name

### 8. Verify

Check in Airtable that:

* ASSET table contains all images
* DOCUMENT table contains all documents with content
* `Import_Project` field shows the correct project names
* Image links in the Content field have the format `![caption](asset:recXXX:attXXX)`

## Troubleshooting

### "Project 'X' not found in Airtable"

This warning appeared in older versions. The updated script now uses `Import_Project` (text field) instead of linked records, so this warning should not appear.

### "Content file not found: notion_export/content.json"

Make sure you ran `notion_to_airtable.py` first and the output folder is `notion_export/` (not `notion_output/`).

### "GitHub URLs are not accessible"

* Verify the repository is public
* Verify images are pushed to the main branch
* Wait a few minutes if you just made the repository public

### "AIRTABLE_API_KEY not set"

Set the API key before the command:

```bash
AIRTABLE_API_KEY=patXXXXX python3 full_import.py
```

### Documents imported without content

Make sure the `Content` field exists in your DOCUMENT table and is a **Long text** field.

### Images not being replaced

* Verify image names in `notion_export/images/` match references in content.json
* The script attempts both exact and fuzzy (partial) matching

## File Structure

```
WriteBase-Notion_Import/
├── notion_to_airtable.py    # Convert Notion export to JSON
├── full_import.py           # Main script - import images + documents
├── import_to_airtable.py    # Documents only (without images)
├── upload_images_to_airtable.py  # Images only
├── README.md
│
├── exports/                 # Your Notion ZIP files
│   └── ExportBlock-xxx.zip
│
├── temp_export/             # Temporary unzipped files
│
└── notion_export/           # Output from conversion
    ├── content.json         # Documents in JSON format
    ├── content.csv          # Documents in CSV format
    ├── projects.json        # List of projects
    ├── images/              # Images with Notion ID prefix
    └── broken_images.txt    # Missing images
```

## Field Mapping

| JSON Field | Airtable Field |
| --- | --- |
| title | Title |
| content | Content |
| status | Status |
| notion_id | Notion_ID |
| tags | Notion_Tag |
| publish_date | Publish_Date |
| project | Import_Project |

## Image Link Format

The script replaces these formats:

| Original format | Replaced with |
| --- | --- |
| `![[image.png]]` | `![image](asset:recXXX:attXXX)` |
| `![[image.png\|alt]]` | `![image](asset:recXXX:attXXX)` |
| `![alt](path/image.png)` | `![alt](asset:recXXX:attXXX)` |

## Security

**Important:** Never put API keys in the code. Always use environment variables:

```bash
# Set temporarily (only for this command)
AIRTABLE_API_KEY=your_key python3 full_import.py

# Or export for the session
export AIRTABLE_API_KEY=your_key
python3 full_import.py
```

## Changelog

### v2.0 (2026-01-12)

- **Fixed:** `content` field mapping (was incorrectly looking for `body`)
- **Changed:** Uses `Import_Project` text field instead of linked PROJECT records
- **Added:** Project mapping from folder structure
- **Added:** `projects.json` output file
- **Improved:** Better handling of nested Notion exports
