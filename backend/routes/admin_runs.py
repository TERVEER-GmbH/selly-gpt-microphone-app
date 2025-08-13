# backend/routes/admin_runs.py

import logging, io, csv, asyncio, re
from quart import Blueprint, request, jsonify, current_app, Response
from backend.security.role_decorator import require_role
from backend.models.testrun import TestParams, TestResult
from backend.db.init_clients import cosmos_admin_db_ready

def _safe_slug(s: str, max_len: int = 60) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^A-Za-z0-9\-_\.]+", "", s)
    return s[:max_len] or "run"

logger = logging.getLogger("logger")
runs_bp = Blueprint("admin_runs", __name__, url_prefix="/admin/runs")

@runs_bp.route("", methods=["GET"])
@require_role("Admin")
async def list_runs():
    """
    GET /admin/runs?includeMetrics=1&offset=&limit=
    -> Standard-Metadaten je Run
       + optional metrics: { count, category_averages, avg_subscore, overall_score,
                             product_score_avg, product_score_norm_avg }
    """
    await cosmos_admin_db_ready.wait()
    include_metrics = request.args.get("includeMetrics") in ("1", "true", "True")

    # NEW: Pagination
    try:
        offset = int(request.args.get("offset", 0))
    except Exception:
        offset = 0
    try:
        limit = int(request.args.get("limit", 0))  # 0 = kein Limit
    except Exception:
        limit = 0

    try:
        client = current_app.cosmos_admin_client
        runs = await client.list_runs(offset=offset if limit or offset else None,
                                      limit=limit if limit else None)

        if not include_metrics:
            return jsonify([r.to_dict() for r in runs]), 200

        # parallelisierte Metrik-Berechnung (du hast Schritt 1 schon umgesetzt)
        tasks = [client.compute_run_metrics(r.id) for r in runs]
        metrics_list = await asyncio.gather(*tasks)
        enriched = []
        for r, m in zip(runs, metrics_list):
            d = r.to_dict()
            d["metrics"] = m
            enriched.append(d)
        return jsonify(enriched), 200

    except Exception:
        logger.exception("list_runs: Fehler")
        return jsonify({"error":"Could not fetch runs"}), 500

@runs_bp.route("", methods=["POST"])
@require_role("Admin")
async def start_run():
    """
    POST /admin/runs
    Body: { prompt_ids: [...], params: {...}, name?: string }
    -> { run_id }
    """
    await cosmos_admin_db_ready.wait()
    data = await request.get_json()
    prompt_ids = data.get("prompt_ids", [])
    params = TestParams(**data.get("params", {}))
    name = data.get("name")

    run_id = await current_app.cosmos_admin_client.start_run(prompt_ids, params, name=name)
    return jsonify({"run_id": run_id}), 201

@runs_bp.route("/<run_id>/status", methods=["GET"])
@require_role("Admin")
async def get_status(run_id):
    """
    GET /admin/runs/<run_id>/status?includeMetrics=1
    {
        run_id, name, prompt_ids, params, status, total, completed, created_at
        + metrics (optional via ?includeMetrics=1)
    }
    """
    await cosmos_admin_db_ready.wait()
    include_metrics = request.args.get("includeMetrics") in ("1", "true", "True")
    try:
        client = current_app.cosmos_admin_client

        # 1) Lauf-Metadaten holen
        run = await client.get_run(run_id)

        # 2) Completed count aus dem result-Container ermitteln (partitioniert nach run_id)
        count_query = "SELECT VALUE COUNT(1) FROM c WHERE c.run_id = @run_id"
        iterator = client.result_container.query_items(
            query=count_query,
            parameters=[{"name": "@run_id", "value": run_id}],
            partition_key=run_id
        )
        completed = 0
        async for cnt in iterator:
            completed = cnt

        payload = {
            "run_id":     run.id,
            "name":       run.name,
            "prompt_ids": run.prompt_ids,
            "params":     run.params.to_dict(),
            "status":     run.status,
            "total":      len(run.prompt_ids),
            "completed":  completed,
            "created_at": run.created_at
        }

        if include_metrics:
            payload["metrics"] = await client.compute_run_metrics(run_id)

        return jsonify(payload), 200
    except Exception:
        logger.exception("Error fetching run status %s", run_id)
        return jsonify({"error": "Could not fetch status"}), 500

