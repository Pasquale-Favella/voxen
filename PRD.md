# Voxen

**Local-first AI Voice Dictation for Desktop**

> Speak. Voxen types.

## 1. Vision

Voxen è una piccola applicazione desktop che permette di trasformare la voce in testo direttamente nell'applicazione in uso.

L'utente preme una scorciatoia globale, parla, rilascia il tasto e Voxen:

1. cattura l'audio;
2. lo trascrive localmente tramite Whisper;
3. applica un post-processing opzionale;
4. inserisce il testo nel campo attivo.

L'obiettivo non è creare un'altra piattaforma AI complessa.

**Voxen deve fare una cosa molto bene: parlare al computer deve essere veloce quanto digitare.**

---

# 2. Product Principles

### Local-first

L'audio non deve essere inviato a server remoti.

La trascrizione deve avvenire localmente.

La connessione Internet deve essere necessaria solamente per eventuali download iniziali di modelli o aggiornamenti esplicitamente richiesti.

### Zero friction

L'utente non deve aprire una finestra prima di parlare.

Il flusso principale è:

**HOTKEY → PARLA → RILASCIA → TESTO**

### Fast

La latenza percepita deve essere minima.

Il modello deve essere caricato e mantenuto in memoria quando Voxen è attivo.

### Invisible

Voxen deve vivere principalmente nella system tray/menu bar.

Non deve occupare spazio sul desktop quando non viene utilizzato.

### Hackable

Configurazione semplice, codice modulare e possibilità di sostituire il motore STT.

---

# 3. Target Users

## Primary

Power users che scrivono molto:

* sviluppatori;
* tecnici;
* professionisti;
* studenti;
* persone che scrivono email/documentazione;
* utenti che utilizzano frequentemente ChatGPT, Claude, Cursor, VS Code, Slack, Discord, browser e terminale.

## Secondary

Utenti che vogliono una soluzione:

* gratuita;
* offline;
* privata;
* senza account;
* senza abbonamento.

---

# 4. Core User Journey

### First launch

L'utente avvia Voxen.

Viene mostrato un onboarding minimale:

**Welcome to Voxen**

> Your voice stays on your computer.

Configurazione:

* microfono;
* lingua;
* modello Whisper;
* hotkey.

Poi:

**Press and hold your hotkey to start speaking.**

Fine onboarding.

---

# 5. Core Interaction

## Push-to-talk

Default hotkey:

`Ctrl + Space`

L'utente:

1. tiene premuto `Ctrl + Space`;
2. Voxen inizia la registrazione;
3. appare un piccolo overlay;
4. l'utente parla;
5. rilascia la combinazione;
6. Voxen termina la registrazione;
7. Whisper trascrive;
8. il testo viene inserito nel cursore.

Esempio:

> User: "Ciao, domani vorrei spostare la riunione alle tre"

↓

> Text field: `Ciao, domani vorrei spostare la riunione alle tre.`

---

# 6. Recording Overlay

Durante la registrazione deve apparire un piccolo overlay non invasivo.

Contenuto:

```text
┌─────────────────────────────┐
│  ●  Listening...     00:04  │
└─────────────────────────────┘
```

L'overlay deve mostrare:

* stato;
* durata;
* livello audio;
* eventualmente anteprima della trascrizione.

Stati:

```text
IDLE
↓
LISTENING
↓
PROCESSING
↓
INSERTING
↓
IDLE
```

In caso di errore:

```text
ERROR
```

con un messaggio breve.

---

# 7. Speech-to-Text Engine

## MVP

Utilizzare:

**faster-whisper**

come backend principale.

Whisper Local utilizza attualmente `faster-whisper`/CTranslate2 e mantiene il modello localmente; questa è una buona base anche per Voxen.

### Supported models

MVP:

* tiny
* base
* small

Post-MVP:

* medium
* large-v3
* large-v3-turbo
* modelli custom

Il modello selezionato deve essere scaricato una sola volta e successivamente utilizzato dalla cache locale.

---

# 8. Language

Voxen deve supportare almeno:

* Italian
* English
* Japanese
* French
* German
* Spanish

Opzione:

```text
Language
[ Auto Detect ▼ ]
```

Possibilità di impostare una lingua fissa per ottenere maggiore velocità/accuratezza.

---

# 9. Text Injection

Dopo la trascrizione Voxen deve inserire il testo nell'applicazione attiva.

Strategia MVP:

```text
Transcript
   ↓
Clipboard
   ↓
Paste
   ↓
Restore Clipboard
```

In questo modo Voxen può funzionare praticamente con qualsiasi applicazione che supporti il paste.

