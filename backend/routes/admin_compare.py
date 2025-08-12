# backend/routes/admin_compare.py
import io, csv, logging
from quart import Blueprint, request, jsonify, current_app, Response
from backend.security.role_decorator import require_role
from backend.db.init_clients import cosmos_admin_db_ready
from backend.services.run_comparer import compare_runs

logger = logging.getLogger("logger")
compare_bp = Blueprint("admin_compare", __name__, url_prefix="/admin/compare")

@compare_bp.route("", methods=["GET"])
@require_role("Admin")
async def compare_get():
    """
    GET /admin/compare?left=<id>&right=<id>&format=summary|full
    """
    await cosmos_admin_db_ready.wait()
    left  = request.args.get("left")
    right = request.args.get("right")
    fmt   = (request.args.get("format") or "full").lower()

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
    - summary + pairs (Union)
    CSV: type, prompt_key, prompt_text, ai_left, ai_right,
         product_norm_left, product_norm_right, delta_product_norm,
         sub_left, sub_right, delta_sub
    """
    await cosmos_admin_db_ready.wait()
    left  = request.args.get("left")
    right = request.args.get("right")
    fmt   = (request.args.get("fmt") or "csv").lower()

    if not left or not right:
        return jsonify({"error": "left and right run ids required"}), 400

    try:
        data = await compare_runs(left, right)
        if fmt == "json":
            return jsonify(data), 200

        # CSV
        output = io.StringIO()
        w = csv.writer(output)
        w.writerow([
            "type","prompt_key","prompt_text",
            "ai_left","ai_right",
            "product_norm_left","product_norm_right","delta_product_norm",
            "sub_left","sub_right","delta_sub"
        ])
        for p in data.get("pairs", []):
            if p.get("matched"):
                L = p["left"]; R = p["right"]
                w.writerow([
                    "matched", p["prompt_key"], L.get("prompt_text",""),
                    L.get("ai_response",""), R.get("ai_response",""),
                    L.get("product_score_norm",0), R.get("product_score_norm",0),
                    p["delta"].get("product_score_norm",0),
                    L.get("subscore",0), R.get("subscore",0),
                    p["delta"].get("subscore",0)
                ])
            else:
                side = p.get("side")
                if side == "left_only":
                    L = p["left"]
                    w.writerow([
                        "left_only", p["prompt_key"], L.get("prompt_text",""),
                        L.get("ai_response",""), "",
                        L.get("product_score_norm",0), "", "",
                        L.get("subscore",0), "", ""
                    ])
                else:
                    R = p["right"]
                    w.writerow([
                        "right_only", p["prompt_key"], R.get("prompt_text",""),
                        "", R.get("ai_response",""),
                        "", R.get("product_score_norm",0), "",
                        "", R.get("subscore",0), ""
                    ])

        csv_bytes = output.getvalue().encode("utf-8-sig")
        filename = f"compare_{left}_vs_{right}.csv"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8",
        }
        return Response(csv_bytes, headers=headers)

    except Exception:
        logger.exception("compare_export: Fehler für left=%s right=%s", left, right)
        return jsonify({"error": "compare export failed"}), 500
