import asyncio
import uuid
import logging
from datetime import datetime
import time
from quart import current_app

from backend.db.init_clients import cosmos_admin_db_ready
from backend.models.testrun import TestResult
from backend.services.comparator import compare_answers
from backend.services.ai_client import call_ai_model


logger = logging.getLogger("logger")

async def _process_run(run):
    client = current_app.cosmos_admin_client
    # Status → Running
    await client.run_container.patch_item(
        item=run.id, partition_key=run.id,
        patch_operations=[{"op":"replace","path":"/status","value":"Running"}]
    )

    for pid in run.prompt_ids:
        prompt = await client.get_prompt(pid)
        # 1) AI call
        ai_resp = await call_ai_model(prompt.text, run.params)
        time.sleep(14)
        # 2) compare
        comp = await compare_answers(ai_resp, prompt.golden_answer, run.params)
        time.sleep(14)
        # 3) build TestResult
        result = TestResult(
            id=str(uuid.uuid4()),
            run_id=run.id,
            prompt_id=pid,
            prompt_text=prompt.text,
            ai_response=ai_resp,
            golden_answer=prompt.golden_answer,
            timestamp=datetime.utcnow()
        )
        # set scores/comments
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
        print('comparison_results_added')

        # 4) speichern
        await client.add_result(run.id, result)

    # 5) Done markieren
    await client.run_container.patch_item(
        item=run.id, partition_key=run.id,
        patch_operations=[{"op":"replace","path":"/status","value":"Done"}]
    )

async def background_runner():
    await cosmos_admin_db_ready.wait()
    client = current_app.cosmos_admin_client

    while True:
        try:
            pending = await client.list_runs(status="Pending")
            for run in pending:
                # wir laufen jeden Prompt selbst durch, um compare_answers einzuweben
                asyncio.create_task(_process_run(run))

        except Exception:
            logger.exception("Background‐Runner: unerwarteter Fehler")
        await asyncio.sleep(10)
