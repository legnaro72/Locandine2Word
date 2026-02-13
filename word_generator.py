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
        table = self.doc.add_table(rows=1, cols=2)
        
        if show_borders:
            table.style = 'Table Grid'
        else:
            table.style = 'Normal Table'
        
        table.columns[0].width = Inches(3.25)
        table.columns[1].width = Inches(3.25)
        
        left_cell = table.rows[0].cells[0]
        self._insert_image(left_cell, image_path, width=Inches(2.8))

        right_cell = table.rows[0].cells[1]
        self._insert_text_details(right_cell, event_data)
        
        # LOGICA SCADUTI
        now = datetime.now()
        ev_date = self.get_sort_date(event_data)
        if ev_date != datetime.max and ev_date.date() < now.date():
            completed_img = "completed.jpg"
            if os.path.exists(completed_img):
                p_comp = right_cell.add_paragraph()
                p_comp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run_comp = p_comp.add_run()
                run_comp.add_picture(completed_img, width=Inches(1.5))
        
        # LOGICA NEW
        if event_data.get('is_new'):
            new_img_path = "new.jpg"
            if os.path.exists(new_img_path):
                p_new = right_cell.add_paragraph()
                p_new.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run_new = p_new.add_run()
                run_new.add_picture(new_img_path, width=Inches(1.5))

        self.doc.add_paragraph()

    def _insert_image(self, cell, image_path, width=Inches(2.5)):
        if os.path.exists(image_path):
            paragraph = cell.paragraphs[0]
            run = paragraph.add_run()
            run.add_picture(image_path, width=width)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def _insert_text_details(self, cell, event_data):
        p = cell.paragraphs[0]
        title_run = p.add_run(event_data.get('title', 'Evento') + '\n')
        title_run.bold = True
        title_run.font.size = Pt(14)
        title_run.font.color.rgb = RGBColor(0, 51, 102)

        def add_field(label, value):
            if value:
                label_run = p.add_run(f"{label}: ")
                label_run.bold = True
                label_run.font.size = Pt(11)
                value_run = p.add_run(f"{value}\n")
                value_run.font.size = Pt(11)

        if event_data.get('date'):
            date_str = event_data['date']
            try:
                dt = dateparser.parse(date_str, languages=['it', 'en'])
                if dt:
                    IT_MONTHS = {1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile", 5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto", 9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre"}
                    date_formatted = f"{dt.day} {IT_MONTHS[dt.month]} {dt.year}"
                else:
                    date_formatted = date_str
            except:
                date_formatted = date_str
            add_field("DATA", date_formatted)

        add_field("ORARIO", event_data.get('time'))
        add_field("LUOGO", event_data.get('location'))
        add_field("PRESSO", event_data.get('venue'))
        add_field("INDIRIZZO", event_data.get('address'))

    @staticmethod
    def get_sort_date(event: Dict) -> datetime:
        d_str = event.get('date', '')
        if not d_str:
            return datetime.max
        try:
            dt = dateparser.parse(d_str, languages=['it', 'en'])
            return dt if dt else datetime.max
        except:
            return datetime.max

    @staticmethod
    def get_province(event: Dict) -> str:
        """Determina la provincia di un evento con supporto a mappature personalizzate."""
        
        # --- CARICAMENTO MAPPATURE PERSONALIZZATE (Luni, Ospedaletti, ecc.) ---
        custom_map_file = "city_mappings.json"
        custom_mappings = {}
        if os.path.exists(custom_map_file):
            try:
                with open(custom_map_file, "r", encoding="utf-8") as f:
                    custom_mappings = json.load(f)
            except:
                pass

        addr = event.get('address', '').strip().upper()
        loc = event.get('location', '').strip().upper()

        # 1. Controllo prioritario nel dizionario personalizzato
        for city, prov in custom_mappings.items():
            if city in loc or city in addr:
                return prov

        # 2. Logica Standard preesistente
        PROV_NORM = {
            'GE': 'GENOVA', 'SP': 'LA SPEZIA', 'SV': 'SAVONA', 'IM': 'IMPERIA', 
            'MS': 'MASSA', 'MASSA CARRARA': 'MASSA', 'CARRARA': 'MASSA', 'AL': 'ALESSANDRIA'
        }
        
        CITY_FALLBACK = {
            'PEGLI': 'GENOVA', 'BOLZANETO': 'GENOVA', 'VOLTRI': 'GENOVA', 'NERVI': 'GENOVA',
            'SARZANA': 'LA SPEZIA', 'FOLLO': 'LA SPEZIA', 'LERICI': 'LA SPEZIA',
            'BRUGNATO': 'LA SPEZIA', 'PIGNONE': 'LA SPEZIA',
            'CEPARANA': 'LA SPEZIA', 'VEZZANO LIGURE': 'LA SPEZIA', 'VEZZANO': 'LA SPEZIA',
            'MARINELLA DI SARZANA': 'LA SPEZIA', 'MARINELLA': 'LA SPEZIA',
            'BOLANO': 'LA SPEZIA', 'ARCOLA': 'LA SPEZIA', 'SANTO STEFANO MAGRA': 'LA SPEZIA',
            'SANTO STEFANO DI MAGRA': 'LA SPEZIA', 'AMEGLIA': 'LA SPEZIA', 'CASTELNUOVO MAGRA': 'LA SPEZIA',
            'DEIVA MARINA': 'LA SPEZIA', 'FRAMURA': 'LA SPEZIA', 'LEVANTO': 'LA SPEZIA',
            'MONTEROSSO': 'LA SPEZIA', 'ORTONOVO': 'LA SPEZIA', 'PORTOVENERE': 'LA SPEZIA',
            'CARCARE': 'SAVONA', 'VARAZZE': 'SAVONA',
            'AULLA': 'MASSA', 'CARRARA': 'MASSA'
        }

        # Prova estrazione da indirizzo
        parts = re.split(r'[\s\-,(]+', addr)
        if parts:
            last_part = parts[-1].strip(' )')
            if last_part in PROV_NORM: return PROV_NORM[last_part]
            if last_part in ['GENOVA', 'SAVONA', 'IMPERIA', 'MASSA', 'ALESSANDRIA']: return last_part
            if last_part == 'LA SPEZIA' or last_part == 'SPEZIA': return 'LA SPEZIA'

        # Prova estrazione da location
        return CITY_FALLBACK.get(loc) or PROV_NORM.get(loc) or "ALTRO"

    def generate_from_data(self, events: List[Dict], output_path: str, mode: str = "standard", show_borders: bool = False):
        self.doc = Document()
        self._setup_default_styles()
        sorted_events = sorted(events, key=self.get_sort_date)

        # TITOLO E STATISTICHE
        title = self.doc.add_heading("Eventi e Locandine", level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        date_para = self.doc.add_paragraph()
        date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = date_para.add_run(f"Documento generato il: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        run.font.size, run.font.italic = Pt(10), True
        
        self.doc.add_paragraph()
        self.doc.add_paragraph("Riepilogo Dati:").runs[0].bold = True
        self.doc.add_paragraph(f"Totale Locandine caricate: {len(sorted_events)}", style='List Bullet')
        
        # --- STATISTICHE GEOGRAFICHE AGGIORNATE ---
        PROV_TO_REG = {
            'GENOVA': 'LIGURIA', 'LA SPEZIA': 'LIGURIA', 'SAVONA': 'LIGURIA', 
            'IMPERIA': 'LIGURIA', 'MASSA': 'TOSCANA', 'ALESSANDRIA': 'PIEMONTE'
        }

        stats = {
            'LIGURIA': {'total': 0, 'provinces': {'GENOVA': 0, 'LA SPEZIA': 0, 'SAVONA': 0, 'IMPERIA': 0}},
            'TOSCANA': {'total': 0, 'provinces': {'MASSA': 0}},
            'PIEMONTE': {'total': 0, 'provinces': {'ALESSANDRIA': 0}},
            'ALTRO': {'total': 0, 'cities': {}}
        }

        for ev in sorted_events:
            prov = self.get_province(ev)
            reg = PROV_TO_REG.get(prov, 'ALTRO')
            
            if reg != 'ALTRO':
                stats[reg]['total'] += 1
                stats[reg]['provinces'][prov] = stats[reg]['provinces'].get(prov, 0) + 1
            else:
                stats['ALTRO']['total'] += 1
                loc = ev.get('location', 'N/D').strip().upper()
                stats['ALTRO']['cities'][loc] = stats['ALTRO']['cities'].get(loc, 0) + 1

        # Scrittura Statistiche nel Word
        reg_txt = ", ".join([f"{r} ({stats[r]['total']})" for r in stats if stats[r]['total'] > 0])
        self.doc.add_paragraph(f"Distribuzione per Regione: {reg_txt}", style='List Bullet')

        prov_list = []
        for r in stats:
            if r != 'ALTRO':
                for p, count in stats[r]['provinces'].items():
                    if count > 0: prov_list.append(f"{p} ({count})")
        
        if stats['ALTRO']['total'] > 0:
            altro_txt = ", ".join([f"{c}({n})" for c, n in stats['ALTRO']['cities'].items()])
            prov_list.append(f"ALTRO [{altro_txt}]")
            
        self.doc.add_paragraph(f"Distribuzione per Provincia: {', '.join(prov_list)}", style='List Bullet')
        
        self.doc.add_page_break()

        # ELENCO EVENTI
        if mode == "standard":
            for idx, event in enumerate(sorted_events):
                self.add_event_entry(event, event.get('image_path', ''), mode=mode, show_borders=show_borders)
                if (idx + 1) % 2 == 0 and (idx + 1) < len(sorted_events):
                    self.doc.add_page_break()
                else:
                    self.doc.add_paragraph().paragraph_format.space_after = Pt(30)
        else:
            i = 0
            while i < len(sorted_events):
                ev1 = sorted_events[i]
                ev2 = sorted_events[i+1] if (i+1) < len(sorted_events) else None
                self.add_minimal_grid_row(ev1, ev2, show_borders=show_borders)
                i += 2
        
        # FIRMA E LOGO
        if os.path.exists("firmaComitato.docx"):
            self.doc.add_paragraph()
            self._append_external_doc("firmaComitato.docx")
            if os.path.exists("LogoNOConfiniTrasparente.png"):
                p_logo = self.doc.add_paragraph()
                p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_logo.add_run().add_picture("LogoNOConfiniTrasparente.png", width=Inches(2.0))

        self.doc.save(output_path)
        return output_path

    def _append_external_doc(self, file_path):
        try:
            external_doc = Document(file_path)
            for element in external_doc.element.body:
                self.doc.element.body.append(element)
        except Exception as e:
            self.doc.add_paragraph(f"[Errore firma: {e}]").italic = True

    def add_minimal_grid_row(self, event1, event2, show_borders=False):
        table = self.doc.add_table(rows=1, cols=2)
        table.style = 'Table Grid' if show_borders else 'Normal Table'
        table.rows[0].allow_break_across_pages = False
        table.columns[0].width = table.columns[1].width = Inches(3.25)
        
        if event1: self._insert_minimal_content(table.rows[0].cells[0], event1)
        if event2: self._insert_minimal_content(table.rows[0].cells[1], event2)
        self.doc.add_paragraph()

    def _insert_minimal_content(self, cell, event_data):
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title = event_data.get('title', 'Evento').upper()
        time = event_data.get('time', '').strip()
        
        title_text = f"{title} - {time}" if time and time not in title else title
        run = p.add_run(title_text)
        run.bold, run.font.size = True, Pt(9)
        p.paragraph_format.keep_with_next = True
        
        img_path = event_data.get('image_path', '')
        now = datetime.now()
        if self.get_sort_date(event_data).date() < now.date() and os.path.exists("completed.jpg"):
            img_path = "completed.jpg"

        if img_path and os.path.exists(img_path):
            p_img = cell.add_paragraph()
            p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_img.add_run().add_picture(img_path, width=Inches(2.8))

    def load_events_from_json(self, json_path: str) -> List[Dict]:
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_events_to_json(self, events: List[Dict], json_path: str):
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
