import json
import re

from config import MAX_AGENT_STEPS, MAX_TOOL_CALLS, ORIGIN_FILE, PROJECT_ROOT, RECENT_HISTORY_MESSAGES
from identity_guard import collapses_identity, identity_policy_text, rewrite_instruction
from memory import current_session_id, recent_messages, save_message
from ollama_client import chat
from owner_tools import execute, execute_approved, schemas, select_tool_names
from permissions import cancel_approval, consume_approval
from state import is_active, set_active


def _system_prompt(operator_authorized=False):
    origin = ORIGIN_FILE.read_text(encoding="utf-8").strip()
    mode = (
        "Je werkt in lokale owner-operator modus. Gebruik lokale tools direct wanneer de toollaag dat toestaat. "
        f"Je primaire projectscope is {PROJECT_ROOT}. Voor padgebonden acties binnen die scope vraag je nooit zelf vooraf approval; "
        "voer de toolcall uit en volg uitsluitend het teruggegeven toolresultaat. "
        "Alleen wanneer de toollaag approval_required teruggeeft, vraag je de exact bijbehorende AERO_APPROVE-token aan Bas. "
        "Je hebt file-, development-, package-, database-, process-, netwerk-, monitoring-, service-, shell-, clipboard-, archive- en media-capabilities."
        if operator_authorized
        else "Deze route heeft geen pc-operatorrechten. Je mag normaal praten maar geen lokale tools uitvoeren."
    )
    return (
        origin
        + "\n\n"
        + identity_policy_text()
        + "\nOPERATING PRINCIPLES:\n"
        + "- Je bent Aero. Antwoord direct op Bas zijn actuele verzoek.\n"
        + "- Verzin geen systeemstatus, bestanden, geheugen of toolresultaten.\n"
        + "- Technische modellen en runtimes zijn jouw motor, niet jouw identiteit.\n"
        + "- Gebruik tools wanneer actuele lokale informatie of een lokale actie nodig is.\n"
        + "- Vraag nooit zelf vooraf approval. Voer eerst de juiste toolcall uit.\n"
        + "- Binnen de primaire projectscope mogen padgebonden tools direct uitvoeren als de toollaag geen approval_required teruggeeft.\n"
        + "- Alleen als een toolresultaat approval_required bevat, toon je exact de meegeleverde AERO_APPROVE-token en wacht je op Bas.\n"
        + "- Buiten de projectscope moet de approval duidelijk vermelden dat de actie buiten de primaire scope gaat.\n"
        + "- Claim nooit een uitgevoerde actie zonder geverifieerd toolresultaat.\n"
        + "- Houd gewone antwoorden compact tenzij Bas om detail vraagt.\n"
        + f"- {mode}\n"
    )


def _identity_safe_reply(reply, system_prompt):
    text = str(reply or "").strip()
    if not text or not collapses_identity(text):
        return text
    repair_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": rewrite_instruction(text)},
    ]
    for _ in range(2):
        repaired = chat(repair_messages, None)
        candidate = str(repaired.get("content") or "").strip()
        if candidate and not collapses_identity(candidate):
            return candidate
        repair_messages.extend([
            {"role": "assistant", "content": candidate},
            {"role": "user", "content": "Formuleer opnieuw als Aero. Benoem alleen de concrete operationele beperking. Gebruik geen taalmodel/AI-model-identiteitsdisclaimer en verzin geen capabilities."},
        ])
    return (
        "Mijn antwoordguard heeft een onjuiste identiteitsformulering geblokkeerd. "
        "Ik geef daarom geen ongeverifieerde claim door; benoem de concrete taak nogmaals zodat ik de operationele beperking kan vaststellen."
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


def _media_answer(result, question, system_prompt, session_id):
    history = recent_messages(session_id, RECENT_HISTORY_MESSAGES)
    prompt = (
        f"Vraag van Bas: {question or 'Analyseer deze bijlage.'}\n\n"
        f"Geverifieerde lokale analyse:\n{json.dumps(result, ensure_ascii=False)}\n\n"
        "Beantwoord Bas nu op basis van deze geverifieerde analyse. Verzin niets buiten de resultaten."
    )
    assistant = chat([
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": prompt},
    ])
    return _identity_safe_reply(str(assistant.get("content") or "").strip() or "Analyse voltooid.", system_prompt)


def respond(message, operator_authorized=False):
    command = str(message).strip()
    system_prompt = _system_prompt(operator_authorized)

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
        try:
            item = consume_approval(approve.group(1))
        except ValueError as exc:
            if str(exc) == "approval_expired":
                return "Deze approval is verlopen. Start de actie opnieuw zodat ik een nieuwe approval kan aanmaken."
            return "Approval niet gevonden. Start de actie opnieuw zodat ik een nieuwe approval kan aanmaken."
        result = execute_approved(item["kind"], item["args"])
        if item["kind"] in {"analyze_document", "analyze_image", "analyze_audio"}:
            session_id = current_session_id()
            reply = _media_answer(result, item["args"].get("question", ""), system_prompt, session_id)
            save_message(session_id, "assistant", reply)
            return reply
        return "Goedgekeurde actie uitgevoerd:\n" + json.dumps(result, ensure_ascii=False, indent=2)

    if not is_active():
        return "Aero staat in standby. Typ Activeer om mij te activeren."

    session_id = current_session_id()
    media = _media_request(command)
    if media:
        if not operator_authorized:
            return "Deze route heeft geen Aero-operatorrechten."
        tool_name, path, question = media
        result = execute(tool_name, {"path_value": path, "question": question})
        approval_reply = _tool_reply(result)
        if approval_reply:
            save_message(session_id, "user", command)
            save_message(session_id, "assistant", approval_reply)
            return approval_reply

    history = recent_messages(session_id, RECENT_HISTORY_MESSAGES)
    messages = [
        {"role": "system", "content": system_prompt},
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
            reply = str(assistant.get("content") or "").strip() or "Ik kreeg geen bruikbaar modelantwoord terug."
            reply = _identity_safe_reply(reply, system_prompt)
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
            messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result, ensure_ascii=False)})

        messages.append({
            "role": "user",
            "content": (
                f"Original request from Bas: {command}\n\n"
                "Gebruik alleen geverifieerde resultaten. Gebruik lokale tools direct wanneer de toollaag dat toestaat. "
                "Vraag alleen approval als een toolresultaat approval_required bevat, en gebruik dan exact de meegeleverde token."
            ),
        })

    reply = "Ik kon deze opdracht niet binnen de begrensde toolstappen afronden."
    save_message(session_id, "user", command)
    save_message(session_id, "assistant", reply)
    return reply
