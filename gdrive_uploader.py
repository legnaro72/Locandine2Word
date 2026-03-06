"""
Google Drive Uploader Module (Streamlit Cloud Compatible)
Carica file PDF su Google Drive usando OAuth2 con refresh token.
Il refresh token è memorizzato in st.secrets -> [gdrive_oauth].
Il Folder ID è in credenziali.json.
"""
import os
import json
import streamlit as st


# --- Costanti ---
CREDENTIALS_FILE = "credenziali.json"
GDRIVE_TARGET_FILENAME = "Eventi Programmati Coordinamento Liguria e Massa.pdf"

DEFAULT_CREDENTIALS = {
    "folder_id": "",
}


def load_credentials():
    """Carica le credenziali dal file JSON."""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
                creds = json.load(f)
            for key, val in DEFAULT_CREDENTIALS.items():
                if key not in creds:
                    creds[key] = val
            return creds
        except Exception:
            pass
    return DEFAULT_CREDENTIALS.copy()


def save_credentials(creds):
    """Salva le credenziali nel file JSON locale."""
    with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
        json.dump(creds, f, ensure_ascii=False, indent=2)


def save_credentials_to_cloud(github_manager):
    """Salva le credenziali su GitHub (cloud)."""
    if not github_manager:
        return False, "GitHub Manager non disponibile."
    try:
        creds = load_credentials()
        creds_bytes = json.dumps(creds, ensure_ascii=False, indent=2).encode('utf-8')
        success, msg = github_manager.upload_file(
            CREDENTIALS_FILE, creds_bytes,
            commit_message="Aggiornamento Folder ID Google Drive"
        )
        return success, msg
    except Exception as e:
        return False, f"Errore salvataggio cloud: {e}"


def load_credentials_from_cloud(github_manager):
    """Scarica le credenziali da GitHub (cloud)."""
    if not github_manager:
        return False, "GitHub Manager non disponibile."
    try:
        import requests
        contents = github_manager.repo.get_contents(CREDENTIALS_FILE)
        headers = {"Authorization": f"token {github_manager.auth.token}"}
        response = requests.get(contents.download_url, headers=headers, timeout=30)
        if response.status_code == 200:
            creds = response.json()
            save_credentials(creds)
            return True, "Credenziali scaricate dal cloud!"
        return False, f"Errore HTTP: {response.status_code}"
    except Exception as e:
        if "404" in str(e) or "Not Found" in str(e):
            return False, "Nessuna credenziale trovata sul cloud."
        return False, f"Errore: {e}"


