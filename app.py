import threading
import io
import copy
import json
import os
import sys
import logging
import uuid
import httpx
import asyncio
import uuid
import time
from quart import (
    Blueprint,
    Quart,
    jsonify,
    make_response,
    request,
    send_from_directory,
    render_template,
    current_app,
    send_file,
    abort
)

from typing import Any, Dict, Optional, List

from openai import AsyncAzureOpenAI
from azure.identity.aio import (
    DefaultAzureCredential,
    get_bearer_token_provider
)
from backend.auth.auth_utils import get_authenticated_user_details
from backend.security.ms_defender_utils import get_msdefender_user_json
from backend.settings import (
    app_settings,
    MINIMUM_SUPPORTED_AZURE_OPENAI_PREVIEW_API_VERSION
)
from backend.utils import (
    format_as_ndjson,
    format_stream_response,
    format_non_streaming_response,
    convert_to_pf_format,
    format_pf_non_streaming_response,
    attach_tool_message
)
from backend.db.init_clients import (
    init_cosmos_history_client,
    init_cosmos_admin_client,
    cosmos_history_db_ready,
    cosmos_admin_db_ready,

)
from backend.tasks.batch_runner import background_runner

from backend.retriever.retriever import get_context_for_query_sync

import tempfile
import azure.cognitiveservices.speech as speechsdk
import ffmpeg
import csv
from azure.storage.blob.aio import BlobServiceClient
import pandas as pd
import certifi
from azure.core.pipeline.transport import AioHttpTransport

from backend.routes.admin_prompts import prompts_bp
from backend.routes.admin_runs import runs_bp
from backend.routes.admin_compare import compare_bp

import re
from collections import deque
import tiktoken


logger = logging.getLogger('logger')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(filename)-14s - %(funcName)-16s - %(levelname)-7s - %(message)s') # Set format

# Create file handler and set level
f_handler = logging.FileHandler('app.log')
f_handler.setLevel(logging.DEBUG)
f_handler.setFormatter(formatter)

# Create console handler and set level
c_handler = logging.StreamHandler(sys.stdout)
c_handler.setLevel(logging.DEBUG)
c_handler.setFormatter(formatter)

# Adding the handlers to the logger
logger.addHandler(f_handler)
logger.addHandler(c_handler)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

#for speech
SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
#for storage
# AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
# AZURE_RESULTS_CONTAINER = os.getenv("AZURE_RESULTS_CONTAINER")
# AZURE_RESULTS_BLOB_NAME = os.getenv("AZURE_RESULTS_BLOB_NAME")

# =============== START Selly Context Helpers ======================

MAX_TURNS = int(os.getenv("SELLY_MAX_HISTORY_TURNS"))
MAX_TOKENS = int(os.getenv("SELLY_MAX_CONTEXT_TOKENS"))
SUMMARIZE_AFTER = int(os.getenv("SELLY_SUMMARIZE_AFTER_TURNS"))

# --- Tokenizer setup ------
MODEL_NAME = os.getenv("AZURE_OPENAI_MODEL")

def get_encoder(model_name: str):
    try:
        return tiktoken.encoding_for_model(model_name) #tikotken is a tokenizer by OpenAI
    except Exception:
        return tiktoken.get_encoding("cl100k_base") #cl100k_base is the name of the general tokenizer for GPT-4, 4o, 3.5 family 
    
ENCODER = get_encoder(MODEL_NAME) #the tokenizer dictionary

def count_text_tokens(text: str) -> int:
    if not text:
        return 0
    return len(ENCODER.encode(text))  #it divides the text into tokens and gives an ID list for each token in the text, the length of this list is the real amount of token; so we get the amount of token for the text we give

def count_messages_tokens(messages: list) -> int:
    """
    a an approximate token count for the chat messages
    """
    total = 0
    for m in messages:
        total += count_text_tokens(m.get("content") or "")
        #role/format overhead is approximately 4-8 tokens:
        total += 6
    return total


def extract_memory_from_user_text(text: str, memory: dict):
    """
    Extract stable user information from natural language input.
    More general logic:
    - key/value pairs (e.g. 'Tarif Basis', 'Verbrauch 3000') 
    - 5-digit German postal codes
    - kWh values
    !we already capture everything with key\value pairs, sonce kWh and postal codes are used so often we indicate them separately
    """
    if not text:
        return
    #General key-value patterns (for ex. Tarif Basis, Verbrauch 3000)
    pairs = re.findall(r"([A-Za-zÄÖÜäöüß]+)\s*[:= ]\s*([A-Za-z0-9ÄÖÜäöüß./-]+)", text)
    for key, value in pairs:
        memory[key.lower()] = value

    #detect plz
    m = re.search(r"\b(\d{5})\b", text)
    if m:
        memory["plz"] = m.group(1)

    #detect yearly usage in kWh
    m = re.search(r"(\d{3,6})\s*kWh", text)
    if m:
        memory["verbrauch"] = m.group(1)

def inject_memory_system_block(messages: list, memory: dict):
    """
    Add a system message at the top telling the model what user facts should be remembered across turns
    """
    if not memory:
        return messages
    mem_line = ", ".join(f"{k}={v}" for k, v in memory.items())
    messages.insert(0, {
        "role": "system",
        "content": f"Persisted user facts to respect in follow-ups: {mem_line}"
    })
    return messages

async def load_last_messages_from_cosmos(conversation_id: str, user_id: str) -> list:
    """
    load Previous messages (user + assistant) from CosmosDB, ignoring tool/system messages
    !warning: this function is currently out of service because we didn't combine it with any cosmosDB account, 
    so we don't have any chat history to load yet!
    """
    if not current_app.cosmos_conversation_client:
        return []
    
    msgs = await current_app.cosmos_conversation_client.get_messages(user_id, conversation_id)
    canon = []
    for m in msgs:
        role = m.get("role")
        if role in ("user", "assistant"):
            canon.append({
                "id": m.get("id"),
                "role": m.get("role"),
                "content": m.get("content", "")
            })
    return canon

async def build_contextful_messages(request_body: dict, request_headers) -> dict:
    """
    main logic:
        - Loads past messages (if conversation_id exists)
        - Extracts memory from the latest user message
        - Injects memory as a system block
        - Applies turn limit (MAX_TURNS)
        - Applies token limit (MAX_TOKENS)
    """

    messages = request_body.get("messages", [])[:] # with "[:]", we copy the list so that we can configure the list without damaging the original one 
    history_meta = request_body.get("history_metadata", {}) or {}
    memory = history_meta.get("memory", {}) or {}
    #Load history from CosmosDB
    conversation_id = history_meta.get("conversation_id")

    #only resolve user & hit Cosmos if Cosmos client exists AND we have a conversation id
    if current_app.cosmos_conversation_client and conversation_id:
        authenticated_user = get_authenticated_user_details(request_headers)
        #Identify user for CosmosDB lookup
        user_id = authenticated_user["user_principal_id"]
        cosmos_msgs = await load_last_messages_from_cosmos(conversation_id, user_id)
        merged = deque(cosmos_msgs) #deque is useful because it can function as FIFO as well as LIFO
        for m in messages:
            merged.append(m)
        messages = list(merged)

    # update memory from latest user message
    if messages and messages[-1].get("role") == "user":
        extract_memory_from_user_text(messages[-1]["content"], memory)
    
    # inject memory as system message at top
    messages = inject_memory_system_block(messages, memory)

    #turn limit (only keep last N user+assistant messages)
    system_msgs = [m for m in messages if m["role"] == "system"]
    turn_msgs = [m for m in messages if m["role"] in ("user", "assistant")]
    turn_msgs = turn_msgs[-2*MAX_TURNS:] #last 2*MAX_TURNS messages per turn, for ex. MAX_TURNS = 8 so the last 16 messages.
    #messages has [user1, bot1, user2, bot2, user3, bot3, user4, bot4, user5, bot5], so we need both both and user messages that's why *2, and -2 because we want the first parts out and only the last parts!
    messages = system_msgs + turn_msgs
    #if the system msgs weren't added then model could forget the rules, answer in wrong format, not apply the plz rules, behave like a free chatbot

    while count_messages_tokens(messages) > MAX_TOKENS and len(messages) > 3: #the 3 is system + user's last message + chatbot's message , so it should be minimum three of these (of course it can be more than 3 but we should consider that the message tokens should not be greater than MAX, if it is then we delete some messages)
        for i in range(1, len(messages)): #skip 0 (system block); index 0 is system, index 1 is user, index 2 is assistant, index 3 is user, index 4 is assistant, ...
            if messages[i]["role"] in ("user", "assistant"):
                del messages[i] #delete the message[i], so we don't delete the system messages only the user and assistant in order to decrease the token
                break
    
    #Debug log: how much context goes in
    used_msgs = [m for m in messages if m.get("role") in ("user", "assistant")]
    turns = len(used_msgs) / 2
    total_tokens = count_messages_tokens(messages)
    logging.info(f"[CONTEXT] Using {len(used_msgs)} messages (~{turns:.1f} turns) | ~{total_tokens} tokens")
    
    # store memory back into metadata
    history_meta["memory"] = memory
    request_body["history_metadata"] = history_meta
    request_body["messages"] = messages
    return request_body

