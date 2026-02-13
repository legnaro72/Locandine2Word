import streamlit as st
import os
import json
import re
import zipfile
import io
import base64
from github_manager import GithubManager
from datetime import datetime
from PIL import Image
from ocr_engine import LocandineOCR
from word_generator import WordGenerator
import dateparser
import pandas as pd
import altair as alt
try:
    from streamlit_mic_recorder import speech_to_text
except ImportError:
    speech_to_text = None  # Fallback gracefully
    
@st.cache_data(show_spinner=False)
def cached_ocr(image_path):
    return st.session_state.ocr_engine.analyze_poster(image_path)

# --- FUNZIONE HELPER AUDIO (Dall'esempio funzionante) ---
def get_base64_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

# Caricamento anticipato della risorsa audio
audio_base64 = get_base64_file("audio.mp3")

# --- STREAMLIT IMAGE WIDTH PARAMETER ---
# Usa il parametro moderno 'width' (valido per st.image(), NON per button/download_button)
IMG_WIDTH_ARG = {"width": "stretch"}

# --- FUNZIONI DI SUPPORTO ---
def normalize_date_to_italian(raw_date):
    """Normalizza date tipo 15/01/2026 o 15 GENNAIO 2026"""
    if not raw_date:
        return ""

    IT_MONTHS = {
        "GENNAIO": "01", "FEBBRAIO": "02", "MARZO": "03",
        "APRILE": "04", "MAGGIO": "05", "GIUGNO": "06",
        "LUGLIO": "07", "AGOSTO": "08", "SETTEMBRE": "09",
        "OTTOBRE": "10", "NOVEMBRE": "11", "DICEMBRE": "12"
    }

    raw_date = raw_date.upper().strip()

    # Caso 15/01/2026
    m = re.match(r"(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{4})", raw_date)
    if m:
        d, mth, y = m.groups()
        return f"{int(d)} {list(IT_MONTHS.keys())[int(mth)-1]} {y}"

    # Caso 15 GENNAIO 2026
    for month_name in IT_MONTHS:
        if month_name in raw_date:
            parts = raw_date.split()
            if len(parts) >= 3:
                return f"{parts[0]} {month_name} {parts[-1]}"

    return raw_date


def save_optimized_image(input_source, save_path, max_width=1200):
    """
    Ridimensiona e comprime un'immagine per risparmiare spazio e velocizzare il cloud.
    input_source: può essere un UploadedFile o un percorso (stringa).
    """
    # 🚀 Se l'immagine esiste già, non rifarla
    if os.path.exists(save_path):
        return True

    try:
        #from PIL import Image
        img = Image.open(input_source)
        # Conversione RGB per salvare in JPEG (gestisce PNG/RGBA)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        w, h = img.size
        if w > max_width:
            new_h = int(h * (max_width / w))
            img = img.resize((max_width, new_h), Image.LANCZOS)

        
        # Salva con compressione (qualità 80 è ottima per OCR)
        img.save(save_path, "JPEG", quality=80, optimize=True)
        return True
    except Exception as e:
        return False

