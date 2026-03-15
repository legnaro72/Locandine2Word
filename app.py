
import streamlit as st
import os
import json
import re
import zipfile
import io
import base64
import math
import warnings
from github_manager import GithubManager
from datetime import datetime
from PIL import Image
from ocr_engine import LocandineOCR
from word_generator import WordGenerator
from album_generator import AlbumGenerator, create_single_sticker
from gdrive_uploader import render_credentials_sidebar, upload_pdf_to_gdrive, GDRIVE_TARGET_FILENAME

# Suppress PyTorch warnings about pin_memory when no GPU is present
warnings.filterwarnings("ignore", message=".*'pin_memory' argument is set as true but no accelerator is found.*")

# Versione: 1.0.1 (Forza reload per reset_city_cache)

def safe_reset_city_cache():
    """Chiama reset_city_cache se disponibile, altrimenti logga errore."""
    if hasattr(WordGenerator, 'reset_city_cache'):
        WordGenerator.reset_city_cache()
    else:
        st.warning("⚠️ Avviso: Modulo WordGenerator non aggiornato. Riavviare l'applicazione Streamlit se il problema persiste.")

def safe_media_rerun():
    """Tenta di pulire la cache dei media di Streamlit prima di riavviare per evitare MediaFileStorageError."""
    try:
        from streamlit.runtime import get_instance
        runtime = get_instance()
        if hasattr(runtime, "media_file_mgr"):
            runtime.media_file_mgr.clear()
    except:
        pass
    
    # Rimuoviamo stati che contengono binari o path di immagini potenzialmente sparite
    keys_to_clear = ['album_cover', 'album_pages', 'album_zip', 'album_pdf', 'backup_zip', 'events', 'data_initialized']
    for k in keys_to_clear:
        if k in st.session_state:
            try: del st.session_state[k]
            except: pass
            
    # Piccola attesa per rilascio file handle prima del ricaricamento
    import time
    time.sleep(0.8)
    st.rerun()
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
@st.cache_data(show_spinner=False)
def get_base64_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

# NOTA: Caricamento audio rimosso qui — avviene una sola volta in get_audio_base64_robust() (cachata)

# --- STREAMLIT IMAGE WIDTH PARAMETER ---
# Usa il parametro moderno 'width' (valido per st.image(), NON per button/download_button)
IMG_WIDTH_ARG = {"width": "stretch"}

# --- COSTANTI DI MODULO (evita ricalcolo ad ogni chiamata) ---
IT_MONTHS = {
    "GENNAIO": "01", "FEBBRAIO": "02", "MARZO": "03",
    "APRILE": "04", "MAGGIO": "05", "GIUGNO": "06",
    "LUGLIO": "07", "AGOSTO": "08", "SETTEMBRE": "09",
    "OTTOBRE": "10", "NOVEMBRE": "11", "DICEMBRE": "12"
}
IT_MONTHS_LIST = list(IT_MONTHS.keys())

PROV_TO_REG = {
    'GENOVA': 'LIGURIA', 'LA SPEZIA': 'LIGURIA', 'SAVONA': 'LIGURIA', 'IMPERIA': 'LIGURIA',
    'MASSA': 'TOSCANA', 'LUCCA': 'TOSCANA',
    'ALESSANDRIA': 'PIEMONTE', 'ASTI': 'PIEMONTE'
}

# --- FUNZIONI DI SUPPORTO ---
def normalize_date_to_italian(raw_date):
    """Normalizza date tipo 15/01/2026 o 15 GENNAIO 2026"""
    if not raw_date:
        return ""

    raw_date = raw_date.upper().strip()

    # Caso 15/01/2026
    m = re.match(r"(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{4})", raw_date)
    if m:
        d, mth, y = m.groups()
        return f"{int(d)} {IT_MONTHS_LIST[int(mth)-1]} {y}"

    # Caso 15 GENNAIO 2026
    for month_name in IT_MONTHS:
        if month_name in raw_date:
            parts = raw_date.split()
            if len(parts) >= 3:
                return f"{parts[0]} {month_name} {parts[-1]}"

    return raw_date


def save_optimized_image(input_source, save_path, max_width=1200):
    """
    Ridimensiona e comprime un'immagine forzando il formato JPEG.
    """
    try:
        img = Image.open(input_source)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        w, h = img.size
        if w > max_width:
            new_h = int(h * (max_width / w))
            img = img.resize((max_width, new_h), Image.LANCZOS)
        
        img.save(save_path, "JPEG", quality=80, optimize=True)
        return True
    except:
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
    st.session_state.audio_enabled = False

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
        # Toggle disattivato di default
        audio_on = st.toggle("🔊 Musica di sottofondo", value=False)
        
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

# Crea directory solo alla prima esecuzione (evita IO inutile ad ogni rerun)
if 'dirs_created' not in st.session_state:
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    st.session_state.dirs_created = True

# Helper per salvataggio pulito (senza metadati temporanei)
def save_events_to_disk():
    if 'events' in st.session_state:
        # Crea una copia pulita senza i metadati _dt e _prov
        clean_events = []
        for ev in st.session_state.events:
            clean_ev = {k: v for k, v in ev.items() if not k.startswith('_')}
            clean_events.append(clean_ev)
            
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(clean_events, f, ensure_ascii=False, indent=2)
        # Marca metadata come sporco per forzare ricalcolo al prossimo refresh
        st.session_state['metadata_dirty'] = True

# Helper per refresh dei dati calcolati (da usare dopo edit/add)
# Usa un flag 'metadata_dirty' per evitare ricalcoli inutili ad ogni rerun
def refresh_event_metadata():
    if 'events' in st.session_state:
        # Ricalcola solo se serve (nuovi eventi senza _dt o flag dirty)
        needs_refresh = st.session_state.get('metadata_dirty', False)
        if not needs_refresh:
            # Controlla se c'è almeno un evento senza metadati
            for ev in st.session_state.events:
                if '_dt' not in ev or '_prov' not in ev:
                    needs_refresh = True
                    break
        
        if needs_refresh:
            for ev in st.session_state.events:
                # Sovrascrive sempre per applicare la nuova logica oraria
                ev['_dt'] = WordGenerator.get_sort_date(ev)
                ev['_prov'] = WordGenerator.get_province(ev)
            st.session_state['metadata_dirty'] = False

# --- CONFIGURAZIONE GITHUB ---
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", None)
GITHUB_REPO = "legnaro72/Locandine2Word"

if 'github_manager' not in st.session_state and GITHUB_TOKEN:
    try:
        st.session_state.github_manager = GithubManager(GITHUB_TOKEN, GITHUB_REPO)
    except Exception as e:
        st.warning(f"⚠️ Impossibile connettersi a GitHub all'avvio. Funzionalità cloud disabilitate. Errore: {e}")
        st.session_state.github_manager = None

# --- AUTO-SYNC CLOUD ALL'AVVIO (INTELLIGENTE) ---
if GITHUB_TOKEN and 'data_initialized' not in st.session_state:
    if st.session_state.get('github_manager'):
        with st.spinner("Sincronizzazione dati dal cloud..."):
            try:
                # 1. Conta eventi locali PRIMA di sovrascrivere
                local_event_count = 0
                if os.path.exists(DATA_FILE):
                    try:
                        with open(DATA_FILE, 'r', encoding='utf-8') as f:
                            local_data = json.load(f)
                            if isinstance(local_data, list):
                                local_event_count = len(local_data)
                    except:
                        pass
                
                # 2. Scarica backup dal cloud
                zip_content = st.session_state.github_manager.download_backup()
                
                # 3. Conta eventi nel cloud (leggi data.json dallo zip senza estrarre)
                cloud_event_count = 0
                for name, zdata in zip_content.items():
                    try:
                        zf = zipfile.ZipFile(io.BytesIO(zdata))
                        if 'data.json' in zf.namelist():
                            cloud_data = json.loads(zf.read('data.json'))
                            if isinstance(cloud_data, list):
                                cloud_event_count = max(cloud_event_count, len(cloud_data))
                        zf.close()
                    except:
                        pass
                
                # 4. Decisione intelligente: sovrascrivi SOLO se il cloud ha più eventi o uguale
                if cloud_event_count >= local_event_count:
                    st.session_state.github_manager.restore_from_zip(zip_content)
                    st.toast(f"✅ Dati sincronizzati dal cloud! ({cloud_event_count} eventi)", icon="☁️")
                else:
                    # Il locale è più completo: NON sovrascrivere!
                    st.warning(
                        f"⚠️ Dati locali più completi del cloud! "
                        f"Locale: {local_event_count} eventi, Cloud: {cloud_event_count} eventi. "
                        f"Dati locali MANTENUTI. Usa '🚀 Salva su GitHub' per aggiornare il cloud."
                    )
            except Exception as e:
                # Se è il primo avvio assoluto o il backup non esiste, ignoriamo l'errore
                if "404" not in str(e):
                    st.info("Avviso: Sincronizzazione automatica non riuscita. Caricamento dati locali.")
    st.session_state.data_initialized = True