@runs_bp.route("/<run_id>/name", methods=["PATCH"])
@require_role("Admin")
async def rename(run_id):
    await cosmos_admin_db_ready.wait()
    try:
        body = await request.get_json() or {}
        name = (body.get("name") or "").strip()
        if not name:
            return jsonify({"error":"name required"}), 400
        await current_app.cosmos_admin_client.rename_run(run_id, name)
        return jsonify({"ok": True}), 200
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception:
        logger.exception("rename: Fehler bei %s", run_id)
        return jsonify({"error":"rename failed"}), 500

@runs_bp.route("/<run_id>/summary", methods=["GET"])
@require_role("Admin")
async def get_summary(run_id):
    """
    GET /admin/runs/<run_id>/summary
    -> { count, category_averages, avg_subscore, overall_score }
    """
    await cosmos_admin_db_ready.wait()
    try:
        metrics = await current_app.cosmos_admin_client.compute_run_metrics(run_id)
        return jsonify(metrics), 200
    except Exception:
        logger.exception("get_summary: Fehler bei %s", run_id)
        return jsonify({"error":"Could not fetch summary"}), 500


@runs_bp.route("/<run_id>/results", methods=["GET"])
@require_role("Admin")
async def get_results(run_id):
    """
    GET /admin/runs/<run_id>/results?offset=&limit=
    -> [{ id, prompt_id, prompt_text, ai_response, golden_answer, timestamp, run_id, ...scores }]
    """
    await cosmos_admin_db_ready.wait()

    # NEW: Pagination
    try:
        offset = int(request.args.get("offset", 0))
    except Exception:
        offset = 0
    try:
        limit = int(request.args.get("limit", 0))  # 0 = kein Limit
    except Exception:
        limit = 0

    try:
        results = await current_app.cosmos_admin_client.list_results(
            run_id,
            offset=offset if limit or offset else None,
            limit=limit if limit else None
        )
        return jsonify([r.to_dict() for r in results]), 200
    except Exception:
        logger.exception("get_results: Fehler bei %s", run_id)
        return jsonify({"error":"Could not fetch results"}), 500

@runs_bp.route("/<run_id>/results/<result_id>", methods=["PATCH"])
@require_role("Admin")
async def patch_result(run_id, result_id):
    """
    PATCH /admin/runs/<run_id>/results/<result_id>
    Body: { any of score/comment fields, optionally ai_response/golden_answer }
    -> updated TestResult
    """
    await cosmos_admin_db_ready.wait()
    try:
        payload = await request.get_json() or {}
        updated = await current_app.cosmos_admin_client.patch_result(run_id, result_id, payload)
        return jsonify(updated.to_dict()), 200
    except Exception:
        logger.exception("patch_result: Fehler für %s/%s", run_id, result_id)
        return jsonify({"error":"Could not patch result"}), 500

@runs_bp.route("/<run_id>/test/<prompt_id>", methods=["POST"])
@require_role("Admin")
async def test_single(run_id, prompt_id):
    """
    Einheitlich: nutzt die zentrale run_tests-Logik
    und gibt das eine Resultat zurück.
    """
    await cosmos_admin_db_ready.wait()
    body = await request.get_json() or {}
    params = TestParams(**body.get("params", {})) if body.get("params") else None
    client = current_app.cosmos_admin_client

    # Sicherstellen, dass der Run existiert, sonst wird ein neuer erstellt
    try:
        await client.get_run(run_id)
    except:
        await client.start_run([prompt_id], params or TestParams(model="gpt-4o", temperature=0, max_tokens=256))

    # Ergebnis über Callback einsammeln
    holder: dict[str, TestResult] = {}
    async def _cb(r: TestResult):
        # wir wollen genau das Result für dieses prompt_id
        if r.prompt_id == prompt_id:
            holder["r"] = r

    await client.run_tests(
        run_id=run_id,
        prompt_ids=[prompt_id],
        params=params or TestParams(model="gpt-4o", temperature=0, max_tokens=256),
        on_result=_cb,
        throttle_seconds=0.0
    )

    res = holder.get("r")
    if not res:
        return jsonify({"error": "No result"}), 500
    return jsonify(res.to_dict()), 200

