import os
import json
import logging
import requests
import dataclasses
import json

from datetime import datetime
from typing import Any, Dict, List, Optional

# DEBUG = os.environ.get("DEBUG", "false")
# if DEBUG.lower() == "true":
#     logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger("logger")


AZURE_SEARCH_PERMITTED_GROUPS_COLUMN = os.environ.get(
    "AZURE_SEARCH_PERMITTED_GROUPS_COLUMN"
)


class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


async def format_as_ndjson(r):
    try:
        async for event in r:
            yield json.dumps(event, cls=JSONEncoder) + "\n"
    except Exception as error:
        logger.exception("Exception while generating response stream: %s", error)
        yield json.dumps({"error": str(error)})


def parse_multi_columns(columns: str) -> list:
    if "|" in columns:
        return columns.split("|")
    else:
        return columns.split(",")


def fetchUserGroups(userToken, nextLink=None):
    # Recursively fetch group membership
    if nextLink:
        endpoint = nextLink
    else:
        endpoint = "https://graph.microsoft.com/v1.0/me/transitiveMemberOf?$select=id"

    headers = {"Authorization": "bearer " + userToken}
    try:
        r = requests.get(endpoint, headers=headers)
        if r.status_code != 200:
            logger.error(f"Error fetching user groups: {r.status_code} {r.text}")
            return []

        r = r.json()
        if "@odata.nextLink" in r:
            nextLinkData = fetchUserGroups(userToken, r["@odata.nextLink"])
            r["value"].extend(nextLinkData)

        return r["value"]
    except Exception as e:
        logger.error(f"Exception in fetchUserGroups: {e}")
        return []


def generateFilterString(userToken):
    # Get list of groups user is a member of
    userGroups = fetchUserGroups(userToken)

    # Construct filter string
    if not userGroups:
        logger.debug("No user groups found")

    group_ids = ", ".join([obj["id"] for obj in userGroups])
    return f"{AZURE_SEARCH_PERMITTED_GROUPS_COLUMN}/any(g:search.in(g, '{group_ids}'))"


def format_non_streaming_response(chatCompletion, history_metadata, apim_request_id):
    response_obj = {
        "id": chatCompletion.id,
        "model": chatCompletion.model,
        "created": chatCompletion.created,
        "object": chatCompletion.object,
        "choices": [{"messages": []}],
        "history_metadata": history_metadata,
        "apim-request-id": apim_request_id,
    }

    if len(chatCompletion.choices) > 0:
        message = chatCompletion.choices[0].message
        if message:
            if hasattr(message, "context"):
                response_obj["choices"][0]["messages"].append(
                    {
                        "role": "tool",
                        "content": json.dumps(message.context),
                    }
                )
            response_obj["choices"][0]["messages"].append(
                {
                    "role": "assistant",
                    "content": message.content,
                }
            )
            return response_obj

    return {}

def format_stream_response(chatCompletionChunk, history_metadata, apim_request_id):
    response_obj = {
        "id": chatCompletionChunk.id,
        "model": chatCompletionChunk.model,
        "created": chatCompletionChunk.created,
        "object": chatCompletionChunk.object,
        "choices": [{"messages": []}],
        "history_metadata": history_metadata,
        "apim-request-id": apim_request_id,
    }

    if len(chatCompletionChunk.choices) > 0:
        delta = chatCompletionChunk.choices[0].delta
        if delta:
            if hasattr(delta, "context"):
                messageObj = {"role": "tool", "content": json.dumps(delta.context)}
                response_obj["choices"][0]["messages"].append(messageObj)
                return response_obj
            if delta.role == "assistant" and hasattr(delta, "context"):
                messageObj = {
                    "role": "assistant",
                    "context": delta.context,
                }
                response_obj["choices"][0]["messages"].append(messageObj)
                return response_obj
            if delta.tool_calls:
                messageObj = {
                    "role": "tool",
                    "tool_calls": {
                        "id": delta.tool_calls[0].id,
                        "function": {
                            "name" : delta.tool_calls[0].function.name,
                            "arguments": delta.tool_calls[0].function.arguments
                        },
                        "type": delta.tool_calls[0].type
                    }
                }
                if hasattr(delta, "context"):
                    messageObj["context"] = json.dumps(delta.context)
                response_obj["choices"][0]["messages"].append(messageObj)
                return response_obj
            else:
                if delta.content:
                    messageObj = {
                        "role": "assistant",
                        "content": delta.content,
                    }
                    response_obj["choices"][0]["messages"].append(messageObj)
                    return response_obj

    return {}