if 'events' not in st.session_state:
    st.session_state.events = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                content = json.load(f)
                if isinstance(content, list):
                    # Normalizzazione automatica al caricamento
                    needs_save = False
                    for ev in content:
                        for key_path in ['image_path', 'sticker_image_path']:
                            if ev.get(key_path):
                                ev[key_path] = ev[key_path].replace('\\', '/')
                                # Auto-healer: se il file non esiste, prova varianti di estensione
                                if not os.path.exists(ev[key_path]):
                                    base_no_ext = os.path.splitext(ev[key_path])[0]
                                    for alt_ext in ['.jpg', '.jpeg', '.png']:
                                        alt_path = base_no_ext + alt_ext
                                        if os.path.exists(alt_path):
                                            ev[key_path] = alt_path
                                            needs_save = True
                                            break

                        if 'date' in ev:
                            ev['date'] = normalize_date_to_italian(ev['date'])
                            
                    # Pre-calcolo dati pesanti (Booster performance)
                    for ev in content:
                        if '_dt' not in ev:
                            ev['_dt'] = WordGenerator.get_sort_date(ev)
                        if '_prov' not in ev:
                            ev['_prov'] = WordGenerator.get_province(ev)
                            
                    st.session_state.events = content
                    if needs_save:
                        save_events_to_disk()
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
                active_images = set()
                
                # 0. Trova immagini in uso (per filtrare uploads)
                current_events = st.session_state.events
                for ev in current_events:
                    img_p = ev.get('image_path', '')
                    if img_p:
                        active_images.add(os.path.basename(img_p))

                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    # 1. Aggiungi il database JSON
                    if os.path.exists(DATA_FILE):
                        zf.write(DATA_FILE, arcname='data.json')
                    
                    if os.path.exists("CITY_FALLBACK.json"):
                        zf.write("CITY_FALLBACK.json", arcname='CITY_FALLBACK.json')
                    
                    # 2. Aggiungi la cartella uploads (SOLO file attivi)
                    if os.path.exists(UPLOADS_DIR):
                        for root, _, files in os.walk(UPLOADS_DIR):
                            for file in files:
                                if file in active_images:
                                    file_path = os.path.join(root, file)
                                    arcname = f"uploads/{os.path.basename(file)}"
                                    zf.write(file_path, arcname=arcname)
                    
                    # 3. Aggiungi la cartella images_album (elaborate)
                    album_dir = "output/images_album"
                    if os.path.exists(album_dir):
                        for root, _, files in os.walk(album_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = f"output/images_album/{os.path.basename(file)}"
                                zf.write(file_path, arcname=arcname)
                
                zip_buffer.seek(0)
                st.session_state['backup_zip'] = zip_buffer
                st.success("Backup ottimizzato creato! Clicca sotto per scaricare.")
            except Exception as e:
                st.error(f"Errore creazione backup: {e}")

    if 'backup_zip' in st.session_state:
        st.download_button(
            label="⬇️ Scarica Backup Completo",
            data=st.session_state['backup_zip'],
            file_name=f"locandine_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
            key="btn_download_backup_local_final",
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
                    safe_reset_city_cache()
                    st.success("Dati ripristinati da GitHub correttamente! Ricarico...")
                    # Rimuoviamo la chiave per forzare la rilettura dal nuovo data.json su disco al rerun
                    st.session_state.show_confirm_pull = False
                    safe_media_rerun()
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
                    
                    safe_reset_city_cache()
                    
                    # Forza ricaricamento totale MA preserva data_initialized
                    # per evitare che l'auto-sync cloud sovrascriva il backup locale appena ripristinato
                    try:
                        from streamlit.runtime import get_instance
                        runtime = get_instance()
                        if hasattr(runtime, "media_file_mgr"):
                            runtime.media_file_mgr.clear()
                    except:
                        pass
                    # Puliamo solo le chiavi necessarie, NON data_initialized
                    for k in ['album_cover', 'album_pages', 'album_zip', 'album_pdf', 'backup_zip', 'events']:
                        if k in st.session_state:
                            try: del st.session_state[k]
                            except: pass
                    import time
                    time.sleep(0.8)
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
                        save_events_to_disk()
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

    st.divider()

    # --- PULIZIA E OTTIMIZZAZIONE MANUALE ---
    with st.expander("🛠️ Strumenti Avanzati (Manutenzione)"):
        st.write("Usa questi strumenti per tenere l'app veloce e leggera.")
        
        # --- GESTIONE LOCALITÀ FALLBACK ---
        st.divider()
        st.markdown("#### 📍 Gestione Mappatura Località -> Province")
        st.info("Qui puoi definire quali località (che non sono capoluogo) appartengono a quali province. Le modifiche avranno effetto immediato su statistiche e grafici.")
        
        # Caricamento JSON con cache in session_state (evita IO disco ad ogni rerun)
        fb_file = "CITY_FALLBACK.json"
        if 'city_fallback_cache' not in st.session_state:
            if not os.path.exists(fb_file):
                st.session_state.city_fallback_cache = {}
            else:
                try:
                    with open(fb_file, "r", encoding="utf-8") as f:
                        st.session_state.city_fallback_cache = json.load(f)
                except:
                    st.session_state.city_fallback_cache = {}
        default_fb = st.session_state.city_fallback_cache

        # Conversione Dict -> DataFrame per editing
        # Usiamo una lista di dizionari
        fb_data = [{"Località": k, "Provincia": v} for k, v in default_fb.items()]
        df_fb = pd.DataFrame(fb_data)

        # Editor (permette aggiunta/rimozione righe)
        edited_df = st.data_editor(
            df_fb,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "Località": st.column_config.TextColumn("Località (Es. PEGLI)", required=True),
                "Provincia": st.column_config.SelectboxColumn(
                    "Provincia",
                    options=["GENOVA", "LA SPEZIA", "SAVONA", "IMPERIA", "MASSA", "LUCCA", "ALESSANDRIA", "ASTI"],
                    required=True
                )
            },
            key="city_fallback_editor"
        )

        # Pulsante Salva
        if st.button("💾 Salva Mappatura Località"):
            # Riconversione DataFrame -> Dict
            new_fb_dict = {}
            # Iteriamo sul dataframe editato
            # Nota: st.data_editor ritorna un DF pandas modificato
            if not edited_df.empty:
                for index, row in edited_df.iterrows():
                    loc = str(row.get("Località", "")).strip().upper()
                    prov = str(row.get("Provincia", "")).strip().upper()
                    if loc and prov:
                        new_fb_dict[loc] = prov
            
            # Salvataggio su disco
            try:
                with open(fb_file, "w", encoding="utf-8") as f:
                    json.dump(new_fb_dict, f, ensure_ascii=False, indent=4)
                
                # Reset Cache (sia WordGenerator che session_state)
                safe_reset_city_cache()
                if 'city_fallback_cache' in st.session_state:
                    del st.session_state['city_fallback_cache']
                st.success(f"✅ Mappatura salvata! ({len(new_fb_dict)} voci)")
                # st.rerun()
            except Exception as e:
                st.error(f"Errore salvataggio: {e}")

        st.divider()
        
        # --- Report Ottimizzazione (persistente dopo rerun) ---
        if 'optimize_report' in st.session_state:
            st.success(st.session_state['optimize_report'])
            if st.button("🆗 OK, ho letto", key="dismiss_opt_report"):
                del st.session_state['optimize_report']
                st.rerun()
        
        if st.button("⚡ Ottimizza Archivio Esistente", help="Ridimensiona tutte le immagini, converti PNG→JPG, elimina orfani e aggiorna il JSON."):
            events_list = st.session_state.events
            album_dir = "output/images_album"
            
            # === FASE 0: Costruisci set di file attivi ===
            active_uploads = set()
            active_stickers = set()
            for ev in events_list:
                img_p = ev.get('image_path', '')
                if img_p:
                    active_uploads.add(os.path.basename(img_p))
                stk_p = ev.get('sticker_image_path', '')
                if stk_p:
                    active_stickers.add(os.path.basename(stk_p))
            
            # === FASE 1: Inventario file su disco ===
            all_uploads = [f for f in os.listdir(UPLOADS_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))] if os.path.exists(UPLOADS_DIR) else []
            all_album = [f for f in os.listdir(album_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))] if os.path.exists(album_dir) else []
            
            orphan_uploads = [f for f in all_uploads if f not in active_uploads]
            orphan_album = [f for f in all_album if f not in active_stickers]
            active_upload_files = [f for f in all_uploads if f in active_uploads]
            active_album_files = [f for f in all_album if f in active_stickers]
            
            total_to_do = len(active_upload_files) + len(active_album_files)
            
            if total_to_do == 0 and not orphan_uploads and not orphan_album:
                st.warning("Nessuna immagine trovata da ottimizzare.")
            else:
                processed = 0
                converted_png = 0
                errors = 0
                orphans_removed = 0
                json_updated = False
                pbar = st.progress(0)
                
                # === FASE 2: Rimuovi orfani UPLOADS ===
                for orphan in orphan_uploads:
                    try:
                        os.remove(os.path.join(UPLOADS_DIR, orphan))
                        orphans_removed += 1
                    except:
                        pass
                
                # === FASE 3: Rimuovi orfani ALBUM ===
                for orphan in orphan_album:
                    try:
                        os.remove(os.path.join(album_dir, orphan))
                        orphans_removed += 1
                    except:
                        pass
                
                # === FASE 4: Ottimizza UPLOADS (+ conversione PNG->JPG con rinomina e aggiornamento JSON) ===
                for i, filename in enumerate(active_upload_files):
                    img_path = os.path.join(UPLOADS_DIR, filename)
                    try:
                        img = Image.open(img_path)
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        
                        if filename.lower().endswith('.png'):
                            new_filename = os.path.splitext(filename)[0] + ".jpg"
                            new_path = os.path.join(UPLOADS_DIR, new_filename)
                            img.save(new_path, "JPEG", quality=80, optimize=True)
                            
                            old_ref = f"{UPLOADS_DIR}/{filename}"
                            new_ref = f"{UPLOADS_DIR}/{new_filename}"
                            for ev in events_list:
                                if ev.get('image_path', '') == old_ref:
                                    ev['image_path'] = new_ref
                                    json_updated = True
                            
                            if os.path.exists(new_path):
                                os.remove(img_path)
                            
                            converted_png += 1
                            processed += 1
                        else:
                            img.save(img_path, "JPEG", quality=80, optimize=True)
                            processed += 1
                    except Exception:
                        errors += 1
                    
                    if total_to_do > 0:
                        pbar.progress((i + 1) / total_to_do)
                
                # === FASE 5: Ottimizza ALBUM (+ conversione PNG->JPG con rinomina e aggiornamento JSON) ===
                start_idx = len(active_upload_files)
                for i, filename in enumerate(active_album_files):
                    old_path = os.path.join(album_dir, filename)
                    try:
                        img = Image.open(old_path)
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        
                        if filename.lower().endswith('.png'):
                            new_filename = os.path.splitext(filename)[0] + ".jpg"
                            new_path = os.path.join(album_dir, new_filename)
                            img.save(new_path, "JPEG", quality=85, optimize=True)
                            
                            old_ref_fwd = f"output/images_album/{filename}"
                            new_ref_fwd = f"output/images_album/{new_filename}"
                            for ev in events_list:
                                stk = ev.get('sticker_image_path', '')
                                if stk and os.path.basename(stk) == filename:
                                    ev['sticker_image_path'] = new_ref_fwd
                                    json_updated = True
                            
                            if os.path.exists(new_path):
                                os.remove(old_path)
                            
                            converted_png += 1
                            processed += 1
                        else:
                            img.save(old_path, "JPEG", quality=85, optimize=True)
                            processed += 1
                    except Exception:
                        errors += 1
                    
                    if total_to_do > 0:
                        pbar.progress((start_idx + i + 1) / total_to_do)
                
                # === FASE 6: Salva JSON se modificato ===
                if json_updated:
                    save_events_to_disk()
                
                # === FASE 7: Report finale ===
                report_lines = [f"Ottimizzazione completa! Elaborati {processed} file ({len(active_upload_files)} locandine + {len(active_album_files)} figurine)."]
                if converted_png > 0:
                    report_lines.append(f"Convertiti {converted_png} file PNG a JPG (JSON aggiornato).")
                if orphans_removed > 0:
                    report_lines.append(f"Rimosse {orphans_removed} immagini orfane ({len(orphan_uploads)} da uploads, {len(orphan_album)} da album).")
                if errors > 0:
                    report_lines.append(f"Errori: {errors}.")
                
                st.session_state['optimize_report'] = " | ".join(report_lines)
                
                # NON usare safe_media_rerun() perche' cancella data_initialized
                # e ri-triggera il cloud sync che sovrascrive il lavoro appena fatto!
                st.rerun()

    # --- CREDENZIALI GOOGLE DRIVE ---
    st.divider()
    st.markdown("### 📤 Google Drive")
    render_credentials_sidebar(github_manager=st.session_state.get('github_manager'))


