# backend/services/run_comparer.py
import hashlib
import logging
from typing import Any, Dict, List, Optional
from quart import current_app

logger = logging.getLogger("logger")


def _prompt_key(prompt_id: Optional[str], prompt_text: str) -> str:
    if prompt_id:
        return f"id:{prompt_id}"
    h = hashlib.sha1((prompt_text or "").encode("utf-8")).hexdigest()
    return f"sha1:{h}"


def _subscore(s: Dict[str, float]) -> float:
    return (
        (s.get("relevance", 0) +
         s.get("factual_accuracy", 0) +
         s.get("completeness", 0) +
         s.get("tone", 0) +
         s.get("comprehensibility", 0)) / 5.0
    )


def _product_raw(s: Dict[str, float]) -> float:
    # PQS = Rohprodukt der 5 Kategorien
    return (
        (s.get("relevance", 0) or 0) *
        (s.get("factual_accuracy", 0) or 0) *
        (s.get("completeness", 0) or 0) *
        (s.get("tone", 0) or 0) *
        (s.get("comprehensibility", 0) or 0)
    )


def _product_norm(prod: float) -> float:
    # fünfte Wurzel (Skala 1–5); bei 0 -> 0
    return (prod ** (1.0 / 5.0)) if prod > 0 else 0.0


def _side_payload(r) -> Dict[str, Any]:
    s = {
        "relevance":         float(getattr(r, "relevance", 0) or 0),
        "factual_accuracy":  float(getattr(r, "factual_accuracy", 0) or 0),
        "completeness":      float(getattr(r, "completeness", 0) or 0),
        "tone":              float(getattr(r, "tone", 0) or 0),
        "comprehensibility": float(getattr(r, "comprehensibility", 0) or 0),
    }
    prod = _product_raw(s)
    return {
        "prompt_id":     getattr(r, "prompt_id", None),
        "prompt_text":   getattr(r, "prompt_text", ""),
        "ai_response":   getattr(r, "ai_response", ""),
        "golden_answer": getattr(r, "golden_answer", ""),
        "scores": s,
        "subscore": _subscore(s),
        "product_score_raw":  prod,               # PQS
        "product_score_norm": _product_norm(prod)
    }


async def _get_run_name(client, run_id: str) -> str:
    """
    Liest den Run-Namen aus dem testruns-Container. Fallback: verkürzte ID.
    (Lazy-Backfill findet in admin_client statt; hier nur Read.)
    """
    try:
        doc = await client.run_container.read_item(item=run_id, partition_key=run_id)
        name = (doc or {}).get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    except Exception as e:
        logger.warning("compare_runs: could not read run %s for name: %s", run_id, e)
    return run_id[:8]


async def compare_runs(left_run_id: str, right_run_id: str) -> Dict[str, Any]:
    """
    Vergleicht zwei Runs:
      - Union aller Prompts (gematched per prompt_id, Fallback sha1(prompt_text))
      - Pairs enthalten: left/right-Seite mit Scores, Subscore, PQS (product_score_raw) & normiertem Produkt
      - Summary enthält pro Seite:
          count, avg_subscore, product_score_avg (PQS Ø), product_score_norm_avg
        sowie coverage und deltas (avg_subscore & product_score_norm_avg & product_score_avg)
    """
    client = current_app.cosmos_admin_client

    # Ergebnisse laden
    left_results  = await client.list_results(left_run_id)
    right_results = await client.list_results(right_run_id)

    left_map: Dict[str, Any] = {}
    right_map: Dict[str, Any] = {}

    for r in left_results:
        key = _prompt_key(getattr(r, "prompt_id", None), getattr(r, "prompt_text", ""))
        left_map[key] = _side_payload(r)

    for r in right_results:
        key = _prompt_key(getattr(r, "prompt_id", None), getattr(r, "prompt_text", ""))
        right_map[key] = _side_payload(r)

    keys_left  = set(left_map.keys())
    keys_right = set(right_map.keys())
    inter      = keys_left & keys_right
    left_only  = keys_left - keys_right
    right_only = keys_right - keys_left
    union      = keys_left | keys_right

    pairs: List[Dict[str, Any]] = []

    # matched
    for k in inter:
        L = left_map[k]
        R = right_map[k]
        pairs.append({
            "prompt_key": k,
            "matched": True,
            "left":  L,
            "right": R,
            "delta": {
                # Norm-Differenz liefern wir direkt mit (rechts - links)
                "product_score_norm": (R["product_score_norm"] - L["product_score_norm"]),
                "subscore":           (R["subscore"] - L["subscore"]),
            }
        })

    # left_only
    for k in left_only:
        L = left_map[k]
        pairs.append({
            "prompt_key": k,
            "matched": False,
            "side": "left_only",
            "left": L,
            "right": None
        })

    # right_only
    for k in right_only:
        R = right_map[k]
        pairs.append({
            "prompt_key": k,
            "matched": False,
            "side": "right_only",
            "left": None,
            "right": R
        })

    # Aggregierte Metriken pro Run
    left_metrics  = await client.compute_run_metrics(left_run_id)
    right_metrics = await client.compute_run_metrics(right_run_id)

    # Run-Namen (für Summary/Exports/UI)
    left_name  = await _get_run_name(client, left_run_id)
    right_name = await _get_run_name(client, right_run_id)

    summary = {
        "left":  {
            "run_id": left_run_id,
            "name": left_name,
            "count": left_metrics["count"],
            "avg_subscore": left_metrics["avg_subscore"],
            "product_score_avg": left_metrics.get("product_score_avg", 0.0),            # PQS Ø
            "product_score_norm_avg": left_metrics.get("product_score_norm_avg", 0.0),  # norm Ø
        },
        "right": {
            "run_id": right_run_id,
            "name": right_name,
            "count": right_metrics["count"],
            "avg_subscore": right_metrics["avg_subscore"],
            "product_score_avg": right_metrics.get("product_score_avg", 0.0),            # PQS Ø
            "product_score_norm_avg": right_metrics.get("product_score_norm_avg", 0.0),  # norm Ø
        },
        "coverage": {
            "intersection": len(inter),
            "left_only":    len(left_only),
            "right_only":   len(right_only),
            "union":        len(union),
        },
        "delta": {
            "avg_subscore":           (right_metrics["avg_subscore"] - left_metrics["avg_subscore"]),
            "product_score_avg":      (right_metrics.get("product_score_avg", 0.0) - left_metrics.get("product_score_avg", 0.0)),
            "product_score_norm_avg": (right_metrics.get("product_score_norm_avg", 0.0) - left_metrics.get("product_score_norm_avg", 0.0)),
        }
    }

    return {
        "summary": summary,
        "pairs":   pairs,
    }
