import os
import asyncio
import threading
import logging
from backend.settings import app_settings
from backend.retriever.search import azure_search_query
from backend.retriever.builder import build_context

logger = logging.getLogger("logger")

def _resolve_limits():
    """
    Liefert (max_context_chars, score_threshold).
    Quelle: AzureSearch-Datasource falls vorhanden, sonst ENV, sonst Defaults.
    """
    ds = getattr(app_settings, "datasource", None)
    max_chars = getattr(ds, "max_context_chars", None)
    threshold = getattr(ds, "score_threshold", None)

    if max_chars is None:
        max_chars = int(os.getenv("OWN_RETRIEVAL_MAX_CONTEXT_CHARS", "15000"))
    if threshold is None:
        try:
            threshold = float(os.getenv("OWN_RETRIEVAL_SCORE_THRESHOLD", "0.3"))
        except ValueError:
            threshold = 0.3

    return max_chars, threshold

def _run_coro_in_new_thread(coro):
    """
    Führt eine Coroutine in einem eigenen Event-Loop auf einem separaten Thread aus
    und gibt das Ergebnis synchron zurück.
    """
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


async def get_context_for_query(query: str) -> str:
    logger.debug("Retrieval gestartet für Query: %r", query)

    hits = await azure_search_query(query)
    if not hits:
        logger.warning("Keine Treffer für Query: %r", query)
        return ""

    max_chars, threshold = _resolve_limits()
    context = build_context(hits, max_chars=max_chars, threshold=threshold)

    if not context:
        logger.warning("Kontext leer nach Filtering für Query: %r", query)

    return context


def get_context_for_query_sync(query: str) -> str:
    """
    Sync-Wrapper für get_context_for_query(query).
    Läuft robust sowohl innerhalb als auch außerhalb eines bereits laufenden Async-Event-Loops.
    """
    try:
        # Wenn dies KEINEN laufenden Loop wirft, ist keiner aktiv -> wir dürfen asyncio.run() nutzen
        asyncio.get_running_loop()
        loop_running = True
    except RuntimeError:
        loop_running = False

    try:
        if loop_running:
            # Wir sind z. B. in Quart/ASGI drin -> neuen Loop auf separatem Thread verwenden
            return _run_coro_in_new_thread(get_context_for_query(query))
        else:
            # Kein Loop aktiv -> ganz normal synchron ausführen
            return asyncio.run(get_context_for_query(query))
    except Exception:
        logger.exception("Fehler beim Sync-Retrieval für Query: %r", query)
        return ""