tab4, tab1, tab2, tab3, tab5 = st.tabs(["📊 Statistiche", "📤 Carica & Analizza", "📋 Modifica Dati", "📖 Export Word", "📖 Creazione Album"])

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
                    # Salva immagine ottimizzata direttamente come JPG
                    base_name = os.path.splitext(uploaded_file.name)[0]
                    image_path = os.path.join(UPLOADS_DIR, f"{base_name}.jpg")
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
                        
                        parsed['image_path'] = f"{UPLOADS_DIR}/{base_name}.jpg"
                        st.session_state[f'temp_data_{idx}'] = parsed
                st.success("Tutte le immagini sono state analizzate! Controlla i moduli sotto.")
                # st.rerun()

        # Identifica le immagini già collegate a eventi esistenti
        existing_imgs = set()
        for ev in st.session_state.events:
             path = ev.get('image_path', '')
             if path:
                 # Gestione sicura separatori (normalizzati a / nel DB)
                 fname = path.replace('\\', '/').split('/')[-1]
                 existing_imgs.add(fname)

        for idx, uploaded_file in enumerate(uploaded_files):
            # Se l'immagine è già in un evento, saltala (nascondi preview)
            if uploaded_file.name in existing_imgs:
                continue

            with st.expander(f"🖼️ {uploaded_file.name}", expanded=True):
                col1, col2 = st.columns([1, 2])
                
                # Salvataggio e Anteprima Immagine (Ottimizzata JPG) — solo se non esiste già
                base_name = os.path.splitext(uploaded_file.name)[0]
                image_path = os.path.join(UPLOADS_DIR, f"{base_name}.jpg")
                if not os.path.exists(image_path):
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
                                save_events_to_disk()
                                
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
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            status_filter = st.selectbox(
                "🔍 1. Filtra per Stato",
                ["Tutto (All)", "Solo i NEW", "Attivi (Futuri + NEW)", "Solo Scaduti"],
                key="mgr_status_filter"
            )
        
        with col_f2:
            geo_filter = st.selectbox(
                "📍 2. Filtra per Luogo",
                ["Tutti", "LIGURIA", "TOSCANA", "PIEMONTE", "GENOVA", "LA SPEZIA", "SAVONA", "IMPERIA", "MASSA", "LUCCA", "ALESSANDRIA", "ASTI"],
                key="mgr_geo_filter"
            )
        
        with col_f3:
            album_filter = st.selectbox(
                "🎨 3. Locandina Album",
                ["Tutti", "Con Locandina Album", "Senza Locandina Album"],
                key="mgr_album_filter"
            )
        
        search_query = st.text_input("📝 Cerca nel testo (Titolo, Luogo, Descrizione...)", "").strip().lower()
        
        # --- FILTRAGGIO UNICO (una sola passata, usa PROV_TO_REG dal livello modulo) ---
        now = datetime.now()
        
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
                if geo_filter in ["LIGURIA", "TOSCANA", "PIEMONTE"]: m_g = (PROV_TO_REG.get(prov, "ALTRO") == geo_filter)
                else: m_g = (prov == geo_filter)
            
            # C. Ricerca Testuale
            m_t = True
            if search_query:
                content = (ev.get('title', '') + ev.get('description', '') + ev.get('location', '') + ev.get('venue', '')).lower()
                m_t = search_query in content
            
            # D. Locandina Album
            m_a = True
            if album_filter == "Con Locandina Album":
                m_a = bool(ev.get('sticker_image_path', ''))
            elif album_filter == "Senza Locandina Album":
                m_a = not bool(ev.get('sticker_image_path', ''))
            
            if m_s and m_g and m_t and m_a:
                indexed_view_events.append((i, ev))

        sorted_view_events = sorted(indexed_view_events, key=lambda x: WordGenerator.get_sort_date(x[1]))
        events_list_view = [e[1] for e in sorted_view_events]
        
        if not events_list_view:
            st.warning(f"Nessun evento trovato con i filtri selezionati.")
        
        # --- STATISTICHE E CONTROLLI ---
        total_ev = len(events_list_view)
        st.write(f"📊 Eventi visualizzati: **{total_ev}** (su {len(events_list)} totali)")

        # Controllo Duplicati (Basato esclusivamente sul Percorso Immagine)
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
                for idx, event in enumerate(events_list): # Azione globale sul database reale
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
                            
                            new_title = f"{weekday} {clean_date} - {location}" if location else f"{weekday} {clean_date}"
                            event['title'] = new_title
                            
                            # Aggiorna anche il widget session_state se esiste, per riflettere la modifica nel form
                            k_tit = f"e_tit_{idx}"
                            if k_tit in st.session_state:
                                st.session_state[k_tit] = new_title

                save_events_to_disk()
                st.success("Titoli aggiornati!")
                st.rerun()

        with col_m3:
            if st.button("✨ Rimuovi NEW"):
                st.session_state.confirm_clear_new = True
            
            if st.session_state.get('confirm_clear_new'):
                st.warning("⚠️ Confermi di voler rimuovere l'etichetta NEW da TUTTI gli eventi?")
                c_y, c_n = st.columns(2)
                if c_y.button("✅ Confermo", key="y_clear_new"):
                    for ev in events_list:
                        ev['is_new'] = False
                    save_events_to_disk()
                    st.session_state.confirm_clear_new = False
                    st.success("Etichette NEW rimosse!")
                    # st.rerun()
                if c_n.button("❌ Annulla", key="n_clear_new"):
                    st.session_state.confirm_clear_new = False
                    # st.rerun()

        with col_m4:
            if st.button("🔄 Riordina Date"):
                events_list.sort(key=WordGenerator.get_sort_date)
                save_events_to_disk()
                st.success("Eventi riordinati!")
                # st.rerun()

        st.info("ℹ️ Gli eventi sono ordinati cronologicamente.")

        # ===== EDITOR FIGURINA come @st.fragment (evita rerun intera pagina con slider) =====
        @st.fragment
        def render_sticker_editor(real_idx, event, events_list_ref):
            """Fragment per l'editor figurina: gli slider aggiornano solo questo blocco."""
            st.markdown("#### 🖼️ Editor Figurina (Maschera 57×80mm)")
            if event.get('sticker_processed') and os.path.exists(event.get('sticker_image_path', '')):
                st.success("✅ Figurina già elaborata!")
                if st.button("🔄 Modifica Figurina", key=f"edit_stk_{real_idx}"):
                    st.session_state[f"show_ed_stk_{real_idx}"] = True
            else:
                if st.button("🖼️ Crea Figurina", key=f"edit_stk_{real_idx}"):
                    st.session_state[f"show_ed_stk_{real_idx}"] = True

            if st.session_state.get(f"show_ed_stk_{real_idx}"):
                ed_c1, ed_c2 = st.columns([1, 1])
                with ed_c2:
                    s_zoom = st.slider("🔍 Zoom", 1.0, 2.0, event.get('stk_zoom', 1.0), 0.05, key=f"sz_{real_idx}")
                    s_strx = st.slider("↔️ Allungamento Orizzontale (Stretch)", 1.0, 1.05, event.get('stk_strx', 1.0), 0.01, key=f"str_{real_idx}")
                    s_offx = st.slider("↔️ Spostamento Orizzontale X", -300, 300, event.get('stk_offx', 0), 10, key=f"sx_{real_idx}")
                    s_offy = st.slider("↕️ Spostamento Verticale Y", -300, 300, event.get('stk_offy', 0), 10, key=f"sy_{real_idx}")
                    
                    img_path = event.get('image_path', '')
                    img_preview = create_single_sticker(
                        img_path, mask_w_mm=57, mask_h_mm=80,
                        zoom=s_zoom, stretch_x=s_strx, offset_x=s_offx, offset_y=s_offy,
                        preview_mode=True
                    )
                    
                    if st.button("💾 Salva Figurina", type="primary", key=f"save_stk_{real_idx}"):
                        # Genera versione pulita da salvare (senza bordo rosso)
                        img_clean = create_single_sticker(
                            img_path, mask_w_mm=57, mask_h_mm=80,
                            zoom=s_zoom, stretch_x=s_strx, offset_x=s_offx, offset_y=s_offy,
                            preview_mode=False
                        )
                        if img_clean:
                            base_name = os.path.splitext(os.path.basename(img_path))[0]
                            out_dir = os.path.join(OUTPUT_DIR, "images_album")
                            os.makedirs(out_dir, exist_ok=True)
                            tgt_path = os.path.join(out_dir, f"{base_name}_sticker.jpg")
                            # Converte in RGB e salva come JPG ottimizzato (molto più leggero di PNG)
                            img_clean.convert("RGB").save(tgt_path, "JPEG", quality=85, optimize=True)
                            
                            events_list_ref[real_idx]['sticker_processed'] = True
                            events_list_ref[real_idx]['sticker_image_path'] = tgt_path
                            # Salva parametri per dopo
                            events_list_ref[real_idx]['stk_zoom'] = s_zoom
                            events_list_ref[real_idx]['stk_strx'] = s_strx
                            events_list_ref[real_idx]['stk_offx'] = s_offx
                            events_list_ref[real_idx]['stk_offy'] = s_offy
                            
                            save_events_to_disk()
                            st.session_state[f"show_ed_stk_{real_idx}"] = False
                            st.rerun()
                            
                with ed_c1:
                    if img_preview:
                        st.caption("Anteprima Figurina (Sfondo Trasparente)")
                        # Usa st.image direttamente con PIL (molto più veloce di base64)
                        st.image(img_preview, width='content')

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
            stck_icon = "🖼️ [OK] " if event.get('sticker_processed') else ""
            title_prefix = f"{dup_icon}{exp_icon}🆕 " if event.get('is_new') else f"{dup_icon}{exp_icon}"
            
            with st.expander(f"{title_prefix}{stck_icon}📅 {event.get('title', 'Titolo n/d')}"):

                # Chiama il fragment dell'editor figurina
                render_sticker_editor(real_idx, event, events_list)
                
                st.divider()

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

                                save_events_to_disk()
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

                        save_events_to_disk()

                        st.success("Aggiornato!")
                        # st.rerun()

                    # Pulsante RIMUOVI NEW (visibile solo se l'evento è nuovo)
                    if event.get('is_new'):
                        if col_b2.button("🚫 Rimuovi Etichetta", key=f"unew_{real_idx}", help="Rimuove l'etichetta NEW da questo evento"):
                            events_list[real_idx]['is_new'] = False
                            save_events_to_disk()
                            # st.rerun()
                    else:
                         col_b2.write("") # Spacer se non c'è il pulsante

                    if col_b3.button("🗑️ Elimina", key=f"del_{real_idx}", type="primary"):
                        events_list.pop(real_idx)
                        save_events_to_disk()
                        st.rerun()

