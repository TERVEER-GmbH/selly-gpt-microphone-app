# backend/routes/admin_compare.py
import io
import csv
import re
import logging
from quart import Blueprint, request, jsonify, current_app, Response
from backend.security.role_decorator import require_role
from backend.db.init_clients import cosmos_admin_db_ready
from backend.services.run_comparer import compare_runs

logger = logging.getLogger("logger")
compare_bp = Blueprint("admin_compare", __name__, url_prefix="/admin/compare")


def _safe_slug(s: str, max_len: int = 60) -> str:
    """Erzeugt einen Dateinamen-tauglichen Slug aus einem Run-Namen."""
    s = (s or "").strip()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^A-Za-z0-9\-_\.]+", "", s)
    return s[:max_len] or "run"


@compare_bp.route("", methods=["GET"])
@require_role("Admin")
async def compare_get():
    """
    GET /admin/compare?left=<id>&right=<id>&format=summary|full

    Liefert:
      - format=summary -> nur "summary" Block (inkl. left/right name, counts, avg_subscore, product_score_norm_avg, coverage, delta)
      - format=full    -> { summary, pairs[ ... ] } (pairs enthält matched/left_only/right_only,
                         inkl. scores, subscore, product_score_raw (PQS) und product_score_norm)
    """
    await cosmos_admin_db_ready.wait()
    left = request.args.get("left")
    right = request.args.get("right")
    fmt = (request.args.get("format") or "full").lower()

    if not left or not right:
        return jsonify({"error": "left and right run ids required"}), 400

    try:
        data = await compare_runs(left, right)
        if fmt == "summary":
            return jsonify(data["summary"]), 200
        return jsonify(data), 200
    except Exception:
        logger.exception("compare_get: Fehler für left=%s right=%s", left, right)
        return jsonify({"error": "compare failed"}), 500


@compare_bp.route("/export", methods=["GET"])
@require_role("Admin")
async def compare_export():
    """
    GET /admin/compare/export?left=<id>&right=<id>&fmt=csv|json

    Exportiert den Vergleich von zwei Runs.

    - fmt=json: gibt das volle Objekt (summary + pairs) zurück.
    - fmt=csv:  schreibt eine flache Tabelle mit folgenden Spalten:

        type, prompt_key, prompt_text, ai_left, ai_right,
        PQS_left, PQS_right, delta_PQS,
        product_norm_left, product_norm_right, delta_product_norm,
        sub_left, sub_right, delta_sub

      Erläuterung:
        * PQS_*           = product_score_raw (Rohprodukt der 5 Kategorien)
        * product_norm_*  = fünfte Wurzel des Produkts (Skala 1–5)
        * delta_* (bei matched): right - left
    """
    await cosmos_admin_db_ready.wait()
    left = request.args.get("left")
    right = request.args.get("right")
    fmt = (request.args.get("fmt") or "csv").lower()

    if not left or not right:
        return jsonify({"error": "left and right run ids required"}), 400

    try:
        data = await compare_runs(left, right)

        if fmt == "json":
            # JSON (summary + pairs) direkt durchreichen
            return jsonify(data), 200

        # CSV vorbereiten
        output = io.StringIO()
        w = csv.writer(output)
        w.writerow([
            "type", "prompt_key", "prompt_text",
            "ai_left", "ai_right",
            "PQS_left", "PQS_right", "delta_PQS",
            "product_norm_left", "product_norm_right", "delta_product_norm",
            "sub_left", "sub_right", "delta_sub"
        ])

        for p in data.get("pairs", []):
            if p.get("matched"):
                L = p["left"]
                R = p["right"]
                # Rohprodukt (PQS)
                pqs_l = L.get("product_score_raw", 0)
                pqs_r = R.get("product_score_raw", 0)
                delta_pqs = pqs_r - pqs_l
                # Normiert
                pn_l = L.get("product_score_norm", 0)
                pn_r = R.get("product_score_norm", 0)
                delta_pn = p["delta"].get("product_score_norm", 0)
                # Subscore
                s_l = L.get("subscore", 0)
                s_r = R.get("subscore", 0)
                delta_s = p["delta"].get("subscore", 0)

                w.writerow([
                    "matched", p.get("prompt_key", ""), L.get("prompt_text", ""),
                    L.get("ai_response", ""), R.get("ai_response", ""),
                    pqs_l, pqs_r, delta_pqs,
                    pn_l, pn_r, delta_pn,
                    s_l, s_r, delta_s
                ])
            else:
                side = p.get("side")
                if side == "left_only":
                    L = p["left"]
                    w.writerow([
                        "left_only", p.get("prompt_key", ""), L.get("prompt_text", ""),
                        L.get("ai_response", ""), "",
                        L.get("product_score_raw", 0), "", "",   # PQS links, rechts leer
                        L.get("product_score_norm", 0), "", "",  # norm links, rechts leer
                        L.get("subscore", 0), "", ""             # Ø links, rechts leer
                    ])
                else:
                    R = p["right"]
                    w.writerow([
                        "right_only", p.get("prompt_key", ""), R.get("prompt_text", ""),
                        "", R.get("ai_response", ""),
                        "", R.get("product_score_raw", 0), "",   # PQS rechts, links leer
                        "", R.get("product_score_norm", 0), "",  # norm rechts, links leer
                        "", R.get("subscore", 0), ""             # Ø rechts, links leer
                    ])

        # Dateiinhalt
        csv_bytes = output.getvalue().encode("utf-8-sig")

        # Sprechender Dateiname mit Run-Namen (falls vorhanden); sonst IDs.
        left_name = data.get("summary", {}).get("left", {}).get("name") or left[:8]
        right_name = data.get("summary", {}).get("right", {}).get("name") or right[:8]
        filename = f"compare_{_safe_slug(left_name)}_vs_{_safe_slug(right_name)}.csv"

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8",
        }
        return Response(csv_bytes, headers=headers)

    except Exception:
        logger.exception("compare_export: Fehler für left=%s right=%s", left, right)
        return jsonify({"error": "compare export failed"}), 500
