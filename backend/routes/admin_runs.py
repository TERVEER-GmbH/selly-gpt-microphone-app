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
    GET /admin/runs
    -> [{ id, prompt_ids, params, status, created_at }]
    """
    await cosmos_admin_db_ready.wait()

    try:
        runs = await current_app.cosmos_admin_client.list_runs()
        return jsonify([r.to_dict() for r in runs]), 200
    except Exception:
        logger.exception("list_runs: Fehler",)
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
    GET /admin/runs/<run_id>/status
    {
        id: string,
        prompt_ids: string[],
        params: { model, temperature, max_tokens, top_p? },
        status: "Pending"|"Running"|"Done",
        total: number,
        completed: number,
        created_at: string
    }
    """
    await cosmos_admin_db_ready.wait()
    try:
        client = current_app.cosmos_admin_client

        # 1) Lauf-Metadaten holen
        run = await client.get_run(run_id)

        # 2) Completed count aus dem result-Container ermitteln (partitioniert nach run_id)
        count_query = "SELECT VALUE COUNT(1) FROM c WHERE c.run_id = @run_id"
        completed = 0
        iterator = client.result_container.query_items(
            query=count_query,
            parameters=[{"name": "@run_id", "value": run_id}],
            partition_key=run_id
        )
        async for cnt in iterator:
            completed = cnt

        # 3) Response mit allen Feldern
        return jsonify({
            "run_id":     run.id,
            "prompt_ids": run.prompt_ids,
            "params":     run.params.to_dict(),
            "status":     run.status,
            "total":      len(run.prompt_ids),
            "completed":  completed,
            "created_at": run.created_at
        }), 200

    except Exception:
        logger.exception("Error fetching run status %s", run_id)
        return jsonify({"error": "Could not fetch status"}), 500

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

@runs_bp.route("/<run_id>/test/<prompt_id>", methods=["POST"])
@require_role("Admin")
async def test_single(run_id, prompt_id):
    """
    wird jetzt eigentlich nur noch zum Inkrementellen Testen benutzt,
    aber im Prinzip genauso wie ein Batch.
    Wenn du hier sofort das Ergebnis zurückgeben willst,
    kannst du synchron client.run_tests mit [prompt_id] aufrufen.
    """
    await cosmos_admin_db_ready.wait()
    params = TestParams(**(await request.get_json() or {}).get("params", {}))
    client = current_app.cosmos_admin_client
    prompt = await client.get_prompt(prompt_id)

    # Wenn Run nicht existiert, erst anlegen
    try:
        await client.get_run(run_id)
    except:
        await client.start_run([prompt_id], params)

    # 1) AI-Antwort holen
    ai_resp = await call_ai_model(prompt.text, params)

    # 2) automatischer Vergleich
    comp = await compare_answers(
        ai_answer=ai_resp,
        golden_answer=prompt.golden_answer,
        params=params
    )

    # 3) TestResult befüllen – inkl. Scores & Kommentare
    result = TestResult(
        id=str(uuid.uuid4()),
        run_id=run_id,
        prompt_id=prompt.id,
        prompt_text=prompt.text,
        ai_response=ai_resp,
        golden_answer=prompt.golden_answer
    )
    # Scores
    result.relevance                 = comp.relevance
    result.relevance_comment         = comp.relevance_comment
    result.factual_accuracy          = comp.factual_accuracy
    result.factual_accuracy_comment  = comp.factual_accuracy_comment
    result.completeness              = comp.completeness
    result.completeness_comment      = comp.completeness_comment
    result.tone                      = comp.tone
    result.tone_comment              = comp.tone_comment
    result.comprehensibility         = comp.comprehensibility
    result.comprehensibility_comment = comp.comprehensibility_comment
    result.overall_comment           = comp.overall_comment

    # 4) speichern und zurückgeben
    await client.add_result(run_id, result)
    return jsonify(result.to_dict()), 200

@runs_bp.route("/<run_id>/results", methods=["GET"])
@require_role("Admin")
async def list_results(run_id):
    await cosmos_admin_db_ready.wait()
    try:
        results = await current_app.cosmos_admin_client.list_results(run_id)
        return jsonify([r.to_dict() for r in results]), 200
    except Exception:
        logger.exception("Error fetching results for run %s", run_id)
        return jsonify({"error": "Could not fetch results"}), 500