#================== END Selly Context Helpers =======================

    
# bp = Blueprint("routes", __name__, static_folder="static", template_folder="static")
bp = Blueprint("routes", __name__)


def create_app():
    static_dir = os.path.join(BASE_DIR, "static")        # backend/static
    app = Quart(
        __name__,
        static_folder=static_dir,                        # wo wirklich die Dateien sind
        static_url_path="",                              # serve assets unter /
        template_folder=static_dir                       # index.html dort
    )

    # Alle existierenden Endpoints
    app.register_blueprint(bp)
    # Admin Prompt Endpoints /admin/prompts & /admin/runs
    app.register_blueprint(prompts_bp)
    app.register_blueprint(runs_bp)
    app.register_blueprint(compare_bp)

    app.config["TEMPLATES_AUTO_RELOAD"] = True

    @app.before_serving
    async def init():

        # History-Client initialisieren
        try:
            app.cosmos_conversation_client = await init_cosmos_history_client()
            cosmos_history_db_ready.set()
            logger.info("Cosmos History Client ready")
        except Exception as e:
            logger.exception("Failed to initialize Cosmos History client")
            raise e

        # Prompt-Client initialisieren
        try:
            app.cosmos_prompt_client = await init_cosmos_admin_client()
            cosmos_admin_db_ready.set()
            logger.info("Cosmos Prompt Client ready")
        except Exception as e:
            logger.exception("Failed to initialize Cosmos Prompt client")
            raise e

    @app.before_serving
    async def start_background_runner():
        # wartet intern auf cosmos_admin_db_ready
        asyncio.create_task(background_runner())

    return app


@bp.route("/")
async def index():
    return await render_template(
        "index.html",
        title=app_settings.ui.title,
        favicon=app_settings.ui.favicon
    )

# the SDK will call our methods whenever it needs more audio samples
class MemoryPCMCallback(speechsdk.audio.PullAudioInputStreamCallback):
    def __init__(self, pcm_bytes: bytes):
        super().__init__()
        self._buf = io.BytesIO(pcm_bytes)
        self._lock = threading.Lock()

    def read(self, buffer: memoryview) -> int:
        with self._lock:
            chunk = self._buf.read(buffer.nbytes)
            if not chunk:
                return 0
            buffer[:len(chunk)] = chunk
            return len(chunk)

    def close(self) -> None:
        with self._lock:
            self._buf.close()
        super().close()

#MicButton uses MediaRecorder to grab raw microphone samples, it packages them into a small WebM file and hands us a Blob

