# backend/routes/admin_runs.py

import uuid, logging
from quart import Blueprint, request, jsonify, current_app
from backend.security.role_decorator import require_role
from backend.models.testrun import TestParams, TestResult
from backend.services.ai_client import call_ai_model
from backend.services.comparator import compare_answers
from backend.db.init_clients import cosmos_admin_db_ready

logger = logging.getLogger("logger")
runs_bp = Blueprint("admin_runs", __name__, url_prefix="/admin/runs")

@runs_bp.route("", methods=["GET"])
@require_role("Admin")
async def list_runs():
    """
    GET /admin/runs?includeMetrics=1
    -> Standard-Metadaten je Run
       + optional metrics: { count, category_averages, avg_subscore, overall_score }
    """
    await cosmos_admin_db_ready.wait()
    include_metrics = request.args.get("includeMetrics") in ("1", "true", "True")

    try:
        client = current_app.cosmos_admin_client
        runs = await client.list_runs()

        if not include_metrics:
            return jsonify([r.to_dict() for r in runs]), 200

        enriched = []
        for r in runs:
            metrics = await client.compute_run_metrics(r.id)
            rd = r.to_dict()
            rd["metrics"] = metrics
            enriched.append(rd)
        return jsonify(enriched), 200

    except Exception:
        logger.exception("list_runs: Fehler")
        return jsonify({"error":"Could not fetch runs"}), 500

@runs_bp.route("", methods=["POST"])
@require_role("Admin")
async def start_run():
    """
    POST /admin/runs
    Body: { prompt_ids: [...], params: {...} }
    -> { run_id }
    """
    await cosmos_admin_db_ready.wait()
    data = await request.get_json()
    prompt_ids = data.get("prompt_ids", [])
    params = TestParams(**data.get("params", {}))
    run_id = await current_app.cosmos_admin_client.start_run(prompt_ids, params)
    return jsonify({"run_id": run_id}), 201

@runs_bp.route("/<run_id>/status", methods=["GET"])
@require_role("Admin")
async def get_status(run_id):
    """
    GET /admin/runs/<run_id>/status?includeMetrics=1
    {
        run_id, prompt_ids, params, status, total, completed, created_at
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
    GET /admin/runs/<run_id>/results
    -> [{ id, prompt_id, prompt_text, ai_response, golden_answer, timestamp, run_id }]
    """
    await cosmos_admin_db_ready.wait()
    try:
        results = await current_app.cosmos_admin_client.list_results(run_id)
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
