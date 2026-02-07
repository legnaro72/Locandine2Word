"""
Generatore di documenti Word con locandine ordinate cronologicamente
"""
import json
import os
import dateparser
import re
from typing import List, Dict
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from docx import Document
from datetime import datetime


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
        # Immagine leggermente più grande per armonia (2.8 invece di 2.5)
        self._insert_image(left_cell, image_path, width=Inches(2.8))

        # Cella Destra (Testo descrittivo)
        right_cell = table.rows[0].cells[1]
        self._insert_text_details(right_cell, event_data)
        
        # Aggiungi spazio dopo la tabella
        self.doc.add_paragraph()

    def _insert_image(self, cell, image_path, width=Inches(2.5)):
        """Helper per inserire un'immagine in una cella"""
        if os.path.exists(image_path):
            paragraph = cell.paragraphs[0]
            run = paragraph.add_run()
            # Adatta larghezza per stare nella cella
            run.add_picture(image_path, width=width)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def _insert_text_details(self, cell, event_data):
        """Inserisce i dettagli testuali senza emoji (formato professionale)"""
        
        p = cell.paragraphs[0]

        # Titolo
        title_run = p.add_run(event_data.get('title', 'Evento') + '\n')
        title_run.bold = True
        title_run.font.size = Pt(14)
        title_run.font.color.rgb = RGBColor(0, 51, 102)

        # Funzione helper per campo etichetta + valore
        def add_field(label, value):
            if value:
                label_run = p.add_run(f"{label}: ")
                label_run.bold = True
                label_run.font.size = Pt(11)

                value_run = p.add_run(f"{value}\n")
                value_run.font.size = Pt(11)

        # Data formattata
        if event_data.get('date'):
            date_str = event_data['date']
            try:
                dt = dateparser.parse(date_str, languages=['it'])
                date_formatted = dt.strftime('%d %B %Y') if dt else date_str
            except:
                date_formatted = date_str
            add_field("DATA", date_formatted)

        add_field("ORARIO", event_data.get('time'))
        add_field("LUOGO", event_data.get('location'))
        add_field("PRESSO", event_data.get('venue'))
        add_field("INDIRIZZO", event_data.get('address'))

        # Descrizione rimosssa su richiesta utente
        pass

    
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
        Genera il documento Word completo:
        1. Pagina Statistiche & Titolo
        2. Eventi (Standard o Minimal)
        3. Firma (se esiste)
        """
        # Creiamo un nuovo documento pulito
        self.doc = Document()
        self._setup_default_styles()

        # Aggiungi ogni evento
        sorted_events = sorted(events, key=self.get_sort_date)

        # 1. TITOLO E STATISTICHE (Sempre "Eventi e Locandine")
        title_text = "Eventi e Locandine"
        title = self.doc.add_heading(title_text, level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Data generazione
        date_para = self.doc.add_paragraph()
        date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
        run = date_para.add_run(f"Documento generato il: {now_str}")
        run.font.size = Pt(10)
        run.font.italic = True
        
        self.doc.add_paragraph() # Spazio

        # Statistiche
        st_h = self.doc.add_paragraph()
        st_h.add_run("Riepilogo Dati:").bold = True
        
        total_ev = len(sorted_events)
        self.doc.add_paragraph(f"Totale Locandine caricate: {total_ev}", style='List Bullet')
        
        # --- STATISTICHE GEOGRAFICHE ---
        # Mappatura Province/Regioni
        PROV_TO_REG = {
            'GENOVA': 'LIGURIA', 'GE': 'LIGURIA',
            'LA SPEZIA': 'LIGURIA', 'SP': 'LIGURIA',
            'SAVONA': 'LIGURIA', 'SV': 'LIGURIA',
            'IMPERIA': 'LIGURIA', 'IM': 'LIGURIA',
            'MASSA': 'TOSCANA', 'MS': 'TOSCANA', 'MASSA CARRARA': 'TOSCANA', 'CARRARA': 'TOSCANA'
        }
        
        # Mappatura nomi per uniformità (Tutto sotto MASSA)
        PROV_NORM = {
            'GE': 'GENOVA', 'SP': 'LA SPEZIA', 'SV': 'SAVONA', 'IM': 'IMPERIA', 
            'MS': 'MASSA', 'MASSA CARRARA': 'MASSA', 'CARRARA': 'MASSA'
        }

        stats = {
            'LIGURIA': {'total': 0, 'provinces': {'GENOVA': 0, 'LA SPEZIA': 0, 'SAVONA': 0, 'IMPERIA': 0}},
            'TOSCANA': {'total': 0, 'provinces': {'MASSA': 0}},
            'ALTRO': {'total': 0, 'cities': {}}
        }

        for ev in sorted_events:
            addr = ev.get('address', '').strip().upper()
            loc = ev.get('location', '').strip().upper()
            
            # 1. Tenta di estrarre la provincia dall'ultima parte dell'indirizzo
            prov_found = None
            if addr:
                # Cerca pattern tipo "... - GE" o "... GENOVA" o "... (SP)"
                parts = re.split(r'[\s\-,(]+', addr)
                last_part = parts[-1].strip(' )')
                if last_part in PROV_TO_REG:
                    prov_found = PROV_NORM.get(last_part, last_part)
            
            # 2. Fallback: mappatura manuale per città se l'indirizzo non ha aiutato
            if not prov_found:
                # (Manteniamo una piccola lista di fallback per sicurezza)
                CITY_FALLBACK = {
                    'PEGLI': 'GENOVA', 'BOLZANETO': 'GENOVA', 'VOLTRI': 'GENOVA', 'NERVI': 'GENOVA',
                    'SARZANA': 'LA SPEZIA', 'FOLLO': 'LA SPEZIA', 'LERICI': 'LA SPEZIA',
                    'BRUGNATO': 'LA SPEZIA', 'PIGNONE': 'LA SPEZIA',
                    'CARCARE': 'SAVONA', 'VARAZZE': 'SAVONA',
                    'AULLA': 'MASSA', 'CARRARA': 'MASSA'
                }
                prov_found = CITY_FALLBACK.get(loc)

            # 3. Assegnazione
            if prov_found:
                reg = PROV_TO_REG.get(prov_found) or PROV_TO_REG.get(next((k for k in PROV_NORM if PROV_NORM[k]==prov_found), ''))
                if reg in stats:
                    stats[reg]['total'] += 1
                    if prov_found in stats[reg]['provinces']:
                        stats[reg]['provinces'][prov_found] += 1
                else:
                    stats['ALTRO']['total'] += 1
                    stats['ALTRO']['cities'][loc] = stats['ALTRO']['cities'].get(loc, 0) + 1
            else:
                # Se proprio non troviamo nulla, proviamo a vedere se la location stessa è una provincia
                if loc in PROV_TO_REG:
                    prov = PROV_NORM.get(loc, loc)
                    reg = PROV_TO_REG[loc]
                    stats[reg]['total'] += 1
                    if prov in stats[reg]['provinces']:
                        stats[reg]['provinces'][prov] += 1
                else:
                    stats['ALTRO']['total'] += 1
                    # Se non è una provincia, è una città "Altro"
                    city_key = loc if loc else 'N/D'
                    stats['ALTRO']['cities'][city_key] = stats['ALTRO']['cities'].get(city_key, 0) + 1

        # Regionale
        reg_parts = []
        for r in ['LIGURIA', 'TOSCANA']:
            if stats[r]['total'] > 0:
                reg_parts.append(f"{r} ({stats[r]['total']})")
        if stats['ALTRO']['total'] > 0:
            reg_parts.append(f"ALTRO ({stats['ALTRO']['total']})")
        
        self.doc.add_paragraph(f"Distribuzione per Regione: {', '.join(reg_parts)}", style='List Bullet')

        # Provinciale
        prov_parts = []
        all_provs = {'GENOVA': 'GE', 'LA SPEZIA': 'SP', 'SAVONA': 'SV', 'IMPERIA': 'IM', 'MASSA': 'MS'}
        for r in ['LIGURIA', 'TOSCANA']:
            for p, count in stats[r]['provinces'].items():
                if count > 0:
                    prov_parts.append(f"{p} ({count})")
        
        # Aggiunta categoria ALTRO con elenco città
        if stats['ALTRO']['total'] > 0:
            altro_cities = ", ".join([f"{c} ({n})" for c, n in sorted(stats['ALTRO']['cities'].items())])
            prov_parts.append(f"ALTRO [{altro_cities}]")
        
        if prov_parts:
            self.doc.add_paragraph(f"Distribuzione per Provincia: {', '.join(prov_parts)}", style='List Bullet')

        # Dettaglio Luoghi
        locations = {}
        for ev in sorted_events:
            loc = ev.get('location', 'N/D').strip().upper()
            locations[loc] = locations.get(loc, 0) + 1
        
        loc_str = ", ".join([f"{loc} ({count})" for loc, count in sorted(locations.items())])
        self.doc.add_paragraph(f"Dettaglio per Località: {loc_str}", style='List Bullet')
        
        self.doc.add_page_break()

        # 2. ELENCO EVENTI
        if mode == "standard":
            # Modalità Standard: 2 eventi per pagina
            for idx, event in enumerate(sorted_events):
                self.add_event_entry(event, event.get('image_path', ''), mode=mode, show_borders=show_borders)
                
                # Ogni 2 eventi (e se non è l'ultimo), aggiungiamo un salto pagina per armonia
                if (idx + 1) % 2 == 0 and (idx + 1) < len(sorted_events):
                    self.doc.add_page_break()
                else:
                    # Spazio abbondante tra i due eventi nella stessa pagina
                    self.doc.add_paragraph().paragraph_format.space_after = Pt(30)
        else:
            i = 0
            while i < len(sorted_events):
                event1 = sorted_events[i]
                event2 = sorted_events[i+1] if (i + 1) < len(sorted_events) else None
                self.add_minimal_grid_row(event1, event2, show_borders=show_borders)
                i += 2
        
        # 3. FIRMA (Append file e inserimento Logo esplicito se presente)
        firma_path = "firmaComitato.docx"
        logo_path = "LogoNOConfiniTrasparente.png"
        
        if os.path.exists(firma_path):
            self.doc.add_paragraph() # Spazio
            self._append_external_doc(firma_path)
            
            # Logo posizionato DOPO la firma
            if os.path.exists(logo_path):
                # Assicuriamoci che ci sia un paragrafo di stacco
                self.doc.add_paragraph()
                p_logo = self.doc.add_paragraph()
                p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run_logo = p_logo.add_run()
                run_logo.add_picture(logo_path, width=Inches(2.0))

        # Salva documento
        self.doc.save(output_path)
        return output_path

    def _append_external_doc(self, file_path):
        """Tenta di appendere il contenuto di un altro file docx"""
        try:
            external_doc = Document(file_path)
            for element in external_doc.element.body:
                self.doc.element.body.append(element)
        except Exception as e:
            # Fallback se l'append diretto fallisce (es. file corrotto)
            p = self.doc.add_paragraph()
            p.add_run(f"[Errore caricamento documento esterno {file_path}: {e}]").italic = True

    def add_minimal_grid_row(self, event1, event2, show_borders=False):
        """
        Aggiunge una riga in modalità minimal:
        Colonna 1: Titolo + Immagine evento 1
        Colonna 2: Titolo + Immagine evento 2 (se presente)
        """
        table = self.doc.add_table(rows=1, cols=2)
        
        if show_borders:
            table.style = 'Table Grid'
        else:
            table.style = 'Normal Table'
            
        # Impedisce alla riga di spezzarsi tra due pagine
        table.rows[0].allow_break_across_pages = False
            
        # Larghezze uguali
        table.columns[0].width = Inches(3.25)
        table.columns[1].width = Inches(3.25)
        
        # Cella 1
        if event1:
            self._insert_minimal_content(table.rows[0].cells[0], event1)
            
        # Cella 2
        if event2:
            self._insert_minimal_content(table.rows[0].cells[1], event2)
            
        self.doc.add_paragraph() # Spazio dopo la riga

    def _insert_minimal_content(self, cell, event_data):
        """Inserisce Titolo (con Ora) + Immagine in una cella (modalità minimal)"""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Titolo (Grassetto, dimensione contenuta)
        # Formato: DATA - ORA - LUOGO
        title = event_data.get('title', 'Evento').upper()
        time = event_data.get('time', '').strip()
        
        if time and time not in title:
            # Ricostruzione titolo con ora se non presente
            # (Assumendo che il titolo originale sia DATA - LUOGO)
            if " - " in title:
                parts = title.split(" - ", 1)
                title_text = f"{parts[0]} - {time} - {parts[1]}"
            else:
                title_text = f"{title} - {time}"
        else:
            title_text = title

        run = p.add_run(title_text)
        run.bold = True
        run.font.size = Pt(9)
        # Forza il titolo a stare insieme al paragrafo successivo (l'immagine)
        p.paragraph_format.keep_with_next = True
        
        # Immagine (Sotto il titolo)
        img_path = event_data.get('image_path', '')
        if img_path and os.path.exists(img_path):
            p_img = cell.add_paragraph()
            p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run_img = p_img.add_run()
            # Adatta larghezza per la griglia
            run_img.add_picture(img_path, width=Inches(2.8))
    
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