@bp.route("/transcribe", methods=["POST"])
async def transcribe():
    start_t = time.time()
    logger.info("Transcription request received")

    # --- Input Validation ---
    webm = await request.data
    if not webm or len(webm) < 1000:  # primitive check
        return jsonify({"text": "", "error": "empty or invalid audio"}), 400

    # --- Convert WebM → PCM ---
    try:
        proc = (
            ffmpeg.input("pipe:0")
                  .output("pipe:1", format="s16le", acodec="pcm_s16le", ac=1, ar="16000")
                  .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True)
        )
        loop = asyncio.get_running_loop()
        pcm_bytes, _ = await loop.run_in_executor(None, lambda: proc.communicate(input=webm, timeout=15))
        if proc.returncode != 0:
            raise RuntimeError("FFmpeg returned non-zero exit code")
        logger.info("FFmpeg → PCM successful")
    except Exception as e:
        logger.exception(f"FFmpeg conversion failed. Error: {e}")
        return jsonify({"text": "", "error": "ffmpeg conversion failed"}), 500

    # --- Setup Speech SDK ---
    try:
        speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)
        langs = ["de-DE", "en-US", "tr-TR", "ru-RU", "pl-PL", "it-IT", "fr-FR", "uk-UA", "cs-CZ", "es-ES"]
        auto_lang = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(langs)
        speech_config.set_property(
            property_id=speechsdk.PropertyId.SpeechServiceConnection_LanguageIdMode,
            value='Continuous'
        )

        fmt = speechsdk.audio.AudioStreamFormat(samples_per_second=16000, bits_per_sample=16, channels=1)
        pull_cb = MemoryPCMCallback(pcm_bytes)
        pull_stream = speechsdk.audio.PullAudioInputStream(pull_cb, fmt)
        audio_cfg = speechsdk.audio.AudioConfig(stream=pull_stream)

        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            auto_detect_source_language_config=auto_lang,
            audio_config=audio_cfg
        )
    except Exception as e:
        logger.exception(f"Speech SDK init failed. Error: {e}")
        return jsonify({"text": "", "error": "speech sdk init failed"}), 500

    # --- Recognition Logic ---
    all_text = []
    text_lock = threading.Lock()
    done = threading.Event()

    def on_rec(evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            with text_lock:
                all_text.append(evt.result.text)

    def on_stop(evt):
        done.set()

    recognizer.recognized.connect(on_rec)
    recognizer.session_stopped.connect(on_stop)
    recognizer.canceled.connect(on_stop)

    try:
        recognizer.start_continuous_recognition()
        # Wait max 30 seconds
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(loop.run_in_executor(None, done.wait), timeout=30)
        recognizer.stop_continuous_recognition()
    except asyncio.TimeoutError:
        recognizer.stop_continuous_recognition()
        logger.warning("Recognition timeout after 30s")
    except Exception as e:
        recognizer.stop_continuous_recognition()
        logger.exception("Speech recognition failed. Error: {e}")
        return jsonify({"text": "", "error": "speech recognition failed"}), 500

    # --- Return Result ---
    transcript = " ".join(all_text).strip()
    duration = time.time() - start_t
    logger.info(f"Transcription done in {duration:.2f}s: {transcript!r}")
    return jsonify({"text": transcript})

@bp.route("/favicon.ico")
async def favicon():
    return await bp.send_static_file("favicon.ico")


@bp.route("/assets/<path:path>")
async def assets(path):
    return await send_from_directory("static/assets", path)

# @bp.route("/evaluate", methods=["POST"])
# async def evaluate():
#     file_path = os.path.join(os.path.dirname(__file__), "sample_prompts.csv")
#     result_rows = []

#     try:
#         with open(file_path, newline='', encoding='utf-8') as csvfile:
#             reader = csv.DictReader(csvfile)
#             for idx,row in enumerate(reader):
#                 # if idx >= 20: #for testing first
#                 #     break
#                 question = row['Question']
#                 expected_answer = row['ExpectedAnswer']
#                 logger.info(f"Processing question {idx+1}: {question}")
#                 request_body = {
#                     "messages": [{
#                         "role": "user",
#                         "content": question
#                     }]
#                 }

#                 try:
#                     response = await complete_chat_request(request_body, request.headers)
#                     #logger.info(f"raw response: {response}") #gives everything

#                     choices = response.get("choices", [])
#                     if choices:
#                         messages = choices[0].get("messages", [])
#                         generated_answer = messages[-1].get("content", "") if messages else ""
#                     else:
#                         generated_answer = ""

#                     logger.info(f"Generated answer for question {idx+1}: {generated_answer}")
#                 except Exception as e:
#                     logger.error(f"Failed to get response for question {idx+1}: {e}")
#                     generated_answer = "ERROR"


#                 result_rows.append({
#                     "question": question,
#                     "generated_answer": generated_answer,
#                     "expected_answer": expected_answer
#                 })

#                 await asyncio.sleep(15) #so that we don't get overload

#         if not AZURE_STORAGE_CONNECTION_STRING:
#             raise ValueError("Plese set Storage Connection String")

#         #save to CSV
#         results_df = pd.DataFrame(result_rows)
#         results_csv_path = os.path.join(tempfile.gettempdir(), "results.csv")
#         results_df.to_csv(results_csv_path, index=False)

#         transport = AioHttpTransport(connection_verify=certifi.where()) #so that our venv could find the certificate

#         #Upload to Azure blob
#         service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING, transport=transport)
#         container_name = AZURE_RESULTS_CONTAINER
#         virtual_dir = "golden_cases/results.csv"
#         client = service_client.get_blob_client(container=container_name, blob=virtual_dir)

#         with open(results_csv_path, "rb") as f:
#             await client.upload_blob(f, overwrite=True) # if a blob witht the same name already exists then overwrite it!!
#         logger.info("uploaded to Azure Blob Storge")

#         return await send_file(results_csv_path, as_attachment=True, attachment_filename="results.csv") #so that we get the result.csv locally too


#     except Exception as e:
#         logger.exception("Error during chatbot evaluation")
#         return jsonify({"error": str(e)}), 500

# # Debug settings
# DEBUG = os.environ.get("DEBUG", "false")
# if DEBUG.lower() == "true":
#     logging.basicConfig(level=logging.DEBUG)

USER_AGENT = "GitHubSampleWebApp/AsyncAzureOpenAI/1.0.0"


# Frontend Settings via Environment Variables
frontend_settings = {
    "auth_enabled": app_settings.base_settings.auth_enabled,
    "feedback_enabled": (
        app_settings.chat_history and
        app_settings.chat_history.enable_feedback
    ),
    "ui": {
        "title": app_settings.ui.title,
        "logo": app_settings.ui.logo,
        "chat_logo": app_settings.ui.chat_logo or app_settings.ui.logo,
        "chat_title": app_settings.ui.chat_title,
        "chat_description": app_settings.ui.chat_description,
        "show_share_button": app_settings.ui.show_share_button,
        "show_chat_history_button": app_settings.ui.show_chat_history_button,
    },
    "sanitize_answer": app_settings.base_settings.sanitize_answer,
    "oyd_enabled": app_settings.base_settings.datasource_type,
    "own_retrieval_enabled": app_settings.base_settings.openai_own_retrieval_enabled,
}


# Enable Microsoft Defender for Cloud Integration
MS_DEFENDER_ENABLED = os.environ.get("MS_DEFENDER_ENABLED", "true").lower() == "true"


azure_openai_tools = []
azure_openai_available_tools = []

# Initialize Azure OpenAI Client
async def init_openai_client():
    azure_openai_client = None

    try:
        # API version check
        if (
            app_settings.azure_openai.preview_api_version
            < MINIMUM_SUPPORTED_AZURE_OPENAI_PREVIEW_API_VERSION
        ):
            raise ValueError(
                f"The minimum supported Azure OpenAI preview API version is '{MINIMUM_SUPPORTED_AZURE_OPENAI_PREVIEW_API_VERSION}'"
            )

        # Endpoint
        if (
            not app_settings.azure_openai.endpoint and
            not app_settings.azure_openai.resource
        ):
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_RESOURCE is required"
            )

        endpoint = (
            app_settings.azure_openai.endpoint
            if app_settings.azure_openai.endpoint
            else f"https://{app_settings.azure_openai.resource}.openai.azure.com/"
        )

        # Authentication
        aoai_api_key = app_settings.azure_openai.key
        ad_token_provider = None
        if not aoai_api_key:
            logger.debug("No AZURE_OPENAI_KEY found, using Azure Entra ID auth")
            async with DefaultAzureCredential() as credential:
                ad_token_provider = get_bearer_token_provider(
                    credential,
                    "https://cognitiveservices.azure.com/.default"
                )

        # Deployment
        deployment = app_settings.azure_openai.model
        if not deployment:
            raise ValueError("AZURE_OPENAI_MODEL is required")

        # Default Headers
        default_headers = {"x-ms-useragent": USER_AGENT}

        # Remote function calls
        if app_settings.azure_openai.function_call_azure_functions_enabled:
            azure_functions_tools_url = f"{app_settings.azure_openai.function_call_azure_functions_tools_base_url}?code={app_settings.azure_openai.function_call_azure_functions_tools_key}"
            async with httpx.AsyncClient() as client:
                response = await client.get(azure_functions_tools_url)
            response_status_code = response.status_code
            if response_status_code == httpx.codes.OK:
                azure_openai_tools.extend(json.loads(response.text))
                for tool in azure_openai_tools:
                    azure_openai_available_tools.append(tool["function"]["name"])
            else:
                logger.error(f"An error occurred while getting OpenAI Function Call tools metadata: {response.status_code}")


        azure_openai_client = AsyncAzureOpenAI(
            api_version=app_settings.azure_openai.preview_api_version,
            api_key=aoai_api_key,
            azure_ad_token_provider=ad_token_provider,
            default_headers=default_headers,
            azure_endpoint=endpoint,
        )

        return azure_openai_client
    except Exception as e:
        logger.exception("Exception in Azure OpenAI initialization", e)
        azure_openai_client = None
        raise e

