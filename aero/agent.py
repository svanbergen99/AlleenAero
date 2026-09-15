import json
import re

from .config import MAX_AGENT_STEPS, MAX_TOOL_CALLS, ORIGIN_FILE, RECENT_HISTORY_MESSAGES
from .memory import current_session_id, recent_messages, save_message
from .ollama_client import chat
from .permissions import cancel_approval, consume_approval
from .state import is_active, set_active
from .tools import execute, execute_approved, schemas, select_tool_names


def _system_prompt(operator_authorized=False):
    origin = ORIGIN_FILE.read_text(encoding="utf-8").strip()
    mode = (
        "Je werkt in lokale owner-operator modus. Gebruik alleen de aangeboden capabilities. "
        "Verzín nooit toolresultaten. Kritieke acties vereisen expliciete approval."
        if operator_authorized
        else "Deze route heeft geen pc-operatorrechten. Je mag normaal praten maar geen lokale tools uitvoeren."
    )
    return (
        origin
        + "\n\nOPERATING PRINCIPLES:\n"
        + "- Je bent Aero. Antwoord direct op Bas zijn actuele verzoek.\n"
        + "- Verzín geen systeemstatus, bestanden, geheugen of toolresultaten.\n"
        + "- Technische modellen en runtimes zijn jouw motor, niet jouw identiteit.\n"
        + "- Gebruik tools alleen wanneer actuele lokale informatie of een lokale actie nodig is.\n"
        + "- Houd gewone antwoorden compact tenzij Bas om detail vraagt.\n"
        + f"- {mode}\n"
    )


def _approval_command(command):
    approve = re.fullmatch(r"AERO_APPROVE\s+([0-9a-fA-F]{10})", command)
    cancel = re.fullmatch(r"AERO_CANCEL\s+([0-9a-fA-F]{10})", command)
    return approve, cancel


def _tool_reply(result):
    if isinstance(result, dict) and result.get("approval_required"):
        return (
            "Deze actie vereist jouw expliciete goedkeuring.\n"
            f"Actie: {result.get('summary')}\n"
            f"Stuur exact: AERO_APPROVE {result.get('approval_id')}\n"
            f"Verloopt over {result.get('expires_seconds')} seconden."
        )
    return None


def respond(message, operator_authorized=False):
    command = str(message).strip()

    if command.lower() in {"activeer", "activeer aero"}:
        set_active(True)
        return "Aero actief."
    if command.lower() == "deactiveer":
        set_active(False)
        return "Aero staat nu in standby."

    approve, cancel = _approval_command(command)
    if approve or cancel:
        if not operator_authorized:
            return "Deze route heeft geen Aero-operatorrechten."
        if cancel:
            return "Actie geannuleerd." if cancel_approval(cancel.group(1)) else "Approval niet gevonden."
        item = consume_approval(approve.group(1))
        result = execute_approved(item["kind"], item["args"])
        return "Goedgekeurde actie uitgevoerd:\n" + json.dumps(result, ensure_ascii=False, indent=2)

    if not is_active():
        return "Aero staat in standby. Typ Activeer om mij te activeren."

    session_id = current_session_id()
    history = recent_messages(session_id, RECENT_HISTORY_MESSAGES)
    messages = [
        {"role": "system", "content": _system_prompt(operator_authorized)},
        *history,
        {"role": "user", "content": command},
    ]

    tool_names = select_tool_names(command) if operator_authorized else []
    tools = schemas(tool_names) if tool_names else None
    tool_calls_used = 0
    seen = {}

    for _ in range(MAX_AGENT_STEPS):
        assistant = chat(messages, tools)
        calls = assistant.get("tool_calls") or []

        if not calls:
            reply = str(assistant.get("content") or "").strip()
            if not reply:
                reply = "Ik kreeg geen bruikbaar modelantwoord terug."
            save_message(session_id, "user", command)
            save_message(session_id, "assistant", reply)
            return reply

        if not operator_authorized:
            return "Deze route heeft geen Aero-operatorrechten."

        messages.append(assistant)
        for call in calls:
            function = call.get("function") or {}
            name = str(function.get("name") or "")
            args = function.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}

            key = name + ":" + json.dumps(args, sort_keys=True, ensure_ascii=False)
            if key in seen:
                result = seen[key]
            elif tool_calls_used >= MAX_TOOL_CALLS:
                result = {"error": "tool_budget_reached"}
            else:
                try:
                    result = execute(name, args)
                except Exception as exc:
                    result = {"error": f"{type(exc).__name__}: {exc}"}
                seen[key] = result
                tool_calls_used += 1

            approval_reply = _tool_reply(result)
            if approval_reply:
                save_message(session_id, "user", command)
                save_message(session_id, "assistant", approval_reply)
                return approval_reply

            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": json.dumps(result, ensure_ascii=False),
            })

        messages.append({
            "role": "user",
            "content": (
                f"Original request from Bas: {command}\n\n"
                "Gebruik de geverifieerde toolresultaten hierboven. "
                "Herhaal geen succesvolle toolcall. Als je genoeg weet, antwoord nu."
            ),
        })

    reply = "Ik kon deze opdracht niet binnen de begrensde toolstappen afronden."
    save_message(session_id, "user", command)
    save_message(session_id, "assistant", reply)
    return reply
