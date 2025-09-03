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
        logger.exceptionf("Speech recognition failed. Error: {e}")
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

def prepare_model_args(request_body, request_headers):
    request_messages = request_body.get("messages", [])

    # Immer einen Basis-Systemprompt setzen:
    # 1) falls vorhanden: Search.role_information (ENV: AZURE_OPENAI_SYSTEM_MESSAGE)
    # 2) sonst: AzureOpenAI.system_message
    base_system_prompt = getattr(app_settings.search, "role_information", None) \
                         or app_settings.azure_openai.system_message

    messages = [{
        "role": "system",
        "content": base_system_prompt
    }]

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
                try:
                    helper["context"] = json.loads(message["context"])
                except Exception:
                    logger.warning("prepare_model_args: invalid JSON in message.context")
            messages.append(helper)

    # Microsoft Defender: User Security Context
    user_security_context = None
    if os.getenv("MS_DEFENDER_ENABLED", "true").lower() == "true":
        try:
            authenticated_user = get_authenticated_user_details(request_headers)
            user_security_context = get_msdefender_user_json(
                authenticated_user, request_headers, app_settings.ui.title
            )
        except Exception:
            logger.exception("prepare_model_args: building user_security_context failed")

    # Basis-Parameter für Chat Completion
    model_args = {
        "messages": messages,
        "temperature": app_settings.azure_openai.temperature,
        "max_tokens": app_settings.azure_openai.max_tokens,
        "top_p": app_settings.azure_openai.top_p,
        "stop": app_settings.azure_openai.stop_sequence,
        "stream": app_settings.azure_openai.stream,
        "model": app_settings.azure_openai.model
    }

    # Nur wenn die letzte Message vom User ist, machen Retrieval/Tools Sinn
    if messages and messages[-1]["role"] == "user":
        # Tools (remote function calling) aktivieren, falls konfiguriert
        if app_settings.azure_openai.function_call_azure_functions_enabled and len(azure_openai_tools) > 0:
            model_args["tools"] = azure_openai_tools

        # Umschalter: eigener Retriever vs. OYD data_sources
        try:
            if app_settings.base_settings.openai_own_retrieval_enabled:
                logger.info("Retrieval-Mode = OWN (OPENAI_OWN_RETRIEVAL_ENABLED=True)")

                user_query = messages[-1]["content"]
                context = None
                try:
                    context = get_context_for_query_sync(user_query)
                except Exception:
                    logger.exception("Own retrieval failed; proceeding without extra context")

                if context and context.strip():
                    # Immer direkt NACH dem Basis-Systemprompt injizieren
                    insertion_index = 1
                    messages.insert(insertion_index, {
                        "role": "system",
                        "content": f"Kontext:\n{context}"
                    })
                    model_args["messages"] = messages
                    logger.debug("Own retrieval context injected (chars=%d)", len(context))
                else:
                    logger.warning("Own retrieval returned no context")
            else:
                logger.info("Retrieval-Mode = OYD (data_sources aktiv)")
                if app_settings.datasource:
                    model_args["extra_body"] = {
                        "data_sources": [
                            app_settings.datasource.construct_payload_configuration(
                                request=request
                            )
                        ]
                    }
        except Exception:
            logger.exception("prepare_model_args: retrieval switching failed")

    # Defender-Kontext unter extra_body anhängen
    if user_security_context:
        try:
            model_args.setdefault("extra_body", {})
            model_args["extra_body"]["user_security_context"] = user_security_context.to_dict()
        except Exception:
            logger.exception("prepare_model_args: attaching user_security_context failed")

    # Maskiertes Logging (Keys/Secrets)
    try:
        model_args_clean = copy.deepcopy(model_args)
        if model_args_clean.get("extra_body"):
            for ds in model_args_clean["extra_body"].get("data_sources", []):
                params = ds.get("parameters", {})
                for k in ("key", "connection_string", "embedding_key", "encoded_api_key", "api_key"):
                    if k in params:
                        params[k] = "*****"
                auth = params.get("authentication", {})
                for k in list(auth.keys()):
                    if k in ("key", "connection_string", "embedding_key", "encoded_api_key", "api_key"):
                        auth[k] = "*****"
                emb = params.get("embedding_dependency", {})
                if isinstance(emb, dict) and "authentication" in emb:
                    for k in list(emb["authentication"].keys()):
                        if k in ("key", "connection_string", "embedding_key", "encoded_api_key", "api_key"):
                            emb["authentication"][k] = "*****"
        logger.debug("REQUEST BODY (sanitized): %s", json.dumps(model_args_clean, indent=4))
    except Exception:
        logger.exception("prepare_model_args: safe logging failed")

    return model_args



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
    filtered_messages = []
    messages = request_body.get("messages", [])
    for message in messages:
        if message.get("role") != 'tool':
            filtered_messages.append(message)

    request_body['messages'] = filtered_messages
    model_args = prepare_model_args(request_body, request_headers)

    try:
        azure_openai_client = await init_openai_client()
        raw_response = await azure_openai_client.chat.completions.with_raw_response.create(**model_args)
        response = raw_response.parse()
        apim_request_id = raw_response.headers.get("apim-request-id")
    except Exception as e:
        logger.exception("Exception in send_chat_request")
        raise e

    return response, apim_request_id