# --- FUNZIONE DI PARSING INTELLIGENTE MIGLIORATA ---
def parse_event_text(text):
    """
    Analizza il testo OCR e lo suddivide nei campi specifici con le seguenti regole:
    1. Data: cerca pattern tipo "gg mese yyyy" (es: 15 GENNAIO 2026)
    2. Ora: cerca pattern tipo "hh:mm" o "hh.mm" (es: 18:30 o 18.30)
    3. Indirizzo: tutto ciò che segue "via", "piazza", "corso", etc.
    4. Presso: tutto ciò che segue la parola "presso"
    5. Descrizione: SEMPRE il testo OCR completo come backup
    6. Luogo: la città/zona (dopo il trattino nella prima riga)
    """
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

    # --- 1. ESTRAZIONE DATA (Pattern: gg mese yyyy) ---
    # Cerca pattern come: "15 GENNAIO 2026", "15 gennaio 2026", "15/01/2026"
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
    
    # Se non troviamo l'anno, aggiungi 2026 di default
    if not data['date']:
        # Cerca almeno giorno + mese
        date_partial = re.search(r'\b(\d{1,2}\s+(?:GENNAIO|FEBBRAIO|MARZO|APRILE|MAGGIO|GIUGNO|LUGLIO|AGOSTO|SETTEMBRE|OTTOBRE|NOVEMBRE|DICEMBRE))\b', text, re.IGNORECASE)
        if date_partial:
            raw_date = date_partial.group(1).strip() + " 2026"
            data['date'] = normalize_date_to_italian(raw_date)

    # --- 2. ESTRAZIONE ORA (Pattern: hh:mm o hh.mm) ---
    # Cerca pattern come: "18:30", "18.30", "Ore 18:30", "h 18.30"
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

    # --- 3. ESTRAZIONE LUOGO (Dalla prima riga dopo eventuale data) ---
    # Di solito è: "LUNEDÌ 15 GENNAIO 2026 - GENOVA"
    first_line = lines[0]
    # Rimuove giorno settimana
    clean_first = re.sub(r'^(?:LUNED[ÌI]|MARTED[ÌI]|MERCOLED[ÌI]|GIOVED[ÌI]|VENERD[ÌI]|SABATO|DOMENICA)\s*', '', first_line, flags=re.IGNORECASE).strip()
    
    # Cerca il trattino che separa data da luogo
    parts = re.split(r'\s*[–\-]\s*', clean_first, maxsplit=1)
    if len(parts) > 1:
        data['location'] = parts[1].strip()

    # --- 4. ESTRAZIONE INDIRIZZO (tutto dopo via/piazza/corso) ---
    # Cerca tutto ciò che segue "Via", "Piazza", "Corso", "Vico", "Largo", "Strada"
    address_patterns = [
        r'(?:Via|Vico|Piazza|Corso|Largo|Strada)\s+[^\n]+',
    ]
    
    for pattern in address_patterns:
        addr_match = re.search(pattern, text, re.IGNORECASE)
        if addr_match:
            # Estrai la riga completa
            addr_full = addr_match.group(0).strip()
            # Pulisci eventuale "- Ore" o altri separatori alla fine
            addr_full = re.sub(r'\s*[-–]\s*(?:Ore|ore).*$', '', addr_full).strip()
            data['address'] = addr_full
            break

    # --- 5. ESTRAZIONE PRESSO/VENUE (parole chiave comuni) ---
    # Cerca "presso" oppure parole chiave come: sala, circolo, teatro, auditorium, centro, biblioteca, etc.
    venue_patterns = [
        # Con "presso"
        r'presso\s+([^\n]+?)(?:\s*[-–]\s*(?:Ore|ore|h|H)|$)',
        r'presso\s+([^\n]+)',
        # Senza "presso" - cerca parole chiave comuni e continua fino a newline o fermati prima di Via/Ore
        r'\b(Sala\s+[^\n]+?)(?=\s*$|\s*\n|(?:\s+(?:Via|Piazza|Corso|Vico|Ore|ore|h|H)\s))',
        r'\b(Circolo\s+[^\n]+?)(?=\s*$|\s*\n|(?:\s+(?:Via|Piazza|Corso|Vico|Ore|ore|h|H)\s))',
        r'\b(Teatro\s+[^\n]+?)(?=\s*$|\s*\n|(?:\s+(?:Via|Piazza|Corso|Vico|Ore|ore|h|H)\s))',
        r'\b(Auditorium\s+[^\n]+?)(?=\s*$|\s*\n|(?:\s+(?:Via|Piazza|Corso|Vico|Ore|ore|h|H)\s))',
        r'\b(Centro\s+[^\n]+?)(?=\s*$|\s*\n|(?:\s+(?:Via|Piazza|Corso|Vico|Ore|ore|h|H)\s))',
        r'\b(Biblioteca\s+[^\n]+?)(?=\s*$|\s*\n|(?:\s+(?:Via|Piazza|Corso|Vico|Ore|ore|h|H)\s))',
        r'\b(Cinema\s+[^\n]+?)(?=\s*$|\s*\n|(?:\s+(?:Via|Piazza|Corso|Vico|Ore|ore|h|H)\s))',
        r'\b(Palazzo\s+[^\n]+?)(?=\s*$|\s*\n|(?:\s+(?:Via|Piazza|Corso|Vico|Ore|ore|h|H)\s))',
        r'\b(Aula\s+[^\n]+?)(?=\s*$|\s*\n|(?:\s+(?:Via|Piazza|Corso|Vico|Ore|ore|h|H)\s))',
        r'\b(Salone\s+[^\n]+?)(?=\s*$|\s*\n|(?:\s+(?:Via|Piazza|Corso|Vico|Ore|ore|h|H)\s))',
    ]
    
    for pattern in venue_patterns:
        presso_match = re.search(pattern, text, re.IGNORECASE)
        if presso_match:
            venue_text = presso_match.group(1).strip()
            # Pulisci eventuale "- Ore" o orari alla fine
            venue_text = re.sub(r'\s*[-–]\s*(?:Ore|ore|h|H).*$', '', venue_text).strip()
            venue_text = re.sub(r'\s*\d{1,2}[:\.]\d{2}.*$', '', venue_text).strip()
            # Rimuovi anche "Via"/"Piazza" se catturati per errore
            venue_text = re.sub(r'\s*[-–]?\s*(?:Via|Piazza|Corso|Vico)\s+.*$', '', venue_text, flags=re.IGNORECASE).strip()
            data['venue'] = venue_text
            break

    # --- 6. TITOLO AUTOMATICO ---
    if data['date'] and data['location']:
        data['title'] = f"{data['date']} – {data['location']}"
    else:
        # Fallback: primi 50 caratteri del testo
        data['title'] = text[:50].replace('\n', ' ').strip() + "..." if text else "Nuovo Evento"
    
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
st.set_page_config(page_title="Locandine2Word", page_icon="🎭", layout="wide", initial_sidebar_state="collapsed")

