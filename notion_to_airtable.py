#!/usr/bin/env python3
"""
Notion to Airtable Converter
Konverterar Notion-export (markdown + CSV) till Airtable-redo format.

Användning:
    python notion_to_airtable.py /path/to/notion/export /path/to/output

Output:
    - output/content.json       - Alla poster i JSON-format för Airtable import
    - output/content.csv        - CSV-version
    - output/images/            - Alla bilder samlade med unika namn
    - output/broken_images.txt  - Lista på bilder som saknas (Obsidian-syntax etc)
"""

import os
import sys
import re
import json
import csv
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict


@dataclass
class ContentItem:
    """En post från Notion-exporten"""
    notion_id: str
    title: str
    status: str = ""
    content_type: str = ""
    ai_keywords: str = ""
    ai_summary: str = ""
    author: str = ""
    link: str = ""
    publish_date: str = ""
    created_time: str = ""
    year: str = ""
    tags: str = ""
    body: str = ""
    images: list = field(default_factory=list)
    broken_images: list = field(default_factory=list)
    child_pages: list = field(default_factory=list)
    source_file: str = ""


def extract_notion_id(filename: str) -> Optional[str]:
    """Extrahera Notion ID från filnamn (sista 32 tecken före .md)"""
    match = re.search(r'([a-f0-9]{32})\.md$', filename)
    return match.group(1) if match else None


def parse_metadata(content: str) -> dict:
    """Extrahera metadata från markdown-filens header"""
    metadata = {}
    lines = content.split('\n')
    
    # Hoppa över titeln (första raden med #)
    start_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('# '):
            start_idx = i + 1
            break
    
    # Parsa key: value par
    for line in lines[start_idx:]:
        line = line.strip()
        if not line:
            continue
        if line.startswith('#') or line.startswith('!') or line.startswith('['):
            break
        
        match = re.match(r'^([A-Za-z\s]+):\s*(.+)$', line)
        if match:
            key = match.group(1).strip().lower().replace(' ', '_')
            value = match.group(2).strip()
            metadata[key] = value
    
    return metadata


def extract_body(content: str) -> str:
    """Extrahera brödtexten efter metadata"""
    lines = content.split('\n')
    body_lines = []
    in_metadata = True
    found_title = False
    
    for line in lines:
        # Hoppa över titeln
        if line.startswith('# ') and not found_title:
            found_title = True
            continue
        
        # Metadata-sektion
        if in_metadata:
            stripped = line.strip()
            # Tom rad eller börjar med något som inte är metadata
            if stripped and not re.match(r'^[A-Za-z\s]+:\s*.+$', stripped):
                in_metadata = False
            elif not stripped:
                continue
            else:
                continue
        
        body_lines.append(line)
    
    return '\n'.join(body_lines).strip()


def find_images(content: str, base_path: Path) -> tuple[list, list]:
    """
    Hitta alla bilder i markdown-innehållet.
    Returnerar (fungerande_bilder, brutna_bilder)
    """
    working_images = []
    broken_images = []
    
    # Markdown-syntax: ![alt](path)
    md_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    for match in re.finditer(md_pattern, content):
        img_path = match.group(2)
        # URL-decode
        img_path = img_path.replace('%20', ' ')
        full_path = base_path / img_path
        
        if full_path.exists():
            working_images.append(str(full_path))
        else:
            broken_images.append(img_path)
    
    # Obsidian-syntax: ![[image.png]]
    obsidian_pattern = r'!\[\[([^\]]+)\]\]'
    for match in re.finditer(obsidian_pattern, content):
        img_name = match.group(1)
        broken_images.append(f"obsidian:{img_name}")
    
    return working_images, broken_images


def find_child_links(content: str) -> list:
    """Hitta länkar till child pages"""
    children = []
    # Notion child page links: [Title](folder/file.md)
    pattern = r'\[([^\]]+)\]\(([^)]+\.md)\)'
    for match in re.finditer(pattern, content):
        children.append({
            'title': match.group(1),
            'path': match.group(2)
        })
    return children


def process_markdown_file(md_path: Path) -> ContentItem:
    """Processa en markdown-fil och returnera ContentItem"""
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    notion_id = extract_notion_id(md_path.name) or md_path.stem
    
    # Titel från första # raden
    title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
    title = title_match.group(1) if title_match else md_path.stem
    
    # Metadata
    meta = parse_metadata(content)
    
    # Body
    body = extract_body(content)
    
    # Bilder
    working_imgs, broken_imgs = find_images(content, md_path.parent)
    
    # Child pages
    children = find_child_links(content)
    
    return ContentItem(
        notion_id=notion_id,
        title=title,
        status=meta.get('status', ''),
        content_type=meta.get('content_type', ''),
        ai_keywords=meta.get('ai_keywords', ''),
        ai_summary=meta.get('ai_summary', ''),
        author=meta.get('author', ''),
        link=meta.get('link', ''),
        publish_date=meta.get('publish_date', ''),
        created_time=meta.get('created_time', ''),
        year=meta.get('year', ''),
        tags=meta.get('tags', ''),
        body=body,
        images=working_imgs,
        broken_images=broken_imgs,
        child_pages=children,
        source_file=str(md_path)
    )