async def openai_remote_azure_function_call(function_name, function_args):
    if app_settings.azure_openai.function_call_azure_functions_enabled is not True:
        return

    azure_functions_tool_url = f"{app_settings.azure_openai.function_call_azure_functions_tool_base_url}?code={app_settings.azure_openai.function_call_azure_functions_tool_key}"
    headers = {'content-type': 'application/json'}
    body = {
        "tool_name": function_name,
        "tool_arguments": json.loads(function_args)
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(azure_functions_tool_url, data=json.dumps(body), headers=headers)
    response.raise_for_status()

    return response.text

# ---------- LOCAL HELPERS (self-contained) ----------

def _content_to_text(c):
    """Extrahiert Klartext aus ChatMessage.content (string oder [{type:'text',...}, ...])."""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for it in c:
            if isinstance(it, dict) and it.get("type") == "text":
                t = it.get("text")
                if isinstance(t, str) and t.strip():
                    parts.append(t)
        return " ".join(parts)
    return ""

def _compose_retrieval_query_from_history(msgs, max_messages=6, max_chars=1200):
    """Baut Query aus den letzten (user/assistant)-Nachrichten, ignoriert tool/system, cappt Länge."""
    if not msgs:
        return ""
    buf = []
    # rückwärts durchs Gespräch, nur user/assistant, jeweils Text extrahieren
    for m in reversed(msgs):
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        txt = _content_to_text(m.get("content"))
        if not txt:
            continue
        tag = "User" if role == "user" else "Assistant"
        buf.append(f"{tag}: {txt}")
        if len(buf) >= max_messages:
            break
    if not buf:
        return ""
    buf.reverse()
    joined = "\n".join(buf).strip()
    # hartes Limit – nehme das letzte Fenster (meist jüngster Kontext am Ende)
    if len(joined) > max_chars:
        joined = joined[-max_chars:]
    return joined

def _normalize_grounding_context(ctx):
    """Wie gehabt: (context_text:str, items:list[dict|str]) aus beliebigen Formen extrahieren."""
    if ctx is None:
        return "", []
    if isinstance(ctx, str):
        s = ctx.strip()
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                parsed = json.loads(s)
                return _normalize_grounding_context(parsed)
            except Exception:
                return s, []
        return s, []
    if isinstance(ctx, dict):
        text = (
            ctx.get("text")
            or ctx.get("context")
            or ctx.get("joined")
            or ctx.get("content")
            or ctx.get("fulltext")
            or ""
        )
        item_keys = ["hits","items","citations","results","documents","docs","matches","snippets","chunks"]
        items = []
        for k in item_keys:
            v = ctx.get(k)
            if isinstance(v, str):
                try:
                    v_parsed = json.loads(v)
                    if isinstance(v_parsed, list) and v_parsed:
                        items = v_parsed; break
                except Exception:
                    pass
            if isinstance(v, list) and v:
                items = v; break
        if not items:
            possible_doc = ctx.get("doc") or ctx.get("document") or ctx.get("record")
            if possible_doc:
                items = [possible_doc]
        return text or "", (items if isinstance(items, list) else [])
    if isinstance(ctx, list):
        parts, items = [], []
        for it in ctx:
            if isinstance(it, str):
                parts.append(it)
            else:
                items.append(it)
        text = "\n---\n".join([p for p in parts if p])
        return text, items
    return str(ctx), []

def _build_snippets_for_frontend(
    items,
    *,
    content_fields=None,
    title_field=None,
    url_field=None,
    filepath_field=None,
    max_chars_per_snippet=1200,
    max_snippets=10
):
    """
    Formt rohe Treffer in FE-kompatible citations um – EXAKTES Zielformat:
      { "content", "title", "url", "filepath", "chunk_id" }
    Alles andere (id, part_index, metadata, reindex_id, score) wird NICHT ausgegeben.
    JSON-/Tarif-Dumps werden nach Möglichkeit aussortiert.
    """
    citations, data_points = [], []
    content_fields = content_fields or ["content","text","chunk","page_content","document","body","snippet","chunk_text"]

    def _first_nonempty(d, fields):
        for f in fields:
            if isinstance(d, dict) and d.get(f):
                return d[f]
        return None

    def _looks_like_json(text: str) -> bool:
        if not isinstance(text, str):
            return False
        s = text.strip()
        return (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))

    def _preferable_title(title: str) -> bool:
        """Bevorzugt PDF/FAQ, meidet .json."""
        if not isinstance(title, str):
            return False
        tl = title.lower()
        if tl.endswith(".json"):
            return False
        return ("faq" in tl) or tl.endswith(".pdf") or True  # Default: zulassen

    for idx, doc in enumerate(items or []):
        if not isinstance(doc, dict):
            continue

        raw_text = _first_nonempty(doc, content_fields)
        if not raw_text:
            continue
        text = str(raw_text)

        # JSON-/Tarif-großblöcke meiden
        title = (doc.get(title_field) if title_field else None) or doc.get("title") or ""
        if _looks_like_json(text) or (isinstance(title, str) and title.lower().endswith(".json")):
            # nur nehmen, falls uns sonst die Zitate ausgehen – wir überspringen sie hier
            continue

        if len(text) > max_chars_per_snippet:
            text = text[:max_chars_per_snippet] + "…"

        url   = (doc.get(url_field) if url_field else None) or doc.get("url") or None
        fp    = (doc.get(filepath_field) if filepath_field else None) or doc.get("filepath") or doc.get("file_path")
        if not fp and title:
            # Dateiname ohne Extension als filepath-Fallback (wie im Soll)
            base = title.rsplit("/",1)[-1].rsplit("\\",1)[-1]
            fp = ".".join(base.split(".")[:-1]) or base

        citations.append({
            "content": text,
            "title": title or "(ohne Titel)",
            "url": url,
            "filepath": fp,
            "chunk_id": str(doc.get("chunk_id")) if doc.get("chunk_id") is not None else None
        })
        data_points.append(text)

        if len(citations) >= max_snippets:
            break

    return citations, data_points


def prepare_model_args(request_body, request_headers):
    """
    Baut model_args für AOAI und – falls OWN Retrieval aktiv – _selly_grounding:
      - History-basierte Query → get_context_for_query_sync
      - Kontext als System-Message injizieren
      - Citations exakt aufs Soll-Format reduziert
      - Intent als Liste zurückgeben
    Rückgabe: (model_args, request_body.get("_selly_grounding"))
    """

    # --- interne Helper: Intent-Liste aus der letzten User-Äußerung bauen ---
    def _build_intents_from_text(user_text: str):
        base = (user_text or "").strip().rstrip("?!.")
        intents = []
        if base:
            low = base.lower()
            if ("unterlagen" in low or "dokument" in low) and ("vertrag" in low):
                intents = [
                    "Dokumente beim Vertragsabschluss für Kunden",
                    "Welche Unterlagen erhält ein Kunde bei Vertragsabschluss?",
                    "Kundendokumente bei Abschluss eines Vertrags",
                ]
            else:
                intents = [base, f"Anfrage: {base}"]
        # deduplizieren, max 3
        seen, out = set(), []
        for it in intents:
            t = (it or "").strip()
            if t and t.lower() not in seen:
                out.append(t)
                seen.add(t.lower())
            if len(out) >= 3:
                break
        return out or ([base] if base else [])

    request_messages = request_body.get("messages", [])

    # Basis-Systemprompt
    base_system_prompt = getattr(app_settings.search, "role_information", None) \
                         or app_settings.azure_openai.system_message

    messages = [{"role": "system", "content": base_system_prompt}]

    # Eingehende Messages übernehmen
    for message in request_messages:
        if not message:
            continue
        role = message.get("role")
        if role == "user":
            messages.append({"role": "user", "content": message.get("content", "")})
        else:
            helper = {
                "role": role,
                "content": message.get("content")
            }
            if "name" in message:
                helper["name"] = message["name"]
            if "function_call" in message:
                helper["function_call"] = message["function_call"]
            if "context" in message:
                # bereits korrekt, ggf. JSON-String beibehalten
                try:
                    helper["context"] = json.loads(message["context"])
                except Exception:
                    pass
            messages.append(helper)

    # Defender-Kontext
    user_security_context = None
    if os.getenv("MS_DEFENDER_ENABLED", "true").lower() == "true":
        try:
            authenticated_user = get_authenticated_user_details(request_headers)
            user_security_context = get_msdefender_user_json(
                authenticated_user, request_headers, app_settings.ui.title
            )
        except Exception:
            logger.exception("prepare_model_args: building user_security_context failed")

    # Basis-Parameter für AOAI
    model_args = {
        "messages": messages,
        "temperature": app_settings.azure_openai.temperature,
        "max_tokens": app_settings.azure_openai.max_tokens,
        "top_p": app_settings.azure_openai.top_p,
        "stop": app_settings.azure_openai.stop_sequence,
        "stream": app_settings.azure_openai.stream,
        "model": app_settings.azure_openai.model
    }

    # Grounding-Merker fürs FE
    request_body["_selly_grounding"] = {"mode": None}

    # ---------- OWN RETRIEVAL ----------
    if messages and messages[-1]["role"] == "user" and app_settings.base_settings.openai_own_retrieval_enabled:
        try:
            # Tools ggf. anhängen (falls verwendet)
            if app_settings.azure_openai.function_call_azure_functions_enabled and len(azure_openai_tools) > 0:
                model_args["tools"] = azure_openai_tools

            # Query aus History für den Retriever
            user_query = _compose_retrieval_query_from_history(messages, max_messages=6, max_chars=1200)
            if not user_query:
                user_query = _content_to_text(messages[-1].get("content"))

            logger.debug("Retriever query (len=%d): %r", len(user_query or ""), (user_query or "")[:300])

            # Kontext holen
            context_raw = None
            try:
                context_raw = get_context_for_query_sync(user_query)
            except Exception:
                logger.exception("Own retrieval failed; proceeding without extra context")

            context_text, items = _normalize_grounding_context(context_raw)

            # Feld-Mapping aus Settings + robuste Defaults
            ds = getattr(app_settings, "datasource", None)
            cfg_fields = (getattr(ds, "content_columns", None) if ds else None) or []
            fallback_fields = ["content","text","chunk","page_content","document","body","snippet","chunk_text"]
            content_fields = list(dict.fromkeys([*cfg_fields, *fallback_fields]))

            title_field    = getattr(ds, "title_column", None) if ds else None
            url_field      = getattr(ds, "url_column", None) if ds else None
            filepath_field = getattr(ds, "filename_column", None) if ds else None

            citations, data_points = _build_snippets_for_frontend(
                items,
                content_fields=content_fields,
                title_field=title_field,
                url_field=url_field,
                filepath_field=filepath_field,
            )

            # Citations aufs EXAKTE Soll-Format reduzieren
            allowed = {"content", "title", "url", "filepath", "chunk_id"}
            filtered_citations = []
            for c in citations:
                if not isinstance(c, dict):
                    continue
                fc = {k: (c.get(k) if c.get(k) is not None else None) for k in allowed}
                # Title/ Filepath Fallbacks
                if not fc.get("title"):
                    fc["title"] = "(ohne Titel)"
                if not fc.get("filepath") and fc.get("title"):
                    base = fc["title"].rsplit("/",1)[-1].rsplit("\\",1)[-1]
                    fc["filepath"] = ".".join(base.split(".")[:-1]) or base
                filtered_citations.append(fc)

            logger.debug("OWN retrieval: built %d citations, %d data_points (reduced to target schema)",
                         len(filtered_citations), len(data_points))

            # Kontext als System-Message injizieren (falls vorhanden)
            if context_text and context_text.strip():
                messages.insert(1, {"role": "system", "content": f"Kontext:\n{context_text}"})
                model_args["messages"] = messages
                logger.debug("Own retrieval context injected (chars=%d)", len(context_text))

            # Intent-Liste aus der letzten User-Message
            user_text_last = _content_to_text(messages[-1].get("content"))
            intent_list = _build_intents_from_text(user_text_last)

            # FE-Grounding vormerken
            request_body["_selly_grounding"] = {
                "mode": "own",
                "intent": intent_list,            # Liste statt String
                "citations": filtered_citations,  # exakt: content,title,url,filepath,chunk_id
                "data_points": data_points
            }

        except Exception:
            logger.exception("prepare_model_args: own retrieval pipeline failed")

    # ---------- (Optional) OYD – falls OWN aus ist und DataSources aktiv sind ----------
    elif messages and messages[-1]["role"] == "user" and not app_settings.base_settings.openai_own_retrieval_enabled:
        try:
            logger.info("Retrieval-Mode = OYD (data_sources aktiv)")
            if app_settings.datasource:
                ds_payload = app_settings.datasource.construct_payload_configuration(request=request)
                model_args["extra_body"] = {"data_sources": [ds_payload]}
                # Intent minimal aus letzter User-Nachricht
                intent_list = _build_intents_from_text(_content_to_text(messages[-1].get("content")))
                request_body["_selly_grounding"] = {"mode": "oyd", "intent": intent_list}
        except Exception:
            logger.exception("prepare_model_args: OYD setup failed")

    # Defender-Kontext anhängen
    if user_security_context:
        try:
            model_args.setdefault("extra_body", {})
            model_args["extra_body"]["user_security_context"] = user_security_context.to_dict()
        except Exception:
            logger.exception("prepare_model_args: attaching user_security_context failed")

    # Maskiertes Logging
    try:
        model_args_clean = copy.deepcopy(model_args)
        if model_args_clean.get("extra_body"):
            for ds_item in model_args_clean["extra_body"].get("data_sources", []):
                params = ds_item.get("parameters", {})
                for k in ("key","connection_string","embedding_key","encoded_api_key","api_key"):
                    if k in params: params[k] = "*****"
                auth = params.get("authentication", {})
                for k in list(auth.keys()):
                    if k in ("key","connection_string","embedding_key","encoded_api_key","api_key"):
                        auth[k] = "*****"
                emb = params.get("embedding_dependency", {})
                if isinstance(emb, dict) and "authentication" in emb:
                    for k in list(emb["authentication"].keys()):
                        if k in ("key","connection_string","embedding_key","encoded_api_key","api_key"):
                            emb["authentication"][k] = "*****"
        logger.debug("REQUEST BODY (sanitized): %s", json.dumps(model_args_clean, indent=4))
    except Exception:
        logger.exception("prepare_model_args: safe logging failed")

    return model_args, request_body.get("_selly_grounding")