# --- FUNZIONE HELPER AUDIO (Base64 Robust) ---
@st.cache_data(show_spinner=False)
def get_audio_base64_robust():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Provo prima i file alternativi che vedo nella tua lista
    possible_names = ["audioGuns.mp3", "audioAltamenteMia.mp3", "audio.mp3", "Audio.mp3"]
    
    for name in possible_names:
        file_path = os.path.join(base_dir, name)
        if os.path.exists(file_path):
            # Controllo che il file NON sia vuoto ( > 1KB )
            if os.path.getsize(file_path) > 1024:
                with open(file_path, "rb") as f:
                    return base64.b64encode(f.read()).decode()
    return None

# --- CARICAMENTO AUDIO CON SPINNER ---
with st.spinner("Caricamento audio di sottofondo..."):
    audio_base64 = get_audio_base64_robust()
    if audio_base64 and not st.session_state.get('app_entered'):
        st.toast("✅ Audio Pronto!", icon="🎵")

if "audio_enabled" not in st.session_state:
    st.session_state.audio_enabled = True

# --- AUDIO PLAYER (REPLICA ESEMPIO "EMAIL EXTRACTOR") ---
# --- AUDIO DISATTIVATO QUI (SPOSTATO DOPO) ---
if False: # audio_base64:
    with st.sidebar:
        st.markdown(f"<h3 style='text-align:center;'>🎵 MUSIC PLAYER</h3>", unsafe_allow_html=True)
        audio_on = st.toggle("🔊 Musica di sottofondo", value=True)
        

        if audio_on:
            # STATUS DINAMICO: Cambia quando entri nell'app.
            # Questo garantisce che Streamlit RICREI il player dopo il click "ENTRA", sbloccando l'autoplay.
            status = "active" if st.session_state.get("app_entered") else "waiting"
            
            audio_html = f"""
                <audio autoplay loop data-status="{status}">
                    <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
                    Your browser does not support the audio element.
                </audio>
            """
            st.markdown(audio_html, unsafe_allow_html=True)
            st.caption("🎶 Musica attiva")
        else:
            st.caption("🔇 Musica disattivata")

# (Blocco else rimosso)

# --- SPLASH SCREEN INIZIALE (NECESSARIA PER SBLOCCO AUDIO BROWSER) ---
if 'app_entered' not in st.session_state:
    st.session_state.app_entered = False

