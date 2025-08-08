import logging
import copy
from typing import Dict, Any

from openai import AsyncAzureOpenAI
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider

from backend.settings import app_settings
from backend.models.testrun import TestParams

logger = logging.getLogger(__name__)
USER_AGENT = "GitHubSampleWebApp/AsyncAzureOpenAI/1.0.0"

# Wird beim ersten Aufruf befüllt, falls du Function-Call-Tools nutzt
azure_openai_tools: list[Dict[str, Any]] = []
azure_openai_available_tools: list[str] = []


async def init_openai_client() -> AsyncAzureOpenAI:
    """
    Initialisiert einmalig den AsyncAzureOpenAI-Client
    mit Key oder Managed Identity.
    """
    # API-Version prüfen
    if (
        app_settings.azure_openai.preview_api_version
        < app_settings.azure_openai.preview_api_version
    ):
        raise RuntimeError(
            f"Unsupported API-Version {app_settings.azure_openai.preview_api_version}"
        )

    # Endpunkt bestimmen
    endpoint = (
        app_settings.azure_openai.endpoint
        or f"https://{app_settings.azure_openai.resource}.openai.azure.com"
    )

    # Authentifizierung
    ad_token_provider = None
    if not app_settings.azure_openai.key:
        cred = DefaultAzureCredential()
        ad_token_provider = get_bearer_token_provider(
            cred, "https://cognitiveservices.azure.com/.default"
        )
    api_key = app_settings.azure_openai.key

    client = AsyncAzureOpenAI(
        api_version=app_settings.azure_openai.preview_api_version,
        api_key=api_key,
        azure_ad_token_provider=ad_token_provider,
        default_headers={"x-ms-useragent": USER_AGENT},
        azure_endpoint=endpoint,
    )
    return client


def prepare_model_args(
    request_body: Dict[str, Any],
    request_headers: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Baut das Grundgerüst für den Chat-Request:
    - system message
    - DataSources aus app_settings (z.B. Cognitive Search)
    - ggf. Function-Call-Tools
    """
    messages = []

    # System Prompt
    messages.append(
        {"role": "system", "content": app_settings.azure_openai.system_message}
    )

    # User
    messages.extend(request_body.get("messages", []))

    model_args: Dict[str, Any] = {
        "model": app_settings.azure_openai.model,
        "temperature": app_settings.azure_openai.temperature,
        "max_tokens": app_settings.azure_openai.max_tokens,
        "top_p": app_settings.azure_openai.top_p,
        "stop": app_settings.azure_openai.stop_sequence,
        "stream": False,
        "messages": messages,
    }

    # Wenn DataSource konfiguriert ist, injizieren
    if app_settings.datasource:
        model_args.setdefault("extra_body", {})["data_sources"] = [
            app_settings.datasource.construct_payload_configuration(
                request=request_headers  # falls Filter nötig
            )
        ]

    # Function-Call-Tools, falls aktiviert
    if app_settings.azure_openai.function_call_azure_functions_enabled:
        model_args["tools"] = azure_openai_tools

    # Entferne Leeres
    clean = copy.deepcopy(model_args)
    clean.pop("extra_body", None)
    logger.debug("Prepared model_args: %s", clean)
    return model_args


async def call_ai_model(prompt_text: str, params: TestParams) -> str:
    """
    Feuert einen einzelnen Prompt an Azure OpenAI:
    - Holt sich Basis-Arguments via prepare_model_args()
    - Überschreibt Model/Temp/MaxTokens/TopP
    - Liefert den reinen Text der ersten Choice zurück
    """
    try:
        # 1) Minimal-Request
        request_body = {"messages": [{"role": "user", "content": prompt_text}]}

        # 2) Basis-Args inkl. Retrieval / Function-Call
        model_args = prepare_model_args(request_body, {})

        # 3) Test-Param-Override
        model_args["model"] = params.model
        model_args["temperature"] = params.temperature
        model_args["max_tokens"] = params.max_tokens
        if params.top_p is not None:
            model_args["top_p"] = params.top_p

        # 4) Client instanziieren
        client = await init_openai_client()
        if client is None:
            raise RuntimeError("Could not init Azure OpenAI client")

        # 5) Completion abrufen (nicht streaming)
        response = await client.chat.completions.create(**model_args)

        # 6) Antwort extrahieren
        return response.choices[0].message.content

    except Exception as e:
        logger.error(
            "call_ai_model: Fehler bei Prompt %r – %s",
            prompt_text,
            str(e),
            exc_info=True,
        )
        raise