def _get_gdrive_service():
    """
    Crea il servizio Google Drive usando OAuth2 con refresh token.
    I dati OAuth sono letti da st.secrets -> [gdrive_oauth].
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    oauth_info = st.secrets.get("gdrive_oauth", None)

    if not oauth_info:
        return None, (
            "⚠️ **OAuth2 non configurato nei Secrets di Streamlit.**\n\n"
            "Esegui `python gdrive_setup.py` in locale per generare il token, "
            "poi copia il blocco `[gdrive_oauth]` nei Secrets di Streamlit Cloud."
        )

    try:
        credentials = Credentials(
            token=None,
            refresh_token=oauth_info["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=oauth_info["client_id"],
            client_secret=oauth_info["client_secret"],
            scopes=['https://www.googleapis.com/auth/drive.file']
        )

        # Forza il refresh per ottenere un access token valido
        credentials.refresh(Request())

        service = build('drive', 'v3', credentials=credentials)
        return service, None
    except Exception as e:
        return None, f"Errore autenticazione Google Drive: {e}"


def upload_pdf_to_gdrive(pdf_path, progress_callback=None):
    """
    Carica un file PDF su Google Drive dell'utente autenticato via OAuth2.
    Il file viene rinominato in GDRIVE_TARGET_FILENAME.
    Se esiste già viene aggiornato (non duplicato).

    Returns: (success, message, link)
    """
    creds = load_credentials()

    if not os.path.exists(pdf_path):
        return False, f"File PDF non trovato: {pdf_path}", None

    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return False, (
            "❌ Librerie Google non installate.\n"
            "Aggiungi al requirements.txt:\n"
            "- google-api-python-client\n- google-auth\n- google-auth-oauthlib"
        ), None

    service, error = _get_gdrive_service()
    if not service:
        return False, error, None

    if progress_callback:
        progress_callback("Connesso a Google Drive!")

    folder_id = creds.get('folder_id', '').strip()

    try:
        # 1. Cerca file esistente per aggiornare anziché duplicare
        query = f"name = '{GDRIVE_TARGET_FILENAME}' and trashed = false"
        if folder_id:
            query += f" and '{folder_id}' in parents"

        results = service.files().list(
            q=query, spaces='drive',
            fields='files(id, name)', pageSize=5
        ).execute()
        existing_files = results.get('files', [])

        # 2. Prepara metadata
        file_metadata = {'name': GDRIVE_TARGET_FILENAME}
        if folder_id:
            file_metadata['parents'] = [folder_id]

        media = MediaFileUpload(pdf_path, mimetype='application/pdf', resumable=True)

        if progress_callback:
            progress_callback("Upload in corso...")

        # 3. Upload o update
        if existing_files:
            file_id = existing_files[0]['id']
            service.files().update(fileId=file_id, media_body=media).execute()
            action = "aggiornato"
        else:
            file = service.files().create(
                body=file_metadata, media_body=media, fields='id'
            ).execute()
            file_id = file.get('id')
            action = "caricato"

        # 4. Ottieni link
        try:
            file_info = service.files().get(fileId=file_id, fields='webViewLink').execute()
            link = file_info.get('webViewLink', f'https://drive.google.com/file/d/{file_id}/view')
        except Exception:
            link = f'https://drive.google.com/file/d/{file_id}/view'

        return True, f"✅ PDF {action} su Google Drive con successo!", link

    except Exception as e:
        return False, f"Errore durante l'upload: {e}", None


def render_credentials_sidebar(github_manager=None):
    """Renderizza la sezione Folder ID nella sidebar."""
    with st.expander("📁 Google Drive — Folder ID", expanded=False):
        current_creds = load_credentials()

        new_folder_id = st.text_input(
            "📁 Folder ID di destinazione",
            value=current_creds.get('folder_id', ''),
            key="gdrive_folder_input",
            help="ID della cartella Google Drive. Lo trovi nell'URL: "
                 "drive.google.com/drive/folders/**QUESTO_È_L_ID**"
        )

        st.caption(f"📄 Nome file: **{GDRIVE_TARGET_FILENAME}**")

        col1, col2 = st.columns(2)

        if col1.button("💾 Salva", key="save_folder_id"):
            save_credentials({"folder_id": new_folder_id})
            st.success("✅ Folder ID salvato!")
            return True

        if col2.button("☁️ Salva su Cloud", key="save_folder_cloud", disabled=not github_manager):
            save_credentials({"folder_id": new_folder_id})
            success, msg = save_credentials_to_cloud(github_manager)
            if success:
                st.success("✅ Salvato su cloud!")
            else:
                st.error(msg)
            return True

        if st.button("📥 Scarica da Cloud", key="load_folder_cloud", disabled=not github_manager):
            success, msg = load_credentials_from_cloud(github_manager)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.warning(msg)

        st.divider()

        # Stato OAuth
        oauth_info = st.secrets.get("gdrive_oauth", None)
        if oauth_info:
            st.success("✅ OAuth2 configurato nei Secrets")
        else:
            st.warning(
                "⚠️ OAuth2 non configurato.\n\n"
                "Esegui `python gdrive_setup.py` in locale, "
                "poi copia il blocco nei Secrets."
            )

    return False
