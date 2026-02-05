"""
Script di esempio per testare il sistema senza interfaccia Streamlit
Utile per debugging e test rapidi
"""
from ocr_engine import LocandineOCR
from word_generator import WordGenerator
import json
import os

def example_usage():
    """Esempio di utilizzo del sistema"""
    
    print("=" * 60)
    print("  LOCANDINE2WORD - Esempio di utilizzo")
    print("=" * 60)
    
    # 1. Inizializza OCR
    print("\n[1] Inizializzazione OCR Engine...")
    ocr = LocandineOCR()
    print("   [OK] OCR pronto")
    
    # 2. Esempio di analisi (se hai un'immagine di test)
    print("\n[2] Esempio di analisi locandina...")
    print("   [INFO] Per testare, metti un'immagine in 'uploads/test.jpg'")
    
    test_image = "uploads/test.jpg"
    if os.path.exists(test_image):
        print(f"   [ANALYZING] Analisi di {test_image}...")
        result = ocr.analyze_poster(test_image)
        
        print("\n   [RESULTS] Risultati:")
        print(f"   - Titolo: {result['title']}")
        print(f"   - Data: {result['date']}")
        print(f"   - Orario: {result['time']}")
        print(f"   - Luogo: {result['location']}")
        print(f"\n   [TEXT] Testo completo estratto:")
        print("   " + "-" * 50)
        print("   " + result['full_text'].replace('\n', '\n   '))
        print("   " + "-" * 50)
    else:
        print("   [WARNING] Nessuna immagine di test trovata")
        print("   [INFO] Crea degli eventi di esempio...")
        
        # Crea eventi di esempio
        example_events = [
            {
                'title': 'Concerto di Primavera',
                'date': '2026-03-15',
                'time': '20:30',
                'location': 'Teatro Comunale',
                'image_path': 'uploads/placeholder.jpg',
                'added_on': '2026-02-05 00:30:00'
            },
            {
                'title': 'Mostra d\'Arte Contemporanea',
                'date': '2026-02-20',
                'time': '18:00',
                'location': 'Galleria Civica',
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
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(example_events, f, ensure_ascii=False, indent=2)
        
        print("   [OK] 3 eventi di esempio creati in data.json")
    
    # 3. Genera documento Word
    print("\n[3] Generazione documento Word...")
    
    # Carica eventi
    with open('data.json', 'r', encoding='utf-8') as f:
        events = json.load(f)
    
    if events:
        generator = WordGenerator()
        output_path = "output/esempio_eventi.docx"
        
        # Crea directory se non esiste
        os.makedirs('output', exist_ok=True)
        
        generator.generate_from_data(events, output_path)
        print(f"   [OK] Documento generato: {output_path}")
        print(f"   [INFO] {len(events)} eventi inclusi")
    else:
        print("   [WARNING] Nessun evento da generare")
    
    print("\n" + "=" * 60)
    print("  [SUCCESS] Test completato!")
    print("=" * 60)
    print("\n[INFO] Per usare l'interfaccia web, esegui: streamlit run app.py")

if __name__ == "__main__":
    example_usage()