if not st.session_state.app_entered:
    st.markdown("""
    <style>
        .splash-container { text-align: center; margin-top: 50px; }
        .splash-title { font-size: 3rem; font-weight: bold; color: #667eea; margin-bottom: 20px; }
        .splash-text { font-size: 1.2rem; color: #555; margin-bottom: 40px; }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="splash-container">', unsafe_allow_html=True)
        
        if os.path.exists("LogoNOConfiniTrasparente.png"):
             st.image("LogoNOConfiniTrasparente.png", width=300)
        else:
            st.markdown('<div class="splash-title">🎭 Locandine2Word</div>', unsafe_allow_html=True)
            
        st.markdown('<div class="splash-text">Il tuo assistente intelligente per la gestione eventi.</div>', unsafe_allow_html=True)
        
        if st.button("🚀 ENTRA E AVVIA APPLICAZIONE", type="primary"):
            st.session_state.app_entered = True
            st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Blocca esecuzione qui finché non si clicca il bottone
    st.stop()


# --- AUDIO PLAYER (AUTOPLAY SICURO) ---
# Eseguito solo dopo Entra
if audio_base64:
    with st.sidebar:
        st.markdown(f"<h3 style='text-align:center;'>🎵 MUSIC PLAYER</h3>", unsafe_allow_html=True)
        # Toggle semplice (identico a esempio)
        audio_on = st.toggle("🔊 Musica di sottofondo", value=True)
        
        if audio_on:
            # HTML Audio PURO - Identico all'esempio
            audio_html = f"""
                <audio autoplay loop>
                    <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
                    Your browser does not support the audio element.
                </audio>
            """
            st.markdown(audio_html, unsafe_allow_html=True)
            st.caption("🎶 Musica attiva")
        else:
            st.caption("🔇 Musica disattivata")



# --- INIZIALIZZAZIONE DATI ---
LOCANDINE_FILE = "locandine.json"
DATA_FILE = "data.json"
UPLOADS_DIR = "uploads"
OUTPUT_DIR = "output"
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- CONFIGURAZIONE GITHUB ---
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", None)
GITHUB_REPO = "legnaro72/Locandine2Word"

if 'github_manager' not in st.session_state and GITHUB_TOKEN:
    st.session_state.github_manager = GithubManager(GITHUB_TOKEN, GITHUB_REPO)

# --- AUTO-SYNC CLOUD ALL'AVVIO ---
if GITHUB_TOKEN and 'data_initialized' not in st.session_state:
    with st.spinner("Sincronizzazione dati dal cloud..."):
        try:
            # Tenta di scaricare l'ultimo stato da GitHub
            zip_content = st.session_state.github_manager.download_backup()
            st.session_state.github_manager.restore_from_zip(zip_content)
            st.toast("✅ Dati sincronizzati dal cloud!", icon="☁️")
        except Exception as e:
            # Se è il primo avvio assoluto o il backup non esiste, ignoriamo l'errore
            if "404" not in str(e):
                st.info("Avviso: Nessun backup cloud trovato o sincronizzazione non riuscita. Caricamento dati locali.")
    st.session_state.data_initialized = True

if 'events' not in st.session_state:
    st.session_state.events = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                content = json.load(f)
                if isinstance(content, list):
                    # Normalizzazione automatica al caricamento
                    for ev in content:
                        if 'image_path' in ev:
                            ev['image_path'] = ev['image_path'].replace('\\', '/')
                        if 'date' in ev:
                            ev['date'] = normalize_date_to_italian(ev['date'])
                    st.session_state.events = content
        except Exception as e:
            st.error(f"Errore caricamento database locale: {e}")


if 'ocr_engine' not in st.session_state:
    st.session_state.ocr_engine = LocandineOCR()

# --- UI PRINCIPALE (CARICATA SOLO DOPO ENTRATA) ---
st.markdown('<h1 class="main-header">🎭 Locandine2Word</h1>', unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Opzioni")
    
    st.divider()
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
            # st.rerun()

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
            # st.rerun()

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




tab4, tab1, tab2, tab3 = st.tabs(["📊 Statistiche", "📤 Carica & Analizza", "📋 Modifica Dati", "📖 Export Word"])

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
        # --- PROCESSO MASSIVO ---
        if st.button("🔍 Analizza tutte le locandine (OCR)", type="secondary"):
            with st.spinner("Analisi di tutte le locandine in corso..."):
                for idx, uploaded_file in enumerate(uploaded_files):
                    # Salva immagine ottimizzata
                    image_path = os.path.join(UPLOADS_DIR, uploaded_file.name)
                    save_optimized_image(uploaded_file, image_path)
                    
                    # Se non è già stato processato
                    if f'temp_data_{idx}' not in st.session_state:
                        json_match = prefill_map.get(uploaded_file.name)
                        if json_match:
                            raw_text_json = json_match.get('text', '')
                            if raw_text_json:
                                parsed = parse_event_text(raw_text_json)
                                for field in ['title', 'date', 'time', 'location', 'venue', 'address', 'description']:
                                    if json_match.get(field): parsed[field] = json_match[field]
                            else:
                                parsed = {k: json_match.get(k, '') for k in ['title', 'date', 'time', 'location', 'venue', 'address', 'description']}
                        else:
                            raw_ocr = cached_ocr(image_path)
                            parsed = parse_event_text(raw_ocr.get('full_text', ''))
                        
                        parsed['image_path'] = f"{UPLOADS_DIR}/{uploaded_file.name}"
                        st.session_state[f'temp_data_{idx}'] = parsed
                st.success("Tutte le immagini sono state analizzate! Controlla i moduli sotto.")
                # st.rerun()

        for idx, uploaded_file in enumerate(uploaded_files):
            with st.expander(f"🖼️ {uploaded_file.name}", expanded=True):
                col1, col2 = st.columns([1, 2])
                
                # Salvataggio e Anteprima Immagine (Ottimizzata)
                image_path = os.path.join(UPLOADS_DIR, uploaded_file.name)
                save_optimized_image(uploaded_file, image_path)
                
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
                                # USA DATI JSON: Parserizza il testo se presente, o usa i campi pronti
                                raw_text_json = json_match.get('text', '')
                                if raw_text_json:
                                    parsed = parse_event_text(raw_text_json)
                                    # Se il JSON ha comunque dei campi specifici pronti, usa quelli come override
                                    for field in ['title', 'date', 'time', 'location', 'venue', 'address', 'description']:
                                        if json_match.get(field):
                                            parsed[field] = json_match[field]
                                else:
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
                            # st.rerun() # Refresh per mostrare il form sotto

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
        # --- SISTEMA DI FILTRAGGIO AVANZATO ---
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            status_filter = st.selectbox(
                "🔍 1. Filtra per Stato",
                ["Tutto (All)", "Solo i NEW", "Attivi (Futuri + NEW)", "Solo Scaduti"],
                key="mgr_status_filter"
            )
        
        with col_f2:
            geo_filter = st.selectbox(
                "📍 2. Filtra per Luogo",
                ["Tutti", "LIGURIA", "TOSCANA", "GENOVA", "LA SPEZIA", "SAVONA", "IMPERIA", "MASSA"],
                key="mgr_geo_filter"
            )
        
        search_query = st.text_input("📝 Cerca nel testo (Titolo, Luogo, Descrizione...)", "").strip().lower()
        
        # Logica di filtraggio combinata
        now = datetime.now()
        
        # Mappatura Province -> Regioni per il filtro (già presente ma definita qui per sicurezza)
        PROV_TO_REG = {
            'GENOVA': 'LIGURIA', 'LA SPEZIA': 'LIGURIA', 'SAVONA': 'LIGURIA', 'IMPERIA': 'LIGURIA',
            'MASSA': 'TOSCANA'
        }

        # Ri-indicizzazione degli eventi filtrati per la visualizzazione corretta
        # Manteniamo l'indice originale per permettere l'aggiornamento corretto
        indexed_view_events = []
        for i, ev in enumerate(st.session_state.events):
            # A. Controllo Stato
            m_s = True
            if status_filter == "Solo i NEW": m_s = ev.get('is_new', False)
            elif status_filter == "Attivi (Futuri + NEW)": m_s = WordGenerator.get_sort_date(ev).date() >= now.date() or ev.get('is_new', False)
            elif status_filter == "Solo Scaduti": m_s = WordGenerator.get_sort_date(ev).date() < now.date() and not ev.get('is_new', False)
            
            # B. Controllo Luogo
            m_g = True
            if geo_filter != "Tutti":
                prov = WordGenerator.get_province(ev)
                if geo_filter in ["LIGURIA", "TOSCANA"]:
                    m_g = (PROV_TO_REG.get(prov, "ALTRO") == geo_filter)
                else:
                    m_g = (prov == geo_filter)
            
            # C. Controllo Ricerca Testuale
            m_t = True
            if search_query:
                content = (ev.get('title', '') + ev.get('description', '') + ev.get('location', '') + ev.get('venue', '')).lower()
                m_t = search_query in content
            
            if m_s and m_g and m_t:
                indexed_view_events.append((i, ev))

        sorted_view_events = sorted(indexed_view_events, key=lambda x: WordGenerator.get_sort_date(x[1]))
        events_list_view = [e[1] for e in sorted_view_events]
        
        if not events_list_view:
            st.warning(f"Nessun evento trovato con i filtri selezionati.")
        
        # --- STATISTICHE E CONTROLLI ---
        total_ev = len(events_list_view)
        st.write(f"📊 Eventi visualizzati: **{total_ev}** (su {len(events_list)} totali)")

        # Controllo Duplicati (Basato esclusivamente sul Percorso Immagine)
        # ... (rest of the duplicate logic) ...
        image_counts = {}
        for ev in events_list_view:
            img_path = ev.get('image_path', '').strip()
            if img_path:
                image_counts[img_path] = image_counts.get(img_path, 0) + 1
        
        duplicate_paths = {path for path, count in image_counts.items() if count > 1}
        
        if duplicate_paths:
            total_dup_events = sum(image_counts[p] for p in duplicate_paths)
            st.error(f"🚨 AVVISO: Trovate **{len(duplicate_paths)}** immagini usate in più eventi!")
        else:
            st.success("✅ Nessun duplicato rilevato nei risultati correnti.")

        # --- BOTTONI DI AZIONE ---
        col_m1, col_m2, col_m3, col_m4 = st.columns([1.5, 1, 1, 1])
        
        with col_m2:
            if st.button("🏷️ Rinomina Auto"):
                for event in events_list: # Azione globale sul database reale
                    raw_date = event.get('date', '').strip()
                    location = event.get('location', '').strip()
                    if raw_date:
                        clean_date = normalize_date_to_italian(raw_date)
                        event['date'] = clean_date
                        #import dateparser
                        dt = dateparser.parse(clean_date, languages=['it'])
                        if dt:
                            day_map_safe = {0: "LUNEDI'", 1: "MARTEDI'", 2: "MERCOLEDI'", 3: "GIOVEDI'", 4: "VENERDI'", 5: "SABATO", 6: "DOMENICA"}
                            weekday = day_map_safe.get(dt.weekday(), "")
                            event['title'] = f"{weekday} {clean_date} - {location}" if location else f"{weekday} {clean_date}"
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(events_list, f, ensure_ascii=False, indent=2)
                st.success("Titoli aggiornati!")
                # st.rerun()

        with col_m3:
            if st.button("✨ Rimuovi NEW"):
                st.session_state.confirm_clear_new = True
            
            if st.session_state.get('confirm_clear_new'):
                st.warning("⚠️ Confermi di voler rimuovere l'etichetta NEW da TUTTI gli eventi?")
                c_y, c_n = st.columns(2)
                if c_y.button("✅ Confermo", key="y_clear_new"):
                    for ev in events_list:
                        ev['is_new'] = False
                    with open(DATA_FILE, 'w', encoding='utf-8') as f:
                        json.dump(events_list, f, ensure_ascii=False, indent=2)
                    st.session_state.confirm_clear_new = False
                    st.success("Etichette NEW rimosse!")
                    # st.rerun()
                if c_n.button("❌ Annulla", key="n_clear_new"):
                    st.session_state.confirm_clear_new = False
                    # st.rerun()

        with col_m4:
            if st.button("🔄 Riordina Date"):
                events_list.sort(key=WordGenerator.get_sort_date)
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(events_list, f, ensure_ascii=False, indent=2)
                st.success("Eventi riordinati!")
                # st.rerun()

        # Ri-indicizzazione degli eventi filtrati per la visualizzazione corretta
        # Manteniamo l'indice originale per permettere l'aggiornamento corretto
        indexed_view_events = []
        for i, ev in enumerate(st.session_state.events):
            # A. Stato
            m_s = True
            if status_filter == "Solo i NEW": m_s = ev.get('is_new', False)
            elif status_filter == "Attivi (Futuri + NEW)": m_s = WordGenerator.get_sort_date(ev).date() >= now.date() or ev.get('is_new', False)
            elif status_filter == "Solo Scaduti": m_s = WordGenerator.get_sort_date(ev).date() < now.date() and not ev.get('is_new', False)
            
            # B. Luogo
            m_g = True
            if geo_filter != "Tutti":
                prov = WordGenerator.get_province(ev)
                if geo_filter in ["LIGURIA", "TOSCANA"]: m_g = (PROV_TO_REG.get(prov, "ALTRO") == geo_filter)
                else: m_g = (prov == geo_filter)
            
            # C. Ricerca Testuale
            m_t = True
            if search_query:
                content = (ev.get('title', '') + ev.get('description', '') + ev.get('location', '') + ev.get('venue', '')).lower()
                m_t = search_query in content
            
            if m_s and m_g and m_t:
                indexed_view_events.append((i, ev))

        sorted_view_events = sorted(indexed_view_events, key=lambda x: WordGenerator.get_sort_date(x[1]))

        st.info("ℹ️ Gli eventi sono ordinati cronologicamente.")

        # -------- LOOP EVENTI --------
        now = datetime.now()
        for real_idx, event in sorted_view_events:
            # Calcolo scadenza
            is_expired = False
            ev_date = WordGenerator.get_sort_date(event)
            if ev_date != datetime.max and ev_date.date() < now.date():
                is_expired = True

            dup_icon = "👯 " if event.get('image_path', '').strip() in duplicate_paths else ""
            exp_icon = "🚫 SCADUTO " if is_expired else ""
            title_prefix = f"{dup_icon}{exp_icon}🆕 " if event.get('is_new') else f"{dup_icon}{exp_icon}"
            
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

                    # Selettore campo con etichette in Italiano
                    field_mapping_ui = {
                        'description': 'Descrizione',
                        'title': 'Titolo',
                        'location': 'Luogo',
                        'venue': 'Presso',
                        'address': 'Indirizzo',
                        'date': 'Data',
                        'time': 'Orario'
                    }
                    
                    selected_ui_label = st.selectbox(
                        "Campo da compilare con la voce",
                        options=list(field_mapping_ui.values()),
                        key=sel_key
                    )
                    
                    # Recupera la chiave tecnica dall'etichetta selezionata
                    final_field = [k for k, v in field_mapping_ui.items() if v == selected_ui_label][0]

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
                            # final_field è già calcolato sopra tramite la UI labels

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
                                # st.rerun()


                st.divider()

                c1, c2 = st.columns([1, 2])
                ###
                # Normalizzazione cross-platform
                image_path = os.path.normpath(event.get('image_path', ''))

                if image_path and os.path.exists(image_path):
                    c1.image(image_path, **IMG_WIDTH_ARG)
                else:
                    c1.error(f"Immagine non trovata: {image_path}")


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
                        # st.rerun()

                    # Pulsante RIMUOVI NEW (visibile solo se l'evento è nuovo)
                    if event.get('is_new'):
                        if col_b2.button("🚫 Rimuovi Etichetta", key=f"unew_{real_idx}", help="Rimuove l'etichetta NEW da questo evento"):
                            events_list[real_idx]['is_new'] = False
                            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                                json.dump(events_list, f, ensure_ascii=False, indent=2)
                            # st.rerun()
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
    events_list_all = st.session_state.get('events', [])
    
    # --- FILTRAGGIO ---
    st.markdown("#### 🔍 1. Filtra Eventi")
    filter_choice = st.radio(
        "Scegli quali eventi includere nell'export:",
        ["Tutti gli eventi", "Solo attivi (non scaduti)", "Solo i NEW", "Solo Provincia di Genova", "Solo Provincia di La Spezia"],
        horizontal=True
    )
    
    now = datetime.now()
    if filter_choice == "Solo attivi (non scaduti)":
        events_list_exp = [ev for ev in events_list_all if WordGenerator.get_sort_date(ev).date() >= now.date()]
    elif filter_choice == "Solo i NEW":
        events_list_exp = [ev for ev in events_list_all if ev.get('is_new')]
    elif filter_choice == "Solo Provincia di Genova":
        events_list_exp = [ev for ev in events_list_all if WordGenerator.get_province(ev) == "GENOVA"]
    elif filter_choice == "Solo Provincia di La Spezia":
        events_list_exp = [ev for ev in events_list_all if WordGenerator.get_province(ev) == "LA SPEZIA"]
    else:
        events_list_exp = events_list_all

    st.write(f"Eventi pronti per la stampa: **{len(events_list_exp)}**")
    st.divider()

    st.markdown("#### 🎨 2. Opzioni Stile")
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

# --- TAB 4: STATISTICHE ---
with tab4:
    st.subheader("📊 Analisi e Distribuzione Eventi")
    
    events_list_stats = st.session_state.get('events', [])
    
    if not events_list_stats:
        st.info("Nessun dato disponibile per le statistiche. Carica degli eventi per iniziare.")
    else:
        # Calcoli di base
        total_ev = len(events_list_stats)
        now = datetime.now()
        
        expired_count = 0
        new_count = 0
        active_count = 0
        
        for ev in events_list_stats:
            ev_date = WordGenerator.get_sort_date(ev)
            if ev.get('is_new'):
                new_count += 1
            
            if ev_date != datetime.max and ev_date.date() < now.date():
                expired_count += 1
            else:
                active_count += 1

        # Metriche principali
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Totale Eventi", total_ev)
        m2.metric("Attivi (Futuri)", active_count)
        m3.metric("Scaduti", expired_count)
        m4.metric("Nuovi (NEW)", new_count)
        
        st.divider()
        
        # Mappatura Province/Regioni (Stessa logica del WordGenerator)
        PROV_TO_REG = {
            'GENOVA': 'LIGURIA', 'LA SPEZIA': 'LIGURIA', 'SAVONA': 'LIGURIA', 
            'IMPERIA': 'LIGURIA', 'MASSA': 'TOSCANA'
        }
        
        stats_geo = {
            'LIGURIA': {'total': 0, 'provinces': {'GENOVA': 0, 'LA SPEZIA': 0, 'SAVONA': 0, 'IMPERIA': 0}},
            'TOSCANA': {'total': 0, 'provinces': {'MASSA': 0}},
            'ALTRO': {'total': 0, 'cities': {}}
        }

        # Elaborazione Geografica
        for ev in events_list_stats:
            prov_found = WordGenerator.get_province(ev)
            loc = ev.get('location', 'N/D').strip().upper()
            
            reg = PROV_TO_REG.get(prov_found)
            if reg:
                stats_geo[reg]['total'] += 1
                if prov_found in stats_geo[reg]['provinces']:
                    stats_geo[reg]['provinces'][prov_found] += 1
            else:
                stats_geo['ALTRO']['total'] += 1
                stats_geo['ALTRO']['cities'][loc] = stats_geo['ALTRO']['cities'].get(loc, 0) + 1

        # --- GRAFICI INTERATTIVI ---
        #import pandas as pd
        #import altair as alt

        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.markdown("#### 🌍 Distribuzione Regionale")
            reg_df = pd.DataFrame({
                "Regione": ["LIGURIA", "TOSCANA", "ALTRO"],
                "Eventi": [stats_geo['LIGURIA']['total'], stats_geo['TOSCANA']['total'], stats_geo['ALTRO']['total']]
            })
            # Rimuoviamo righe con 0 eventi per pulizia grafico
            reg_df = reg_df[reg_df["Eventi"] > 0]
            if not reg_df.empty:
                # Creazione Grafico a Torta (Donut) con Altair
                pie_chart = alt.Chart(reg_df).mark_arc(innerRadius=50).encode(
                    theta=alt.Theta(field="Eventi", type="quantitative"),
                    color=alt.Color(field="Regione", type="nominal", scale=alt.Scale(range=['#667eea', '#764ba2', '#ff9a9e'])),
                    tooltip=['Regione', 'Eventi']
                ).properties(height=300)
                
                st.altair_chart(pie_chart, width="stretch")
            else:
                st.write("Nessun dato regionale.")

        with col_g2:
            st.markdown("#### 🗺️ Dettaglio Province")
            prov_data = []
            for reg in ['LIGURIA', 'TOSCANA']:
                for p, count in stats_geo[reg]['provinces'].items():
                    if count > 0:
                        prov_data.append({"Provincia": p, "Eventi": count, "Regione": reg})
            
            if prov_data:
                prov_df = pd.DataFrame(prov_data).sort_values(by="Eventi", ascending=False)
                
                # Usa Altair con colori differenziati per regione
                prov_chart = alt.Chart(prov_df).mark_bar().encode(
                    x=alt.X('Provincia:N', sort='-y', title='Provincia'),
                    y=alt.Y('Eventi:Q', title='Numero Eventi'),
                    color=alt.Color('Regione:N', 
                                   scale=alt.Scale(
                                       domain=['LIGURIA', 'TOSCANA'],
                                       range=['#667eea', '#ff9a9e']  # Viola per LIGURIA, Rosa per TOSCANA
                                   ),
                                   legend=alt.Legend(title="Regione")),
                    tooltip=['Provincia', 'Regione', 'Eventi']
                ).properties(height=300)
                
                st.altair_chart(prov_chart, width="stretch")
            else:
                st.write("Nessun dato provinciale.")

        st.divider()
        
        # --- SECONDA RIGA GRAFICI ---
        col_g3, col_g4 = st.columns([2, 1])
        
        with col_g3:
            st.markdown("#### 📍 Top 10 Località")
            all_locations = {}
            for ev in events_list_stats:
                loc = ev.get('location', 'N/D').strip().upper()
                all_locations[loc] = all_locations.get(loc, 0) + 1
            
            loc_df = pd.DataFrame([{"Località": k, "Eventi": v} for k, v in all_locations.items()])
            loc_df = loc_df.sort_values(by="Eventi", ascending=False).head(10)
            
            if not loc_df.empty:
                # Usa Altair per mantenere l'ordinamento corretto
                loc_chart = alt.Chart(loc_df).mark_bar(color='#667eea').encode(
                    x=alt.X('Eventi:Q', title='Numero Eventi'),
                    y=alt.Y('Località:N', sort='-x', title='Località'),
                    tooltip=['Località', 'Eventi']
                ).properties(height=300)
                
                st.altair_chart(loc_chart, width="stretch")
            else:
                st.write("Dati non sufficienti.")

        with col_g4:
            st.markdown("#### 📊 Stato Archivio")
            status_df = pd.DataFrame({
                "Stato": ["Attivi", "Scaduti", "NEW"],
                "Conteggio": [active_count, expired_count, new_count]
            })
            st.data_editor(
                status_df,
                column_config={
                    "Conteggio": st.column_config.NumberColumn(
                        format="%d 🎭",
                    ),
                },
                hide_index=True,
                width="stretch"
            )

        st.divider()
        st.info("💡 I grafici si aggiornano automaticamente ogni volta che modifichi o aggiungi un evento.")

        # --- PULIZIA E OTTIMIZZAZIONE MANUALE ---
        with st.expander("🛠️ Strumenti Avanzati (Manutenzione)"):
            st.write("Usa questi strumenti per tenere l'app veloce e leggera.")
            if st.button("⚡ Ottimizza Archivio Esistente", help="Ridimensiona tutte le immagini caricate in precedenza per occupare meno spazio."):
                files = [f for f in os.listdir(UPLOADS_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                if not files:
                    st.warning("Nessuna immagine trovata da ottimizzare.")
                else:
                    processed = 0
                    errors = 0
                    pbar = st.progress(0)
                    for i, filename in enumerate(files):
                        img_path = os.path.join(UPLOADS_DIR, filename)
                        if save_optimized_image(img_path, img_path):
                            processed += 1
                        else:
                            errors += 1
                        pbar.progress((i + 1) / len(files))
                    st.success(f"✅ Ottimizzazione completata! Processate {processed} immagini. (Fallite: {errors})")
                    st.info("Nota: Al prossimo salvataggio su GitHub, il backup sarà molto più leggero.")