def process_directory(input_dir: Path) -> list[ContentItem]:
    """Processa alla markdown-filer i en katalog"""
    items = []
    
    # Hitta alla .md filer
    for md_file in input_dir.rglob('*.md'):
        # Skippa filer i __MACOSX
        if '__MACOSX' in str(md_file):
            continue
        
        try:
            item = process_markdown_file(md_file)
            items.append(item)
        except Exception as e:
            print(f"⚠️  Kunde inte processa {md_file}: {e}")
    
    return items


def copy_images(items: list[ContentItem], output_dir: Path) -> dict:
    """Kopiera alla bilder till output/images/ med unika namn"""
    images_dir = output_dir / 'images'
    images_dir.mkdir(exist_ok=True)
    
    image_mapping = {}  # original_path -> new_filename
    
    for item in items:
        for img_path in item.images:
            src = Path(img_path)
            if src.exists():
                # Skapa unikt namn: notion_id_originalnamn
                new_name = f"{item.notion_id[:8]}_{src.name}"
                dst = images_dir / new_name
                
                # Hantera duplicerade namn
                counter = 1
                while dst.exists():
                    new_name = f"{item.notion_id[:8]}_{counter}_{src.name}"
                    dst = images_dir / new_name
                    counter += 1
                
                shutil.copy2(src, dst)
                image_mapping[str(src)] = new_name
    
    return image_mapping


def export_json(items: list[ContentItem], output_path: Path):
    """Exportera till JSON"""
    data = []
    for item in items:
        d = asdict(item)
        # Konvertera listor till kommaseparerade strängar för Airtable
        d['images'] = ', '.join([Path(p).name for p in item.images])
        d['broken_images'] = ', '.join(item.broken_images)
        d['child_pages'] = ', '.join([c['title'] for c in item.child_pages])
        data.append(d)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def export_csv(items: list[ContentItem], output_path: Path):
    """Exportera till CSV"""
    if not items:
        return
    
    fieldnames = [
        'notion_id', 'title', 'status', 'content_type', 'ai_keywords',
        'ai_summary', 'author', 'link', 'publish_date', 'created_time',
        'year', 'tags', 'body', 'images', 'broken_images', 'child_pages',
        'source_file'
    ]
    
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for item in items:
            row = asdict(item)
            row['images'] = ', '.join([Path(p).name for p in item.images])
            row['broken_images'] = ', '.join(item.broken_images)
            row['child_pages'] = ', '.join([c['title'] for c in item.child_pages])
            writer.writerow(row)


def export_broken_images(items: list[ContentItem], output_path: Path):
    """Skriv lista på brutna bilder"""
    broken = []
    for item in items:
        for img in item.broken_images:
            broken.append(f"{item.title}: {img}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(broken))


def main():
    if len(sys.argv) < 2:
        print("Användning: python notion_to_airtable.py <notion_export_dir> [output_dir]")
        print("\nExempel:")
        print("  python notion_to_airtable.py ./Content ./output")
        sys.exit(1)
    
    input_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('./notion_output')
    
    if not input_dir.exists():
        print(f"❌ Mappen finns inte: {input_dir}")
        sys.exit(1)
    
    # Skapa output-katalog
    output_dir.mkdir(exist_ok=True)
    
    print(f"📂 Läser från: {input_dir}")
    print(f"📁 Skriver till: {output_dir}")
    print()
    
    # Processa alla filer
    items = process_directory(input_dir)
    print(f"✅ Hittade {len(items)} poster")
    
    # Räkna statistik
    with_images = sum(1 for i in items if i.images)
    with_broken = sum(1 for i in items if i.broken_images)
    total_broken = sum(len(i.broken_images) for i in items)
    
    print(f"   - {with_images} med fungerande bilder")
    print(f"   - {with_broken} med brutna bildreferenser ({total_broken} totalt)")
    print()
    
    # Kopiera bilder
    print("📷 Kopierar bilder...")
    image_mapping = copy_images(items, output_dir)
    print(f"   - {len(image_mapping)} bilder kopierade")
    print()
    
    # Exportera
    print("💾 Exporterar...")
    export_json(items, output_dir / 'content.json')
    print(f"   - {output_dir / 'content.json'}")
    
    export_csv(items, output_dir / 'content.csv')
    print(f"   - {output_dir / 'content.csv'}")
    
    if total_broken > 0:
        export_broken_images(items, output_dir / 'broken_images.txt')
        print(f"   - {output_dir / 'broken_images.txt'}")
    
    print()
    print("✨ Klart!")
    print()
    print("Nästa steg:")
    print("1. Importera content.csv till Airtable")
    print("2. Ladda upp bilder från images/ manuellt eller via script")
    print("3. Kör bild-download-scriptet för att hämta Notion-länkade bilder (kommer senare)")


if __name__ == '__main__':
    main()