async def promptflow_request(request):
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {app_settings.promptflow.api_key}",
        }
        # Adding timeout for scenarios where response takes longer to come back
        logger.debug(f"Setting timeout to {app_settings.promptflow.response_timeout}")
        async with httpx.AsyncClient(
            timeout=float(app_settings.promptflow.response_timeout)
        ) as client:
            pf_formatted_obj = convert_to_pf_format(
                request,
                app_settings.promptflow.request_field_name,
                app_settings.promptflow.response_field_name
            )
            # NOTE: This only support question and chat_history parameters
            # If you need to add more parameters, you need to modify the request body
            response = await client.post(
                app_settings.promptflow.endpoint,
                json={
                    app_settings.promptflow.request_field_name: pf_formatted_obj[-1]["inputs"][app_settings.promptflow.request_field_name],
                    "chat_history": pf_formatted_obj[:-1],
                },
                headers=headers,
            )
        resp = response.json()
        resp["id"] = request["messages"][-1]["id"]
        return resp
    except Exception as e:
        logger.error(f"An error occurred while making promptflow_request: {e}")


async def process_function_call(response):
    response_message = response.choices[0].message
    messages = []

    if response_message.tool_calls:
        for tool_call in response_message.tool_calls:
            # Check if function exists
            if tool_call.function.name not in azure_openai_available_tools:
                continue

            function_response = await openai_remote_azure_function_call(tool_call.function.name, tool_call.function.arguments)

            # adding assistant response to messages
            messages.append(
                {
                    "role": response_message.role,
                    "function_call": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                    "content": None,
                }
            )

            # adding function response to messages
            messages.append(
                {
                    "role": "function",
                    "name": tool_call.function.name,
                    "content": function_response,
                }
            )  # extend conversation with function response

        return messages

    return None

async def send_chat_request(request_body, request_headers):
    filtered = [m for m in request_body.get("messages", []) if m.get("role") != "tool"]
    request_body = dict(request_body, messages=filtered)

    model_args, grounding_payload = prepare_model_args(request_body, request_headers)

    try:
        azure_openai_client = await init_openai_client()
        raw_response = await azure_openai_client.chat.completions.with_raw_response.create(**model_args)
        response = raw_response.parse()
        apim_request_id = raw_response.headers.get("apim-request-id")
        return response, apim_request_id, grounding_payload
    except Exception:
        logger.exception("Exception in send_chat_request")
        raise


async def complete_chat_request(request_body: Dict[str, Any], request_headers: Dict[str, str]) -> Dict[str, Any]:
    # Promptflow passt durch wie gehabt
    if app_settings.base_settings.use_promptflow:
        pf_resp = await promptflow_request(request_body)
        history_metadata = request_body.get("history_metadata", {})
        return format_pf_non_streaming_response(
            pf_resp,
            history_metadata,
            app_settings.promptflow.response_field_name,
            app_settings.promptflow.citations_field_name
        )

    # AOAI + unser Grounding
    response, apim_request_id, grounding_payload = await send_chat_request(request_body, request_headers)
    history_metadata = request_body.get("history_metadata", {})

    # Assistant-Text extrahieren
    assistant_text = ""
    try:
        if getattr(response, "choices", None):
            m = response.choices[0].message
            assistant_text = getattr(m, "content", "") or ""
    except Exception:
        logger.exception("Could not extract assistant content")

    # Tool-JSON exakt gemäß Zielschema bauen
    tool_json = None
    try:
        if isinstance(grounding_payload, dict) and grounding_payload.get("mode") == "own":
            citations = grounding_payload.get("citations") or []
            intents   = grounding_payload.get("intent") or []
            intent_str = ", ".join(intents) if isinstance(intents, list) else (str(intents) if intents else "")
            # Nur die erlaubten Keys in den Citations belassen (Sicherheitshalber)
            allowed = {"content", "title", "url", "filepath", "chunk_id"}
            norm_citations = []
            for c in citations:
                if isinstance(c, dict):
                    nc = {k: (c.get(k) if c.get(k) is not None else None) for k in allowed}
                    # Fallbacks
                    if not nc.get("title"):
                        nc["title"] = "(ohne Titel)"
                    if not nc.get("filepath") and nc.get("title"):
                        base = nc["title"].rsplit("/",1)[-1].rsplit("\\",1)[-1]
                        nc["filepath"] = ".".join(base.split(".")[:-1]) or base
                    norm_citations.append(nc)
            tool_json = json.dumps(
                {"citations": norm_citations, "intent": intent_str},
                ensure_ascii=False
            )
    except Exception:
        logger.exception("Building tool JSON failed")

    # FE-Response-Grundgerüst
    fe = {
        "id": getattr(response, "id", str(uuid.uuid4())),
        "model": getattr(response, "model", app_settings.azure_openai.model),
        "created": getattr(response, "created", int(time.time())),
        "object": "extensions.chat.completion",
        "choices": [{"messages": []}],
        "history_metadata": history_metadata,
        "apim-request-id": apim_request_id
    }

    # WICHTIG: Keine vorherigen Request-Nachrichten in die Antwort einbetten.
    # Das Frontend fügt User-/History-Nachrichten selbst hinzu –
    # hier nur (optional) Tool + Assistant für DIESE Antwort liefern.

    # 1) TOOL direkt vor ASSISTANT (nur wenn vorhanden) – ohne id/date Felder
    if tool_json:
        fe["choices"][0]["messages"].append({
            "role": "tool",
            "content": tool_json
        })

    # 2) ASSISTANT – KEIN 'context' Feld anhängen
    fe["choices"][0]["messages"].append({
        "role": "assistant",
        "content": assistant_text or ""
    })

    # Logging (truncated)
    try:
        logger.debug("Final FE response (truncated): %s", json.dumps(fe, indent=2))
    except Exception:
        logger.exception("Logging FE response failed")

    return fe