async def complete_chat_request(request_body, request_headers):
    """
    Schickt die Anfrage an AOAI/Promptflow, verarbeitet ggf. Function Calls
    und erzeugt IMMER ein gültiges non_streaming_response-Objekt.
    """
    # 1) Promptflow-Short-Circuit
    if app_settings.base_settings.use_promptflow:
        response = await promptflow_request(request_body)
        history_metadata = request_body.get("history_metadata", {})
        return format_pf_non_streaming_response(
            response,
            history_metadata,
            app_settings.promptflow.response_field_name,
            app_settings.promptflow.citations_field_name
        )

    # 2) AOAI-Flow
    non_streaming_response = None
    apim_request_id = None

    response, apim_request_id = await send_chat_request(request_body, request_headers)

    # Diagnose-Logging (sicher, ohne Secrets)
    try:
        mode = "OWN" if app_settings.base_settings.openai_own_retrieval_enabled else "OYD"
        has_ds = bool(app_settings.datasource)

        num_choices = 0
        first_msg_preview = ""
        try:
            if hasattr(response, "choices") and response.choices:
                num_choices = len(response.choices)
                first = getattr(response.choices[0], "message", None)
                if first and getattr(first, "content", None):
                    first_msg_preview = str(first.content)[:200].replace("\n", " ")
        except Exception:
            pass

        usage_info = None
        try:
            usage = getattr(response, "usage", None)
            if usage is not None:
                usage_info = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
        except Exception:
            pass

        logger.info(
            "AOAI response | mode=%s | has_ds=%s | apim_request_id=%s | choices=%s | usage=%s | preview=%r",
            mode, has_ds, apim_request_id, num_choices, usage_info, first_msg_preview
        )
    except Exception as e:
        logger.exception("Post-send logging failed: %s", e)

    # 3) (Optionale) Citations debuggen – niemals die Hauptantwort blockieren
    try:
        raw = response.model_dump() if hasattr(response, "model_dump") else response
        logger.debug("RAW OYD RESPONSE (truncated to 4000 chars): %s", str(raw)[:4000])

        if hasattr(response, "choices") and response.choices:
            msg = response.choices[0].message
            ctx = getattr(msg, "context", None) if hasattr(msg, "context") else None
            if ctx:
                citations = ctx.get("citations") or ctx.get("documents")
                if citations:
                    for i, c in enumerate(citations):
                        text = c.get("content") or c.get("text") or ""
                        src  = c.get("title") or c.get("filepath") or c.get("id") or "unknown"
                        logger.debug("CITATION #%d src=%s len=%d preview=%r", i, src, len(text), text[:300])
    except Exception as e:
        logger.warning("Failed to debug citations: %s", e)

    # 4) Normale Nicht-Streaming-Antwort bauen (robust)
    try:
        history_metadata = request_body.get("history_metadata", {})
        non_streaming_response = format_non_streaming_response(
            response, history_metadata, apim_request_id
        )
    except Exception as e:
        logger.exception("format_non_streaming_response failed — falling back: %s", e)
        # Fallback: minimaler Response-Body aus dem SDK-Objekt
        try:
            content = ""
            if hasattr(response, "choices") and response.choices:
                first = getattr(response.choices[0], "message", None)
                if first and getattr(first, "content", None):
                    content = str(first.content)
            non_streaming_response = {
                "id": request_body.get("messages", [{}])[-1].get("id") or str(uuid.uuid4()),
                "choices": [{
                    "messages": [{"role": "assistant", "content": content}],
                }],
                "apim_request_id": apim_request_id
            }
        except Exception:
            # letzter Schutz – niemals ohne Response rausgehen
            non_streaming_response = {
                "id": str(uuid.uuid4()),
                "choices": [{
                    "messages": [{"role": "assistant", "content": ""}],
                }],
                "apim_request_id": apim_request_id
            }

    # 5) Function Calling: falls aktiv, zweiter Turn und erneut formatieren
    if app_settings.azure_openai.function_call_azure_functions_enabled:
        try:
            function_response = await process_function_call(response)
            if function_response:
                request_body["messages"].extend(function_response)
                response2, apim_request_id2 = await send_chat_request(request_body, request_headers)
                history_metadata = request_body.get("history_metadata", {})
                try:
                    non_streaming_response = format_non_streaming_response(
                        response2, history_metadata, apim_request_id2
                    )
                except Exception as e:
                    logger.exception("format_non_streaming_response (function pass) failed — keeping prior: %s", e)
        except Exception as e:
            logger.exception("Function call processing failed — continuing with first answer: %s", e)

    return non_streaming_response


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
    response, apim_request_id = await send_chat_request(request_body, request_headers)
    history_metadata = request_body.get("history_metadata", {})

    async def generate(apim_request_id, history_metadata):
        if app_settings.azure_openai.function_call_azure_functions_enabled:
            # Maintain state during function call streaming
            function_call_stream_state = AzureOpenaiFunctionCallStreamState()

            async for completionChunk in response:
                stream_state = await process_function_call_stream(completionChunk, function_call_stream_state, request_body, request_headers, history_metadata, apim_request_id)

                # No function call, asistant response
                if stream_state == "INITIAL":
                    yield format_stream_response(completionChunk, history_metadata, apim_request_id)

                # Function call stream completed, functions were executed.
                # Append function calls and results to history and send to OpenAI, to stream the final answer.
                if stream_state == "COMPLETED":
                    request_body["messages"].extend(function_call_stream_state.function_messages)
                    function_response, apim_request_id = await send_chat_request(request_body, request_headers)
                    async for functionCompletionChunk in function_response:
                        yield format_stream_response(functionCompletionChunk, history_metadata, apim_request_id)

        else:
            async for completionChunk in response:
                yield format_stream_response(completionChunk, history_metadata, apim_request_id)

    return generate(apim_request_id=apim_request_id, history_metadata=history_metadata)


async def conversation_internal(request_body, request_headers):
    try:
        if app_settings.azure_openai.stream and not app_settings.base_settings.use_promptflow:
            result = await stream_chat_request(request_body, request_headers)
            response = await make_response(format_as_ndjson(result))
            response.timeout = None
            response.mimetype = "application/json-lines"
            return response
        else:
            result = await complete_chat_request(request_body, request_headers)
            return jsonify(result)

    except Exception as ex:
        logger.exception(ex)
        if hasattr(ex, "status_code"):
            return jsonify({"error": str(ex)}), ex.status_code
        else:
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
                        "maximilian.hofmann@syna.de"
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