def format_pf_non_streaming_response(
    chatCompletion, history_metadata, response_field_name, citations_field_name, message_uuid=None
):
    if chatCompletion is None:
        logger.error(
            "chatCompletion object is None - Increase PROMPTFLOW_RESPONSE_TIMEOUT parameter"
        )
        return {
            "error": "No response received from promptflow endpoint increase PROMPTFLOW_RESPONSE_TIMEOUT parameter or check the promptflow endpoint."
        }
    if "error" in chatCompletion:
        logger.error(f"Error in promptflow response api: {chatCompletion['error']}")
        return {"error": chatCompletion["error"]}

    logger.debug(f"chatCompletion: {chatCompletion}")
    try:
        messages = []

        # (1) Optional: letztes User-Echo aus PF ist nicht bekannt → hier NICHT setzen.
        #  -> Das Echo setzt du zentral in app.complete_chat_request (siehe unten).
        #    Für PF-Pfad brauchst du daher dieselbe Logik dort (s. Punkt 1b).

        # (2) Tool zuerst
        if citations_field_name in chatCompletion:
            citation_content = {"intent": "", "citations": chatCompletion[citations_field_name], "data_points": []}
            messages.append({
                "role": "tool",
                "content": json.dumps(citation_content, ensure_ascii=False)
            })

        # (3) Assistant danach
        if response_field_name in chatCompletion:
            messages.append({
                "role": "assistant",
                "content": chatCompletion[response_field_name]
            })

        response_obj = {
            "id": chatCompletion["id"],
            "model": "",
            "created": "",
            "object": "",
            "history_metadata": history_metadata,
            "choices": [{ "messages": messages }]
        }
        return response_obj
    except Exception as e:
        logger.error(f"Exception in format_pf_non_streaming_response: {e}")
        return {}


def convert_to_pf_format(input_json, request_field_name, response_field_name):
    output_json = []
    logger.debug(f"Input json: {input_json}")
    # align the input json to the format expected by promptflow chat flow
    for message in input_json["messages"]:
        if message:
            if message["role"] == "user":
                new_obj = {
                    "inputs": {request_field_name: message["content"]},
                    "outputs": {response_field_name: ""},
                }
                output_json.append(new_obj)
            elif message["role"] == "assistant" and len(output_json) > 0:
                output_json[-1]["outputs"][response_field_name] = message["content"]
    logger.debug(f"PF formatted response: {output_json}")
    return output_json


def comma_separated_string_to_list(s: str) -> List[str]:
    '''
    Split comma-separated values into a list.
    '''
    return s.strip().replace(' ', '').split(',')

####################
# GROUNDING
####################

def _map_citation(c: Dict[str, Any]) -> Dict[str, Any]:
    """Mappt beliebige RAG/SDK-Zitation auf FE-Citation-Schema."""
    # Eingänge flexibel: 'content' | 'text', 'title' | 'filepath' | 'id', ...
    content = c.get("content") or c.get("text") or ""
    cid = (
        c.get("id")
        or c.get("reindex_id")
        or c.get("filepath")
        or c.get("title")
        or c.get("url")
        or "unknown"
    )

    # optionales Metadaten-Feld als String (FE erwartet string | null)
    metadata_obj = (
        c.get("metadata")
        or c.get("@search")  # falls was vom Search kommt
        or {}
    )
    try:
        metadata_str = json.dumps(metadata_obj, ensure_ascii=False) if metadata_obj else None
    except Exception:
        metadata_str = None

    return {
        # FE-Felder (siehe api/models.ts)
        "part_index": c.get("part_index"),             # optional
        "content": content,
        "id": str(cid),
        "title": c.get("title"),
        "filepath": c.get("filepath"),
        "url": c.get("url"),
        "metadata": metadata_str,                      # string | null
        "chunk_id": c.get("chunk_id") or c.get("chunkId"),
        "reindex_id": c.get("reindex_id"),            # optional
        # Backend-interne Felder werden bewusst NICHT übertragen
    }

