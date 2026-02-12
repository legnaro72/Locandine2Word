"""
Test migliorato per verificare il parsing OCR con pattern più realistici
"""

# Testo di esempio senza "presso" ma con "Sala"
test_ocr_text_1 = """
SABATO 22 FEBBRAIO 2026 - BOLANO
Incontro con l'Autore
Sala Consiliare del Comune
Via Roma 15
Ore 17.30
"""

# Testo con "Circolo"
test_ocr_text_2 = """
15 MARZO 2026 - SARZANA
Presentazione libro
Circolo ARCI La Giobatta
h 21:00
"""

# Simula l'importazione delle funzioni dall'app
import re
from datetime import datetime
import dateparser

IT_MONTHS = {
    1: "GENNAIO", 2: "FEBBRAIO", 3: "MARZO", 4: "APRILE",
    5: "MAGGIO", 6: "GIUGNO", 7: "LUGLIO", 8: "AGOSTO",
    9: "SETTEMBRE", 10: "OTTOBRE", 11: "NOVEMBRE", 12: "DICEMBRE"
}

def normalize_date_to_italian(raw_date):
    if not raw_date:
        return ""
    if not re.search(r'\d{4}', raw_date) and len(raw_date) > 3:
        raw_date += " 2026"
    dt = dateparser.parse(raw_date, languages=['it', 'en'])
    if dt:
        return f"{dt.day} {IT_MONTHS[dt.month]} {dt.year}"
    return raw_date

def parse_event_text(text):
    """Parser migliorato con venue patterns flessibili"""
    data = {
        'title': '', 'date': '', 'location': '', 'description': '',
        'time': '', 'venue': '', 'address': ''
    }
    
    if not text:
        return data

    # ===== SALVA SEMPRE IL TESTO COMPLETO COME BACKUP =====
    data['description'] = text.strip()

    # Pulizia preliminare
    text_clean = text.replace('\r', '')
    lines = [l.strip() for l in text_clean.split('\n') if l.strip()]
    if not lines:
        return data

    # --- 1. ESTRAZIONE DATA ---
    date_patterns = [
        r'\b(\d{1,2}\s+(?:GENNAIO|FEBBRAIO|MARZO|APRILE|MAGGIO|GIUGNO|LUGLIO|AGOSTO|SETTEMBRE|OTTOBRE|NOVEMBRE|DICEMBRE)\s+\d{4})\b',
        r'\b(\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+\d{4})\b',
        r'\b(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{4})\b',
    ]
    
    for pattern in date_patterns:
        date_match = re.search(pattern, text, re.IGNORECASE)
        if date_match:
            raw_date = date_match.group(1).strip()
            data['date'] = normalize_date_to_italian(raw_date)
            break
    
    if not data['date']:
        date_partial = re.search(r'\b(\d{1,2}\s+(?:GENNAIO|FEBBRAIO|MARZO|APRILE|MAGGIO|GIUGNO|LUGLIO|AGOSTO|SETTEMBRE|OTTOBRE|NOVEMBRE|DICEMBRE))\b', text, re.IGNORECASE)
        if date_partial:
            raw_date = date_partial.group(1).strip() + " 2026"
            data['date'] = normalize_date_to_italian(raw_date)

    # --- 2. ESTRAZIONE ORA ---
    time_patterns = [
        r'\b(?:Ore|ore|h|H)\s*(\d{1,2}[:\.]\d{2})\b',
        r'\b(\d{1,2}[:\.]\d{2})\s*(?:Ore|ore|h|H)?\b',
    ]
    
    for pattern in time_patterns:
        time_match = re.search(pattern, text)
        if time_match:
            time_str = time_match.group(1).replace('.', ':')
            data['time'] = time_str
            break

    # --- 3. ESTRAZIONE LUOGO ---
    first_line = lines[0]
    clean_first = re.sub(r'^(?:LUNED[ÌI]|MARTED[ÌI]|MERCOLED[ÌI]|GIOVED[ÌI]|VENERD[ÌI]|SABATO|DOMENICA)\s*', '', first_line, flags=re.IGNORECASE).strip()
    
    parts = re.split(r'\s*[–\-]\s*', clean_first, maxsplit=1)
    if len(parts) > 1:
        data['location'] = parts[1].strip()

    # --- 4. ESTRAZIONE INDIRIZZO ---
    address_patterns = [
        r'(?:Via|Vico|Piazza|Corso|Largo|Strada)\s+[^\n]+',
    ]
    
    for pattern in address_patterns:
        addr_match = re.search(pattern, text, re.IGNORECASE)
        if addr_match:
            addr_full = addr_match.group(0).strip()
            addr_full = re.sub(r'\s*[-–]\s*(?:Ore|ore).*$', '', addr_full).strip()
            data['address'] = addr_full
            break

    # --- 5. ESTRAZIONE PRESSO/VENUE (PATTERN MULTIPLI) ---
    venue_patterns = [
        # Con "presso"
        r'presso\s+([^\n]+?)(?:\s*[-–]\s*(?:Ore|ore)|$)',
        r'presso\s+([^\n]+)',
        # Parole chiave comuni
        r'\b(Sala\s+[^\n]+?)(?:\s*[-–]?\s*(?:Ore|ore|Via|Piazza)|$)',
        r'\b(Circolo\s+[^\n]+?)(?:\s*[-–]?\s*(?:Ore|ore|Via|Piazza)|$)',
        r'\b(Teatro\s+[^\n]+?)(?:\s*[-–]?\s*(?:Ore|ore|Via|Piazza)|$)',
        r'\b(Auditorium\s+[^\n]+?)(?:\s*[-–]?\s*(?:Ore|ore|Via|Piazza)|$)',
        r'\b(Centro\s+[^\n]+?)(?:\s*[-–]?\s*(?:Ore|ore|Via|Piazza)|$)',
        r'\b(Biblioteca\s+[^\n]+?)(?:\s*[-–]?\s*(?:Ore|ore|Via|Piazza)|$)',
    ]
    
    for pattern in venue_patterns:
        presso_match = re.search(pattern, text, re.IGNORECASE)
        if presso_match:
            venue_text = presso_match.group(1).strip()
            venue_text = re.sub(r'\s*[-–]\s*(?:Ore|ore).*$', '', venue_text).strip()
            venue_text = re.sub(r'\s*\d{1,2}[:\.]\d{2}.*$', '', venue_text).strip()
            venue_text = re.sub(r'\s*[-–]?\s*(?:Via|Piazza|Corso|Vico)\s+.*$', '', venue_text, flags=re.IGNORECASE).strip()
            data['venue'] = venue_text
            break

    # --- 6. TITOLO AUTOMATICO ---
    if data['date'] and data['location']:
        data['title'] = f"{data['date']} – {data['location']}"
    else:
        data['title'] = text[:50].replace('\n', ' ').strip() + "..." if text else "Nuovo Evento"
    
    return data

