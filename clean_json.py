#!/usr/bin/env python3
"""
Rensa content.json från extra citattecken i status-fältet
"""

import json
import sys
from pathlib import Path

def clean_value(value):
    """Rensa extra citattecken"""
    if isinstance(value, str):
        # Ta bort ledande/avslutande citattecken och whitespace
        value = value.strip()
        while value.startswith('"') or value.startswith("'"):
            value = value[1:]
        while value.endswith('"') or value.endswith("'"):
            value = value[:-1]
        value = value.strip()
    return value

def main():
    if len(sys.argv) < 2:
        print("Användning: python3 clean_json.py ./output/content.json")
        sys.exit(1)
    
    filepath = Path(sys.argv[1])
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Rensa alla strängar
    for record in data:
        for key in record:
            if isinstance(record[key], str):
                record[key] = clean_value(record[key])
    
    # Skriv tillbaka
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Rensat {len(data)} poster")
    
    # Visa unika statusar
    statuses = sorted(set(r.get('status', '') for r in data if r.get('status')))
    print(f"📋 Statusar: {', '.join(statuses)}")

if __name__ == '__main__':
    main()
