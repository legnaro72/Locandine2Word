"""
Generatore di documenti Word con locandine ordinate cronologicamente
"""
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from datetime import datetime
import json
import os
import dateparser
from typing import List, Dict


class WordGenerator:
    def __init__(self, template_path: str = None):
        """
        Inizializza il generatore
        Se template_path è None, crea un documento nuovo
        """
        if template_path and os.path.exists(template_path):
            self.doc = Document(template_path)
        else:
            self.doc = Document()
            self._setup_default_styles()
    
    def _setup_default_styles(self):
        """Configura gli stili di default del documento"""
        # Imposta margini
        sections = self.doc.sections
        for section in sections:
            section.top_margin = Inches(0.5)
            section.bottom_margin = Inches(0.5)
            section.left_margin = Inches(0.75)
            section.right_margin = Inches(0.75)
    
    def add_event_entry(self, event_data: Dict, image_path: str, mode: str = "standard", show_borders: bool = True):
        """
        Aggiunge una singola entry evento al documento
        Formato: Tabella 1x2 (immagine a sinistra, testo o immagine a destra)
        """
        # Crea tabella 1 riga x 2 colonne
        table = self.doc.add_table(rows=1, cols=2)
        
        # Gestione bordi
        if show_borders:
            table.style = 'Table Grid'
        else:
            # Rimuove bordi se non è settato 'Table Grid' di default, 
            # o usa uno stile senza bordi. 
            # In python-docx 'Normal Table' di solito non ha bordi visibili.
            table.style = 'Normal Table'
        
        # Imposta larghezza colonne (40% immagine, 60% testo/immagine)
        # Nota: In modalità minimal, potremmo volerle uguali, ma manteniamo la struttura per ora
        table.columns[0].width = Inches(3.25)
        table.columns[1].width = Inches(3.25)
        
        # Cella Sinistra (Sempre Immagine)
        left_cell = table.rows[0].cells[0]
        self._insert_image(left_cell, image_path)

        # Cella Destra (Testo o Immagine)
        right_cell = table.rows[0].cells[1]
        
        if mode == "minimal":
            # In modalità minimal, anche la colonna destra contiene l'immagine
            self._insert_image(right_cell, image_path)
        else:
            # Modalità standard: inserisce il testo descrittivo
            self._insert_text_details(right_cell, event_data)
        
        # Aggiungi spazio dopo la tabella
        self.doc.add_paragraph()

    def _insert_image(self, cell, image_path):
        """Helper per inserire un'immagine in una cella"""
        if os.path.exists(image_path):
            paragraph = cell.paragraphs[0]
            run = paragraph.add_run()
            # Adatta larghezza per stare nella cella
            run.add_picture(image_path, width=Inches(2.5))
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def _insert_text_details(self, cell, event_data):
        """Helper per inserire i dettagli testuali nell cella"""
        text_paragraph = cell.paragraphs[0]
        
        # Titolo evento (grassetto, più grande)
        title_run = text_paragraph.add_run(event_data.get('title', 'Evento') + '\n')
        title_run.bold = True
        title_run.font.size = Pt(14)
        title_run.font.color.rgb = RGBColor(0, 51, 102)
        
        # Data
        if event_data.get('date'):
            # Prova a parsare per formattazione pulita, altrimenti lascia raw
            date_str = event_data['date']
            try:
                dt = dateparser.parse(date_str, languages=['it'])
                if dt:
                    date_formatted = dt.strftime('%d %B %Y')
                else:
                    date_formatted = date_str
            except:
                date_formatted = date_str
            
            date_run = text_paragraph.add_run(f"📅 Data: {date_formatted}\n")
            date_run.font.size = Pt(11)
        
        # Orario
        if event_data.get('time'):
            time_run = text_paragraph.add_run(f"🕐 Orario: {event_data['time']}\n")
            time_run.font.size = Pt(11)
        
        # Luogo
        if event_data.get('location'):
            location_run = text_paragraph.add_run(f"📍 Luogo: {event_data['location']}\n")
            location_run.font.size = Pt(11)

        # Presso
        if event_data.get('venue'):
            venue_run = text_paragraph.add_run(f"🏛️ Presso: {event_data['venue']}\n")
            venue_run.font.size = Pt(11)

        # Indirizzo
        if event_data.get('address'):
            address_run = text_paragraph.add_run(f"📍 Indirizzo: {event_data['address']}\n")
            address_run.font.size = Pt(11)

        # Descrizione
        if event_data.get('description'):
            desc_run = text_paragraph.add_run(f"\n📄 Descrizione:\n{event_data['description']}")
            desc_run.font.size = Pt(10)
            desc_run.font.italic = True
    
    def generate_from_data(self, events: List[Dict], output_path: str, mode: str = "standard", show_borders: bool = False):
        """
        Genera il documento Word completo da una lista di eventi
        Gli eventi vengono automaticamente ordinati per data (dalla più vicina in poi)
        """
    @staticmethod
    def get_sort_date(event: Dict) -> datetime:
        """Helper statico per ottenere la data datetime da un evento"""
        d_str = event.get('date', '')
        if not d_str:
            return datetime.max # Metti in fondo se non ha data
        
        # Usa dateparser per capire la data
        try:
            dt = dateparser.parse(d_str, languages=['it'])
            if dt:
                return dt
        except:
            pass
        return datetime.max # Fallback in fondo

    def generate_from_data(self, events: List[Dict], output_path: str, mode: str = "standard", show_borders: bool = False):
        """
        Genera il documento Word completo da una lista di eventi
        Gli eventi vengono automaticamente ordinati per data (dalla più vicina in poi)
        """
        
        # Ordina eventi
        # "dalle più recenti, quelle che avverranno prima": ASCENDENTE mette prima gli eventi prossimi.
        sorted_events = sorted(events, key=self.get_sort_date)
        
        # Aggiungi titolo documento
        title_text = "Eventi e Locandine" if mode == "standard" else "Locandine (Minimal)"
        title = self.doc.add_heading(title_text, level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Aggiungi data generazione
        date_para = self.doc.add_paragraph()
        date_para.add_run(f"Documento generato il: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        date_para.runs[0].font.size = Pt(9)
        date_para.runs[0].font.italic = True
        
        self.doc.add_paragraph()  # Spazio
        
        # Aggiungi ogni evento
        for event in sorted_events:
            self.add_event_entry(event, event.get('image_path', ''), mode=mode, show_borders=show_borders)
        
        # Salva documento
        self.doc.save(output_path)
        return output_path
    
    def load_events_from_json(self, json_path: str) -> List[Dict]:
        """Carica eventi dal file JSON"""
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_events_to_json(self, events: List[Dict], json_path: str):
        """Salva eventi nel file JSON"""
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(events, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # Test
    generator = WordGenerator()
    print("Word Generator inizializzato correttamente!")
