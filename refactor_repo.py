import os
import shutil

DOCS = "docs"
OLD_IMAGES = os.path.join(DOCS, "images")
NEW_ALBUM = os.path.join(DOCS, "albums", "2x3")

print("Creazione nuova struttura...")

os.makedirs(NEW_ALBUM, exist_ok=True)

print("Spostamento immagini...")

if os.path.exists(OLD_IMAGES):
    for file in os.listdir(OLD_IMAGES):
        src = os.path.join(OLD_IMAGES, file)
        dst = os.path.join(NEW_ALBUM, file)

        if os.path.isfile(src):
            shutil.move(src, dst)
            print("moved:", file)

    print("Rimozione cartella images vuota")

    try:
        os.rmdir(OLD_IMAGES)
    except:
        pass

print("Refactor completato")
