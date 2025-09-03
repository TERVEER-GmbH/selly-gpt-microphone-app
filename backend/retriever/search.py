import os
import httpx
import logging
from typing import Any, Dict, List
from httpx import HTTPStatusError

from backend.settings import app_settings

logger = logging.getLogger("logger")

# Lt. aktueller MS-Doku (Data plane):
# Stable: 2024-07-01  | Preview: 2025-05-01-preview
SEARCH_API_VERSION = os.getenv("AZURE_SEARCH_API_VERSION", "2024-07-01")


def _resolve_azure_search_cfg():
    """
    Liefert die Azure Cognitive Search Datasource-Konfig aus app_settings.
    Wir erwarten, dass app_settings.datasource vom Typ _AzureSearchSettings ist,
    wenn 'AZURE_COGNITIVE_SEARCH' konfiguriert wurde.
    """
    ds = getattr(app_settings, "datasource", None)
    if not ds:
        raise RuntimeError("Keine datasource konfiguriert (app_settings.datasource ist None).")
    # Minimalprüfung auf die für uns benötigten Felder
    for attr in ("endpoint", "index", "key", "top_k", "semantic_search_config"):
        if not hasattr(ds, attr):
            # nicht fatal für key/semantic_search_config, aber endpoint/index/top_k brauchen wir
            if attr in ("endpoint", "index", "top_k"):
                raise RuntimeError(f"Datasource ist kein Azure Search-Setup (fehlendes Feld '{attr}').")
    return ds


def _resolve_search_endpoint() -> str:
    ds = _resolve_azure_search_cfg()
    return str(ds.endpoint).rstrip("/")


def _resolve_index_name() -> str:
    ds = _resolve_azure_search_cfg()
    return ds.index


def _resolve_search_key() -> str | None:
    ds = _resolve_azure_search_cfg()
    # Fallback aus ENV, falls in Settings kein Key steht (z. B. Managed Identity in Zukunft)
    return getattr(ds, "key", None) or os.getenv("AZURE_SEARCH_KEY")


def _resolve_top_k(default: int = 5) -> int:
    ds = _resolve_azure_search_cfg()
    try:
        return int(getattr(ds, "top_k", default) or default)
    except Exception:
        return default


def _resolve_semantic_config() -> str | None:
    ds = _resolve_azure_search_cfg()
    val = getattr(ds, "semantic_search_config", None)
    return val or None


async def azure_search_query(query: str) -> List[Dict[str, Any]]:
    """
    Führt eine einfache Volltextsuche über Azure AI Search aus (POST /docs/search).
    Nutzt die Stable-API-Version 2024-07-01 (oder aus ENV AZURE_SEARCH_API_VERSION).
    """
    endpoint = _resolve_search_endpoint()
    index = _resolve_index_name()
    api_key = _resolve_search_key()
    top_k = _resolve_top_k()
    semantic_config = _resolve_semantic_config()

    # Offizielles Pfadformat gemäß Doku (mit Klammern/Quotes ist okay; ohne geht meist auch)
    url = (
        f"{endpoint}/indexes('{index}')/docs/search"
        f"?api-version={SEARCH_API_VERSION}"
    )

    body: Dict[str, Any] = {
        "search": query,
        "queryType": "simple",
        "top": top_k,
        "searchMode": "any",
    }
    # semanticConfiguration nur setzen, wenn vorhanden
    if semantic_config:
        body["semanticConfiguration"] = semantic_config

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["api-key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            try:
                resp.raise_for_status()
            except HTTPStatusError as he:
                logger.error(
                    "AzureSearch HTTP %s: %s | body=%s",
                    he.response.status_code, url, he.response.text
                )
                return []
            data = resp.json()
            hits = data.get("value", [])
            logger.info("AzureSearch: %d Treffer für Query=%r (top=%s, api-version=%s)",
                        len(hits), query, top_k, SEARCH_API_VERSION)
            return hits
    except Exception:
        logger.exception("AzureSearch Anfrage fehlgeschlagen")
        return []
