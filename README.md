# AlleenAero

Schone, zelfstandige basis voor **Aero**. Geen Lord Commander, LCW, Mastermind of legacy-identiteit.

## Wat deze repo bevat

- Lokale Ollama/Qwen chatruntime
- Model: `project-ai-engine:27b`
- `think: false`
- `num_ctx: 8192`
- `keep_alive: 10m`
- Persistente SQLite-chatgeschiedenis
- Clean-slate geheugen: `data/aero.db` ontstaat pas bij eerste start
- Clean-slate origin: alleen `ORIGIN.md` bepaalt de basisidentiteit
- Begrensde recente context en tool-loop
- Dynamische toolselectie: gewone chat krijgt geen tool-schema's
- Bestands-, project-, proces-, poort- en GPU-observatietools
- Schrijftools met backup van bestaande tekstbestanden
- Owner-approval voor verwijderen, verplaatsen, process kill, programma starten en externe scopes
- Loopback operator-cookie voor lokale bediening
- Activeer/deactiveer status
- Stale-safe runtime lock: dode PID-locks worden automatisch opgeschoond
- Documentanalyse voor tekst/PDF/DOCX
- Optionele lokale vision-service en audio-transcriptie
- Unit tests voor memory, runtime locks en toolselectie

## Starten

Vereisten:

1. Python 3.11+
2. Ollama actief op `127.0.0.1:11434`
3. Model `project-ai-engine:27b`
4. Installeer basisdependencies:

```powershell
python -m pip install -r requirements.txt
```

Start Aero:

```powershell
.\start_aero.ps1
```

Daarna:

- UI: `http://127.0.0.1:8091/`
- Chat API: `http://127.0.0.1:8091/api/chat`
- Health: `http://127.0.0.1:8091/health`

## Clean slate

Er wordt niets uit een oude Aero-installatie geïmporteerd. `data/aero.db`, status, externe grants en runtime-locks staan buiten Git en worden lokaal aangemaakt.

## Beveiligingsmodel

Binnen deze repo kan Aero lezen. Wijzigingen via `write_text` en `make_dir` zijn alleen beschikbaar in geautoriseerde write-scopes. Externe folders moeten expliciet via een approval worden toegevoegd. Kritieke acties geven eerst een `AERO_APPROVE <id>` opdracht terug.

## Multimodaal

Documenten werken lokaal met `pypdf` en `python-docx`.

Vision verwacht standaard een OpenAI-compatible endpoint op `http://127.0.0.1:8110` met model `aero-vision`. Dit is instelbaar via `AERO_VISION_BASE_URL` en `AERO_VISION_MODEL`.

Audio-transcriptie gebruikt optioneel `faster-whisper`. Installeer dat pakket wanneer audio nodig is.

## Testen

```powershell
python -m unittest discover -s tests -v
```

## Belangrijk

Dit project bevat alleen Aero's nieuwe technische basis en nieuwe origin. Geen oude memorydatabase, legacy prompts, legacy identities of oude geschiedenis worden meegenomen.
