# retriever/search.py
import os
import logging
from typing import Any, Dict, List, Optional

import httpx
from httpx import HTTPStatusError

from backend.settings import app_settings

logger = logging.getLogger("logger")

# Aktuelle Data-Plane API für /indexes/*/docs/search
SEARCH_API_VERSION = "2024-07-01"

# Optionales Feature-Flag:
# true  -> versuche serverseitige Vektorisierung (kind="text"), erfordert Vectorizer im Index
# false -> clientseitige Embeddings (kind="vector"), benötigt AOAI-Embedding-Deployment
USE_SERVER_VECTORIZER = os.getenv("AZURE_SEARCH_USE_SERVER_VECTORIZER", "false").lower() == "true"


# ---------------------- Konfig-Helpers ---------------------- #
def _get_azure_search_cfg():
    """
    Liefert das Azure-Search-Configobjekt aus app_settings.datasource,
    FALLS der Datasource-Typ AzureCognitiveSearch ist. Sonst None.
    Erwartete Felder: endpoint, index, key, top_k, query_type, vector_columns.
    """
    ds = getattr(app_settings, "datasource", None)
    if ds and hasattr(ds, "endpoint") and hasattr(ds, "index"):
        return ds
    return None


def _resolve_search_endpoint() -> str:
    ds = _get_azure_search_cfg()
    if ds and getattr(ds, "endpoint", None):
        return ds.endpoint.rstrip("/")

    env_ep = os.getenv("AZURE_SEARCH_ENDPOINT")
    if env_ep:
        return env_ep.rstrip("/")

    raise RuntimeError("Azure Search endpoint ist nicht konfiguriert (datasource.endpoint oder AZURE_SEARCH_ENDPOINT).")


def _resolve_index_name() -> str:
    ds = _get_azure_search_cfg()
    if ds and getattr(ds, "index", None):
        return ds.index

    env_idx = os.getenv("AZURE_SEARCH_INDEX")
    if env_idx:
        return env_idx

    raise RuntimeError("Azure Search Index ist nicht konfiguriert (datasource.index oder AZURE_SEARCH_INDEX).")


def _resolve_search_key() -> Optional[str]:
    ds = _get_azure_search_cfg()
    return (getattr(ds, "key", None) if ds else None) or os.getenv("AZURE_SEARCH_KEY")


def _vector_fields_csv() -> Optional[str]:
    """
    Liefert kommaseparierte Liste der Vektor-Felder.
    Quelle: settings.datasource.vector_columns oder ENV AZURE_SEARCH_VECTOR_COLUMNS
    """
    ds = _get_azure_search_cfg()
    vec_cols = None
    if ds and getattr(ds, "vector_columns", None):
        if isinstance(ds.vector_columns, list):
            vec_cols = ",".join(ds.vector_columns)
        elif isinstance(ds.vector_columns, str):
            vec_cols = ds.vector_columns

    if not vec_cols:
        env_vec = os.getenv("AZURE_SEARCH_VECTOR_COLUMNS")
        if env_vec:
            vec_cols = env_vec

    if vec_cols:
        vec_cols = ",".join([c.strip() for c in vec_cols.split(",") if c.strip()])

    return vec_cols or None


def _normalized_query_type() -> str:
    """
    Normalisiert den query_type aus Settings/ENV:
    - 'vector_simple_hybrid' (oder Alias)
    - 'vector'
    - 'simple' (Default)
    Alles mit 'semantic' wird bewusst auf 'vector_simple_hybrid' bzw. 'simple' herabgestuft.
    """
    ds = _get_azure_search_cfg()
    qtype = (getattr(ds, "query_type", "simple") or "simple")
    q = str(qtype).strip().lower().replace("-", "_")
    if q in ("vectorsimplehybrid", "vector_simple_hybrid"):
        return "vector_simple_hybrid"
    if q == "vector":
        return "vector"
    if "semantic" in q:
        return "vector_simple_hybrid"
    return "simple"


