"""
Script rapido per generare un documento Word di esempio
senza usare OCR (per evitare problemi di download modelli)
"""
from word_generator import WordGenerator
import json
import os

print("=" * 60)
print("  LOCANDINE2WORD - Generazione documento di esempio")
print("=" * 60)

# Crea eventi di esempio
example_events = [
    {
        'title': 'Mostra d\'Arte Contemporanea',
        'date': '2026-02-20',
        'time': '18:00',
        'location': 'Galleria Civica',
        'image_path': 'uploads/placeholder.jpg',
        'added_on': '2026-02-05 00:30:00'
    },
    {
        'title': 'Concerto di Primavera',
        'date': '2026-03-15',
        'time': '20:30',
        'location': 'Teatro Comunale',
        'image_path': 'uploads/placeholder.jpg',
        'added_on': '2026-02-05 00:30:00'
    },
    {
        'title': 'Spettacolo Teatrale',
        'date': '2026-04-10',
        'time': '21:00',
        'location': 'Teatro Nuovo',
        'image_path': 'uploads/placeholder.jpg',
        'added_on': '2026-02-05 00:30:00'
    }
]

# Salva in data.json
print("\n[1] Salvataggio eventi in data.json...")
with open('data.json', 'w', encoding='utf-8') as f:
    json.dump(example_events, f, ensure_ascii=False, indent=2)
print(f"   [OK] {len(example_events)} eventi salvati")

# Genera documento Word
print("\n[2] Generazione documento Word...")
generator = WordGenerator()
output_path = "output/esempio_eventi.docx"

# Crea directory se non esiste
os.makedirs('output', exist_ok=True)

generator.generate_from_data(example_events, output_path)
print(f"   [OK] Documento generato: {output_path}")
print(f"   [INFO] {len(example_events)} eventi inclusi (ordinati cronologicamente)")

print("\n" + "=" * 60)
print("  [SUCCESS] Documento di esempio creato!")
print("=" * 60)
print(f"\n[INFO] Apri il file: {output_path}")
print("[INFO] Per usare l'app web: streamlit run app.py")