class AzureOpenaiFunctionCallStreamState():
    def __init__(self):
        self.tool_calls = []                # All tool calls detected in the stream
        self.tool_name = ""                 # Tool name being streamed
        self.tool_arguments_stream = ""     # Tool arguments being streamed
        self.current_tool_call = None       # JSON with the tool name and arguments currently being streamed
        self.function_messages = []         # All function messages to be appended to the chat history
        self.streaming_state = "INITIAL"    # Streaming state (INITIAL, STREAMING, COMPLETED)


async def process_function_call_stream(completionChunk, function_call_stream_state, request_body, request_headers, history_metadata, apim_request_id):
    if hasattr(completionChunk, "choices") and len(completionChunk.choices) > 0:
        response_message = completionChunk.choices[0].delta

        # Function calling stream processing
        if response_message.tool_calls and function_call_stream_state.streaming_state in ["INITIAL", "STREAMING"]:
            function_call_stream_state.streaming_state = "STREAMING"
            for tool_call_chunk in response_message.tool_calls:
                # New tool call
                if tool_call_chunk.id:
                    if function_call_stream_state.current_tool_call:
                        function_call_stream_state.tool_arguments_stream += tool_call_chunk.function.arguments if tool_call_chunk.function.arguments else ""
                        function_call_stream_state.current_tool_call["tool_arguments"] = function_call_stream_state.tool_arguments_stream
                        function_call_stream_state.tool_arguments_stream = ""
                        function_call_stream_state.tool_name = ""
                        function_call_stream_state.tool_calls.append(function_call_stream_state.current_tool_call)

                    function_call_stream_state.current_tool_call = {
                        "tool_id": tool_call_chunk.id,
                        "tool_name": tool_call_chunk.function.name if function_call_stream_state.tool_name == "" else function_call_stream_state.tool_name
                    }
                else:
                    function_call_stream_state.tool_arguments_stream += tool_call_chunk.function.arguments if tool_call_chunk.function.arguments else ""

        # Function call - Streaming completed
        elif response_message.tool_calls is None and function_call_stream_state.streaming_state == "STREAMING":
            function_call_stream_state.current_tool_call["tool_arguments"] = function_call_stream_state.tool_arguments_stream
            function_call_stream_state.tool_calls.append(function_call_stream_state.current_tool_call)

            for tool_call in function_call_stream_state.tool_calls:
                tool_response = await openai_remote_azure_function_call(tool_call["tool_name"], tool_call["tool_arguments"])

                function_call_stream_state.function_messages.append({
                    "role": "assistant",
                    "function_call": {
                        "name" : tool_call["tool_name"],
                        "arguments": tool_call["tool_arguments"]
                    },
                    "content": None
                })
                function_call_stream_state.function_messages.append({
                    "tool_call_id": tool_call["tool_id"],
                    "role": "function",
                    "name": tool_call["tool_name"],
                    "content": tool_response,
                })

            function_call_stream_state.streaming_state = "COMPLETED"
            return function_call_stream_state.streaming_state

        else:
            return function_call_stream_state.streaming_state


async def stream_chat_request(request_body, request_headers):
    # 3 Werte entpacken, grounding_payload wird für Tool-Message genutzt
    response, apim_request_id, grounding_payload = await send_chat_request(request_body, request_headers)
    history_metadata = request_body.get("history_metadata", {})

    async def generate(apim_request_id, history_metadata):
        # Falls eigener Retrieval-Modus aktiv war, sende zuerst eine Tool-Message (nur wenn Inhalte vorhanden)
        own_mode = isinstance(grounding_payload, dict) and grounding_payload.get("mode") == "own"
        sent_initial_tool = False
        try:
            if own_mode:
                citations = grounding_payload.get("citations") or []
                intents = grounding_payload.get("intent") or []
                intent_str = ", ".join(intents) if isinstance(intents, list) else (str(intents) if intents else "")
                allowed = {"content", "title", "url", "filepath", "chunk_id"}
                norm_citations = []
                for c in citations:
                    if isinstance(c, dict):
                        nc = {k: (c.get(k) if c.get(k) is not None else None) for k in allowed}
                        if not nc.get("title"):
                            nc["title"] = "(ohne Titel)"
                        if not nc.get("filepath") and nc.get("title"):
                            base = nc["title"].rsplit("/",1)[-1].rsplit("\\",1)[-1]
                            nc["filepath"] = ".".join(base.split(".")[:-1]) or base
                        norm_citations.append(nc)

                if norm_citations or intent_str:
                    tool_event = {
                        "id": str(uuid.uuid4()),
                        "model": getattr(app_settings.azure_openai, "model", ""),
                        "created": int(time.time()),
                        "object": "chat.completion.chunk",
                        "choices": [{
                            "messages": [{
                                "role": "tool",
                                "content": json.dumps({"citations": norm_citations, "intent": intent_str}, ensure_ascii=False)
                            }]
                        }],
                        "history_metadata": history_metadata,
                        "apim-request-id": apim_request_id
                    }
                    sent_initial_tool = True
                    yield tool_event
        except Exception:
            logger.exception("stream_chat_request: failed to emit initial tool message")
        if app_settings.azure_openai.function_call_azure_functions_enabled:
            function_call_stream_state = AzureOpenaiFunctionCallStreamState()

            async for completionChunk in response:
                stream_state = await process_function_call_stream(
                    completionChunk, function_call_stream_state,
                    request_body, request_headers, history_metadata, apim_request_id
                )

                if stream_state == "INITIAL":
                    resp_obj = format_stream_response(completionChunk, history_metadata, apim_request_id)
                    if own_mode and sent_initial_tool and resp_obj and resp_obj.get("choices"):
                        msgs = resp_obj["choices"][0].get("messages") or []
                        filtered = [m for m in msgs if m.get("role") != "tool"]
                        if not filtered:
                            continue
                        resp_obj["choices"][0]["messages"] = filtered
                    yield resp_obj

                if stream_state == "COMPLETED":
                    request_body["messages"].extend(function_call_stream_state.function_messages)
                    # NEU: erneut 3 Werte entpacken; grounding_payload wird nicht genutzt
                    function_response, apim_request_id, _ = await send_chat_request(request_body, request_headers)
                    async for functionCompletionChunk in function_response:
                        resp_obj2 = format_stream_response(functionCompletionChunk, history_metadata, apim_request_id)
                        if own_mode and sent_initial_tool and resp_obj2 and resp_obj2.get("choices"):
                            msgs2 = resp_obj2["choices"][0].get("messages") or []
                            filtered2 = [m for m in msgs2 if m.get("role") != "tool"]
                            if not filtered2:
                                continue
                            resp_obj2["choices"][0]["messages"] = filtered2
                        yield resp_obj2
        else:
            async for completionChunk in response:
                resp_obj = format_stream_response(completionChunk, history_metadata, apim_request_id)
                # Bei eigenem Retrieval: zusätzliche Tool-Nachrichten aus delta.context unterdrücken,
                # wenn bereits ein Tool-Event gesendet wurde
                if own_mode and sent_initial_tool and resp_obj and resp_obj.get("choices"):
                    msgs = resp_obj["choices"][0].get("messages") or []
                    filtered = [m for m in msgs if m.get("role") != "tool"]
                    if not filtered:
                        continue
                    resp_obj["choices"][0]["messages"] = filtered
                yield resp_obj

    return generate(apim_request_id=apim_request_id, history_metadata=history_metadata)

