"""
OCR Engine per l'estrazione automatica di informazioni dalle locandine
"""
import easyocr
import re
from datetime import datetime
import dateparser
from typing import Dict, Optional, List
import numpy as np


class LocandineOCR:
    def __init__(self):
        """Inizializza il reader OCR per italiano"""
        self.reader = easyocr.Reader(['it', 'en'], gpu=False)
    
    def extract_text(self, image_path: str) -> str:
        """Estrae tutto il testo dall'immagine"""
        result = self.reader.readtext(image_path)
        # Ordina per posizione verticale (y coordinate)
        result_sorted = sorted(result, key=lambda x: x[0][0][1])
        text_lines = [item[1] for item in result_sorted]
        return '\n'.join(text_lines)
    
    def extract_date(self, text: str) -> Optional[datetime]:
        """
        Estrae la data dal testo usando pattern multipli
        Supporta formati come:
        - 15 Febbraio 2026
        - 15/02/2026
        - Sabato 15 Feb
        - 15.02.2026
        """
        # Pattern comuni per date italiane
        patterns = [
            r'\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}',  # 15/02/2026
            r'\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+\d{4}',
            r'\d{1,2}\s+(?:gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic)[a-z]*\.?\s+\d{4}',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(0)
                # Usa dateparser per parsing robusto
                parsed_date = dateparser.parse(
                    date_str, 
                    languages=['it'],
                    settings={'PREFER_DATES_FROM': 'future'}
                )
                if parsed_date:
                    return parsed_date
        
        return None
    
    def extract_time(self, text: str) -> Optional[str]:
        """
        Estrae l'orario dal testo
        Formati supportati: 20:30, 20.30, ore 20:30, h 20:30
        """
        patterns = [
            r'(?:ore|h)?\s*(\d{1,2}[:\.]\d{2})',
            r'(\d{1,2}[:\.]\d{2})\s*(?:ore|h)?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                time_str = match.group(1).replace('.', ':')
                return time_str
        
        return None
    
    def extract_location(self, text: str) -> Optional[str]:
        """
        Estrae il luogo dall'evento
        Cerca pattern comuni come "presso", "a", "c/o", nomi di sale/teatri
        """
        # Pattern per luoghi
        location_patterns = [
            r'(?:presso|@|c/o)\s+([^\n]+)',
            r'(?:teatro|sala|auditorium|centro)\s+([^\n]+)',
            r'(?:via|piazza|corso)\s+([^\n,]+)',
        ]
        
        for pattern in location_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                location = match.group(0).strip()
                # Limita lunghezza
                if len(location) < 100:
                    return location
        
        return None
    
    def extract_title(self, text: str) -> str:
        """
        Estrae il titolo (di solito la prima riga significativa)
        """
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Cerca la prima riga con almeno 3 caratteri che non sia una data o orario
        for line in lines[:5]:  # Controlla solo le prime 5 righe
            # Salta se sembra una data o orario
            if re.search(r'\d{1,2}[\/\.\-]\d{1,2}', line):
                continue
            if re.search(r'\d{1,2}[:\.]\d{2}', line):
                continue
            if len(line) >= 3:
                return line
        
        # Fallback: prima riga
        return lines[0] if lines else "Evento"
        
    def parse_event_text(self, text: str) -> Dict:
        """
        Parser intelligente per estrarre campi granulari e pulire la descrizione
        """
        # 1. Estrai Data
        dt = self.extract_date(text)
        date_str = ""
        if dt:
            date_str = dt.strftime("%d/%m/2026")
        else:
            match = re.search(r'(\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre))', text, re.I)
            if match:
                date_str = f"{match.group(1)} 2026"

        # 2. Estrai Orario
        time_str = self.extract_time(text) or ""

        # 3. Inizializza campi
        location = ""
        venue = ""
        address = ""
        clean_lines = []
        
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        for line in lines:
            lower_line = line.lower()
            
            # Salta righe che contengono solo la data e la città (intestazione)
            if any(m in lower_line for m in ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno']):
                # Se c'è un trattino, quello che segue è probabilmente la location
                parts = re.split(r'[–\-\—]', line)
                if len(parts) > 1:
                    # Se la prima parte ha la data, la seconda è la location
                    if any(m in parts[0].lower() for m in ['gennaio', 'febbraio', 'marzo']):
                        location = parts[1].strip()
                continue
            
            # Estrazione Presso (Venue)
            if 'presso' in lower_line:
                venue_match = re.search(r'presso\s+([^\–\-\|]+)', line, re.I)
                if venue_match:
                    venue = venue_match.group(1).strip()
                    # Rimuovi la parte "presso..." dalla riga per pulire la descrizione
                    line = line.replace(venue_match.group(0), "").strip()
            
            # Estrazione Indirizzo
            if any(kw in lower_line for kw in ['via ', 'vico ', 'piazza ', 'corso ']):
                addr_match = re.search(r'((?:via|vico|piazza|corso)\s+[^\–\-\|]+)', line, re.I)
                if addr_match:
                    address = addr_match.group(1).strip()
                    # Rimuovi l'indirizzo dalla riga
                    line = line.replace(addr_match.group(0), "").strip()

            # Pulizia finale della riga da orari residui
            line = re.sub(r'(?:ore|h)?\s*\d{1,2}[:\.]\d{2}', '', line, flags=re.I).strip()
            line = re.sub(r'[–\-\—\|\/]$', '', line).strip() # Rimuove separatori a fine riga
            
            if len(line) > 3:
                clean_lines.append(line)

        # 4. Costruisci Descrizione e Titolo
        description = " ".join(clean_lines) if clean_lines else "Incontro sulla riforma della Giustizia"
        title = clean_lines[0] if clean_lines else "Nuovo Evento"
        
        return {
            'title': title,
            'date_text': date_str,
            'time': time_str,
            'location': location,
            'venue': venue,
            'address': address,
            'description': description
        }

    def analyze_from_text(self, text: str) -> Dict:
        """
        Analizza un testo pre-estratto usando il nuovo parser intelligente
        """
        parsed = self.parse_event_text(text)
        # Integriamo con i vecchi nomi per compatibilità se necessario, 
        # ma preferiamo il nuovo formato granulare
        return parsed

    def analyze_poster(self, image_path: str) -> Dict:
        """
        Analizza completamente una locandina
        """
        full_text = self.extract_text(image_path)
        parsed = self.parse_event_text(full_text)
        parsed['full_text'] = full_text
        parsed['image_path'] = image_path
        return parsed


if __name__ == "__main__":
    # Test
    ocr = LocandineOCR()
    print("OCR Engine inizializzato correttamente!")
