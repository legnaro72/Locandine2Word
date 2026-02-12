# 🎵 Audio di Background - Guida

## 📌 Posizionamento File

Il file audio deve essere chiamato **`audio.mp3`** e posizionato nella **root del progetto**, allo stesso livello di `app.py`:

```
Locandine2Word/
├── app.py
├── audio.mp3          ← QUI!
├── word_generator.py
├── ocr_engine.py
├── data.json
└── ...
```

---

## ✅ Funzionalità

### 🎚️ **Controllo dalla Sidebar**

1. Apri l'applicazione Streamlit
2. Nella **sidebar** (pannello sinistro), in alto trovi:
   ```
   ⚙️ Opzioni
   └── ☑ 🎵 Musica di sottofondo
   ```
3. La checkbox è **ATTIVA di default** (musica parte automaticamente)
4. **Deseleziona** per disattivare la musica
5. **Seleziona** per riattivarla

---

## ⚙️ Come Funziona

### 🔹 **Comportamento Default (ON)**
- ✅ All'avvio dell'app, la musica **parte automaticamente**
- ✅ Il player è **invisibile** (non occupa spazio nell'interfaccia)
- ✅ La musica si ripete in **loop continuo**

### 🔹 **Gestione Stato**
```python
# Salva lo stato nel session_state di Streamlit
if 'audio_enabled' not in st.session_state:
    st.session_state.audio_enabled = True  # ON di default

# Checkbox nella sidebar
audio_enabled = st.checkbox("🎵 Musica di sottofondo", 
                            value=st.session_state.audio_enabled)
```

### 🔹 **Player HTML**
- Usa un tag `<audio>` HTML5 nascosto
- Attributi:
  - `autoplay` - Parte automaticamente
  - `loop` - Ripetizione infinita
  - `style="display: none;"` - Invisibile
- Audio encodato in **Base64** per l'embedding diretto

---

## 🎼 Formato Audio Consigliato

### 📝 **Specifiche Ottimali**

| Parametro | Valore Consigliato |
|-----------|-------------------|
| **Formato** | MP3 |
| **Bitrate** | 128 kbps (sufficiente per background) |
| **Sample Rate** | 44.1 kHz |
| **Canali** | Stereo |
| **Durata** | 2-5 minuti (poi si ripete) |
| **Dimensione** | Max 5 MB (per caricamento veloce) |

### 🎹 **Tipo di Musica Suggerito**

Per un'app gestionale, scegli musica:
- ✅ **Strumentale** (no voce)
- ✅ **Rilassante** (ambient, classica, lofi)
- ✅ **Volume moderato** (non troppo intensa)
- ✅ **Senza interruzioni brusche**

Esempi:
- Musica classica leggera (es. Chopin, Debussy)
- Ambient / Chill
- Lofi Hip Hop
- Jazz strumentale

---

## 🔧 Risoluzione Problemi

### ❌ **L'audio non parte**

**Controlla:**
1. ✅ Il file si chiama esattamente `audio.mp3` (minuscolo)
2. ✅ È nella directory principale del progetto
3. ✅ La checkbox "🎵 Musica di sottofondo" è **selezionata**
4. ✅ Il browser permette l'autoplay (alcuni browser bloccano audio automatico)

**Soluzione browser:**
- Chrome/Edge: Clicca da qualche parte nella pagina, poi ricarica
- Firefox: Vai in Impostazioni → Privacy → Autoplay → Permetti
- Safari: Preferenze → Siti web → Riproduzione automatica → Consenti

### ❌ **L'audio si interrompe**

**Causa:** Streamlit ricarica la pagina durante l'interazione

**Limitazione:** Ogni volta che cambi tab o interagisci con widget, Streamlit ricarica e l'audio riparte da capo. È una limitazione di Streamlit.

**Possibili soluzioni avanzate (opzionali):**
- Usare Streamlit `st.experimental_fragment` per isolare componenti
- Implementare un player JavaScript persistente
- Usare un servizio esterno per streaming audio

### ❌ **File troppo grande**

**Problema:** L'embedding Base64 aumenta la dimensione del 33%

**Soluzione:**
1. Comprimi l'audio a 96-128 kbps
2. Accorcia la durata a 2-3 minuti
3. Usa tool come Audacity per ottimizzare

---

## 💡 Suggerimenti

### 📂 **Fonti Audio Royalty-Free**

Dove trovare musica gratuita e legale:
- [YouTube Audio Library](https://studio.youtube.com/channel/UC/music) - Gratis, no copyright
- [FreePD](https://freepd.com/) - Musica di pubblico dominio
- [Bensound](https://www.bensound.com/) - Tracce gratuite con attribuzione
- [Incompetech](https://incompetech.com/) - Kevin MacLeod (CC)
- [Purple Planet](https://www.purple-planet.com/) - Royalty free

### 🎨 **Personalizzazione**

Vuoi cambiare icona o testo della checkbox?
```python
# In app.py, riga ~293
audio_enabled = st.checkbox("🎶 Audio Ambientale", ...)
# o
audio_enabled = st.checkbox("🔊 Sottofondo Musicale", ...)
```

### 🎚️ **Volume**

Il volume è controllato dal browser dell'utente. Per impostare un volume iniziale più basso, modifica l'HTML:

```python
# In app.py, aggiungi attributo volume
audio_html = f"""
<audio autoplay loop volume="0.5" style="display: none;">
    ...
</audio>
"""
```
Nota: `volume` va da 0.0 (muto) a 1.0 (max)

---

## 📊 Performance

### 💾 **Impatto sul Caricamento**

- File 3 MB → Dopo Base64: ~4 MB
- Caricamento iniziale: +0.5-2 secondi (dipende da connessione)
- **Dopo il primo load**: Browser mette in cache

### ⚡ **Ottimizzazione**

Se noti rallentamenti:
1. Riduci dimensione audio a < 2 MB
2. Considera hosting esterno (Google Drive, Dropbox)
3. Usa formato più compresso (OGG Vorbis)

---

## 🚀 Upgrade Futuri (Opzionali)

Possibili miglioramenti:
- [ ] Playlist multipla con rotazione casuale
- [ ] Slider volume nella sidebar
- [ ] Scelta tra più tracce
- [ ] Visualizzatore di spettro audio
- [ ] Pausa/Play invece di on/off completo

---

**Buon ascolto!** 🎵✨