Fallback:

se non esiste un campo di testo attivo, Voxen mostra il risultato in una piccola finestra:

```text
┌─────────────────────────────────┐
│ Ciao, questo è il testo...      │
│                                 │
│             [ Copy ]             │
└─────────────────────────────────┘
```

---

# 10. Basic Post-processing

Il primo MVP NON deve dipendere da un LLM.

Implementare solamente trasformazioni deterministiche:

* capitalizzazione iniziale;
* spaziatura;
* punteggiatura finale;
* normalizzazione base;
* sostituzione di comandi vocali.

Esempio:

Input:

> `ciao come stai punto`

Output:

> `Ciao, come stai.`

---

# 11. Voice Formatting

Supportare comandi vocali basilari:

```text
comma
period
question mark
exclamation mark
new line
new paragraph
```

Esempio:

> `ciao Marco comma nuova riga ci vediamo domani punto`

↓

```text
Ciao Marco,
Ci vediamo domani.
```

Il sistema deve permettere di definire mapping personalizzati.

---

# 12. Voice Editing

MVP:

```text
scratch that
```

Cancella l'ultima frase trascritta.

Successivamente:

```text
delete last sentence
delete last word
new paragraph
```

Questa funzionalità deve essere implementata solamente dopo aver stabilizzato la trascrizione base.

---

# 13. Profiles

Voxen deve avere pochi profili predefiniti.

### Dictation

```yaml
auto_paste: true
punctuation: true
voice_commands: true
```

### Code

```yaml
auto_paste: true
punctuation: false
voice_commands: false
```

### Chat

```yaml
auto_paste: true
auto_send: false
punctuation: true
```

L'utente può creare profili personalizzati in una fase successiva.

---

# 14. Per-App Behaviour

Post-MVP.

Voxen può riconoscere l'applicazione attiva e applicare una configurazione specifica.

Esempio:

```yaml
rules:

  - apps:
      - code.exe
      - cursor.exe

    punctuation: false

  - apps:
      - slack.exe
      - discord.exe

    punctuation: true
```

Questo segue un concetto già presente in Whisper Local, dove il comportamento può cambiare in base all'applicazione foreground.

---

# 15. AI Text Processing

## Phase 2

Integrare LLM locali.

Backend iniziale:

**Ollama**

Pipeline:

```text
Microphone
    ↓
Whisper
    ↓
Raw transcript
    ↓
Local LLM
    ↓
Clean transcript
    ↓
Paste
```

Use cases:

### Clean

Corregge:

* punteggiatura;
* maiuscole;
* esitazioni;
* ripetizioni.

### Rewrite

L'utente può dire:

> "riscrivilo in modo più professionale"

### Translate

> "translate to English"

### Summarize

> "summarize this"

Tutto opzionale.

Se Ollama non è installato, Voxen continua a funzionare normalmente.

---

# 16. Global Hotkeys

MVP:

```text
Ctrl + Space
```

Configurabile.

Future:

```text
Hold hotkey → Dictation
Double tap → Continuous mode
Secondary hotkey → AI rewrite
```

La hotkey deve funzionare indipendentemente dall'applicazione attiva.

---

# 17. Continuous Mode

Post-MVP.

Permette di parlare senza tenere premuta la hotkey.

```text
START
 ↓
record
 ↓
VAD detects silence
 ↓
transcribe
 ↓
paste
 ↓
record again
```

Utile per:

* documentazione;
* appunti;
* email lunghe;
* brainstorming.

Whisper Local implementa già una modalità analoga di continuous dictation.

---

# 18. Voice Activity Detection

Utilizzare VAD per evitare di processare lunghi periodi di silenzio.

Pipeline:

```text
Microphone
     ↓
Audio buffer
     ↓
VAD
     ↓
Speech detected
     ↓
Whisper
```

Il VAD deve anche permettere di migliorare la UX del continuous mode.

---

# 19. Audio Buffer

Utilizzare un piccolo pre-roll buffer.

Obiettivo:

evitare di perdere la prima parola quando l'utente inizia a parlare immediatamente dopo la pressione della hotkey.

Target:

**~300–500 ms**

Whisper Local utilizza attualmente un buffer pre-roll di 500 ms proprio per evitare il clipping della prima parola.

---

# 20. System Tray

Voxen deve avere una system tray icon.

Menu:

```text
Voxen
────────────────
● Ready

Microphone >
Language >
Model >

────────────────
Profile >

────────────────
Settings
History

────────────────
Pause
Quit
```

Durante la registrazione:

```text
● Recording...
```

---

# 21. Settings

## General

