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
You are an expert evaluator. Compare ONLY the provided "prompt" and "golden_answer" with the provided "ai_answer". Do not use external knowledge or hidden context. Your task is to score five categories on a 1–5 scale and write brief German comments. Output MUST be exactly one JSON object, no code fences, no prose, no additional keys.

CATEGORIES & CRITERIA (apply strictly):

A) Relevance ("relevance", "relevance_comment")
- Antwort bezieht sich klar auf die gestellte Frage (kein Abschweifen).
- Nutzt nur relevante Informationen, spiegelt die Intention korrekt wider.
- Vermeidet unnötige Details, die nicht zur Frage beitragen.

B) Factual Accuracy ("factual_accuracy", "factual_accuracy_comment")
- Alle Aussagen sind durch die GOLDEN-Answer belegbar.
- Keine Halluzinationen oder Widersprüche.
- Keine Vermischung mit externem, nicht abgesichertem Wissen.
- Bei Unsicherheit: korrekt angeben, dass keine Information vorliegt.

C) Completeness ("completeness", "completeness_comment")
- Deckt alle relevanten Aspekte der Frage ab.
- Lässt keine wichtigen Punkte aus.
- Mehrschritt-/Bedingungsfälle werden vollständig genannt.
- Ergänzungen nur, wenn kontextrelevant.

D) Tone ("tone", "tone_comment")
- Sprache sachlich/professionell/freundlich je nach Kontext.
- Kein unangemessener Ton (belehrend, sarkastisch, abwertend).
- Konsistent mit einem professionellen Unternehmensstil.
- Passt zur Situation des Nutzers (z. B. empathisch bei Support).

E) Comprehensibility ("comprehensibility", "comprehensibility_comment")
- Klare, logisch strukturierte Antwort.
- Prägnant, ohne unnötige Komplexität.
- Keine ungeklärten Fachbegriffe (sofern Zielgruppe das nicht erwartet).
- Ton zum Use Case passend.

SCORING (for all five categories):
- 5 = Vorbildlich: voll erfüllt, keine nennenswerten Mängel.
- 4 = Gut: weitgehend erfüllt, kleine Mängel ohne Relevanz für das Ergebnis.
- 3 = Teils/teils: solide, aber merkliche Lücken/Schwächen.
- 2 = Schwach: deutliche Mängel, Ergebnis nur bedingt brauchbar.
- 1 = Unzureichend: falsch, irreführend, oder am Bedarf vorbei.

COMMENT RULES:
- Alle *_comment Felder auf DEUTSCH.
- Maximal 1–2 kurze Sätze pro Kommentar.
- Keine Wiederholung der kompletten Antworten, nur Bewertung/Begründung.
- "overall_comment" fasst die wichtigsten Abweichungen/prioritären Verbesserungen zusammen (ebenfalls DEUTSCH, 1–2 Sätze).

OUTPUT FORMAT (JSON ONLY, numbers 1–5 as integers):
{
  "relevance": 1|2|3|4|5,
  "relevance_comment": "…",
  "factual_accuracy": 1|2|3|4|5,
  "factual_accuracy_comment": "…",
  "completeness": 1|2|3|4|5,
  "completeness_comment": "…",
  "tone": 1|2|3|4|5,
  "tone_comment": "…",
  "comprehensibility": 1|2|3|4|5,
  "comprehensibility_comment": "…",
  "overall_comment": "…"
}

IMPORTANT:
- Base your judgement ONLY on the three inputs: prompt, ai_answer and golden_answer.
- If ai_answer matches golden_answer in Inhalt, aber ist nur anders formuliert → hohe Werte (meist 4–5).
- If ai_answer introduces unverifizierbare Inhalte → factual_accuracy abwerten.
- If ai_answer lässt wesentliche Punkte der golden_answer aus → completeness abwerten.
- Return exactly one valid JSON object. No markdown, no backticks, no extra text.
"""

async def compare_answers(orig_prompt:str, ai_answer: str, golden_answer: str, params: TestParams) -> ComparisonResult:
    payload = json.dumps({
        "prompt": orig_prompt,
        "ai_answer": ai_answer,
        "golden_answer": golden_answer
    })
    prompt = _COMPARATOR_SYSTEM_PROMPT + "\n\n" + payload

    try:
        raw = await call_ai_model(prompt, params)
    except Exception as e:
        logger.error("compare_answers: AI-Call failed: %s", e, exc_info=True)
        raise

    text = raw.strip()
    # Optionales Safeguard falls doch mal Fences kommen:
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        m2 = re.search(r"(\{.*\})", text, re.S)
        if m2:
            text = m2.group(1)

    try:
        data = json.loads(text)
    except Exception as e:
        logger.error("compare_answers: Failed to parse JSON from AI response: %r\nCleaned text: %r\nError: %s", raw, text, e)
        raise

    return ComparisonResult.from_dict(data)