@runs_bp.route("/<run_id>/metrics", methods=["GET"])
@require_role("Admin")
async def run_metrics(run_id):
    """
    GET /admin/runs/<run_id>/metrics
    -> { count, category_averages, avg_subscore, overall_score, product_score_avg, product_score_norm_avg }
    """
    await cosmos_admin_db_ready.wait()
    try:
        metrics = await current_app.cosmos_admin_client.compute_run_metrics(run_id)
        return jsonify(metrics), 200
    except Exception:
        logger.exception("run_metrics: Fehler bei %s", run_id)
        return jsonify({"error": "Could not compute metrics"}), 500

@runs_bp.route("/<run_id>/export", methods=["GET"])
@require_role("Admin")
async def export_run(run_id):
    """
    GET /admin/runs/<run_id>/export?fmt=csv|json
    CSV-Spalten:
      prompt_id, prompt_text, golden_answer, ai_response,
      relevance, factual_accuracy, completeness, tone, comprehensibility,
      subscore, product_score_raw, product_score_norm, timestamp
    """
    await cosmos_admin_db_ready.wait()
    fmt = (request.args.get("fmt") or "csv").lower()
    client = current_app.cosmos_admin_client
    try:
        results = await client.list_results(run_id)
        if fmt == "json":
            # JSON mit berechneten Feldern
            payload = []
            for r in results:
                rel  = float(getattr(r, "relevance", 0) or 0)
                fact = float(getattr(r, "factual_accuracy", 0) or 0)
                comp = float(getattr(r, "completeness", 0) or 0)
                tone = float(getattr(r, "tone", 0) or 0)
                compr= float(getattr(r, "comprehensibility", 0) or 0)
                sub  = (rel + fact + comp + tone + compr) / 5.0
                prod = rel * fact * comp * tone * compr
                prodn= (prod ** 0.2) if prod > 0 else 0.0
                payload.append({
                    **r.to_dict(),
                    "subscore": sub,
                    "product_score_raw": prod,
                    "product_score_norm": prodn,
                })
            return jsonify(payload), 200

        # CSV
        output = io.StringIO()
        w = csv.writer(output)
        w.writerow([
            "prompt_id","prompt_text","golden_answer","ai_response",
            "relevance","factual_accuracy","completeness","tone","comprehensibility",
            "subscore","product_score_raw","product_score_norm","timestamp"
        ])
        for r in results:
            rel  = float(getattr(r, "relevance", 0) or 0)
            fact = float(getattr(r, "factual_accuracy", 0) or 0)
            comp = float(getattr(r, "completeness", 0) or 0)
            tone = float(getattr(r, "tone", 0) or 0)
            compr= float(getattr(r, "comprehensibility", 0) or 0)
            sub  = (rel + fact + comp + tone + compr) / 5.0
            prod = rel * fact * comp * tone * compr
            prodn= (prod ** 0.2) if prod > 0 else 0.0
            w.writerow([
                r.prompt_id, r.prompt_text, r.golden_answer, r.ai_response,
                rel, fact, comp, tone, compr,
                sub, prod, prodn, r.timestamp.isoformat()
            ])

        csv_bytes = output.getvalue().encode("utf-8-sig")
        name = ""
        try:
            run_doc = await current_app.cosmos_admin_client.run_container.read_item(item=run_id, partition_key=run_id)
            name = run_doc.get("name") or ""
        except Exception:
            pass
        slug = _safe_slug(name) if name else f"run_{run_id[:8]}"

        filename = f"{slug}_{run_id}.csv" if fmt == "csv" else f"{slug}_{run_id}.json"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8" if fmt == "csv" else "application/json; charset=utf-8",
        }
        return Response(csv_bytes, headers=headers)
    except Exception:
        logger.exception("export_run: Fehler bei %s", run_id)
        return jsonify({"error": "Could not export run"}), 500