async def conversation_internal(request_body, request_headers):
    try:
        #build context (memory, trimming, token cap)
        request_body = await build_contextful_messages(request_body, request_headers)
        # Streaming wie gehabt (echte Tokens → NDJSON-Stream)
        if app_settings.azure_openai.stream and not app_settings.base_settings.use_promptflow:
            result_iter = await stream_chat_request(request_body, request_headers)
            resp = await make_response(format_as_ndjson(result_iter))
            resp.timeout = None
            resp.mimetype = "application/json-lines"
            return resp

        # Non-Streaming → exakt 1 NDJSON-Event (dein FE erwartet immer NDJSON)
        one_obj = await complete_chat_request(request_body, request_headers)

        async def one_event():
            yield one_obj

        resp = await make_response(format_as_ndjson(one_event()))
        resp.timeout = None
        resp.mimetype = "application/json-lines"
        return resp

    except Exception as ex:
        logger.exception(ex)
        if hasattr(ex, "status_code"):
            return jsonify({"error": str(ex)}), ex.status_code
        return jsonify({"error": str(ex)}), 500



@bp.route("/conversation", methods=["POST"])
async def conversation():
    if not request.is_json:
        return jsonify({"error": "request must be json"}), 415
    request_json = await request.get_json()

    return await conversation_internal(request_json, request.headers)


@bp.route("/frontend_settings", methods=["GET"])
def get_frontend_settings():
    try:
        return jsonify(frontend_settings), 200
    except Exception as e:
        logger.exception("Exception in /frontend_settings")
        return jsonify({"error": str(e)}), 500


## Conversation History API ##
@bp.route("/history/generate", methods=["POST"])
async def add_conversation():
    await cosmos_history_db_ready.wait()
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    ## check request for conversation_id
    request_json = await request.get_json()
    conversation_id = request_json.get("conversation_id", None)

    try:
        # make sure cosmos is configured
        if not current_app.cosmos_conversation_client:
            raise Exception("CosmosDB is not configured or not working")

        # check for the conversation_id, if the conversation is not set, we will create a new one
        history_metadata = {}
        if not conversation_id:
            title = await generate_title(request_json["messages"])
            conversation_dict = await current_app.cosmos_conversation_client.create_conversation(
                user_id=user_id, title=title
            )
            conversation_id = conversation_dict["id"]
            history_metadata["title"] = title
            history_metadata["date"] = conversation_dict["createdAt"]

        ## Format the incoming message object in the "chat/completions" messages format
        ## then write it to the conversation history in cosmos
        messages = request_json["messages"]
        if len(messages) > 0 and messages[-1]["role"] == "user":
            createdMessageValue = await current_app.cosmos_conversation_client.create_message(
                uuid=str(uuid.uuid4()),
                conversation_id=conversation_id,
                user_id=user_id,
                input_message=messages[-1],
            )
            if createdMessageValue == "Conversation not found":
                raise Exception(
                    "Conversation not found for the given conversation ID: "
                    + conversation_id
                    + "."
                )
        else:
            raise Exception("No user message found")

        # Submit request to Chat Completions for response
        request_body = await request.get_json()
        history_metadata["conversation_id"] = conversation_id
        request_body["history_metadata"] = history_metadata
        return await conversation_internal(request_body, request.headers)

    except Exception as e:
        logger.exception("Exception in /history/generate")
        return jsonify({"error": str(e)}), 500


@bp.route("/history/update", methods=["POST"])
async def update_conversation():
    await cosmos_history_db_ready.wait()
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    ## check request for conversation_id
    request_json = await request.get_json()
    conversation_id = request_json.get("conversation_id", None)

    try:
        # make sure cosmos is configured
        if not current_app.cosmos_conversation_client:
            raise Exception("CosmosDB is not configured or not working")

        # check for the conversation_id, if the conversation is not set, we will create a new one
        if not conversation_id:
            raise Exception("No conversation_id found")

        ## Format the incoming message object in the "chat/completions" messages format
        ## then write it to the conversation history in cosmos
        messages = request_json["messages"]
        if len(messages) > 0 and messages[-1]["role"] == "assistant":
            if len(messages) > 1 and messages[-2].get("role", None) == "tool":
                # write the tool message first
                await current_app.cosmos_conversation_client.create_message(
                    uuid=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    user_id=user_id,
                    input_message=messages[-2],
                )
            # write the assistant message
            await current_app.cosmos_conversation_client.create_message(
                uuid=messages[-1]["id"],
                conversation_id=conversation_id,
                user_id=user_id,
                input_message=messages[-1],
            )
        else:
            raise Exception("No bot messages found")

        # Submit request to Chat Completions for response
        response = {"success": True}
        return jsonify(response), 200

    except Exception as e:
        logger.exception("Exception in /history/update")
        return jsonify({"error": str(e)}), 500


@bp.route("/history/message_feedback", methods=["POST"])
async def update_message():
    await cosmos_history_db_ready.wait()
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    ## check request for message_id
    request_json = await request.get_json()
    message_id = request_json.get("message_id", None)
    message_feedback = request_json.get("message_feedback", None)
    try:
        if not message_id:
            return jsonify({"error": "message_id is required"}), 400

        if not message_feedback:
            return jsonify({"error": "message_feedback is required"}), 400

        ## update the message in cosmos
        updated_message = await current_app.cosmos_conversation_client.update_message_feedback(
            user_id, message_id, message_feedback
        )
        if updated_message:
            return (
                jsonify(
                    {
                        "message": f"Successfully updated message with feedback {message_feedback}",
                        "message_id": message_id,
                    }
                ),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "error": f"Unable to update message {message_id}. It either does not exist or the user does not have access to it."
                    }
                ),
                404,
            )

    except Exception as e:
        logger.exception("Exception in /history/message_feedback")
        return jsonify({"error": str(e)}), 500


@bp.route("/history/delete", methods=["DELETE"])
async def delete_conversation():
    await cosmos_history_db_ready.wait()
    ## get the user id from the request headers
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    ## check request for conversation_id
    request_json = await request.get_json()
    conversation_id = request_json.get("conversation_id", None)

    try:
        if not conversation_id:
            return jsonify({"error": "conversation_id is required"}), 400

        ## make sure cosmos is configured
        if not current_app.cosmos_conversation_client:
            raise Exception("CosmosDB is not configured or not working")

        ## delete the conversation messages from cosmos first
        deleted_messages = await current_app.cosmos_conversation_client.delete_messages(
            conversation_id, user_id
        )

        ## Now delete the conversation
        deleted_conversation = await current_app.cosmos_conversation_client.delete_conversation(
            user_id, conversation_id
        )

        return (
            jsonify(
                {
                    "message": "Successfully deleted conversation and messages",
                    "conversation_id": conversation_id,
                }
            ),
            200,
        )
    except Exception as e:
        logger.exception("Exception in /history/delete")
        return jsonify({"error": str(e)}), 500


@bp.route("/history/list", methods=["GET"])
async def list_conversations():
    await cosmos_history_db_ready.wait()
    offset = request.args.get("offset", 0)
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    ## make sure cosmos is configured
    if not current_app.cosmos_conversation_client:
        raise Exception("CosmosDB is not configured or not working")

    ## get the conversations from cosmos
    conversations = await current_app.cosmos_conversation_client.get_conversations(
        user_id, offset=offset, limit=25
    )
    if not isinstance(conversations, list):
        return jsonify({"error": f"No conversations for {user_id} were found"}), 404

    ## return the conversation ids

    return jsonify(conversations), 200


