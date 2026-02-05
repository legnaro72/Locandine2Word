# 🚀 GUIDA RAPIDA - Locandine2Word

## ⚡ Avvio Rapido (3 passi)

### 1. Verifica installazione
```bash
python quick_demo.py
```
Questo crea un documento Word di esempio in `output/esempio_eventi.docx`

### 2. Avvia l'applicazione web
**Opzione A - Doppio click:**
```
avvia_app.bat
```

**Opzione B - Da terminale:**
```bash
streamlit run app.py
```

### 3. Usa l'applicazione
L'app si aprirà automaticamente nel browser su `http://localhost:8501`

---

## 📋 Workflow completo

1. **Carica Locandine** (tab "📤 Carica Locandine")
   - Clicca "Browse files"
   - Seleziona una o più immagini JPG/PNG
   - Clicca "🔍 Analizza con OCR"

2. **Verifica e Modifica**
   - Controlla i dati estratti automaticamente
   - Modifica se necessario
   - Clicca "💾 Salva evento"

3. **Genera Documento**
   - Vai alla tab "📖 Anteprima Documento"
   - Clicca "📥 Genera e Scarica Documento Word"
   - Scarica il file generato

---

## ⚙️ Funzionalità principali

### OCR Automatico
- Estrae **data**, **titolo**, **orario**, **luogo**
- Supporta formati multipli di date italiane
- Riconoscimento intelligente del testo

### Ordinamento Cronologico
- Gli eventi sono sempre ordinati per data
- Inserimento automatico nel punto corretto
- Nessun bisogno di riordinare manualmente

### Gestione Eventi
- Visualizza tutti gli eventi salvati
- Modifica o elimina eventi
- Database JSON persistente

### Esportazione Word
- Formato professionale
- Tabelle con immagine + testo
- Formattazione automatica

---

## 🔧 Risoluzione Problemi

### L'OCR è lento la prima volta
**Normale!** EasyOCR scarica i modelli al primo avvio (~100MB)
- Attendi il completamento del download
- Le volte successive sarà veloce

### Errori di encoding nel terminale
**Soluzione:** Usa l'interfaccia web Streamlit invece della console
```bash
streamlit run app.py
```

### Il documento Word non si apre
**Verifica:**
- Il file è in `output/esempio_eventi.docx`
- Hai Microsoft Word o LibreOffice installato
- Il file non è aperto da un altro programma

---

## 📁 Struttura File

```
Locandine2Word/
├── app.py                    # ⭐ Applicazione principale
├── avvia_app.bat             # 🚀 Avvio rapido Windows
├── quick_demo.py             # 🎯 Demo veloce
├── data.json                 # 💾 Database eventi
├── uploads/                  # 📸 Immagini caricate
└── output/                   # 📄 Documenti generati
```

---

## 💡 Tips & Tricks

### Per risultati OCR migliori:
- Usa immagini ad alta risoluzione
- Assicurati che il testo sia leggibile
- Evita immagini troppo scure o sfocate

### Personalizzazione:
- Modifica `word_generator.py` per cambiare il formato del documento
- Modifica `ocr_engine.py` per aggiungere pattern di riconoscimento

### Backup:
- Il file `data.json` contiene tutti i tuoi eventi
- Fai backup periodici di questo file

---

## 🎯 Prossimi Passi

1. ✅ Hai generato il documento di esempio
2. ⏭️ Avvia l'app web: `streamlit run app.py`
3. 📸 Carica le tue prime locandine
4. 🎉 Genera il tuo primo documento personalizzato!

---

**Buon lavoro! 🎭**
