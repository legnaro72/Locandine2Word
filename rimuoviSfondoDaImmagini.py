import os
import cv2
import numpy as np
from tkinter import Tk, filedialog

def scegli_cartella():
    root = Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="Seleziona la cartella con le immagini")
    return folder

def rimuovi_sfondo_bianco(img):
    # Converti in RGBA
    img_rgba = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)

    # Crea maschera dei pixel quasi bianchi
    lower = np.array([240, 240, 240])
    upper = np.array([255, 255, 255])
    mask_white = cv2.inRange(img, lower, upper)

    # Flood fill dai bordi per trovare SOLO lo sfondo
    h, w = mask_white.shape
    flood_mask = np.zeros((h + 2, w + 2), np.uint8)

    floodfilled = mask_white.copy()

    # Riempie dai 4 angoli (background)
    cv2.floodFill(floodfilled, flood_mask, (0, 0), 128)
    cv2.floodFill(floodfilled, flood_mask, (w-1, 0), 128)
    cv2.floodFill(floodfilled, flood_mask, (0, h-1), 128)
    cv2.floodFill(floodfilled, flood_mask, (w-1, h-1), 128)

    # Solo il bianco connesso ai bordi → sfondo
    background_mask = (floodfilled == 128)

    # Applica trasparenza
    img_rgba[background_mask] = [0, 0, 0, 0]

    return img_rgba

def processa_cartella(cartella):
    estensioni = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff')

    for file in os.listdir(cartella):
        if file.lower().endswith(estensioni):
            path = os.path.join(cartella, file)
            print(f"Elaboro: {file}")

            img = cv2.imread(path)

            if img is None:
                print(f"Errore nel leggere {file}")
                continue

            risultato = rimuovi_sfondo_bianco(img)

            nome, _ = os.path.splitext(file)
            output_path = os.path.join(cartella, f"{nome}_SS.png")

            cv2.imwrite(output_path, risultato)

    print("✔ Elaborazione completata!")

if __name__ == "__main__":
    cartella = scegli_cartella()
    if cartella:
        processa_cartella(cartella)
    else:
        print("Nessuna cartella selezionata.")