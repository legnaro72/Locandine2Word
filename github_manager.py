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
        self.g = Github(auth=self.auth, timeout=120)
        self.repo = self.g.get_repo(repo_name)
        self.backup_filename = "github_backup.zip"

    def create_backup_zip(self, data_file, uploads_dir, images_album_dir="output/images_album"):
        """Crea due file zip in memoria: uno per i dati (data + uploads) e uno per i ritagli (images_album)."""
        zips = {}
        
        # --- ZIP 1: Data e Uploads ---
        zip_main_buffer = io.BytesIO()
        active_images = set()

        with zipfile.ZipFile(zip_main_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            if os.path.exists(data_file):
                zf.write(data_file, arcname='data.json')
                try:
                    with open(data_file, 'r', encoding='utf-8') as f:
                        events = json.load(f)
                    for e in events:
                        img = e.get('image_path', '')
                        if img:
                            active_images.add(os.path.basename(img))
                except:
                    pass
            
            if os.path.exists("CITY_FALLBACK.json"):
                zf.write("CITY_FALLBACK.json", arcname="CITY_FALLBACK.json")
            
            if os.path.exists(uploads_dir):
                for root, _, files in os.walk(uploads_dir):
                    for file in files:
                        if file in active_images:
                            file_path = os.path.join(root, file)
                            arcname = f"uploads/{os.path.basename(file)}"
                            zf.write(file_path, arcname=arcname)
        
        zip_main_buffer.seek(0)
        zips['github_backup_main.zip'] = zip_main_buffer.getvalue()

        # --- ZIP 2: Images Album (Figurine Elaborate) ---
        zip_album_buffer = io.BytesIO()
        has_album_files = False
        with zipfile.ZipFile(zip_album_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            if os.path.exists(images_album_dir):
                for root, _, files in os.walk(images_album_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        has_album_files = True
                        arcname = f"output/images_album/{os.path.basename(file)}"
                        zf.write(file_path, arcname=arcname)
        
        if has_album_files:
            zip_album_buffer.seek(0)
            zips['github_backup_album.zip'] = zip_album_buffer.getvalue()

        return zips

    def upload_backup(self, zips_dict):
        """Carica la lista di zip file sul repository in sequenza separata, riducendo le dimensioni dei singoli Payload JSON."""
        message = f"Backup automatico del {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Multi-Pacchetto)"
        errors = []
        
        for path, zip_content in zips_dict.items():
            try:
                # Cerca lo SHA senza scaricare il contenuto
                contents = self.repo.get_contents(path)
                self.repo.update_file(path, message, zip_content, contents.sha)
            except Exception as e:
                # Se il file in questione non esiste, crealo
                if "404" in str(e) or "Not Found" in str(e):
                    try:
                        self.repo.create_file(path, message, zip_content)
                    except Exception as e2:
                        errors.append(f"Errore durante creazione {path}: {e2}")
                else:
                    errors.append(f"Errore durante aggiornamento {path}: {e}")
        
        # --- PULIZIA: Elimina il vecchio backup monolitico legacy se esiste ---
        try:
            old_backup = self.repo.get_contents(self.backup_filename)  # "github_backup.zip"
            self.repo.delete_file(
                self.backup_filename,
                f"Rimosso backup monolitico legacy ({self.backup_filename}) dopo migrazione a multi-pacchetto",
                old_backup.sha
            )
        except:
            pass  # Se non esiste, niente da fare
                    
        if errors:
            return False, "\n".join(errors)
        return True, "Pacchetti Backup (Multiplo) aggiornati su GitHub!"

    def download_backup(self):
        """Scarica i/il file backup.zip dal repository GitHub. Preferisce i nuovi split; usa il legacy solo come fallback."""
        zips_dict = {}
        import requests
        headers = {"Authorization": f"token {self.auth.token}"}
        
        # 1. Prova prima i nuovi archivi separati (strategia multi-pacchetto)
        new_targets = ['github_backup_main.zip', 'github_backup_album.zip']
        
        for path in new_targets:
            try:
                contents = self.repo.get_contents(path)
                response = requests.get(contents.download_url, headers=headers, timeout=120)
                if response.status_code == 200:
                    zips_dict[path] = response.content
            except:
                pass  # file opzionale o non ancora creato
        
        # 2. SOLO se NON abbiamo trovato il backup main (nuovo), proviamo il legacy monolitico
        #    IMPORTANTE: NON scaricare il legacy se i nuovi esistono, altrimenti sovrascrive data.json!
        if 'github_backup_main.zip' not in zips_dict:
            try:
                contents = self.repo.get_contents('github_backup.zip')
                response = requests.get(contents.download_url, headers=headers, timeout=120)
                if response.status_code == 200:
                    zips_dict['github_backup.zip'] = response.content
            except:
                pass
                
        if not zips_dict:
            raise Exception("Nessun frammento di backup trovato su GitHub.")
            
        return zips_dict

    def upload_file(self, repo_path, file_content, commit_message=None):
        """
        Carica un singolo file (binario o testo) nel repository GitHub al path specificato.
        Args:
            repo_path: percorso nel repo (es. 'docs/images/page_1.jpg')
            file_content: bytes del file
            commit_message: messaggio di commit (opzionale)
        Returns:
            (success: bool, message: str)
        """
        if commit_message is None:
            commit_message = f"Upload {repo_path} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        try:
            # Verifica se il file esiste già
            try:
                contents = self.repo.get_contents(repo_path)
                self.repo.update_file(repo_path, commit_message, file_content, contents.sha)
            except Exception as e:
                if "404" in str(e) or "Not Found" in str(e):
                    self.repo.create_file(repo_path, commit_message, file_content)
                else:
                    raise e
            return True, f"File {repo_path} caricato con successo."
        except Exception as e:
            return False, f"Errore upload {repo_path}: {e}"

    def restore_from_zip(self, zips_dict):
        """Estrae i contenuti di tutti gli zip passati nella directory corrente."""
        for name, zip_content in zips_dict.items():
            zip_file = io.BytesIO(zip_content)
            with zipfile.ZipFile(zip_file) as z:
                z.extractall(".")
        return True