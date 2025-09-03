import logging
from typing import List, Dict

logger = logging.getLogger("logger")


def build_context(hits: List[Dict], max_chars: int, threshold: float) -> str:
    """
    Baut einen Kontextstring aus Search-Treffern.
    - Filtert nach Score
    - schneidet nach max_chars ab
    """
    if not hits:
        logger.warning("build_context: keine Treffer übergeben")
        return ""

    context_parts = []
    used = 0
    kept = 0

    for h in hits:
        score = h.get("@search.score", 0)
        if score < threshold:
            logger.debug("Dokument unter Score-Threshold %.2f → %.2f", threshold, score)
            continue

        snippet = h.get("content") or h.get("text") or ""
        if not snippet:
            logger.debug("Dokument ohne content/text übersprungen: %s", h.get("id"))
            continue

        if used + len(snippet) > max_chars:
            logger.info("Kontext abgeschnitten bei %d Zeichen", used)
            break

        context_parts.append(snippet.strip())
        used += len(snippet)
        kept += 1

    logger.info("Kontext aufgebaut: %d Dokumente, %d Zeichen", kept, used)
    return "\n---\n".join(context_parts)
