import os
import zipfile
import io
import json
from datetime import datetime
from github import Github, Auth
import streamlit as st

class GithubManager:
    def __init__(self, token, repo_name):
        self.auth = Auth.Token(token)
        # Aumentiamo il timeout a 120 secondi per gestire file più pesanti
        self.g = Github(auth=self.auth, timeout=120)
        self.repo = self.g.get_repo(repo_name)
        self.backup_filename = "github_backup.zip"

    def create_backup_zip(self, data_file, uploads_dir):
        """Crea uno zip in memoria con data.json e la cartella uploads."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 1. Aggiungi il database JSON
            if os.path.exists(data_file):
                zf.write(data_file, arcname='data.json')
            
            # 2. Aggiungi la cartella uploads
            if os.path.exists(uploads_dir):
                for root, _, files in os.walk(uploads_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # Salva nel zip con percorso relativo 'uploads/nomefile'
                        zf.write(file_path, arcname=os.path.join('uploads', file))
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    def upload_backup(self, zip_content):
        """Carica (o aggiorna) il file backup.zip sul repository GitHub."""
        path = self.backup_filename
        message = f"Backup automatico del {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        try:
            # Cerca lo SHA senza scaricare il contenuto (ottimizzato)
            contents = self.repo.get_contents(path)
            # update_file invia il contenuto in base64, che aumenta il volume del 33%
            self.repo.update_file(path, message, zip_content, contents.sha)
            return True, "Backup aggiornato su GitHub!"
        except Exception as e:
            # Se il file non esiste, lo creiamo
            if "404" in str(e):
                self.repo.create_file(path, message, zip_content)
                return True, "Nuovo backup creato su GitHub!"
            else:
                return False, f"Errore durante l'upload: {e}"

    def download_backup(self):
        """Scarica il file backup.zip dal repository GitHub."""
        try:
            # Per file > 1MB, get_contents restituisce solo i metadati, non il contenuto.
            # Dobbiamo usare l'URL di download diretto.
            contents = self.repo.get_contents(self.backup_filename)
            
            import requests
            # Usiamo il token per scaricare l'URL (necessario se il repo è privato)
            # NOTA: GITHUB_TOKEN è accessibile dalla variabile fornita all'init
            headers = {"Authorization": f"token {self.auth.token}"}
            response = requests.get(contents.download_url, headers=headers, timeout=120)
            
            if response.status_code == 200:
                return response.content
            else:
                raise Exception(f"GitHub API ha risposto con codice {response.status_code}")
                
        except Exception as e:
            raise Exception(f"Impossibile scaricare il backup da GitHub: {e}")

    def restore_from_zip(self, zip_content):
        """Estrae il contenuto dello zip nella directory corrente."""
        zip_file = io.BytesIO(zip_content)
        with zipfile.ZipFile(zip_file) as z:
            z.extractall(".")
        return True
