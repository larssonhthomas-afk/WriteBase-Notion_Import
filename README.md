# Notion → Airtable Import

Import Notion exports to Airtable with images.

## Overview

This process takes a Notion export and imports it to Airtable:
1. **Images** → ASSET table
2. **Documents** → DOCUMENT table (with image links replaced)

## Prerequisites

- Python 3.9+
- `requests` library: `pip3 install requests`
- Airtable API key from https://airtable.com/create/tokens
- GitHub account (for image hosting)

## Airtable Structure

### ASSET table
| Field | Type |
|-------|------|
| Caption | Text |
| Attachment | Attachment |
| Type | Formula (computed) |

### DOCUMENT table
| Field | Type |
|-------|------|
| Title | Text |
| Content | Long text |
| Status | Single select |
| Notion_ID | Text |
| Notion_Tag | Text |
| Publish_Date | Text |
| PROJECT | Link to PROJECT |

### PROJECT table
| Field | Type |
|-------|------|
| Title | Text |

## Step-by-Step Guide

### 1. Export from Notion

1. Open Notion
2. Go to **Settings & Members** → **Settings**
3. Scroll down to **Export all workspace content**
4. Select **Markdown & CSV**
5. Download the ZIP file

### 2. Prepare the Export

1. Unzip the ZIP file
2. Run `notion_to_airtable.py` to convert:

```bash
python3 notion_to_airtable.py /path/to/notion/export ./notion_export
```

This creates:
- `notion_export/content.json` - All documents
- `notion_export/images/` - All images with Notion ID prefix
- `notion_export/broken_images.txt` - Missing images

### 3. Upload to GitHub

Images must be accessible via public URLs:

```bash
git add notion_export/
git commit -m "Add Notion export"
git push origin main
```

**Important:** The repository must be **public** for image links to work.

### 4. Configure the Script

Open `full_import.py` and verify these values:

```python
BASE_ID = "app7rJKwiEkVKn79v"  # Your Airtable Base ID
GITHUB_OWNER = "your-username"
GITHUB_REPO = "your-repo"
GITHUB_BRANCH = "main"
```

### 5. Run the Import

```bash
AIRTABLE_API_KEY=your_api_key python3 full_import.py
```

The script will:
1. Upload all images to the ASSET table
2. Create a mapping between image names and Airtable IDs
3. Import all documents to the DOCUMENT table
4. Replace image links with `![caption](asset:recID:attID)` format

### 6. Verify

Check in Airtable that:
- ASSET table contains all images
- DOCUMENT table contains all documents
- Image links in the Content field have the format `![caption](asset:recXXX:attXXX)`

## Troubleshooting

### "GitHub URLs are not accessible"
- Verify the repository is public
- Verify images are pushed to the main branch
- Wait a few minutes if you just made the repository public

### "AIRTABLE_API_KEY not set"
Set the API key before the command:
```bash
AIRTABLE_API_KEY=patXXXXX python3 full_import.py
```

### "Field cannot accept value because it's computed"
The field is a formula in Airtable and cannot be written to. Remove that field from the script.

### Images not being replaced
- Verify image names in `notion_export/images/` match references in content.json
- The script attempts both exact and fuzzy (partial) matching

## File Structure

```
├── notion_to_airtable.py    # Convert Notion export to JSON
├── full_import.py           # Main script - import images + documents
├── import_to_airtable.py    # Documents only (without images)
├── upload_images_to_airtable.py  # Images only
└── notion_export/
    ├── content.json         # Documents in JSON format
    ├── content.csv          # Documents in CSV format
    ├── images/              # Images with Notion ID prefix
    └── broken_images.txt    # Missing images
```

## Image Link Format

The script replaces these formats:

| Original format | Replaced with |
|-----------------|---------------|
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
