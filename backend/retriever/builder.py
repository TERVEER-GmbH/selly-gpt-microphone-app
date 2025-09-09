# retriever/builder.py
import logging
from typing import List, Dict, Tuple

logger = logging.getLogger("logger")


def build_context_and_citations(
    hits: List[Dict],
    max_chars: int,
    threshold: float
) -> Tuple[str, List[Dict]]:
    """
    Aus Search-Treffern:
    - filtere nach Score
    - schneide Kontext bei max_chars
    - erzeuge citations[] mit Metadaten
    Rückgabe: (context_text, citations_list)
    """
    if not hits:
        logger.warning("build_context_and_citations: keine Treffer übergeben")
        return "", []

    context_parts: List[str] = []
    citations: List[Dict] = []
    used = 0

    for h in hits:
        score = h.get("@search.score", 0.0) or 0.0
        if score < threshold:
            logger.debug("Dokument unter Score-Threshold %.2f → %.2f", threshold, score)
            continue

        # übliche Feldnamen probieren
        snippet = h.get("content") or h.get("text") or h.get("chunk") or ""
        if not snippet:
            logger.debug("Dokument ohne content/text/chunk übersprungen: %s", h.get("id"))
            continue

        # Metadaten (falls vorhanden)
        citation = {
            "id": h.get("id") or h.get("document_id") or "",
            "title": h.get("title") or "",
            "url": h.get("url") or "",
            "filepath": h.get("filepath") or h.get("filename") or "",
            "score": float(score),
            "snippet": snippet[:500],  # fürs Frontend eine kurze Vorschau
        }

        # Kontext-Limit
        if used + len(snippet) > max_chars:
            remaining = max_chars - used
            if remaining > 0:
                context_parts.append(snippet[:remaining].rstrip())
                used += remaining
            logger.info("Kontext abgeschnitten bei %d Zeichen", used)
            citations.append(citation)
            break

        context_parts.append(snippet.strip())
        used += len(snippet)
        citations.append(citation)

    logger.info("Kontext aufgebaut: %d Dok., %d Zeichen", len(citations), used)
    return "\n---\n".join(context_parts), citations
