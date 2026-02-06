import streamlit as st
import os
import json
import re
import zipfile
import io
from github_manager import GithubManager
from datetime import datetime
from PIL import Image
from ocr_engine import LocandineOCR
from word_generator import WordGenerator
try:
    from streamlit_mic_recorder import speech_to_text
except ImportError:
    speech_to_text = None  # Fallback gracefully

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
        # Forza l'uso di / anche su Windows per compatibilità Cloud
        data['image_path'] = f"{image_base_path}/{image_file}"
        
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

# --- CONFIGURAZIONE GITHUB ---
# La configurazione corretta va fatta nei Secrets di Streamlit (GITHUB_TOKEN)
# Localmente: creare .streamlit/secrets.toml con GITHUB_TOKEN="tuo_token"
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", None)
GITHUB_REPO = "legnaro72/Locandine2Word"

if 'github_manager' not in st.session_state and GITHUB_TOKEN:
    st.session_state.github_manager = GithubManager(GITHUB_TOKEN, GITHUB_REPO)

if 'events' not in st.session_state:
    st.session_state.events = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                content = json.load(f)
                if isinstance(content, list):
                    # Normalizzazione percorsi (\ -> /) per compatibilità cloud
                    for ev in content:
                        if 'image_path' in ev:
                            ev['image_path'] = ev['image_path'].replace('\\', '/')
                    st.session_state.events = content
        except Exception as e:
            st.error(f"Errore caricamento database locale: {e}")


if 'ocr_engine' not in st.session_state:
    st.session_state.ocr_engine = LocandineOCR()

