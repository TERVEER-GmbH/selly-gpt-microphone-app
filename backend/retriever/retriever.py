# retriever/retriever.py
import asyncio
import threading
import logging
from typing import Dict, Any

from backend.settings import app_settings
from backend.retriever.search import azure_search_query
from backend.retriever.builder import build_context_and_citations

logger = logging.getLogger("logger")


def _run_coro_in_new_thread(coro):
    result_box = {}
    exc_box = {}

    def runner():
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result_box["result"] = loop.run_until_complete(coro)
        except Exception as e:
            exc_box["exc"] = e
        finally:
            try:
                loop.stop()
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass

    t = threading.Thread(target=runner, name="retriever-sync-runner", daemon=True)
    t.start()
    t.join()
    if "exc" in exc_box:
        raise exc_box["exc"]
    return result_box.get("result")


async def get_context_for_query(query: str) -> Dict[str, Any]:
    """
    High-Level Retrieval (async).
    Rückgabe:
      {
        "context": "<kontext-text>",
        "citations": [ {id,title,url,filepath,score,snippet}, ... ]
      }
    """
    logger.debug("Retrieval gestartet für Query: %r", query)

    hits = await azure_search_query(query)
    if not hits:
        logger.warning("Keine Treffer für Query: %r", query)
        return {"context": "", "citations": []}

    context, citations = build_context_and_citations(
        hits,
        max_chars=getattr(app_settings.datasource, "max_context_chars", 15000),
        threshold=getattr(app_settings.datasource, "score_threshold", 0.3),
    )

    if not context:
        logger.warning("Kontext leer nach Filtering für Query: %r", query)

    return {"context": context, "citations": citations}


def get_context_for_query_sync(query: str) -> Dict[str, Any]:
    """
    Sync-Wrapper für get_context_for_query(query).
    Läuft robust innerhalb/außerhalb laufender Event-Loops.
    """
    try:
        asyncio.get_running_loop()
        loop_running = True
    except RuntimeError:
        loop_running = False

    try:
        if loop_running:
            return _run_coro_in_new_thread(get_context_for_query(query))
        else:
            return asyncio.run(get_context_for_query(query))
    except Exception:
        logger.exception("Fehler beim Sync-Retrieval für Query: %r", query)
        return {"context": "", "citations": []}