def _build_tool_message_content(
    citations: List[Dict[str, Any]],
    intent: Optional[str] = None,
) -> str:
    """Erzeugt den JSON-String, den das FE erwartet: { citations, intent }."""
    payload = {
        "citations": [_map_citation(c) for c in citations],
        "intent": intent or "",  # Platzhalter, falls unbekannt
    }
    return json.dumps(payload, ensure_ascii=False)

def build_tool_message_from_oyd_context(sdk_ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Nimmt das Azure OpenAI 'context' Objekt (OYD) und baut die Tool-Message.
    Erwartet Felder wie 'citations' oder 'documents' im SDK-Kontext.
    """
    raw = sdk_ctx.get("citations") or sdk_ctx.get("documents") or []
    content = _build_tool_message_content(raw, intent=sdk_ctx.get("intent"))
    return {
        "id": "",  # wird später auf die Response-ID gesetzt
        "role": "tool",
        "content": content,
        "date": "",  # wird im Stream/Formatter gesetzt
    } if raw else None

def build_tool_message_from_own_context(own_ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Nimmt unseren eigenen Retrieval-Block (z. B. _selly_grounding) und baut Tool-Message.
    Akzeptiert:
      - "citations": [...], optional
      - "context_text": string (falls keine Zitationen vorliegen)
    """
    if not isinstance(own_ctx, dict):
        return None

    # bevorzugt strukturierte Zitationen; andernfalls eine einzige „Text“-Citation als Fallback
    raw = own_ctx.get("citations") or []
    if not raw and own_ctx.get("context_text"):
        raw = [{
            "id": "context_text",
            "title": "Context",
            "content": own_ctx.get("context_text"),
            "url": None,
            "filepath": None,
        }]

    if not raw:
        return None

    content = _build_tool_message_content(raw, intent=own_ctx.get("intent"))
    return {
        "id": "",
        "role": "tool",
        "content": content,
        "date": "",
    }

def attach_tool_message(
    response_obj: Dict[str, Any],
    oyd_ctx: Optional[Dict[str, Any]],
    own_ctx: Optional[Dict[str, Any]],
) -> None:
    """
    Mutiert response_obj so, dass choices[0].messages ggf. eine 'tool'-Message
    direkt VOR der letzten 'assistant'-Message enthält.
    """
    try:
        choices = response_obj.get("choices") or []
        if not choices:
            return
        msgs = choices[0].get("messages") or []
        # letzte Assistant-Message finden
        last_idx = None
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("role") == "assistant":
                last_idx = i
                break
        if last_idx is None:
            return

        # Tool-Message bauen
        tool_msg = None
        if isinstance(oyd_ctx, dict):
            tool_msg = build_tool_message_from_oyd_context(oyd_ctx)
        if tool_msg is None and isinstance(own_ctx, dict):
            tool_msg = build_tool_message_from_own_context(own_ctx)

        if not tool_msg:
            return

        # Response-Metadaten übernehmen
        tool_msg["id"] = response_obj.get("id") or tool_msg["id"] or ""
        tool_msg["date"] = datetime.utcnow().isoformat() + "Z"

        # WICHTIG: assistant.context entfernen (FE liest aus tool-message)
        try:
            if "context" in msgs[last_idx]:
                del msgs[last_idx]["context"]
        except Exception:
            pass

        # Tool vor die Assistant-Message einfügen
        msgs.insert(last_idx, tool_msg)
        choices[0]["messages"] = msgs
    except Exception:
        # fail-safe: niemals den Response-Aufbau sprengen
        import logging
        logging.getLogger("logger").exception("attach_tool_message failed")