# --- TAB 3: EXPORT (con st.form — nessun rerun durante la configurazione) ---
with tab3:
    st.subheader("Generazione Documento")
    events_list_all = st.session_state.get('events', [])
    
    # Refresh metadata prima del form (necessario per i filtri)
    refresh_event_metadata()

    with st.form("word_generation_form"):
        # --- FILTRAGGIO ---
        st.markdown("#### 🔍 1. Filtra Eventi")
        filter_choice = st.radio(
            "Scegli quali eventi includere nell'export:",
            ["Tutti gli eventi", "Solo attivi (non scaduti)", "Solo i NEW", "Solo Provincia di Genova", "Solo Provincia di La Spezia"],
            horizontal=True
        )

        st.divider()

        st.markdown("#### 🎨 2. Opzioni Stile")
        col_opts1, col_opts2 = st.columns(2)
        with col_opts1:
            export_mode_sel = st.radio("Stile Documento", ["Standard (Foto + Testo)", "Minimal (Solo Foto)"])
        with col_opts2:
            st.write("") # Spacer
            st.write("") 
            show_borders_opt = st.checkbox("Mostra bordi tabella", value=True)

        st.divider()

        # --- BOTTONI DI GENERAZIONE (form_submit_button) ---
        col_gen1, col_gen2 = st.columns(2)
        with col_gen1:
            genera_word = st.form_submit_button("📥 Genera Word", type="primary")
        with col_gen2:
            genera_pdf = st.form_submit_button("📄 Genera PDF (senza statistiche)")

    # --- LOGICA POST-FORM (eseguita solo al submit) ---
    if genera_word or genera_pdf:
        now_date = datetime.now().date()
        
        # Filtraggio ottimizzato (senza ricalcolare date)
        if filter_choice == "Solo attivi (non scaduti)":
            events_list_exp = [ev for ev in events_list_all if ev.get('_dt', datetime.max).date() >= now_date]
        elif filter_choice == "Solo i NEW":
            events_list_exp = [ev for ev in events_list_all if ev.get('is_new')]
        elif filter_choice == "Solo Provincia di Genova":
            events_list_exp = [ev for ev in events_list_all if ev.get('_prov') == "GENOVA"]
        elif filter_choice == "Solo Provincia di La Spezia":
            events_list_exp = [ev for ev in events_list_all if ev.get('_prov') == "LA SPEZIA"]
        else:
            events_list_exp = events_list_all

        export_mode = "minimal" if "Minimal" in export_mode_sel else "standard"

        if not events_list_exp:
            st.error("Nessun evento da stampare!")
        elif genera_word:
            with st.spinner("Creazione documento Word in corso..."):
                gen = WordGenerator()
                out_path = os.path.join(OUTPUT_DIR, doc_name)
                gen.generate_from_data(
                    events_list_exp, 
                    out_path, 
                    mode=export_mode, 
                    show_borders=show_borders_opt
                )
                
                with open(out_path, 'rb') as f:
                    st.download_button(
                        label="⬇️ Scarica Word",
                        data=f,
                        file_name=doc_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                st.success("Documento Word pronto!")

        elif genera_pdf:
            with st.spinner("Creazione PDF in corso..."):
                gen = WordGenerator()
                pdf_doc_name = os.path.splitext(doc_name)[0] + "_nostat.docx"
                pdf_out_docx = os.path.join(OUTPUT_DIR, pdf_doc_name)
                gen.generate_from_data(
                    events_list_exp,
                    pdf_out_docx,
                    mode=export_mode,
                    show_borders=show_borders_opt,
                    skip_stats=True
                )
                
                # Tentativo conversione PDF
                pdf_path = os.path.splitext(pdf_out_docx)[0] + ".pdf"
                pdf_converted = False
                try:
                    from docx2pdf import convert
                    convert(pdf_out_docx, pdf_path)
                    pdf_converted = True
                except Exception as e:
                    st.warning(f"⚠️ Errore conversione PDF: {e}")
                
                if pdf_converted and os.path.exists(pdf_path):
                    # Salva il path PDF in session_state per il bottone upload
                    st.session_state['last_pdf_path'] = pdf_path
                    st.session_state['last_pdf_name'] = os.path.splitext(doc_name)[0] + ".pdf"
                    
                    with open(pdf_path, 'rb') as f:
                        st.download_button(
                            label="⬇️ Scarica PDF",
                            data=f,
                            file_name=os.path.splitext(doc_name)[0] + ".pdf",
                            mime="application/pdf"
                        )
                    st.success("PDF pronto!")
                else:
                    # Fallback: offri il Word senza stats
                    st.session_state['last_pdf_path'] = pdf_out_docx
                    st.session_state['last_pdf_name'] = pdf_doc_name
                    
                    with open(pdf_out_docx, 'rb') as f:
                        st.download_button(
                            label="⬇️ Scarica Word (senza statistiche)",
                            data=f,
                            file_name=pdf_doc_name,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                    st.warning("Conversione PDF non disponibile. Scarica il Word senza statistiche e convertilo in PDF manualmente.")
    
    # --- BOTTONE UPLOAD GOOGLE DRIVE (fuori dal form, sempre visibile se c'è un PDF pronto) ---
    if 'last_pdf_path' in st.session_state and os.path.exists(st.session_state.get('last_pdf_path', '')):
        st.divider()
        st.markdown("#### ☁️ Upload su Google Drive")
        st.caption(f"📄 Il file verrà caricato come: **{GDRIVE_TARGET_FILENAME}**")
        
        if st.button("📤 Carica PDF su Google Drive", type="primary", key="btn_upload_gdrive"):
            pdf_source = st.session_state['last_pdf_path']
            
            with st.spinner(f"Upload di '{GDRIVE_TARGET_FILENAME}' su Google Drive..."):
                def progress_cb(msg):
                    st.toast(msg, icon="☁️")
                
                success, message, link = upload_pdf_to_gdrive(pdf_source, progress_callback=progress_cb)
                
                if success:
                    st.success(message)
                    if link:
                        st.markdown(f"🔗 [Apri su Google Drive]({link})")
                else:
                    st.error(message)

@st.cache_data(show_spinner=False)
def compute_statistics(events_list_stats):
    import pandas as pd
    total_ev = len(events_list_stats)
    now = datetime.now()
    
    expired_count = 0
    new_count = 0
    active_count = 0
    
    # NOTA: usa PROV_TO_REG dal livello modulo (evita duplicazione)
    
    stats_geo = {
        'LIGURIA': {'total': 0, 'provinces': {'GENOVA': 0, 'LA SPEZIA': 0, 'SAVONA': 0, 'IMPERIA': 0}},
        'TOSCANA': {'total': 0, 'provinces': {'MASSA': 0, 'LUCCA': 0}},
        'PIEMONTE': {'total': 0, 'provinces': {'ALESSANDRIA': 0, 'ASTI': 0}},
        'ALTRO': {'total': 0, 'cities': {}}
    }
    
    all_locations = {}
    time_data = []
    
    check_filename = {}
    check_datetime = {}
    check_address = {}

    events_with_dates = []

    for ev in events_list_stats:
        # Usa dati pre-calcolati (o calcola se mancano)
        ev_date = ev.get('_dt')
        if not ev_date: ev_date = WordGenerator.get_sort_date(ev)
        
        events_with_dates.append((ev, ev_date))
        
        if ev.get('is_new'):
            new_count += 1
        
        if ev_date != datetime.max and ev_date.date() < now.date():
            expired_count += 1
        else:
            active_count += 1

        prov_found = ev.get('_prov')
        if not prov_found: prov_found = WordGenerator.get_province(ev)
        
        loc = ev.get('location', 'N/D').strip().upper()
        
        reg = PROV_TO_REG.get(prov_found)
        if reg:
            stats_geo[reg]['total'] += 1
            if prov_found in stats_geo[reg]['provinces']:
                stats_geo[reg]['provinces'][prov_found] += 1
        else:
            stats_geo['ALTRO']['total'] += 1
            stats_geo['ALTRO']['cities'][loc] = stats_geo['ALTRO']['cities'].get(loc, 0) + 1
            
        all_locations[loc] = all_locations.get(loc, 0) + 1
        
        if ev_date != datetime.max:
            time_data.append(ev_date.date())

        title = ev.get('title', 'N/D')
        
        img_rel_path = ev.get('image_path', '')
        if img_rel_path:
            fname = os.path.basename(img_rel_path)
            if fname not in check_filename: check_filename[fname] = []
            check_filename[fname].append(title)
        
        d_raw = ev.get('date', '').strip().upper()
        t_raw = ev.get('time', '').strip().upper()
        if d_raw and t_raw:
            dt_key = f"{d_raw} alle {t_raw}"
            if dt_key not in check_datetime: check_datetime[dt_key] = []
            check_datetime[dt_key].append(title)
        
        addr_raw = ev.get('address', '').strip().upper()
        if addr_raw and len(addr_raw) > 5:
            if addr_raw not in check_address: check_address[addr_raw] = []
            check_address[addr_raw].append(title)

    sorted_events = [x[0] for x in sorted(events_with_dates, key=lambda item: item[1])]
    
    daily_stats = []
    if time_data:
        min_date = min(time_data)
        max_date = max(time_data)
        all_days = pd.date_range(start=min_date, end=max_date).date
        
        time_series = pd.Series(time_data)
        date_counts = time_series.value_counts().to_dict()
        
        total_time_events = len(time_data)
        cumulative = 0
        for d in all_days:
            count_today = date_counts.get(d, 0)
            cumulative += count_today
            active_at_d = total_time_events - cumulative + count_today
            
            daily_stats.append({
                "Data": d,
                "Eventi Giornalieri": count_today,
                "Totale Progressivo": cumulative,
                "Eventi Attivi": active_at_d
            })

    table_rows = []
    for ev in sorted_events:
        table_rows.append({
            "Data": ev.get('date', ''),
            "Titolo": ev.get('title', ''),
            "Località": ev.get('location', ''),
            "Provincia": WordGenerator.get_province(ev),
            "Indirizzo": ev.get('address', ''),
            "Orario": ev.get('time', ''),
            "NEW": "⭐" if ev.get('is_new') else ""
        })

    return {
        "total_ev": total_ev,
        "active_count": active_count,
        "expired_count": expired_count,
        "new_count": new_count,
        "stats_geo": stats_geo,
        "all_locations": all_locations,
        "daily_stats": daily_stats,
        "table_rows": table_rows,
        "check_filename": check_filename,
        "check_datetime": check_datetime,
        "check_address": check_address
    }

# --- TAB 4: STATISTICHE ---
with tab4:
    st.subheader("📊 Analisi e Distribuzione Eventi")
    
    events_list_stats = st.session_state.get('events', [])
    
    if not events_list_stats:
        st.info("Nessun dato disponibile per le statistiche. Carica degli eventi per iniziare.")
    else:
        # SOLUZIONE RADICALE: Calcolo solo su richiesta o se non presente
        if 'last_stats' not in st.session_state or st.button("📊 Aggiorna Statistiche"):
            with st.spinner("Elaborazione dati in corso..."):
                refresh_event_metadata()
                st.session_state.last_stats = compute_statistics(events_list_stats)
        
        stats = st.session_state.last_stats
        
        # Metriche principali
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Totale Eventi", stats['total_ev'])
        m2.metric("Attivi (Futuri)", stats['active_count'])
        m3.metric("Scaduti", stats['expired_count'])
        m4.metric("Nuovi (NEW)", stats['new_count'])
        
        st.divider()
        
        stats_geo = stats['stats_geo']

        # --- GRAFICI INTERATTIVI ---
        #import pandas as pd
        #import altair as alt

        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.markdown("#### 🌍 Distribuzione Regionale")
            # Prepariamo il dettaglio per il tooltip
            lig_dettaglio = ", ".join([f"{p} ({c})" for p, c in stats_geo['LIGURIA']['provinces'].items() if c > 0])
            tos_dettaglio = ", ".join([f"{p} ({c})" for p, c in stats_geo['TOSCANA']['provinces'].items() if c > 0])
            pie_dettaglio = ", ".join([f"{p} ({c})" for p, c in stats_geo['PIEMONTE']['provinces'].items() if c > 0])
            alt_dettaglio = ", ".join([f"{loc} ({count})" for loc, count in sorted(stats_geo['ALTRO']['cities'].items(), key=lambda x: x[1], reverse=True)])

            reg_df = pd.DataFrame({
                "Regione": ["LIGURIA", "TOSCANA", "PIEMONTE", "ALTRO"],
                "Eventi": [stats_geo['LIGURIA']['total'], stats_geo['TOSCANA']['total'], stats_geo['PIEMONTE']['total'], stats_geo['ALTRO']['total']],
                "Dettaglio": [lig_dettaglio, tos_dettaglio, pie_dettaglio, alt_dettaglio]
            })
            # Rimuoviamo righe con 0 eventi per pulizia grafico
            reg_df = reg_df[reg_df["Eventi"] > 0]
            if not reg_df.empty:
                # Creazione Grafico a Torta (Donut) con Altair
                pie_chart = alt.Chart(reg_df).mark_arc(innerRadius=50).encode(
                    theta=alt.Theta(field="Eventi", type="quantitative"),
                    color=alt.Color(field="Regione", type="nominal", scale=alt.Scale(range=['#667eea', '#ff9a9e', '#764ba2', '#cccccc'])),
                    tooltip=['Regione', 'Eventi', 'Dettaglio']
                ).properties(height=300)
                
                st.altair_chart(pie_chart, width="stretch")
                
                # Mostra elenco testuale se ci sono località in ALTRO
                if stats_geo['ALTRO']['total'] > 0:
                    st.caption(f"**Località 'ALTRO':** {alt_dettaglio}")
            else:
                st.write("Nessun dato regionale.")

        with col_g2:
            st.markdown("#### 🗺️ Dettaglio Province")
            prov_data = []
            for reg in ['LIGURIA', 'TOSCANA', 'PIEMONTE']:
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
                                       domain=['LIGURIA', 'TOSCANA', 'PIEMONTE'],
                                       range=['#667eea', '#ff9a9e', '#764ba2']
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
            all_locations = stats['all_locations']
            
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
                "Conteggio": [stats['active_count'], stats['expired_count'], stats['new_count']]
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
        
        # --- ANALISI TEMPORALE ---
        st.markdown("### 📈 Andamento Temporale")
        
        if stats['daily_stats']:
            df_time = pd.DataFrame(stats['daily_stats'])
            
            # 1. Grafico Andamento (Cumulativo e Attivi)
            df_melted = df_time.melt(id_vars=["Data"], value_vars=["Totale Progressivo", "Eventi Attivi"], 
                                     var_name="Tipo", value_name="Conteggio")
            
            # Linea verticale per OGGI
            today_dt = datetime.now().date()
            today_line = alt.Chart(pd.DataFrame({'Data': [pd.to_datetime(today_dt)]})).mark_rule(
                color='red', 
                strokeDash=[5, 5],
                size=2
            ).encode(x='Data:T')

            line_chart = alt.Chart(df_melted).mark_line(interpolate='monotone', strokeWidth=3).encode(
                x=alt.X('Data:T', title='Data'),
                y=alt.Y('Conteggio:Q', title='Numero Eventi'),
                color=alt.Color('Tipo:N', scale=alt.Scale(domain=['Totale Progressivo', 'Eventi Attivi'], range=['#667eea', '#ff9a9e'])),
                tooltip=['Data:T', 'Conteggio', 'Tipo']
            ).properties(height=350, title="Evoluzione del Volume Eventi")
            
            st.altair_chart(line_chart + today_line, width="stretch")
            
            # 2. Istogramma Giornaliero
            hist_chart = alt.Chart(df_time).mark_bar(color='#764ba2', opacity=0.8).encode(
                x=alt.X('Data:T', title='Giorno'),
                y=alt.Y('Eventi Giornalieri:Q', title='Eventi Previsti'),
                tooltip=['Data:T', 'Eventi Giornalieri']
            ).properties(height=200, title="Frequenza Giornaliera Eventi")
            
            st.altair_chart(hist_chart + today_line, width="stretch")
        else:
            st.info("Aggiungi eventi con date valide per visualizzare l'analisi temporale.")

        st.divider()

        # --- TABELLA RIASSUNTIVA ---
        st.markdown("### 📋 Elenco Riepilogativo Eventi")
        
        table_rows = stats['table_rows']
        
        if table_rows:
            st.dataframe(
                pd.DataFrame(table_rows),
                column_config={
                    "Data": st.column_config.TextColumn("Data", width="small"),
                    "NEW": st.column_config.TextColumn("NEW", width="small"),
                    "Titolo": st.column_config.TextColumn("Titolo", width="medium"),
                },
                hide_index=True,
                width="stretch"
            )
        
        st.divider()

        # --- CONTROLLO INTEGRITÀ E DUPLICATI ---
        st.markdown("### ⚠️ Avvisi Integrità e Conflitti")
        
        check_filename = stats['check_filename']
        check_datetime = stats['check_datetime']
        check_address = stats['check_address']
        
        any_warning = False
        
        # Visualizzazione Avvisi Filename
        for fname, titles in check_filename.items():
            if len(titles) > 1:
                st.warning(f"🖼️ **Stessa Immagine (Filename):** Il file `{fname}` è usato da:\n" + "".join([f"- {t}\n" for t in titles]))
                any_warning = True
        
        # Controllo Dimensioni su disco ONDEMAND
        if st.button("🔍 Controlla Integrità File (Dimensioni/Doppioni su Disco)"):
            with st.spinner("Scansionando disco..."):
                check_size = {}
                for ev in events_list_stats:
                    img_path = ev.get('image_path', '')
                    if img_path and os.path.exists(img_path):
                        fsize = os.path.getsize(img_path)
                        if fsize not in check_size: check_size[fsize] = []
                        check_size[fsize].append(ev.get('title', 'N/D'))
                
                size_warning = False
                for fsize, titles in check_size.items():
                    if len(titles) > 1:
                        filenames = set([os.path.basename(ev.get('image_path','')) for ev in events_list_stats if ev.get('title') in titles])
                        if len(filenames) > 1:
                            st.warning(f"⚖️ **Immagini Sospette (Stessa Size):** Immagini diverse con dimensione `{fsize} bytes` in:\n" + "".join([f"- {t}\n" for t in titles]))
                            size_warning = True
                if not size_warning:
                    st.success("Tutte le immagini su disco hanno pesi regolari, nessun duplicato sospetto trovato.")
                
        # Visualizzazione Avvisi Indirizzo (Stesso indirizzo)
        for addr, titles in check_address.items():
            if len(titles) > 1:
                st.warning(f"📍 **Indirizzo Duplicato:** Lo stesso indirizzo `{addr}` compare in:\n" + "".join([f"- {t}\n" for t in titles]))
                any_warning = True
                
        # Visualizzazione Avvisi Conflitto Orario (INFO - AZZURRINO)
        for dt, titles in check_datetime.items():
            if len(titles) > 1:
                st.info(f"📅 **Nota Orario:** Più eventi lo stesso giorno alla stessa ora (`{dt}`). Casistica ammessa, verifica per scrupolo:\n" + "".join([f"- {t}\n" for t in titles]))
                any_warning = True
        
        if not any_warning:
            st.success("✅ Nessun conflitto rilevato tra immagini o orari.")

        st.divider()
        st.info("💡 I grafici si aggiornano automaticamente ogni volta che modifichi o aggiungi un evento.")

# --- TAB 5: CREAZIONE ALBUM FIGURINE ---
with tab5:
    st.subheader("📖 Album Figurine — Stile Panini")
    st.markdown("""
    <style>
    .album-hero {
        background: linear-gradient(135deg, #1e375a 0%, #2a4f80 50%, #1a3050 100%);
        border: 3px solid #c8aa50;
        border-radius: 16px;
        padding: 25px;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    }
    .album-hero h2 { color: #dcc364; margin: 0 0 8px 0; font-size: 1.6rem; }
    .album-hero p { color: #b0a880; margin: 0; font-size: 0.95rem; }
    </style>
    
    <div class="album-hero">
        <h2>🏆 ALBUM — GIUSTO DIRE NO</h2>
        <p>Genera un album collezionabile con tutte le locandine degli eventi, in stile Panini!</p>
    </div>
    """, unsafe_allow_html=True)
    
    events_album = st.session_state.get('events', [])
    
    if not events_album:
        st.warning("⚠️ Nessun evento disponibile. Carica delle locandine per creare l'album.")
    else:
        # Conta solo eventi con immagine valida (risoluzione robusta)
        def _check_img_path(p):
            if not p: return False
            p = p.replace('\\', '/')
            if os.path.exists(p): return True
            if os.path.exists(os.path.join(os.getcwd(), p)): return True
            return False

        # Includi TUTTI gli eventi per permettere la generazione di placeholder per quelli senza immagine
        valid_album_events = list(events_album)
        total_figurine = len(valid_album_events)
        
        if total_figurine == 0:
            st.warning("⚠️ Nessuna immagine valida trovata nella cartella uploads.")
        else:
            # Refresh metadata pre-form (necessario per ordinamento/filtro)
            refresh_event_metadata()

            # =============================================
            # IMMAGINI PERSONALIZZATE (Fuori dal form per vitare crash/reset su mobile)
            # =============================================
            st.markdown("### 🖼️ Immagini Copertina e Retro")

            # Selectbox per copertine preset da GitHub
            cover_preset_options = {
                "Nessuna (logo o upload manuale)": None,
                "🇲 Genova 46 — CopertinaAlbumGenova46OK.png": "CopertinaAlbumGenova46OK.png",
                "🏋 Pilli — PilliCopertinaAlbum.png": "PilliCopertinaAlbum.png",
            }
            album_cover_preset = st.selectbox(
                "📚 Copertina Predefinita",
                options=list(cover_preset_options.keys()),
                index=0,
                help="Scegli una delle copertine predefinite oppure 'Nessuna' per caricare la tua o usare il logo di default.",
                key="album_cover_preset"
            )
            selected_preset_file = cover_preset_options[album_cover_preset]

            col_img1, col_img2 = st.columns(2)

            with col_img1:
                st.markdown("**Immagine Prima Pagina (Copertina)**")
                if selected_preset_file:
                    st.success(f"Copertina preset selezionata: `{selected_preset_file}`")
                    uploaded_cover_img = None
                else:
                    st.caption("Se non carichi nulla, viene usato il logo di default.")
                    uploaded_cover_img = st.file_uploader(
                        "Carica immagine copertina",
                        type=['png', 'jpg', 'jpeg'],
                        key="album_cover_upload",
                        label_visibility="collapsed"
                    )

            with col_img2:
                st.markdown("**Immagine Ultima Pagina (Retro)**")
                st.caption("Se non carichi nulla, viene usato il logo piccolo di default.")
                uploaded_back_img = st.file_uploader(
                    "Carica immagine pagina finale",
                    type=['png', 'jpg', 'jpeg'],
                    key="album_back_upload",
                    label_visibility="collapsed"
                )

            # =============================================
            # FORM UNICO — NESSUN RERUN DURANTE CONFIGURAZIONE
            # =============================================
            with st.form("album_generation_form"):
                
                # Opzione logo con sfondo bianco
                col_opt1, col_opt2 = st.columns(2)
                with col_opt1:
                    logo_white_bg = st.checkbox(
                        "⚪ Logo ultima pagina con cerchio bianco (non trasparente)",
                        value=True,
                        help="Se attivo, l'interno del cerchio del logo nell'ultima pagina avrà sfondo bianco anziché trasparente.",
                        key="album_logo_white_bg"
                    )
                with col_opt2:
                    logo_cover_white_bg = st.checkbox(
                        "⚪ Logo PRIMA pagina con cerchio bianco (se predefinito)",
                        value=False,
                        help="Se attivo e non carichi una vera copertina, il logo in prima pagina avrà sfondo bianco anziché trasparente.",
                        key="album_logo_cover_white_bg"
                    )
                    
                col_opt3, col_opt4 = st.columns(2)
                with col_opt3:
                    album_logo_cover_full_page = st.checkbox(
                        "🖼️ Logo PRIMA pagina a tutta altezza",
                        value=True,
                        help="Se attivo e non carichi una vera copertina, il logo in copertina proverà a riempire verticalmente lo spazio disponibile.",
                        key="album_logo_cover_full"
                    )
                with col_opt4:
                    album_show_banner = st.checkbox(
                        "🚩 Mostra banner in cima alla copertina",
                        value=False,
                        help="Se disattivato, il banner verde 'Giusto Dire No' in alto verrà nascosto.",
                        key="album_show_banner"
                    )

                sticker_fill_mode = st.radio(
                    "🎴 Modalità riempimento figurina",
                    options=["trasparente", "espansione", "opaco"],
                    format_func=lambda x: {
                        "opaco": "🟨 Opaco — Sfondo crema classico",
                        "trasparente": "📸 Trasparente — Si vede la trama dell'album",
                        "espansione": "✨ Espansione intelligente — Riempie con sfondo sfocato"
                    }.get(x, x),
                    index=0,
                    help=(
                        "▪ **Trasparente**: lo sfondo della figurina è trasparente, mostra la trama dell'album sotto.\n"
                        "▪ **Espansione intelligente**: allarga lo sfondo con una versione sfocata dell'immagine stessa "
                        "senza deformare il soggetto, perfetto per riempire il formato 57×82mm.\n"
                        "▪ **Opaco**: sfondo classico color crema pieno."
                    ),
                    key="album_fill_mode"
                )

                col_ratio1, col_ratio2 = st.columns([1, 1])
                with col_ratio1:
                    album_force_aspect_ratio = st.checkbox(
                        "📏 Forza proporzione figurina",
                        value=False,
                        help="Forza le immagini a rispettare la proporzione classica 57×Hmm. Gli spazi vuoti vengono riempiti secondo la modalità scelta sopra.",
                        key="album_force_aspect_ratio"
                    )
                with col_ratio2:
                    sticker_height_mm = st.slider(
                        "Altezza figurina (mm)",
                        min_value=76, max_value=80, value=80, step=2,
                        help="57mm è la larghezza fissa. L'altezza va da 76 a 80mm. Riducendola, l'immagine verrà tagliata leggermente ai bordi. Attiva 'Forza proporzione' per usare questo valore.",
                        key="album_sticker_height"
                    )
                
                st.divider()

                # --- SEZIONE STAMPA ---
                st.markdown("### 🖨️ Opzioni formato Stampa")
                col_print1, col_print2 = st.columns(2)
                with col_print1:
                    album_empty_mode = st.checkbox(
                        "📖 Crea Album Fisico (Vuoto)",
                        value=False,
                        help="Il PDF dell'album mostrerà solo il bordino vuoto e il numero, per poterci incollare le figurine sopra."
                    )
                with col_print2:
                    album_export_stickers = st.checkbox(
                        "✂️ Estrai Figurine Singole",
                        value=False,
                        help="Genera anche un archivio ZIP con tutte le singole figurine esatte fuso con la trama di sfondo per poterle stampare a parte ed incollarle."
                    )
                
                album_preprocess = st.checkbox(
                    "🖼️ Ignora elaborazioni manuali e ricalcola tutto",
                    value=False,
                    help=(
                        "Se attivato, verranno ricalcolate e ignorate tutte le elaborazioni grafiche per ciascuna maschera "
                        "effettuate nella sezione Modifica Dati, e tutto verrà ricalcolato usando le immagini originali."
                    ),
                    key="album_preprocess"
                )
                
                col_sum1, col_sum2 = st.columns(2)
                with col_sum1:
                    album_show_summary = st.checkbox(
                        "📋 Includi Elenco Riepilogativo",
                        value=False,
                        help="Aggiunge una o più pagine con l'elenco cronologico di tutti gli eventi presenti nell'album, prima delle pagine di chiusura.",
                        key="album_show_summary"
                    )
                with col_sum2:
                    album_summary_epp = st.slider(
                        "Eventi per pagina riepilogo",
                        min_value=30, max_value=80, value=50, step=5,
                        help="Quanti eventi mostrare per ogni pagina di riepilogo (layout a 2 colonne).",
                        key="album_summary_epp"
                    )

                st.divider()
                
                # --- SEZIONE LAYOUT FIGURINE ---
                st.markdown("### 📐 Layout Figurine")
                
                col_lay1, col_lay2, col_lay3 = st.columns(3)
                
                with col_lay1:
                    album_cols = st.number_input(
                        "📊 Colonne per pagina",
                        min_value=1, max_value=4, value=2, step=1,
                        key="album_cols_input",
                        help="Numero di colonne di figurine per ogni pagina (1-4)"
                    )
                
                with col_lay2:
                    album_rows = st.number_input(
                        "📏 Righe per pagina",
                        min_value=1, max_value=5, value=3, step=1,
                        key="album_rows_input",
                        help="Numero di righe di figurine per ogni pagina (1-5)"
                    )
                
                with col_lay3:
                    album_layout = st.selectbox(
                        "🔀 Distribuzione colonne",
                        ["Verticale (dritte)", "Obliquo (sfalsate)"],
                        key="album_layout_sel",
                        help="Verticale: colonne allineate. Obliquo: righe alternate sfalsate."
                    )

                st.divider()
                
                # --- SEZIONE ORDINAMENTO E FILTRO ---
                st.markdown("### 🔧 Ordinamento e Filtri")
                
                col_opt1, col_opt2 = st.columns(2)
                with col_opt1:
                    album_sort = st.selectbox(
                        "📅 Ordinamento Figurine",
                        ["Cronologico (Data)", "Alfabetico (Località)", "Ordine di Inserimento"],
                        key="album_sort_order"
                    )
                with col_opt2:
                    album_filter = st.selectbox(
                        "🔍 Filtra Eventi",
                        ["Tutti", "Solo Attivi", "Solo NEW", "Solo Elaborati (OK)"],
                        key="album_filter_sel"
                    )

                st.divider()
                
                # --- BOTTONE DI GENERAZIONE (form_submit_button) ---
                genera_album = st.form_submit_button("🏆 Genera Album Figurine", type="primary")

            # =============================================
            # LOGICA POST-FORM (eseguita solo al submit)
            # =============================================
            
            # Metriche (calcolate fuori dal form con i valori correnti)
            layout_value = "obliquo" if "Obliquo" in album_layout else "verticale"
            stickers_per_page = album_cols * album_rows
            total_pages = math.ceil(total_figurine / stickers_per_page)
            
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("🎴 Figurine Totali", total_figurine)
            col_m2.metric("📄 Pagine Album", total_pages)
            col_m3.metric("🖼️ Per Pagina", stickers_per_page)
            col_m4.metric("📐 Layout", f"{album_cols}×{album_rows}")

            if genera_album:
                # Salva il layout selezionato per la successiva generazione del flipbook
                st.session_state['album_cols'] = album_cols
                st.session_state['album_rows'] = album_rows
                
                # Applicazione ordinamento
                sorted_album_events = list(valid_album_events)
                
                if album_sort == "Cronologico (Data)":
                    sorted_album_events.sort(key=lambda e: WordGenerator.get_sort_date(e))
                elif album_sort == "Alfabetico (Località)":
                    sorted_album_events.sort(key=lambda e: e.get('location', '').strip().upper())
                
                # Applicazione filtro
                now_album = datetime.now()
                if album_filter == "Solo Attivi":
                    sorted_album_events = [ev for ev in sorted_album_events 
                                           if ev.get('_dt', datetime.max).date() >= now_album.date()]
                elif album_filter == "Solo NEW":
                    sorted_album_events = [ev for ev in sorted_album_events if ev.get('is_new')]
                elif album_filter == "Solo Elaborati (OK)":
                    sorted_album_events = [ev for ev in sorted_album_events if ev.get('sticker_processed')]
                
                if not sorted_album_events:
                    st.warning("Nessun evento corrisponde ai filtri selezionati.")
                else:
                    # Ricalcola dopo filtro
                    total_figurine_filtered = len(sorted_album_events)
                    total_pages_filtered = math.ceil(total_figurine_filtered / stickers_per_page)
                    
                    if total_figurine_filtered != total_figurine:
                        st.info(f"📊 Con i filtri attuali: **{total_figurine_filtered}** figurine su **{total_pages_filtered}** pagine")

                    album_output_dir = os.path.join(OUTPUT_DIR, "album")
                    
                    with st.spinner("🎨 Creazione dell'album in stile Panini... Attendere prego."):
                        # Sostituisci i path nelle copie degli eventi
                        album_events_to_use = []
                        used_stickers_count = 0
                        for ev in sorted_album_events:
                            ev_copy = dict(ev)
                            stk_p = ev_copy.get('sticker_image_path', '').replace('\\', '/')
                            
                            # Verifica robusta esistenza figurina
                            stk_exists = False
                            if stk_p:
                                if os.path.exists(stk_p): 
                                    stk_exists = True
                                elif os.path.exists(os.path.join(os.getcwd(), stk_p)):
                                    stk_exists = True
                                    stk_p = os.path.join(os.getcwd(), stk_p).replace('\\', '/')
                            
                            # Se non vogliamo ricalcolare e la figurina esiste, USALA come immagine sorgente
                            if not album_preprocess and stk_exists:
                                ev_copy['image_path'] = stk_p
                                used_stickers_count += 1
                            album_events_to_use.append(ev_copy)
                        
                        if used_stickers_count > 0:
                            st.info(f"✨ Utilizzate **{used_stickers_count}** figurine elaborate trovate in `output/images_album`.")
                        
                        # Prepara immagini custom come PIL Image
                        custom_cover_pil = None
                        custom_back_pil = None

                        # Priorita: 1) Copertina preset  2) Upload manuale  3) default (logo)
                        if selected_preset_file:
                            # Carica la copertina preset dal filesystem locale
                            preset_path = selected_preset_file
                            if not os.path.exists(preset_path):
                                # Prova nella directory corrente
                                preset_path = os.path.join(os.getcwd(), selected_preset_file)
                            if os.path.exists(preset_path):
                                try:
                                    custom_cover_pil = Image.open(preset_path).convert("RGBA")
                                    st.info(f"Copertina preset: `{selected_preset_file}`")
                                except Exception as e:
                                    st.warning(f"Impossibile leggere la copertina preset: {e}. Uso default.")
                            else:
                                st.warning(f"File copertina preset `{selected_preset_file}` non trovato. Uso default.")
                        elif uploaded_cover_img:
                            try:
                                custom_cover_pil = Image.open(uploaded_cover_img).convert("RGBA")
                            except Exception:
                                st.warning("Impossibile leggere l'immagine copertina. Uso default.")
                        
                        if uploaded_back_img:
                            try:
                                custom_back_pil = Image.open(uploaded_back_img).convert("RGBA")
                            except Exception:
                                st.warning("⚠️ Impossibile leggere l'immagine retro. Uso default.")
                        
                        gen = AlbumGenerator(
                            bg_image_path="giustidireno.png",
                            logo_path="LogoNOConfiniTrasparente.png",
                            rows=album_rows,
                            cols=album_cols,
                            layout=layout_value,
                            custom_cover_image=custom_cover_pil,
                            custom_back_image=custom_back_pil,
                            logo_white_bg=logo_white_bg,
                            logo_cover_white_bg=logo_cover_white_bg,
                            logo_cover_full_page=album_logo_cover_full_page,
                            show_banner=album_show_banner,
                            sticker_fill_mode=sticker_fill_mode,
                            force_aspect_ratio=album_force_aspect_ratio,
                            sticker_height_mm=sticker_height_mm,
                            empty_album_mode=album_empty_mode,
                            export_stickers=album_export_stickers,
                            show_summary=album_show_summary,
                            summary_events_per_page=album_summary_epp
                        )
                        cover_path, page_paths, pdf_buffer, pdf_empty_buffer, zip_buffer = gen.generate_full_album(
                            album_events_to_use, output_dir=album_output_dir
                        )
                        
                        st.session_state['album_cover'] = cover_path
                        st.session_state['album_pages'] = page_paths
                        st.session_state['album_pdf'] = pdf_buffer
                        st.session_state['album_pdf_empty'] = pdf_empty_buffer
                        st.session_state['album_zip'] = zip_buffer
                    
                    st.success(f"✅ Album generato! {len(page_paths) - 1} pagine figurine + copertina + retro.")
                    st.balloons()

            # =============================================
            # SEZIONE 5: ANTEPRIMA E DOWNLOAD (fuori dal form, sempre visibile se album già generato)
            # =============================================
            if 'album_cover' in st.session_state and st.session_state.get('album_pages'):
                st.divider()
                st.markdown("### 📖 Anteprima Album")
                
                # Download PDF e/o ZIP
                col_down1, col_down2, col_down3 = st.columns(3)
                with col_down1:
                    if st.session_state.get('album_pdf'):
                        st.download_button(
                            label="📥 Scarica Album Completo",
                            data=st.session_state['album_pdf'],
                            file_name="Album_Figurine.pdf",
                            mime="application/pdf",
                            type="primary",
                            key="btn_download_album_pdf"
                        )
                
                with col_down2:
                    if st.session_state.get('album_pdf_empty'):
                        st.download_button(
                            label="📥 Scarica Album VUOTO",
                            data=st.session_state['album_pdf_empty'],
                            file_name="Album_Vuoto.pdf",
                            mime="application/pdf",
                            key="btn_download_album_empty"
                        )
                        
                with col_down3:
                    if st.session_state.get('album_zip'):
                        st.download_button(
                            label="📥 Scarica ZIP Figurine",
                            data=st.session_state['album_zip'],
                            file_name="Figurine_Singole_da_stampare.zip",
                            mime="application/zip",
                            type="primary" if st.session_state.get('album_pdf_empty') else "secondary",
                            key="btn_download_album_zip"
                        )
                
                # =============================================
                # SEZIONE 5b: CREA FLIPBOOK
                # =============================================
                st.divider()
                if st.button("📚 Create Flipbook", type="secondary", key="btn_create_flipbook",
                             help="Estrae le pagine dal PDF come immagini JPG, crea pages.json e salva tutto localmente e su GitHub (docs/)."):
                    pdf_data = st.session_state.get('album_pdf')
                    if not pdf_data:
                        st.error("❌ Nessun PDF disponibile. Genera prima l'album.")
                    else:
                        with st.spinner("📚 Creazione Flipbook in corso... Estrazione pagine dal PDF a 300 DPI"):
                            try:
                                import fitz  # PyMuPDF
                                
                                # Calcola formato da session state (default 2x3 se non trovato)
                                album_cols = st.session_state.get('album_cols', 2)
                                album_rows = st.session_state.get('album_rows', 3)
                                album_format = f"{album_cols}x{album_rows}"

                                # Prepara cartelle locali
                                flipbook_images_dir = os.path.join("docs", "albums", album_format)
                                flipbook_docs_dir = "docs"
                                os.makedirs(flipbook_images_dir, exist_ok=True)
                                
                                # Apri il PDF dal buffer
                                pdf_data.seek(0)
                                pdf_bytes = pdf_data.read()
                                pdf_data.seek(0)  # Reset per usi futuri
                                
                                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                                total_pdf_pages = len(doc)
                                
                                progress_bar = st.progress(0, text="Estraendo pagine...")
                                
                                pages_json = []
                                github_mgr = st.session_state.get('github_manager')
                                upload_errors = []
                                
                                for page_idx in range(total_pdf_pages):
                                    page_num = page_idx + 1
                                    progress_bar.progress(
                                        page_num / (total_pdf_pages + 1),
                                        text=f"Estraendo pagina {page_num} di {total_pdf_pages}..."
                                    )
                                    
                                    # Renderizza la pagina a 300 DPI
                                    page = doc.load_page(page_idx)
                                    # 300 DPI / 72 DPI default = ~4.17x zoom
                                    zoom = 300.0 / 72.0
                                    mat = fitz.Matrix(zoom, zoom)
                                    pix = page.get_pixmap(matrix=mat)
                                    
                                    # Converti in PIL Image e salva come JPEG
                                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                                    
                                    img_filename = f"page_{page_num}.jpg"
                                    img_local_path = os.path.join(flipbook_images_dir, img_filename)
                                    img.save(img_local_path, "JPEG", quality=90, dpi=(300, 300))
                                    
                                    # Determina tipo: prime due e ultime due = "cartone"
                                    if page_num in [1, 2, total_pdf_pages - 1, total_pdf_pages]:
                                        page_type = "cartone"
                                    else:
                                        page_type = "carta"
                                    
                                    pages_json.append({
                                        "page_number": page_num,
                                        # Il JSON ora vive nella stessa cartella delle immagini, path relativo semplice
                                        "image": f"page_{page_num}.jpg",
                                        "type": page_type,
                                        "dpi": 300
                                    })
                                    
                                    # Upload immagine su GitHub
                                    if github_mgr:
                                        with open(img_local_path, "rb") as f_img:
                                            img_bytes = f_img.read()
                                        repo_path = f"docs/albums/{album_format}/{img_filename}"
                                        ok, msg = github_mgr.upload_file(
                                            repo_path, img_bytes,
                                            commit_message=f"Flipbook: upload {img_filename} ({album_format})"
                                        )
                                        if not ok:
                                            upload_errors.append(msg)
                                
                                doc.close()
                                
                                # Salva pages.json localmente nella cartella specifica del formato
                                pages_json_path = os.path.join(flipbook_images_dir, "pages.json")
                                pages_json_content = json.dumps(pages_json, ensure_ascii=False, indent=4)
                                with open(pages_json_path, "w", encoding="utf-8") as f_json:
                                    f_json.write(pages_json_content)
                                
                                # Upload pages.json su GitHub
                                if github_mgr:
                                    json_repo_path = f"docs/albums/{album_format}/pages.json"
                                    ok, msg = github_mgr.upload_file(
                                        json_repo_path,
                                        pages_json_content.encode("utf-8"),
                                        commit_message=f"Flipbook: upload pages.json ({album_format})"
                                    )
                                    if not ok:
                                        upload_errors.append(msg)
                                
                                progress_bar.progress(1.0, text="Completato!")
                                
                                # Report finale
                                st.success(
                                    f"✅ Flipbook creato con successo!\n\n"
                                    f"📄 **{total_pdf_pages}** pagine estratte a 300 DPI\n\n"
                                    f"💾 Immagini salvate in `docs/images/`\n\n"
                                    f"📋 `pages.json` salvato in `docs/`\n\n"
                                    f"{'☁️ File caricati su GitHub' if github_mgr else '⚠️ GitHub non configurato, salvato solo localmente'}"
                                )
                                
                                if upload_errors:
                                    st.warning("⚠️ Alcuni upload su GitHub hanno avuto problemi:\n" + "\n".join(upload_errors))
                                
                            except ImportError:
                                st.error(
                                    "❌ **PyMuPDF non installato!**\n\n"
                                    "Per usare il Flipbook è necessario installare PyMuPDF:\n\n"
                                    "```\npip install PyMuPDF\n```"
                                )
                            except Exception as e:
                                st.error(f"❌ Errore creazione Flipbook: {e}")
                
                st.divider()
                
                # Copertina
                st.markdown("#### 🎨 Copertina")
                if os.path.exists(st.session_state['album_cover']):
                    st.image(st.session_state['album_cover'], caption="Copertina Album", **IMG_WIDTH_ARG)
                
                st.divider()
                
                # Pagine — @st.fragment per navigazione fluida senza rerun pagina intera
                @st.fragment
                def album_page_browser():
                    st.markdown("#### 📄 Pagine dell'Album")
                    album_pages = st.session_state['album_pages']
                    
                    # Navigazione pagine
                    if len(album_pages) > 1:
                        page_select = st.slider(
                            "Sfoglia le pagine", 
                            min_value=1, 
                            max_value=len(album_pages), 
                            value=1,
                            key="album_page_slider"
                        )
                    else:
                        page_select = 1
                    
                    page_path = album_pages[page_select - 1]
                    if os.path.exists(page_path):
                        # Identifica se è la back cover
                        is_back = (page_select == len(album_pages))
                        caption = "Pagina Finale (Retro)" if is_back else f"Pagina {page_select} di {len(album_pages)}"
                        st.image(page_path, caption=caption, **IMG_WIDTH_ARG)
                    
                    # Griglia miniature
                    if len(album_pages) > 1:
                        st.divider()
                        with st.expander("🗂️ Visualizza tutte le Miniature (Miniature)", expanded=False):
                            n_thumb_cols = min(4, len(album_pages))
                            thumb_cols = st.columns(n_thumb_cols)
                            for idx, pg_path in enumerate(album_pages):
                                with thumb_cols[idx % n_thumb_cols]:
                                    if os.path.exists(pg_path):
                                        is_back = (idx == len(album_pages) - 1)
                                        cap = "Retro" if is_back else f"Pag. {idx + 1}"
                                        st.image(pg_path, caption=cap, width=280)
                
                album_page_browser()