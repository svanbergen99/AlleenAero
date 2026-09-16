import json
import re

from .config import MAX_AGENT_STEPS, MAX_TOOL_CALLS, ORIGIN_FILE, PROJECT_ROOT, RECENT_HISTORY_MESSAGES
from .memory import current_session_id, recent_messages, save_message
from .ollama_client import chat
from .permissions import cancel_approval, consume_approval
from .state import is_active, set_active
from .owner_tools import execute, execute_approved, schemas, select_tool_names
from .tools import execute as execute_legacy


def _system_prompt(operator_authorized=False):
    origin = ORIGIN_FILE.read_text(encoding="utf-8").strip()
    mode = (
        "Je werkt in lokale owner-operator modus. Iedere lokale file- of execute-actie vraagt eerst expliciete approval. "
        f"Je primaire projectscope is {PROJECT_ROOT}. Buiten die scope mag je alleen een concrete actie voorstellen; "
        "je voert buiten de scope niets uit voordat Bas die exacte actie goedkeurt. Vrije shell-commando's zijn niet beschikbaar."
        if operator_authorized
        else "Deze route heeft geen pc-operatorrechten. Je mag normaal praten maar geen lokale tools uitvoeren."
    )
    return (
        origin
        + "\n\nOPERATING PRINCIPLES:\n"
        + "- Je bent Aero. Antwoord direct op Bas zijn actuele verzoek.\n"
        + "- Verzín geen systeemstatus, bestanden, geheugen of toolresultaten.\n"
        + "- Technische modellen en runtimes zijn jouw motor, niet jouw identiteit.\n"
        + "- Gebruik tools wanneer actuele lokale informatie of een lokale actie nodig is.\n"
        + "- Een toolcall voert de actie nog niet uit: hij maakt eerst een owner-approval aan.\n"
        + "- Approval geldt alleen voor de exacte voorgestelde actie en argumenten.\n"
        + "- Als een pad buiten de projectscope ligt, zeg duidelijk waarom dat nodig is en vraag approval voordat je leest, schrijft of uitvoert.\n"
        + "- Voor execute_file geldt: approval voor uitvoering betekent ook approval voor het gedrag van dat script/programmaatje zelf.\n"
        + "- Houd gewone antwoorden compact tenzij Bas om detail vraagt.\n"
        + f"- {mode}\n"
    )


def _media_request(command):
    match = re.match(
        r"^Bas heeft een mediabijlage toegevoegd: (.+?)\nGebruik (analyze_(?:document|image|audio)) .*?\nVraag van Bas: (.*)$",
        command,
        re.S,
    )
    if not match:
        return None
    return match.group(2), match.group(1).strip(), match.group(3).strip()


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
        return f"Aero actief. Projectscope: {PROJECT_ROOT}"
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
    media = _media_request(command)
    if media:
        if not operator_authorized:
            return "Deze route heeft geen Aero-operatorrechten."
        tool_name, path, question = media
        try:
            verified = execute_legacy(tool_name, {"path_value": path, "question": question})
        except Exception as exc:
            reply = f"Ik kon de bijlage niet analyseren: {type(exc).__name__}: {exc}"
            save_message(session_id, "user", command)
            save_message(session_id, "assistant", reply)
            return reply
        history = recent_messages(session_id, RECENT_HISTORY_MESSAGES)
        prompt = (
            f"Vraag van Bas: {question}\n\n"
            f"Geverifieerde lokale analyse:\n{json.dumps(verified, ensure_ascii=False)}\n\n"
            "Beantwoord Bas nu op basis van deze analyse. Verzín niets buiten de geverifieerde resultaten."
        )
        assistant = chat([
            {"role": "system", "content": _system_prompt(True)},
            *history,
            {"role": "user", "content": prompt},
        ])
        reply = str(assistant.get("content") or "").strip() or "Analyse voltooid."
        save_message(session_id, "user", command)
        save_message(session_id, "assistant", reply)
        return reply

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
                "Gebruik alleen geverifieerde resultaten. Als een lokale actie nodig is, vraag approval via de juiste tool. "
                "Voer niets lokaal uit zonder approval."
            ),
        })

    reply = "Ik kon deze opdracht niet binnen de begrensde toolstappen afronden."
    save_message(session_id, "user", command)
    save_message(session_id, "assistant", reply)
    return reply
