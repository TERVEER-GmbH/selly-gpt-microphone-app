# backend/services/comparator.py
import json
import logging
import re

from backend.models.testrun import ComparisonResult
from backend.models.testrun import TestParams
from backend.services.ai_client import call_ai_model

logger = logging.getLogger('logger')

# System-Prompt für die automatische Bewertung
_COMPARATOR_SYSTEM_PROMPT = """
You are an expert evaluator. Compare the AI answer against the golden (correct) answer.
For each of the following five categories, assign a score between 0.0 and 1.0 (higher is better),
and provide a brief comment explaining your assessment.

Categories:
1) relevance
2) factual_accuracy
3) completeness
4) tone
5) comprehensibility

Return your output as a single JSON object with the keys:
- relevance (float)
- relevance_comment (string)
- factual_accuracy (float)
- factual_accuracy_comment (string)
- completeness (float)
- completeness_comment (string)
- tone (float)
- tone_comment (string)
- comprehensibility (float)
- comprehensibility_comment (string)
- overall_comment (string), optional summary

Ensure the JSON is valid and nothing else is output.
"""

async def compare_answers(ai_answer: str, golden_answer: str, params: TestParams) -> ComparisonResult:
    # 1) Prompt bauen
    payload = json.dumps({
        "ai_answer": ai_answer,
        "golden_answer": golden_answer
    })
    prompt = _COMPARATOR_SYSTEM_PROMPT + "\n\n" + payload

    # 2) AI-Call
    try:
        raw = await call_ai_model(prompt, params)
    except Exception as e:
        logger.error("compare_answers: AI-Call failed: %s", e, exc_info=True)
        raise

    # 3) Roh-Antwort säubern
    text = raw.strip()
    # Falls Markdown-Code-Fence vorhanden, alles dazwischen extrahieren
    # z.B. ```json { ... } ``` oder ```{ ... }```
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        # Falls keine Fence, versuchen wir, das erste JSON-Objekt herauszupfen
        m2 = re.search(r"(\{.*\})", text, re.S)
        if m2:
            text = m2.group(1)
        # sonst belassen wir text wie es ist

    # 4) JSON parsen
    try:
        data = json.loads(text)
    except Exception as e:
        logger.error(
            "compare_answers: Failed to parse JSON from AI response: %r\nCleaned text: %r\nError: %s",
            raw, text, e
        )
        raise

    # 5) ComparisonResult bauen
    return ComparisonResult.from_dict(data)
