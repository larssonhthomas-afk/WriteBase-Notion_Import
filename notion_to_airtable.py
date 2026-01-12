#!/usr/bin/env python3
"""
Notion Export to Airtable Import Script (v2)

Converts Notion markdown exports to JSON format for Airtable import.
Maps subfolders to PROJECT names.

Usage:
    python3 notion_to_airtable.py /path/to/notion/export ./output_folder
"""

import os
import sys
import json
import re
import shutil
from pathlib import Path
from datetime import datetime

def extract_title_from_filename(filename):
    """
    Remove Notion ID from filename to get clean title.
    Example: "My Document 281fc2711b808049b837d239a4b31baf.md" -> "My Document"
    """
    # Remove .md extension
    name = filename.replace('.md', '')
    
    # Remove Notion ID (32 char hex at the end)
    # Pattern: space + 32 hex characters at end
    pattern = r'\s+[a-f0-9]{32}$'
    clean_name = re.sub(pattern, '', name)
    
    return clean_name.strip()

def extract_notion_id(filename):
    """Extract the 32-char Notion ID from filename."""
    pattern = r'([a-f0-9]{32})'
    match = re.search(pattern, filename)
    return match.group(1) if match else None

def get_project_from_path(file_path, base_path):
    """
    Determine project name from folder structure.
    
    Structure:
    - Private & Shared/Matter/... -> "Matter"
    - Private & Shared/Politik/... -> "Politik"
    - Private & Shared/Projekt (egna)/Forefront/... -> "Forefront"
    - Private & Shared/Projekt (egna)/Social Selling/... -> "Social Selling"
    - Root level .md files -> "Inbox"
    """
    rel_path = os.path.relpath(file_path, base_path)
    parts = Path(rel_path).parts
    
    # Skip "Private & Shared" if present
    if parts and parts[0] == "Private & Shared":
        parts = parts[1:]
    
    if not parts:
        return "Inbox"
    
    # If only one part (the file itself), it's a root-level file
    if len(parts) == 1:
        return "Inbox"
    
    # If first folder is "Projekt (egna)", use the subfolder as project
    if parts[0] == "Projekt (egna)":
        if len(parts) > 2:  # Has subfolder
            return clean_project_name(parts[1])
        else:
            return "Projekt"
    
    # Otherwise use the first folder as project (clean it)
    return clean_project_name(parts[0])

def clean_project_name(name):
    """Remove Notion ID from folder/project name."""
    # Remove Notion ID (32 char hex at the end)
    pattern = r'\s+[a-f0-9]{32}$'
    clean = re.sub(pattern, '', name)
    return clean.strip()

def find_images_in_content(content):
    """Find all image references in markdown content."""
    images = []
    
    # Pattern 1: ![alt](path)
    pattern1 = r'!\[([^\]]*)\]\(([^)]+)\)'
    for match in re.finditer(pattern1, content):
        alt, path = match.groups()
        if not path.startswith('http'):
            images.append({'alt': alt, 'path': path, 'full_match': match.group(0)})
    
    # Pattern 2: ![[filename]] or ![[filename|alt]]
    pattern2 = r'!\[\[([^\]|]+)(?:\|([^\]]*))?\]\]'
    for match in re.finditer(pattern2, content):
        filename, alt = match.groups()
        images.append({'alt': alt or filename, 'path': filename, 'full_match': match.group(0)})
    
    return images

def process_notion_export(input_dir, output_dir):
    """Process all markdown files from Notion export."""
    
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    # Create output directories
    output_path.mkdir(parents=True, exist_ok=True)
    images_dir = output_path / 'images'
    images_dir.mkdir(exist_ok=True)
    
    documents = []
    all_images = []
    broken_images = []
    projects_found = set()
    
    # Find all markdown files
    md_files = list(input_path.rglob('*.md'))
    print(f"Found {len(md_files)} markdown files")
    
    for md_file in md_files:
        # Skip if in __MACOSX folder
        if '__MACOSX' in str(md_file):
            continue
            
        # Read content
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {md_file}: {e}")
            continue
        
        # Extract metadata
        filename = md_file.name
        title = extract_title_from_filename(filename)
        notion_id = extract_notion_id(filename)
        project = get_project_from_path(md_file, input_path)
        projects_found.add(project)
        
        # Find images in content
        images = find_images_in_content(content)
        
        # Process images
        for img in images:
            img_path = md_file.parent / img['path']
            if img_path.exists():
                # Copy image to output with notion_id prefix
                new_filename = f"{notion_id}_{Path(img['path']).name}" if notion_id else Path(img['path']).name
                new_path = images_dir / new_filename
                try:
                    shutil.copy2(img_path, new_path)
                    all_images.append({
                        'original': img['path'],
                        'new_name': new_filename,
                        'alt': img['alt'],
                        'document_notion_id': notion_id
                    })
                    # Update content with new image reference
                    content = content.replace(img['full_match'], f"![{img['alt']}]({new_filename})")
                except Exception as e:
                    print(f"Error copying image {img_path}: {e}")
                    broken_images.append(str(img_path))
            else:
                broken_images.append(str(img_path))
        
        # Create document record
        doc = {
            'title': title,
            'content': content,
            'notion_id': notion_id,
            'project': project,
            'source_file': str(md_file.relative_to(input_path)),
            'status': 'Imported'
        }
        documents.append(doc)
    
    # Write outputs
    # JSON (main output)
    with open(output_path / 'content.json', 'w', encoding='utf-8') as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)
    
    # CSV (backup)
    import csv
    with open(output_path / 'content.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['title', 'content', 'notion_id', 'project', 'source_file', 'status'])
        writer.writeheader()
        writer.writerows(documents)
    
    # Projects list
    with open(output_path / 'projects.json', 'w', encoding='utf-8') as f:
        json.dump(sorted(list(projects_found)), f, ensure_ascii=False, indent=2)
    
    # Broken images log
    if broken_images:
        with open(output_path / 'broken_images.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(broken_images))
    
    # Summary
    print(f"\n{'='*50}")
    print(f"SUMMARY")
    print(f"{'='*50}")
    print(f"Documents processed: {len(documents)}")
    print(f"Projects found: {len(projects_found)}")
    for p in sorted(projects_found):
        count = len([d for d in documents if d['project'] == p])
        print(f"  - {p}: {count} docs")
    print(f"Images copied: {len(all_images)}")
    print(f"Broken image references: {len(broken_images)}")
    print(f"\nOutput written to: {output_path}")
    print(f"  - content.json")
    print(f"  - content.csv")
    print(f"  - projects.json")
    print(f"  - images/")
    if broken_images:
        print(f"  - broken_images.txt")

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 notion_to_airtable.py <input_dir> <output_dir>")
        print("\nExample:")
        print("  python3 notion_to_airtable.py ~/Downloads/notion_export ./notion_output")
        sys.exit(1)
    
    input_dir = sys.argv[1]
    output_dir = sys.argv[2]
    
    if not os.path.exists(input_dir):
        print(f"Error: Input directory does not exist: {input_dir}")
        sys.exit(1)
    
    process_notion_export(input_dir, output_dir)

if __name__ == '__main__':
    main()
