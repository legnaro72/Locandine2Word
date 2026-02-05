# Locandine2Word - Test Suite

import os
import sys

# Aggiungi la directory corrente al path
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test che tutti i moduli si importino correttamente"""
    print("[TEST 1] Verifica import moduli...")
    
    try:
        from ocr_engine import LocandineOCR
        print("   [OK] ocr_engine importato")
    except Exception as e:
        print(f"   [FAIL] Errore import ocr_engine: {e}")
        return False
    
    try:
        from word_generator import WordGenerator
        print("   [OK] word_generator importato")
    except Exception as e:
        print(f"   [FAIL] Errore import word_generator: {e}")
        return False
    
    return True

def test_ocr_initialization():
    """Test inizializzazione OCR"""
    print("\n[TEST 2] Inizializzazione OCR Engine...")
    
    try:
        from ocr_engine import LocandineOCR
        ocr = LocandineOCR()
        print("   [OK] OCR Engine inizializzato correttamente")
        return True
    except Exception as e:
        print(f"   [FAIL] Errore inizializzazione OCR: {e}")
        return False

def test_word_generator():
    """Test generatore Word"""
    print("\n[TEST 3] Inizializzazione Word Generator...")
    
    try:
        from word_generator import WordGenerator
        generator = WordGenerator()
        print("   [OK] Word Generator inizializzato correttamente")
        return True
    except Exception as e:
        print(f"   [FAIL] Errore inizializzazione Word Generator: {e}")
        return False

def test_directories():
    """Test creazione directory"""
    print("\n[TEST 4] Verifica directory...")
    
    dirs = ['uploads', 'output']
    for dir_name in dirs:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
            print(f"   [OK] Directory '{dir_name}' creata")
        else:
            print(f"   [OK] Directory '{dir_name}' gia' esistente")
    
    return True

def test_json_database():
    """Test database JSON"""
    print("\n[TEST 5] Verifica database JSON...")
    
    import json
    
    if not os.path.exists('data.json'):
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump([], f)
        print("   [OK] File data.json creato")
    else:
        try:
            with open('data.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"   [OK] File data.json valido ({len(data)} eventi)")
        except Exception as e:
            print(f"   [FAIL] Errore lettura data.json: {e}")
            return False
    
    return True

def run_all_tests():
    """Esegue tutti i test"""
    print("=" * 50)
    print("  LOCANDINE2WORD - TEST SUITE")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_ocr_initialization,
        test_word_generator,
        test_directories,
        test_json_database
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 50)
    print("  RISULTATI")
    print("=" * 50)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n[OK] Test superati: {passed}/{total}")
    
    if passed == total:
        print("\n[SUCCESS] Tutti i test sono passati! L'applicazione e' pronta.")
        print("\n[INFO] Per avviare l'app, esegui: streamlit run app.py")
    else:
        print("\n[WARNING] Alcuni test sono falliti. Controlla gli errori sopra.")
    
    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
