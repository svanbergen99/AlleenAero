from .config import ORIGIN_FILE, RECENT_HISTORY_MESSAGES
from .memory import current_session_id, recent_messages, save_message
from .ollama_client import chat


def _system_prompt():
    origin = ORIGIN_FILE.read_text(encoding="utf-8").strip()
    return (
        origin
        + "\n\nOPERATING PRINCIPLES:\n"
        + "- Je bent Aero. Antwoord direct op Bas zijn actuele verzoek.\n"
        + "- Verzín geen systeemstatus, bestanden, geheugen of toolresultaten.\n"
        + "- Technische modellen en runtimes zijn jouw motor, niet jouw identiteit.\n"
        + "- Gewone chat gebruikt geen tools tenzij een concrete lokale actie dat vereist.\n"
        + "- Houd antwoorden compact tenzij Bas om detail vraagt.\n"
    )


def respond(message):
    session_id = current_session_id()
    history = recent_messages(session_id, RECENT_HISTORY_MESSAGES)
    messages = [
        {"role": "system", "content": _system_prompt()},
        *history,
        {"role": "user", "content": str(message)},
    ]

    assistant = chat(messages)
    reply = str(assistant.get("content") or "").strip()
    if not reply:
        reply = "Ik kreeg geen bruikbaar modelantwoord terug."

    save_message(session_id, "user", message)
    save_message(session_id, "assistant", reply)
    return reply