* launch at startup;
* hotkey;
* auto paste;
* auto send;
* notifications.

## Audio

* microphone;
* input device;
* gain;
* VAD sensitivity.

## Whisper

* model;
* language;
* device;
* compute type.

## Appearance

* overlay enabled;
* overlay position;
* overlay opacity.

## AI

* enable LLM processing;
* Ollama URL;
* model;
* default transformation.

---

# 22. History

MVP:

salvare localmente le ultime trascrizioni.

Schema:

```text
id
timestamp
application
duration
language
raw_text
processed_text
```

UI:

```text
Today

14:32  Ciao, domani...
13:18  Vorrei modificare...
11:04  Implementa questa...
```

Azioni:

* copy;
* delete;
* search.

L'utente deve poter disabilitare completamente la cronologia.

---

# 23. Privacy

Privacy deve essere una caratteristica architetturale, non una promessa di marketing.

Default:

```text
NO ACCOUNT
NO CLOUD
NO TELEMETRY
NO AUDIO UPLOAD
```

Il modello Whisper deve essere eseguito localmente.

L'unico traffico previsto nel setup iniziale è il download del modello, se l'utente non lo possiede già. Questo è coerente con il funzionamento documentato di Whisper Local.

Ogni eventuale funzione cloud futura deve essere:

* opt-in;
* chiaramente indicata;
* disattivata di default.

---

# 24. Offline Mode

Dopo il download del modello:

**Voxen deve funzionare completamente offline.**

Test obbligatorio:

```text
Disable network
      ↓
Launch Voxen
      ↓
Press hotkey
      ↓
Speak
      ↓
Text appears
```

Success = offline requirement soddisfatto.

---

# 25. Architecture

Per il primo MVP suggerisco di mantenere l'architettura estremamente semplice:

```text
┌──────────────────────────────┐
│          Voxen App            │
├──────────────────────────────┤
│                              │
│  Global Hotkey               │
│       ↓                      │
│  Audio Capture               │
│       ↓                      │
│  Ring Buffer + VAD           │
│       ↓                      │
│  Whisper Engine              │
│       ↓                      │
│  Post Processor              │
│       ↓                      │
│  Text Injector               │
│       ↓                      │
│  Active Application          │
│                              │
└──────────────────────────────┘
```

Componenti:

```text
HotkeyManager
AudioRecorder
AudioBuffer
VAD
WhisperEngine
PostProcessor
TextInjector
Overlay
Tray
SettingsStore
HistoryStore
```

Ogni componente deve avere un'interfaccia indipendente.

---

# 26. Backend Abstraction

Non accoppiare Voxen direttamente a Whisper.

Definire:

```typescript
interface SpeechToTextEngine {
  load(): Promise<void>;

  transcribe(
    audio: AudioBuffer,
    options: TranscriptionOptions
  ): Promise<Transcript>;

  unload(): Promise<void>;
}
```

Implementazione iniziale:

```text
FasterWhisperEngine
```

Possibili implementazioni future:

```text
WhisperCppEngine
WhisperKitEngine
ParakeetEngine
```

Whisper Local supporta già l'idea di backend intercambiabili, incluso whisper.cpp, quindi vale la pena mantenere questa separazione fin dall'inizio.

---

# 27. AI Processor Abstraction

Analogamente:

```typescript
interface TextProcessor {
  process(
    text: string,
    context: ProcessingContext
  ): Promise<string>;
}
```

Implementazioni:

```text
IdentityProcessor
RuleBasedProcessor
OllamaProcessor
```

MVP:

```text
IdentityProcessor
RuleBasedProcessor
```

Phase 2:

```text
OllamaProcessor
```

---

# 28. Configuration

Configurazione locale:

```yaml
app:
  launch_at_startup: true

hotkey:
  push_to_talk: "CTRL+SPACE"

audio:
  device: default
  preroll_ms: 500

whisper:
  model: base
  language: auto
  device: auto

output:
  auto_paste: true
  auto_send: false

postprocess:
  capitalization: true
  punctuation: true

history:
  enabled: true
  max_items: 500
```

---

# 29. Tech Stack Proposal

Per mantenere il progetto semplice:

### Desktop

**Tauri**

per:

* Windows;
* macOS;
* futuro Linux;
* system tray;
* global shortcuts;
* lightweight desktop shell.

### UI

**React + TypeScript**

### Styling

**Tailwind CSS**

### Backend

Per l'MVP si può scegliere:

**Python sidecar**

per l'inference Whisper.

Motivo: ecosistema `faster-whisper` molto semplice da integrare.

Architettura:

