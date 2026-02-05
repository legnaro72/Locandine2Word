# 🎭 Locandine2Word

**Automatizza l'estrazione di informazioni da locandine eventi e genera documenti Word ordinati cronologicamente**

---

## 🎯 Cosa fa questo progetto?

Locandine2Word è un'applicazione web che:

1. **📸 Carica locandine** (immagini JPG/PNG)
2. **🔍 Estrae automaticamente** con OCR:
   - Data dell'evento
   - Titolo
   - Orario
   - Luogo
3. **📝 Genera documenti Word** con:
   - Tabelle (immagine a sinistra, info a destra)
   - Ordinamento cronologico automatico
   - Formattazione professionale
4. **🔄 Inserimento intelligente**: se aggiungi una locandina con data intermedia, viene posizionata nel punto corretto

---

## 🚀 Come avviare l'applicazione

### Metodo 1: Avvio rapido (Windows)
Fai doppio click su:
```
avvia_app.bat
```

### Metodo 2: Da terminale
```bash
streamlit run app.py
```

L'applicazione si aprirà automaticamente nel browser all'indirizzo: `http://localhost:8501`

---

## 📦 Struttura del progetto

```
Locandine2Word/
├── app.py                 # Applicazione Streamlit principale
├── ocr_engine.py          # Motore OCR per estrazione dati
├── word_generator.py      # Generatore documenti Word
├── data.json              # Database eventi (JSON)
├── requirements.txt       # Dipendenze Python
├── uploads/               # Immagini caricate
├── output/                # Documenti Word generati
└── README.md              # Questa guida
```

---

## 🎨 Funzionalità principali

### 1️⃣ Carica Locandine
- Upload multiplo di immagini
- Preview immediata
- Analisi OCR automatica

### 2️⃣ Estrazione Intelligente
- **Data**: supporta formati multipli (15/02/2026, 15 Febbraio 2026, ecc.)
- **Orario**: riconosce 20:30, 20.30, ore 20:30
- **Luogo**: identifica "presso", "teatro", "via", ecc.
- **Titolo**: estrae automaticamente il titolo principale

### 3️⃣ Modifica Manuale
- Tutti i campi estratti sono modificabili
- Correzione errori OCR facilitata
- Validazione dati

### 4️⃣ Gestione Eventi
- Visualizzazione lista completa
- Ordinamento cronologico
- Eliminazione singoli eventi
- Reset database

### 5️⃣ Generazione Word
- Documento sempre ordinato per data
- Formato professionale
- Tabelle con immagini e testo
- Download diretto

---

## 🛠️ Tecnologie utilizzate

- **EasyOCR**: Riconoscimento ottico caratteri (italiano + inglese)
- **Python-docx**: Generazione documenti Word
- **Streamlit**: Interfaccia web moderna
- **Dateparser**: Parsing intelligente delle date
- **Pillow**: Gestione immagini

---

## 📖 Guida d'uso

### Passo 1: Carica una locandina
1. Vai alla tab **"📤 Carica Locandine"**
2. Clicca su **"Browse files"** e seleziona una o più immagini
3. Clicca su **"🔍 Analizza con OCR"**

### Passo 2: Verifica e modifica
1. Controlla le informazioni estratte
2. Modifica eventuali errori
3. Clicca su **"💾 Salva evento"**

### Passo 3: Genera il documento
1. Vai alla tab **"📖 Anteprima Documento"**
2. Clicca su **"📥 Genera e Scarica Documento Word"**
3. Scarica il file generato

---

## 🎯 Casi d'uso

✅ **Organizzatori eventi**: gestione calendario locandine  
✅ **Teatri e cinema**: archivio programmazione  
✅ **Associazioni culturali**: documentazione attività  
✅ **Uffici stampa**: raccolta materiali promozionali  

---

## 🔧 Configurazione avanzata

### Personalizzare il template Word
Modifica `word_generator.py` per cambiare:
- Stili di formattazione
- Dimensioni immagini
- Layout tabelle
- Colori e font

### Migliorare l'OCR
In `ocr_engine.py` puoi:
- Aggiungere pattern di riconoscimento
- Personalizzare regex per date/orari
- Aggiungere altre lingue

---

## ❓ FAQ

**Q: L'OCR non riconosce bene il testo**  
A: Assicurati che l'immagine sia di buona qualità e ben illuminata. Puoi modificare manualmente i campi estratti.

**Q: Come elimino tutti gli eventi?**  
A: Usa il pulsante "🗑️ Elimina tutti gli eventi" nella sidebar.

**Q: Posso usare un template Word esistente?**  
A: Sì, modifica `WordGenerator.__init__()` passando il path del template.

**Q: Dove vengono salvati i documenti?**  
A: Nella cartella `output/` del progetto.

---

## 🚀 Prossimi sviluppi possibili

- [ ] Export in PDF
- [ ] Integrazione con Google Calendar
- [ ] Riconoscimento automatico logo/brand
- [ ] Multi-lingua OCR
- [ ] Versione eseguibile (.exe)
- [ ] API REST per integrazione

---

## 📄 Licenza

Progetto open source - Usa e modifica liberamente!

---

## 🤝 Supporto

Per problemi o suggerimenti, apri una issue o contatta lo sviluppatore.

**Buon lavoro con Locandine2Word! 🎭**