@bp.route("/history/read", methods=["POST"])
async def get_conversation():
    await cosmos_history_db_ready.wait()
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    ## check request for conversation_id
    request_json = await request.get_json()
    conversation_id = request_json.get("conversation_id", None)

    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400

    ## make sure cosmos is configured
    if not current_app.cosmos_conversation_client:
        raise Exception("CosmosDB is not configured or not working")

    ## get the conversation object and the related messages from cosmos
    conversation = await current_app.cosmos_conversation_client.get_conversation(
        user_id, conversation_id
    )
    ## return the conversation id and the messages in the bot frontend format
    if not conversation:
        return (
            jsonify(
                {
                    "error": f"Conversation {conversation_id} was not found. It either does not exist or the logged in user does not have access to it."
                }
            ),
            404,
        )

    # get the messages for the conversation from cosmos
    conversation_messages = await current_app.cosmos_conversation_client.get_messages(
        user_id, conversation_id
    )

    ## format the messages in the bot frontend format
    messages = [
        {
            "id": msg["id"],
            "role": msg["role"],
            "content": msg["content"],
            "createdAt": msg["createdAt"],
            "feedback": msg.get("feedback"),
        }
        for msg in conversation_messages
    ]

    return jsonify({"conversation_id": conversation_id, "messages": messages}), 200


@bp.route("/history/rename", methods=["POST"])
async def rename_conversation():
    await cosmos_history_db_ready.wait()
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    ## check request for conversation_id
    request_json = await request.get_json()
    conversation_id = request_json.get("conversation_id", None)

    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400

    ## make sure cosmos is configured
    if not current_app.cosmos_conversation_client:
        raise Exception("CosmosDB is not configured or not working")

    ## get the conversation from cosmos
    conversation = await current_app.cosmos_conversation_client.get_conversation(
        user_id, conversation_id
    )
    if not conversation:
        return (
            jsonify(
                {
                    "error": f"Conversation {conversation_id} was not found. It either does not exist or the logged in user does not have access to it."
                }
            ),
            404,
        )

    ## update the title
    title = request_json.get("title", None)
    if not title:
        return jsonify({"error": "title is required"}), 400
    conversation["title"] = title
    updated_conversation = await current_app.cosmos_conversation_client.upsert_conversation(
        conversation
    )

    return jsonify(updated_conversation), 200


@bp.route("/history/delete_all", methods=["DELETE"])
async def delete_all_conversations():
    await cosmos_history_db_ready.wait()
    ## get the user id from the request headers
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    # get conversations for user
    try:
        ## make sure cosmos is configured
        if not current_app.cosmos_conversation_client:
            raise Exception("CosmosDB is not configured or not working")

        conversations = await current_app.cosmos_conversation_client.get_conversations(
            user_id, offset=0, limit=None
        )
        if not conversations:
            return jsonify({"error": f"No conversations for {user_id} were found"}), 404

        # delete each conversation
        for conversation in conversations:
            ## delete the conversation messages from cosmos first
            deleted_messages = await current_app.cosmos_conversation_client.delete_messages(
                conversation["id"], user_id
            )

            ## Now delete the conversation
            deleted_conversation = await current_app.cosmos_conversation_client.delete_conversation(
                user_id, conversation["id"]
            )
        return (
            jsonify(
                {
                    "message": f"Successfully deleted conversation and messages for user {user_id}"
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception("Exception in /history/delete_all")
        return jsonify({"error": str(e)}), 500


@bp.route("/history/clear", methods=["POST"])
async def clear_messages():
    await cosmos_history_db_ready.wait()
    ## get the user id from the request headers
    authenticated_user = get_authenticated_user_details(request_headers=request.headers)
    user_id = authenticated_user["user_principal_id"]

    ## check request for conversation_id
    request_json = await request.get_json()
    conversation_id = request_json.get("conversation_id", None)

    try:
        if not conversation_id:
            return jsonify({"error": "conversation_id is required"}), 400

        ## make sure cosmos is configured
        if not current_app.cosmos_conversation_client:
            raise Exception("CosmosDB is not configured or not working")

        ## delete the conversation messages from cosmos
        deleted_messages = await current_app.cosmos_conversation_client.delete_messages(
            conversation_id, user_id
        )

        return (
            jsonify(
                {
                    "message": "Successfully deleted messages in conversation",
                    "conversation_id": conversation_id,
                }
            ),
            200,
        )
    except Exception as e:
        logger.exception("Exception in /history/clear_messages")
        return jsonify({"error": str(e)}), 500


@bp.route("/history/ensure", methods=["GET"])
async def ensure_cosmos():
    await cosmos_history_db_ready.wait()
    if not app_settings.chat_history:
        return jsonify({"error": "CosmosDB is not configured"}), 404

    try:
        success, err = await current_app.cosmos_conversation_client.ensure()
        if not current_app.cosmos_conversation_client or not success:
            if err:
                return jsonify({"error": err}), 422
            return jsonify({"error": "CosmosDB is not configured or not working"}), 500

        return jsonify({"message": "CosmosDB is configured and working"}), 200
    except Exception as e:
        logger.exception("Exception in /history/ensure")
        cosmos_exception = str(e)
        if "Invalid credentials" in cosmos_exception:
            return jsonify({"error": cosmos_exception}), 401
        elif "Invalid CosmosDB database name" in cosmos_exception:
            return (
                jsonify(
                    {
                        "error": f"{cosmos_exception} {app_settings.chat_history.database} for account {app_settings.chat_history.account}"
                    }
                ),
                422,
            )
        elif "Invalid CosmosDB container name" in cosmos_exception:
            return (
                jsonify(
                    {
                        "error": f"{cosmos_exception}: {app_settings.chat_history.conversations_container}"
                    }
                ),
                422,
            )
        else:
            return jsonify({"error": "CosmosDB is not working"}), 500

async def generate_title(conversation_messages) -> str:
    ## make sure the messages are sorted by _ts descending
    title_prompt = "Summarize the conversation so far into a 4-word or less title. Do not use any quotation marks or punctuation. Do not include any other commentary or description."

    messages = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in conversation_messages
    ]
    messages.append({"role": "user", "content": title_prompt})

    try:
        azure_openai_client = await init_openai_client()
        response = await azure_openai_client.chat.completions.create(
            model=app_settings.azure_openai.model, messages=messages, temperature=1, max_tokens=64
        )

        title = response.choices[0].message.content
        return title
    except Exception as e:
        logger.exception("Exception while generating title", e)
        return messages[-2]["content"]

@bp.route("/auth/whoami", methods=["GET"])
async def whoami():
    """Gibt Userinformationen und Rollen zurück (für das Frontend)."""
    user = get_authenticated_user_details(request.headers)
    roles = user.get("roles", []) if user else []

    admin_email_list = ["cornelius.heidrich.extern@syna.de",
                        "sebastian.hahn.extern@syna.de",
                        "torsten.terveer.extern@syna.de",
                        "christin.schulz.extern@syna.de",
                        "charlotte.goiczyk.extern@syna.de",
                        "sebastian.ostermann@syna.de",
                        "maximilian.hofmann@syna.de",
                        "sven.sorosz@suewag.de",
                        "andranik.stepanyan@suewag.de"]

    return jsonify({
        "authenticated": user is not None,
        "user_name": user.get("display_name") or user.get("user_name"),
        "email": user.get("email"),
        "roles": roles,
        "is_admin": "Admin" in roles or user.get("email") in admin_email_list,
    })

@bp.route('/.auth/me', methods=['GET'])
async def azure_auth_me():
    return await whoami()

@bp.route("/<path:path>")
async def spa(path):
    # wenn’s eine API‐Route ist, 404 werfen
    if path.startswith(("conversation","history","auth",".auth","transcribe","admin")):
        return abort(404)
    # sonst index.html ausliefern
    return await send_file(os.path.join(app.static_folder, "index.html"))

app = create_app()