# ---------------------- Embeddings (clientseitig) ---------------------- #
async def _embed_query(query: str) -> Optional[List[float]]:
    """
    Holt Embeddings über Azure OpenAI.
    Unterstützt zwei Wege:
      1) embedding_name (Deployment-Name auf demselben AOAI-Ressourcen-Endpunkt wie Chat)
      2) embedding_endpoint + embedding_key (separates/externes Endpoint)
    Gibt Liste von Floats zurück oder None bei Fehler.
    """
    if not query or not query.strip():
        return None

    emb_name = getattr(app_settings.azure_openai, "embedding_name", None)
    emb_endpoint = getattr(app_settings.azure_openai, "embedding_endpoint", None)
    emb_key = getattr(app_settings.azure_openai, "embedding_key", None)

    try:
        # Variante 1: gleiches AOAI-Endpoint + Deployment-Name
        if emb_name and app_settings.azure_openai.endpoint:
            from openai import AsyncAzureOpenAI
            client = AsyncAzureOpenAI(
                api_version=app_settings.azure_openai.preview_api_version,
                api_key=app_settings.azure_openai.key,
                azure_endpoint=app_settings.azure_openai.endpoint,
            )
            resp = await client.embeddings.create(model=emb_name, input=query)
            vec = resp.data[0].embedding if resp and resp.data else None
            return vec

        # Variante 2: separates Endpoint + Key
        if emb_endpoint and emb_key:
            from openai import AsyncAzureOpenAI
            client = AsyncAzureOpenAI(
                api_version=app_settings.azure_openai.preview_api_version,
                api_key=emb_key,
                azure_endpoint=emb_endpoint,
            )
            model = emb_name if emb_name else "embedding"  # falls Name extern anders lautet
            resp = await client.embeddings.create(model=model, input=query)
            vec = resp.data[0].embedding if resp and resp.data else None
            return vec

        logger.warning("Kein Embedding-Deployment konfiguriert (embedding_name oder embedding_endpoint+embedding_key fehlen).")
        return None

    except Exception:
        logger.exception("Embedding-Aufruf fehlgeschlagen")
        return None


# ---------------------- Body-Builder ---------------------- #
async def _build_request_body(query: str) -> Dict[str, Any]:
    """
    Baut den Request-Body für POST /docs/search (API 2024-07-01).
    - simple
    - vector (nur Vektor, clientseitig)
    - vector_simple_hybrid (Text + Vektor, clientseitig)
    Niemals 'semanticConfiguration' setzen.
    """
    ds = _get_azure_search_cfg()
    top_k = getattr(ds, "top_k", 5) or 5
    qtype = _normalized_query_type()
    vec_fields = _vector_fields_csv()

    body: Dict[str, Any] = {
        "top": top_k,
        "searchMode": "any",
    }

    # Default-Textsuche immer zulässig
    def add_text_search():
        body["queryType"] = "simple"
        body["search"] = query or "*"

    # Vector-Teil hinzufügen – serverseitig (kind="text") ODER clientseitig (kind="vector")
    async def add_vector_part():
        if not vec_fields:
            return False

        # 1) Serverseitig (erfordert Vectorizer im Index)
        if USE_SERVER_VECTORIZER:
            body["vectorQueries"] = [{
                "kind": "text",
                "text": query or "",
                "fields": vec_fields,
                "k": top_k
            }]
            return True

        # 2) Clientseitig: Embedding erzeugen
        vec = await _embed_query(query or "")
        if vec and isinstance(vec, list):
            body["vectorQueries"] = [{
                "kind": "vector",
                "vector": vec,
                "fields": vec_fields,
                "k": top_k
            }]
            return True

        logger.warning("VectorQueries konnten nicht erzeugt werden (kein Vectorizer & Embedding fehlgeschlagen) – fallback auf Textsuche.")
        return False

    # Aufbau nach Query-Type
    if qtype == "simple":
        add_text_search()

    elif qtype == "vector":
        added = await add_vector_part()
        if not added:
            # Fallback auf simple
            add_text_search()

    elif qtype == "vector_simple_hybrid":
        add_text_search()             # Basis-Text
        await add_vector_part()       # versucht optional Vector hinzuzufügen (wenn möglich)

    else:
        # Sicherheitsfallback
        add_text_search()

    return body


# ---------------------- Hauptfunktion ---------------------- #
async def azure_search_query(query: str) -> List[Dict[str, Any]]:
    """
    Suche gegen Azure AI Search (API 2024-07-01).
    - respektiert query_type (simple/vector/vector_simple_hybrid)
    - setzt NIE semanticConfiguration
    - nutzt Vector-Queries server- oder clientseitig (je nach Konfiguration)
    - robuster Fallback auf simple
    Gibt die rohen Dokumente aus 'value' zurück (List[dict]).
    """
    endpoint = _resolve_search_endpoint()
    index = _resolve_index_name()
    api_key = _resolve_search_key()

    url = f"{endpoint}/indexes/{index}/docs/search?api-version={SEARCH_API_VERSION}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["api-key"] = api_key

    body = await _build_request_body(query)

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("value", [])
            logger.info(
                "AzureSearch: %d Treffer | qtype=%s | vector=%s(server=%s) | query=%r",
                len(hits),
                _normalized_query_type(),
                "yes" if "vectorQueries" in body else "no",
                "true" if USE_SERVER_VECTORIZER else "false",
                query
            )
            return hits

    except HTTPStatusError as he:
        # 400 bei fehlendem Vectorizer -> Fallback-Strategie loggen
        try:
            text = he.response.text
        except Exception:
            text = "<no body>"
        logger.error("AzureSearch HTTP %s: %s | body=%s", he.response.status_code, url, text)

    except Exception:
        logger.exception("AzureSearch Anfrage fehlgeschlagen")

    return []
