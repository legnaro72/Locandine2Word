import streamlit as st
import os
import json
import re
import zipfile
import io
from datetime import datetime
from PIL import Image
from ocr_engine import LocandineOCR
from word_generator import WordGenerator

# --- STREAMLIT IMAGE WIDTH PARAMETER ---
# Usa il parametro moderno 'width' (valido per st.image(), NON per button/download_button)
IMG_WIDTH_ARG = {"width": "stretch"}

# --- FUNZIONE DI PARSING INTELLIGENTE ---
def parse_event_text(text):
    """
    Analizza il testo OCR e lo suddivide nei campi specifici richiesti.
    """
    data = {
        'title': '', 'date': '', 'location': '', 'description': '',
        'time': '', 'venue': '', 'address': ''
    }
    
    if not text:
        return data

    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    # 1. Analisi Prima Riga (Solitamente DATA - LUOGO)
    if len(lines) > 0:
        first_line = lines[0]
        # Cerca separatore "–" o "-"
        parts = re.split(r'\s+[–-]\s+', first_line, maxsplit=1)
        
        # Estrazione Data
        raw_date = parts[0].strip()
        # Aggiungi anno 2026 se non presente e se sembra una data
        if raw_date and '2026' not in raw_date and not re.search(r'\d{4}', raw_date):
             # Evita di aggiungerlo se la stringa è spazzatura corta
            if len(raw_date) > 3: 
                raw_date += " 2026"
        data['date'] = raw_date
        
        # Estrazione Luogo (Parte dopo il trattino nella prima riga)
        if len(parts) > 1:
            data['location'] = parts[1].strip()

    # 2. Analisi Righe Successive (Descrizione, Orario, Presso)
    if len(lines) > 1:
        rest_text = " ".join(lines[1:])
        
        # Cerca pattern Orario (es. Ore 16:30, 16.30, 16,30)
        time_match = re.search(r'(?:Ore|ore)\s*(\d{1,2}[:.,]\d{2})', rest_text)
        
        if time_match:
            # Normalizza orario con i due punti
            data['time'] = time_match.group(1).replace('.', ':').replace(',', ':')
            
            # Testo PRIMA dell'orario -> Solitamente la DESCRIZIONE
            pre_time = rest_text[:time_match.start()].strip()
            # Pulisce trattini finali
            data['description'] = pre_time.rstrip(' –-')
            
            # Testo DOPO l'orario -> Solitamente il PRESSO (Luogo specifico)
            post_time = rest_text[time_match.end():].strip()
            if post_time.startswith('–') or post_time.startswith('-'):
                post_time = post_time[1:].strip()
            data['venue'] = post_time
        else:
            # Se non trova l'orario, considera tutto descrizione
            data['description'] = rest_text

    # 3. Ricerca Indirizzo (Via, Piazza, ecc.) nel testo completo
    address_match = re.search(r'(?:Via|Vico|Piazza|Corso|Largo|Strada)\s+[A-Z][a-z]+.*?\d+', text, re.IGNORECASE)
    if address_match:
        data['address'] = address_match.group(0)

    # Titolo di default se vuoto usa la descrizione troncata
    if not data['title']:
        data['title'] = data['description'][:50] + "..." if data['description'] else "Nuovo Evento"
    
    return data

# --- FUNZIONE DI PARSING DA JSON ---
def parse_json_event(json_entry, image_base_path="uploads"):
    """
    Parsare un evento dal formato JSON locandine.json.
    Usa la stessa logica di 'parse_event_text' per coerenza,
    rispettando la struttura a righe del testo.
    """
    text = json_entry.get('text', '')
    image_file = json_entry.get('image_file', '')
    
    # Usa il parser principale (che gestisce meglio newlines e struttura)
    data = parse_event_text(text)
    
    # Aggiungi percorso immagine
    if image_file:
        data['image_path'] = os.path.join(image_base_path, image_file)
        
    # Fallback per il titolo se il parser lo ha lasciato vuoto o generico
    # (sovrascrive solo se title manca o è quello di default)
    if not data.get('title') or data.get('title') == "Nuovo Evento":
        if data.get('date') and data.get('location'):
             data['title'] = f"{data['date']} – {data['location']}"
    
    return data

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Locandine2Word", page_icon="🎭", layout="wide")

