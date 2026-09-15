# AlleenAero

Schone basis voor **Aero**. Geen Lord Commander, LCW, Mastermind of legacy-identiteit.

## Kern

- Lokale Ollama/Qwen runtime
- Model: `project-ai-engine:27b`
- `think: false`
- `num_ctx: 8192`
- `keep_alive: 10m`
- Persistente SQLite-chatgeschiedenis
- Clean-slate geheugen: de database wordt pas lokaal bij de eerste start aangemaakt
- Clean-slate origin: alleen `ORIGIN.md` bepaalt de basisidentiteit
- Beperkte recente context zodat gewone chat snel blijft
- Toolarchitectuur voorbereid, maar niet standaard meegestuurd bij gewone chat
- Geen overgenomen legacy-code of legacy-memory

## Starten

Vereisten: Python 3.11+ en Ollama met `project-ai-engine:27b`.

```powershell
.\start_aero.ps1
```

Daarna:

- Chat API: `http://127.0.0.1:8091/api/chat`
- Health: `http://127.0.0.1:8091/health`

## Clean slate

`data/aero.db` staat in `.gitignore` en bestaat niet in de repository. Bij de eerste start wordt een volledig nieuwe database aangemaakt. Er wordt niets uit een oude Aero-installatie geïmporteerd.