```text
Tauri
  │
  ├── React UI
  │
  └── Rust Core
        │
        ├── Global Hotkey
        ├── Clipboard
        ├── Window Management
        │
        └── Python STT Worker
                 │
                 └── faster-whisper
```

Alternativa futura:

portare il motore completamente in Rust/C++ per eliminare il sidecar Python.

---

# 30. MVP Scope

L'MVP deve contenere SOLO:

### Must have

* [ ] Windows support
* [ ] system tray
* [ ] global push-to-talk
* [ ] microphone selection
* [ ] audio recording
* [ ] 300–500 ms pre-roll
* [ ] Whisper local
* [ ] automatic model download
* [ ] Italian + English
* [ ] auto-paste
* [ ] basic punctuation
* [ ] recording overlay
* [ ] settings
* [ ] startup option
* [ ] completely offline after model download

### Explicitly NOT in MVP

* [ ] Ollama
* [ ] voice commands
* [ ] profiles
* [ ] per-app rules
* [ ] history
* [ ] continuous dictation
* [ ] streaming transcription
* [ ] translation
* [ ] system audio capture
* [ ] local API
* [ ] Linux
* [ ] macOS

Queste funzionalità possono arrivare successivamente.

---

# 31. MVP Success Criteria

Voxen è considerato riuscito quando:

### UX

L'utente può:

```text
Press
 ↓
Speak
 ↓
Release
 ↓
Text appears
```

in meno di pochi secondi.

### Accuracy

Per italiano e inglese la trascrizione deve essere sufficientemente accurata per uso quotidiano.

### Latency

Target:

```text
Hotkey → recording: <100 ms perceived
Release → transcription: <2 s for short utterances
```

su hardware moderno.

### Reliability

100 sessioni consecutive senza:

* crash;
* perdita dell'hotkey;
* audio bloccato;
* clipboard corrotto.

### Privacy

Durante il normale utilizzo:

```text
Network requests = 0
```

---

# 32. Phase 2

Dopo il MVP:

1. Ollama integration
2. voice commands
3. profiles
4. per-app rules
5. history
6. continuous dictation
7. custom dictionaries
8. voice editing
9. streaming preview

---

# 33. Phase 3

Funzionalità avanzate:

### Local AI transforms

```text
"rewrite professionally"
"make it shorter"
"translate to English"
"fix grammar"
```

### Smart context

Voxen può sapere quale applicazione è attiva:

```text
VS Code → developer mode
Slack → conversational mode
Email → professional mode
Terminal → raw mode
```

### Developer mode

Possibilità di dire:

> "create a TypeScript interface for a user"

e ottenere codice senza normalizzazione della punteggiatura.

---

# 34. Future Local API

Esporre eventualmente:

```http
POST /v1/audio/transcriptions
```

su localhost.

Questo permetterebbe di utilizzare Voxen come motore STT locale per:

* VS Code;
* Cursor;
* n8n;
* Open WebUI;
* applicazioni custom.

Whisper Local offre già una API locale compatibile con l'API Whisper di OpenAI; è una feature interessante da aggiungere solo dopo aver stabilizzato il core.

---

# 35. Competitive Positioning

Voxen non deve cercare di battere Wispr Flow sul numero di funzionalità.

Il posizionamento iniziale è:

> **The tiny, local, open-source voice keyboard.**

Differenziazione:

|                 | Voxen |
| --------------- | ----- |
| Local           | ✅     |
| Offline         | ✅     |
| Free            | ✅     |
| Open source     | ✅     |
| Account         | ❌     |
| Cloud           | ❌     |
| Subscription    | ❌     |
| Global hotkey   | ✅     |
| Any application | ✅     |
| Whisper         | ✅     |
| Lightweight     | ✅     |

---

# 36. Definition of Done

La versione `0.1.0` può essere pubblicata quando:

* Windows installer funziona;
* Voxen parte nella system tray;
* hotkey globale funziona;
* microfono configurabile;
* modello Whisper viene scaricato/cachato;
* registrazione funziona;
* trascrizione funziona offline;
* testo viene inserito nell'app attiva;
* overlay funziona;
* impostazioni vengono persistite;
* nessun dato audio viene inviato online;
* README contiene installazione, privacy e troubleshooting;
* repository contiene una licenza open-source.

---

# 37. Product Philosophy

Voxen deve evitare il feature creep.

La domanda per ogni nuova feature è:

> **Does this make speaking to the computer faster?**

Se la risposta è no, la feature non appartiene al core di Voxen.

Il prodotto deve rimanere:

**small · fast · local · private · hackable**

---

# 38. One-line pitch

> **Voxen turns your voice into text, locally and instantly — anywhere you can type.**