st.markdown("""
<style>
    .main-header { font-size: 2.5rem; background: linear-gradient(90deg, #667eea, #764ba2); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: bold; }
    .stButton>button { width: 100%; border-radius: 5px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- INIZIALIZZAZIONE DATI ---
LOCANDINE_FILE = "locandine.json"
DATA_FILE = "data.json"
UPLOADS_DIR = "uploads"
OUTPUT_DIR = "output"
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

if 'events' not in st.session_state:
    loaded = False
    # 1. Prova a caricare lo stato salvato (data.json)
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                content = json.load(f)
                if content:
                    st.session_state.events = content
                    loaded = True
        except Exception as e:
            st.warning(f"Errore caricamento data.json: {e}")

    # 2. Se vuoto, carica il dataset iniziale (locandine.json)
    if not loaded:
        st.session_state.events = []
        if os.path.exists(LOCANDINE_FILE):
            try:
                with open(LOCANDINE_FILE, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                    # Converti ogni entry
                    for entry in raw_data:
                        parsed = parse_json_event(entry, image_base_path=UPLOADS_DIR)
                        parsed['added_on'] = datetime.now().strftime('%Y-%m-%d')
                        st.session_state.events.append(parsed)
                
                # Salva subito il nuovo stato
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(st.session_state.events, f, ensure_ascii=False, indent=2)
                st.info(f"Caricati {len(st.session_state.events)} eventi da {LOCANDINE_FILE}")
            except Exception as e:
                st.error(f"Errore caricamento {LOCANDINE_FILE}: {e}")


if 'ocr_engine' not in st.session_state:
    st.session_state.ocr_engine = LocandineOCR()

# --- UI PRINCIPALE ---
st.markdown('<h1 class="main-header">🎭 Locandine2Word</h1>', unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Opzioni")
    doc_name = st.text_input("Nome file Word", "Eventi.docx")
    st.divider()
    
    st.markdown("### � Backup & Portabilità")
    
    # --- EXPORT BACKUP ---
    if st.button("📦 Crea Backup (.zip)"):
        with st.spinner("Creazione archivio in corso..."):
            try:
                # Creazione ZIP in memoria
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    # 1. Aggiungi il database JSON
                    if os.path.exists(DATA_FILE):
                        zf.write(DATA_FILE, arcname='data.json')
                    
                    # 2. Aggiungi la cartella uploads
                    if os.path.exists(UPLOADS_DIR):
                        for root, _, files in os.walk(UPLOADS_DIR):
                            for file in files:
                                file_path = os.path.join(root, file)
                                # Salva nel zip con percorso relativo 'uploads/nomefile'
                                zf.write(file_path, arcname=os.path.join('uploads', file))
                
                zip_buffer.seek(0)
                st.session_state['backup_zip'] = zip_buffer
                st.success("Backup creato! Clicca sotto per scaricare.")
            except Exception as e:
                st.error(f"Errore creazione backup: {e}")

    if 'backup_zip' in st.session_state:
        st.download_button(
            label="⬇️ Scarica Backup Completo",
            data=st.session_state['backup_zip'],
            file_name=f"locandine_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
            mime="application/zip"
        )
    
    st.write("---")

    # --- IMPORT BACKUP ---
    uploaded_backup = st.file_uploader("Ripristina Backup (ZIP o JSON)", type=['zip', 'json'])
    
    if uploaded_backup:
        if st.button("♻️ Ripristina/Importa"):
            try:
                # Caso 1: È un file ZIP (Backup Completo)
                if uploaded_backup.name.endswith('.zip'):
                    with zipfile.ZipFile(uploaded_backup) as z:
                        # Estrai tutto nella cartella corrente (sovrascrive data.json e uploads/)
                        z.extractall(".")
                    
                    # Ricarica lo stato
                    st.session_state.events = [] # Reset memoria
                    if os.path.exists(DATA_FILE):
                        with open(DATA_FILE, 'r', encoding='utf-8') as f:
                            st.session_state.events = json.load(f)
                    
                    st.success("Backup ripristinato con successo! Ricarico...")
                    st.rerun()

                # Caso 2: È un file JSON (Vecchio metodo Import)
                elif uploaded_backup.name.endswith('.json'):
                    new_data = json.load(uploaded_backup)
                    if isinstance(new_data, list):
                        count = 0
                        for entry in new_data:
                            # Logica importazione
                            if 'title' in entry: # Già processato
                                st.session_state.events.append(entry)
                                count += 1
                        
                        # Salva unione
                        with open(DATA_FILE, 'w', encoding='utf-8') as f:
                            json.dump(st.session_state.events, f, ensure_ascii=False, indent=2)
                        st.success(f"Aggiunti {count} eventi dal JSON.")
                        st.rerun()

            except Exception as e:
                st.error(f"Errore durante il ripristino: {e}")

    st.divider()
    if st.button("🗑️ Reset Database Completo"):
        st.session_state.events = []
        with open(DATA_FILE, 'w') as f: json.dump([], f)
        st.rerun()

tab1, tab2, tab3 = st.tabs(["📤 Carica & Analizza", "📋 Modifica Dati", "📖 Export Word"])

# --- TAB 1: CARICAMENTO ---
with tab1:
    st.subheader("Carica nuove locandine")
    uploaded_files = st.file_uploader("Trascina qui le immagini", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    
    if uploaded_files:
        for idx, uploaded_file in enumerate(uploaded_files):
            with st.expander(f"🖼️ {uploaded_file.name}", expanded=True):
                col1, col2 = st.columns([1, 2])
                
                # Salvataggio e Anteprima Immagine
                image_path = os.path.join(UPLOADS_DIR, uploaded_file.name)
                with open(image_path, 'wb') as f:
                    f.write(uploaded_file.getbuffer())
                
                # Visualizza immagine (con fix compatibilità)
                col1.image(image_path, **IMG_WIDTH_ARG)
                
                with col2:
                    # Pulsante OCR
                    if st.button(f"🔍 Estrai Dati", key=f"ocr_{idx}"):
                        with st.spinner("Analisi OCR in corso..."):
                            # 1. OCR
                            raw_ocr = st.session_state.ocr_engine.analyze_poster(image_path)
                            # FIX: usa 'full_text' perché 'text' non esiste nel dict restituito
                            raw_text = raw_ocr.get('full_text', '')
                            # 2. Parsing
                            parsed = parse_event_text(raw_text)
                            parsed['image_path'] = image_path
                            # Salva in temp per mostrare il form
                            st.session_state[f'temp_data_{idx}'] = parsed
                            st.success("Dati estratti! Verifica qui sotto.")

                    # Form di Verifica (appare SOLO se abbiamo i dati in temp)
                    if f'temp_data_{idx}' in st.session_state:
                        data = st.session_state[f'temp_data_{idx}']
                        st.markdown("---")
                        st.markdown("#### ✏️ Verifica e Salva")
                        
                        with st.form(key=f"save_form_{idx}"):
                            # Titolo
                            f_title = st.text_input("Titolo Evento", data['title'])
                            
                            # Griglia campi
                            c_a1, c_a2 = st.columns(2)
                            f_date = c_a1.text_input("Data (+Anno)", data['date'])
                            f_time = c_a2.text_input("Orario", data['time'])
                            
                            c_b1, c_b2 = st.columns(2)
                            f_loc = c_b1.text_input("Luogo (Città/Zona)", data['location'])
                            f_venue = c_b2.text_input("Presso (Struttura)", data['venue'])
                            
                            f_addr = st.text_input("Indirizzo", data['address'])
                            f_desc = st.text_area("Descrizione", data['description'])
                            
                            # Pulsante Salva
                            if st.form_submit_button("💾 Aggiungi agli Eventi"):
                                new_event = {
                                    'title': f_title, 'date': f_date, 'time': f_time,
                                    'location': f_loc, 'venue': f_venue, 'address': f_addr,
                                    'description': f_desc, 'image_path': data['image_path'],
                                    'added_on': datetime.now().strftime('%Y-%m-%d')
                                }
                                st.session_state.events.append(new_event)
                                # Salva su disco
                                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                                    json.dump(st.session_state.events, f, ensure_ascii=False, indent=2)
                                
                                st.success("Evento salvato correttamente! Vai al Tab 'Modifica Dati' per vederlo.")
                                # Pulisce lo stato temp
                                del st.session_state[f'temp_data_{idx}']
                                st.rerun()

# --- TAB 2: GESTIONE ---
with tab2:
    st.subheader("Gestione Eventi Salvati")
    
    if not st.session_state.events:
        st.info("Nessun evento in archivio.")
    else:
        col_m1, col_m2 = st.columns([3, 1])
        with col_m2:
            if st.button("🔄 Riordina Date", help="Forza l'ordinamento cronologico di tutti gli eventi salvati"):
                st.session_state.events.sort(key=WordGenerator.get_sort_date)
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(st.session_state.events, f, ensure_ascii=False, indent=2)
                st.success("Eventi riordinati!")
                st.rerun()
        # Prepara la lista con indici originali per poter modificare/eliminare correttamente
        # Lista di tuple: (indice_originale, evento)
        indexed_events = list(enumerate(st.session_state.events))
        
        # Ordina usando la logica condivisa in WordGenerator (per Data)
        # WordGenerator.get_sort_date è statico
        sorted_indexed_events = sorted(
            indexed_events, 
            key=lambda x: WordGenerator.get_sort_date(x[1])
        )

        st.info("ℹ️ Gli eventi sono ordinati cronologicamente (dal più prossimo al più lontano).")

        for real_idx, event in sorted_indexed_events:
            with st.expander(f"📅 {event.get('date', 'Data n/d')} - {event.get('title', 'Titolo n/d')}"):
                c1, c2 = st.columns([1, 2])
                
                # Immagine
                if os.path.exists(event['image_path']):
                    c1.image(event['image_path'], **IMG_WIDTH_ARG)
                else:
                    c1.error("Immagine non trovata")
                
                with c2:
                    st.markdown("### Modifica Dettagli")
                    
                    # Campi modificabili
                    n_title = st.text_input("Titolo", event.get('title', ''), key=f"e_tit_{real_idx}")
                    
                    r1, r2 = st.columns(2)
                    n_date = r1.text_input("Data", event.get('date', ''), key=f"e_dat_{real_idx}")
                    n_time = r2.text_input("Orario", event.get('time', ''), key=f"e_tim_{real_idx}")
                    
                    r3, r4 = st.columns(2)
                    n_loc = r3.text_input("Luogo", event.get('location', ''), key=f"e_loc_{real_idx}")
                    n_venue = r4.text_input("Presso", event.get('venue', ''), key=f"e_ven_{real_idx}")
                    
                    n_addr = st.text_input("Indirizzo", event.get('address', ''), key=f"e_add_{real_idx}")
                    n_desc = st.text_area("Descrizione", event.get('description', ''), key=f"e_des_{real_idx}", height=100)
                    
                    # Pulsantiera
                    col_b1, col_b2 = st.columns([1, 1])
                    
                    if col_b1.button("💾 Aggiorna", key=f"upd_{real_idx}"):
                        # Aggiorna l'oggetto in memoria
                        st.session_state.events[real_idx].update({
                            'title': n_title, 'date': n_date, 'time': n_time,
                            'location': n_loc, 'venue': n_venue, 'address': n_addr,
                            'description': n_desc
                        })
                        # Salva su file
                        with open(DATA_FILE, 'w', encoding='utf-8') as f:
                            json.dump(st.session_state.events, f, ensure_ascii=False, indent=2)
                        st.success("Aggiornato!")
                        st.rerun()
                        
                    if col_b2.button("🗑️ Elimina", key=f"del_{real_idx}", type="primary"):
                        st.session_state.events.pop(real_idx)
                        with open(DATA_FILE, 'w', encoding='utf-8') as f:
                            json.dump(st.session_state.events, f, ensure_ascii=False, indent=2)
                        st.rerun()

# --- TAB 3: EXPORT ---
with tab3:
    st.subheader("Generazione Documento")
    st.write(f"Eventi pronti per la stampa: **{len(st.session_state.events)}**")
    
    
    col_opts1, col_opts2 = st.columns(2)
    with col_opts1:
        export_mode_sel = st.radio("Stile Documento", ["Standard (Foto + Testo)", "Minimal (Solo Foto)"])
    with col_opts2:
        st.write("") # Spacer
        st.write("") 
        show_borders_opt = st.checkbox("Mostra bordi tabella", value=True)

    export_mode = "minimal" if "Minimal" in export_mode_sel else "standard"

    if st.button("📥 Genera Word", type="primary"):
        if not st.session_state.events:
            st.error("Nessun evento da stampare!")
        else:
            with st.spinner("Creazione documento Word in corso..."):
                gen = WordGenerator()
                out_path = os.path.join(OUTPUT_DIR, doc_name)
                # Passiamo la lista ordinata e le opzioni
                gen.generate_from_data(
                    st.session_state.events, 
                    out_path, 
                    mode=export_mode, 
                    show_borders=show_borders_opt
                )
                
                with open(out_path, 'rb') as f:
                    st.download_button(
                        label="⬇️ Scarica File",
                        data=f,
                        file_name=doc_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                st.success("Documento pronto!")