# --- UI PRINCIPALE ---
st.markdown('<h1 class="main-header">🎭 Locandine2Word</h1>', unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Opzioni")
    doc_name = st.text_input("Nome file Word", "Eventi.docx")
    st.divider()
    
    st.markdown("### 📦 Backup & Portabilità")
    
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
                                # Forza l'uso di / nello ZIP per compatibilità Linux/Cloud
                                arcname = f"uploads/{os.path.basename(file)}"
                                zf.write(file_path, arcname=arcname)
                
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

    st.markdown("### ☁️ Sincronizzazione GitHub")
    
    if not GITHUB_TOKEN:
        st.warning("⚠️ GitHub non configurato. Inserisci il GITHUB_TOKEN nei Secrets di Streamlit per attivare il backup cloud.")
    
    # --- GITHUB PUSH ---
    if st.button("🚀 Salva su GitHub (Cloud)", disabled=not GITHUB_TOKEN):
        st.session_state.show_confirm_push = True
    
    if st.session_state.get('show_confirm_push'):
        st.warning("⚠️ Confermi di voler inviare l'attuale database e le immagini su GitHub?")
        col_c1, col_c2 = st.columns(2)
        if col_c1.button("✅ Sì, Invia", key="confirm_push_btn"):
            with st.spinner("Sincronizzazione con GitHub in corso..."):
                try:
                    zip_data = st.session_state.github_manager.create_backup_zip(DATA_FILE, UPLOADS_DIR)
                    success, msg = st.session_state.github_manager.upload_backup(zip_data)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
                except Exception as e:
                    st.error(f"Errore GitHub: {e}")
            st.session_state.show_confirm_push = False
            # st.rerun() # Evitiamo rerun immediato per far leggere il msg
        if col_c2.button("❌ Annulla", key="cancel_push_btn"):
            st.session_state.show_confirm_push = False
            st.rerun()

    # --- GITHUB PULL ---
    if st.button("☁️ Carica da GitHub (Cloud)", disabled=not GITHUB_TOKEN):
        st.session_state.show_confirm_pull = True

    if st.session_state.get('show_confirm_pull'):
        st.error("⚠️ ATTENZIONE: Questo sovrascriverà tutti i dati locali con quelli di GitHub!")
        col_cp1, col_cp2 = st.columns(2)
        if col_cp1.button("✅ Sì, Ripristina", key="confirm_pull_btn"):
            with st.spinner("Scaricamento backup da GitHub..."):
                try:
                    zip_content = st.session_state.github_manager.download_backup()
                    st.session_state.github_manager.restore_from_zip(zip_content)
                    st.success("Dati ripristinati da GitHub correttamente! Ricarico...")
                    # Rimuoviamo la chiave per forzare la rilettura dal nuovo data.json su disco al rerun
                    if 'events' in st.session_state:
                        del st.session_state['events']
                    st.session_state.show_confirm_pull = False
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore durante il ripristino: {e}")
            st.session_state.show_confirm_pull = False
        if col_cp2.button("❌ Annulla", key="cancel_pull_btn"):
            st.session_state.show_confirm_pull = False
            st.rerun()

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
                    
                    # Forza ricaricamento totale
                    if 'events' in st.session_state:
                        del st.session_state['events']
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
        with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump([], f)
        if 'events' in st.session_state:
            del st.session_state['events']
        st.rerun()

tab1, tab2, tab3 = st.tabs(["📤 Carica & Analizza", "📋 Modifica Dati", "📖 Export Word"])

# --- TAB 1: CARICAMENTO ---
with tab1:
    st.subheader("Carica nuove locandine")
    
    # 1. OPTIONAL: Caricamento JSON Precompilato
    prefill_map = {}
    prefill_file = st.file_uploader("📂 Carica JSON Metadati (Opzionale)", type=['json'], help="Se hai un JSON con campi 'filename', 'title', 'date' ecc., caricalo qui per saltare l'OCR.")
    
    if prefill_file is not None:
        try:
            pf_data = json.load(prefill_file)
            count_pf = 0
            if isinstance(pf_data, list):
                for item in pf_data:
                    # Cerca una chiave filename
                    fname = item.get('filename') or item.get('image') or item.get('file')
                    if fname:
                        # Normalizza un po' i nomi (solo nome file base)
                        fname_clean = os.path.basename(fname)
                        prefill_map[fname_clean] = item
                        count_pf += 1
            if count_pf > 0:
                st.success(f"✅ Caricati metadati per {count_pf} file.")
            else:
                st.warning("Nessun campo 'filename' trovato nel JSON.")
        except Exception as e:
            st.error(f"Errore lettura JSON: {e}")

    uploaded_files = st.file_uploader("Trascina qui le immagini", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    
    if uploaded_files:
        for idx, uploaded_file in enumerate(uploaded_files):
            with st.expander(f"🖼️ {uploaded_file.name}", expanded=True):
                col1, col2 = st.columns([1, 2])
                
                # Salvataggio e Anteprima Immagine
                image_path = os.path.join(UPLOADS_DIR, uploaded_file.name)
                # Salva solo se non esiste o aggiorna? Meglio sovrascrivere per sicurezza
                with open(image_path, 'wb') as f:
                    f.write(uploaded_file.getbuffer())
                
                # Visualizza immagine
                col1.image(image_path, **IMG_WIDTH_ARG)
                
                with col2:
                    # Check match JSON
                    json_match = prefill_map.get(uploaded_file.name)
                    
                    if json_match:
                        st.info("✨ Dati precompilati trovati da JSON!")
                        btn_label = "✅ Usa Dati da JSON"
                    else:
                        btn_label = "🔍 Estrai Dati (OCR)"

                    # Pulsante Elaborazione
                    if st.button(btn_label, key=f"proc_{idx}"):
                        with st.spinner("Elaborazione..."):
                            
                            if json_match:
                                # USA DATI JSON
                                parsed = {
                                    'title': json_match.get('title', ''),
                                    'date': json_match.get('date', ''),
                                    'time': json_match.get('time', ''),
                                    'location': json_match.get('location', ''),
                                    'venue': json_match.get('venue', ''),
                                    'address': json_match.get('address', ''),
                                    'description': json_match.get('description', '')
                                }
                            else:
                                # USA OCR
                                raw_ocr = st.session_state.ocr_engine.analyze_poster(image_path)
                                raw_text = raw_ocr.get('full_text', '')
                                parsed = parse_event_text(raw_text)
                            
                            # Forza separatore /
                            parsed['image_path'] = f"{UPLOADS_DIR}/{uploaded_file.name}"
                            
                            # Salva in temp per mostrare il form
                            st.session_state[f'temp_data_{idx}'] = parsed
                            st.rerun() # Refresh per mostrare il form sotto

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
                                    'added_on': datetime.now().strftime('%Y-%m-%d'),
                                    'is_new': True
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
    
    # Recupero sicuro degli eventi
    events_list = st.session_state.get('events', [])
    
    if not events_list:
        st.info("Nessun evento in archivio.")
    else:
        col_m1, col_m2, col_m3 = st.columns([2, 1, 1])
        
        with col_m2:
            if st.button("🏷️ Rinomina Auto"):
                import dateparser
                import locale
                try:
                    locale.setlocale(locale.LC_TIME, 'it_IT.utf8')
                except:
                    pass

                for event in events_list:
                    raw_date = event.get('date', '').strip()
                    location = event.get('location', '').strip()
                    
                    if raw_date:
                        dt = dateparser.parse(raw_date, languages=['it'])
                        if dt:
                            clean_date = dt.strftime("%d %B %Y").upper()
                            event['date'] = clean_date
                            
                            day_map_safe = {
                                0: "LUNEDI'", 1: "MARTEDI'", 2: "MERCOLEDI'", 
                                3: "GIOVEDI'", 4: "VENERDI'", 5: "SABATO'", 6: "DOMENICA"
                            }
                            weekday = day_map_safe.get(dt.weekday(), "")
                            full_date_string = f"{weekday} {clean_date}"
                            
                            event['title'] = f"{full_date_string} - {location}" if location else full_date_string
                
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(events_list, f, ensure_ascii=False, indent=2)
                st.success("Date pulite e Titoli rinominati!")
                st.rerun()

        with col_m3:
            if st.button("🔄 Riordina Date"):
                events_list.sort(key=WordGenerator.get_sort_date)
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(events_list, f, ensure_ascii=False, indent=2)
                st.success("Eventi riordinati!")
                st.rerun()

        indexed_events = list(enumerate(events_list))
        sorted_indexed_events = sorted(
            indexed_events, 
            key=lambda x: WordGenerator.get_sort_date(x[1])
        )

        st.info("ℹ️ Gli eventi sono ordinati cronologicamente.")

        # -------- LOOP EVENTI --------
        for real_idx, event in sorted_indexed_events:
            title_prefix = "🆕 " if event.get('is_new') else ""
            with st.expander(f"{title_prefix}📅 {event.get('title', 'Titolo n/d')}"):

                # ===== INIZIALIZZAZIONE WIDGET STATE SICURA =====
                def init_widget(key, default):
                    if key not in st.session_state:
                        st.session_state[key] = default

                k_tit = f"e_tit_{real_idx}"
                k_dat = f"e_dat_{real_idx}"
                k_tim = f"e_tim_{real_idx}"
                k_loc = f"e_loc_{real_idx}"
                k_ven = f"e_ven_{real_idx}"
                k_add = f"e_add_{real_idx}"
                k_des = f"e_des_{real_idx}"

                init_widget(k_tit, event.get('title', ''))
                init_widget(k_dat, event.get('date', ''))
                init_widget(k_tim, event.get('time', ''))
                init_widget(k_loc, event.get('location', ''))
                init_widget(k_ven, event.get('venue', ''))
                init_widget(k_add, event.get('address', ''))
                init_widget(k_des, event.get('description', ''))


                # ===== DETTATURA =====
                if speech_to_text:
                    st.markdown("#### 🎤 Dettatura Vocale")

                    sel_key = f"sel_field_{real_idx}"
                    mic_buffer_key = f"mic_buffer_{real_idx}"

                    # Selettore campo
                    st.selectbox(
                        "Campo da compilare con la voce",
                        options=['description', 'title', 'location', 'venue', 'address', 'date', 'time'],
                        key=sel_key
                    )

                    # Microfono salva SOLO in buffer
                    text_dettato = speech_to_text(
                        language='it',
                        start_prompt="🔴 PARLA",
                        stop_prompt="⏹️ STOP",
                        just_once=True,
                        key=f"stt_widget_{real_idx}"
                    )

                    if text_dettato:
                        st.session_state[mic_buffer_key] = text_dettato

                    # Se c'è testo nel buffer lo mostriamo
                    if mic_buffer_key in st.session_state:
                        st.info(f"Testo rilevato: {st.session_state[mic_buffer_key]}")

                        if st.button("✅ Inserisci nel campo selezionato", key=f"apply_mic_{real_idx}"):

                            final_field = st.session_state.get(sel_key, "description")

                            mapping = {
                                'title': k_tit,
                                'date': k_dat,
                                'time': k_tim,
                                'location': k_loc,
                                'venue': k_ven,
                                'address': k_add,
                                'description': k_des
                            }

                            widget_k = mapping.get(final_field)

                            if widget_k:
                                st.session_state[widget_k] = st.session_state[mic_buffer_key]
                                event[final_field] = st.session_state[mic_buffer_key]

                                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                                    json.dump(events_list, f, ensure_ascii=False, indent=2)

                                del st.session_state[mic_buffer_key]
                                st.success("Campo aggiornato!")
                                st.rerun()


                st.divider()

                c1, c2 = st.columns([1, 2])

                # Normalizzazione cross-platform
                image_path = os.path.normpath(event.get('image_path', ''))

                if image_path and os.path.exists(image_path):
                    c1.image(image_path, **IMG_WIDTH_ARG)
                else:
                    c1.error(f"Immagine non trovata: {image_path}")

                else:
                    c1.error("Immagine non trovata")

                with c2:
                    st.markdown("### Modifica Dettagli")

                    n_title = st.text_input("Titolo", key=k_tit)
                    r1, r2 = st.columns(2)
                    n_date = r1.text_input("Data", key=k_dat)
                    n_time = r2.text_input("Orario", key=k_tim)

                    r3, r4 = st.columns(2)
                    n_loc = r3.text_input("Luogo", key=k_loc)
                    n_venue = r4.text_input("Presso", key=k_ven)

                    n_addr = st.text_input("Indirizzo", key=k_add)
                    n_desc = st.text_area("Descrizione", key=k_des, height=100)

                    col_b1, col_b2, col_b3 = st.columns([1, 1, 1])

                    if col_b1.button("💾 Aggiorna", key=f"upd_{real_idx}"):
                        events_list[real_idx].update({
                            'title': n_title,
                            'date': n_date,
                            'time': n_time,
                            'location': n_loc,
                            'venue': n_venue,
                            'address': n_addr,
                            'description': n_desc
                        })

                        with open(DATA_FILE, 'w', encoding='utf-8') as f:
                            json.dump(events_list, f, ensure_ascii=False, indent=2)

                        st.success("Aggiornato!")
                        st.rerun()

                    # Pulsante RIMUOVI NEW (visibile solo se l'evento è nuovo)
                    if event.get('is_new'):
                        if col_b2.button("🚫 Rimuovi Etichetta", key=f"unew_{real_idx}", help="Rimuove l'etichetta NEW da questo evento"):
                            events_list[real_idx]['is_new'] = False
                            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                                json.dump(events_list, f, ensure_ascii=False, indent=2)
                            st.rerun()
                    else:
                         col_b2.write("") # Spacer se non c'è il pulsante

                    if col_b3.button("🗑️ Elimina", key=f"del_{real_idx}", type="primary"):
                        events_list.pop(real_idx)
                        with open(DATA_FILE, 'w', encoding='utf-8') as f:
                            json.dump(events_list, f, ensure_ascii=False, indent=2)
                        st.rerun()

# --- TAB 3: EXPORT ---
with tab3:
    st.subheader("Generazione Documento")
    # Usa events_list invece di session_state
    events_list_exp = st.session_state.get('events', [])
    st.write(f"Eventi pronti per la stampa: **{len(events_list_exp)}**")
    
    
    col_opts1, col_opts2 = st.columns(2)
    with col_opts1:
        export_mode_sel = st.radio("Stile Documento", ["Standard (Foto + Testo)", "Minimal (Solo Foto)"])
    with col_opts2:
        st.write("") # Spacer
        st.write("") 
        show_borders_opt = st.checkbox("Mostra bordi tabella", value=True)

    export_mode = "minimal" if "Minimal" in export_mode_sel else "standard"

    if st.button("📥 Genera Word", type="primary"):
        if not events_list_exp:
            st.error("Nessun evento da stampare!")
        else:
            with st.spinner("Creazione documento Word in corso..."):
                gen = WordGenerator()
                out_path = os.path.join(OUTPUT_DIR, doc_name)
                # Passiamo la lista ordinata e le opzioni
                gen.generate_from_data(
                    events_list_exp, 
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