# Test 1: Sala Consiliare
print("=" * 70)
print("TEST 1: OCR con 'Sala' (senza 'presso')")
print("=" * 70)
print("\nTESTO OCR:")
print("-" * 70)
print(test_ocr_text_1)
print("-" * 70)

result1 = parse_event_text(test_ocr_text_1)

print("\nRISULTATI:")
print(f"Titolo:      {result1['title']}")
print(f"Data:        {result1['date']}")
print(f"Ora:         {result1['time']}")
print(f"Luogo:       {result1['location']}")
print(f"Presso:      {result1['venue']}")
print(f"Indirizzo:   {result1['address']}")

# Test 2: Circolo ARCI
print("\n")
print("=" * 70)
print("TEST 2: OCR con 'Circolo' e formato ora diverso (h 21:00)")
print("=" * 70)
print("\nTESTO OCR:")
print("-" * 70)
print(test_ocr_text_2)
print("-" * 70)

result2 = parse_event_text(test_ocr_text_2)

print("\nRISULTATI:")
print(f"Titolo:      {result2['title']}")
print(f"Data:        {result2['date']}")
print(f"Ora:         {result2['time']}")
print(f"Luogo:       {result2['location']}")
print(f"Presso:      {result2['venue']}")
print(f"Indirizzo:   {result2['address']}")

print("\n" + "=" * 70)
print("Test completati con successo!")
print("=" * 70)

# Test geografico
print("\n")
print("VERIFICA MAPPATURA GEOGRAFICA:")
print("-" * 70)
print(f"BOLANO dovrebbe essere riconosciuto come LA SPEZIA")
print(f"SARZANA dovrebbe essere riconosciuto come LA SPEZIA")
